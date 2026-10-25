"""Train, export and verify the EfficientCrackNet-style crack locator (D14).

Needs torch (CPU), onnx and onnxruntime, i.e. the training venv C:\\Users\\User\\prohori_train_venv, NOT the system
Python.  Inference (src/prohori/dnnseg.py) needs only OpenCV >= 5.0 (cv2.dnn).

    prohori_train_venv\\Scripts\\python tools\\train_crackseg.py count                     # params / GFLOPs per variant
    prohori_train_venv\\Scripts\\python tools\\train_crackseg.py train --recipe crack500 --hours 2.5
    prohori_train_venv\\Scripts\\python tools\\train_crackseg.py train --recipe joint --init runs\\crack500\\best.pt --hours 1.5
    prohori_train_venv\\Scripts\\python tools\\train_crackseg.py export --ckpt runs\\crack500\\best.pt --out models\\crackseg\\x.onnx

Architecture: a re-implementation of EfficientCrackNet (Zim et al., WACV 2025, arXiv 2409.18099, "S2" in
research/LITERATURE.md).  The paper gives the building blocks (DSC, EEM = DoG x LoG with SE residual, ULSAM, MobileViT,
U-Net skeleton, Dice loss) but NOT the channel counts, depth, patch size, heads, optimiser or schedule and no code
is public, so those are our choices, made to land at ~0.26 M parameters.  Every deviation is listed in
models/crackseg/README.md and research/DNN_NOTES.md.  Only ops that cv2.dnn (OpenCV 5.0) loads are used and the graph
is exported with a STATIC input size (the tile size), so all Reshapes are constant.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import queue
import sys
import threading
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import torch  # noqa: E402
import torch.nn as nn  # noqa: E402
import torch.nn.functional as F  # noqa: E402

MEAN = (0.485, 0.456, 0.406)          # RGB, applied inside the network (so the ONNX takes 0..1 RGB)
STD = (0.229, 0.224, 0.225)


# ----------------------------------------------------------------------------- blocks


class DSC(nn.Module):
    """Depthwise-separable conv: dw kxk -> pw 1x1 -> BN -> ReLU (BN + ReLU after each DSC layer, paper 3.4)."""

    def __init__(self, cin, cout, k=3, stride=1):
        super().__init__()
        self.dw = nn.Conv2d(cin, cin, k, stride, k // 2, groups=cin, bias=False)
        self.pw = nn.Conv2d(cin, cout, 1, bias=False)
        self.bn = nn.BatchNorm2d(cout)

    def forward(self, x):
        return F.relu(self.bn(self.pw(self.dw(x))))


def _gauss3(sigma: float) -> np.ndarray:
    ax = np.array([-1.0, 0.0, 1.0])
    g = np.exp(-(ax[:, None] ** 2 + ax[None, :] ** 2) / (2 * sigma**2))
    return g / g.sum()


def _log3(sigma: float) -> np.ndarray:
    """3x3 Laplacian-of-Gaussian kernel (paper Eq. 2), zero-sum."""
    ax = np.array([-1.0, 0.0, 1.0])
    r2 = ax[:, None] ** 2 + ax[None, :] ** 2
    k = (r2 - 2 * sigma**2) / sigma**4 * np.exp(-r2 / (2 * sigma**2))
    return k - k.mean()


class SE(nn.Module):
    """Squeeze-excitation (paper: SEM in the EEM residual)."""

    def __init__(self, c, r=2):
        super().__init__()
        self.fc1 = nn.Conv2d(c, max(c // r, 4), 1)
        self.fc2 = nn.Conv2d(max(c // r, 4), c, 1)

    def forward(self, x):
        s = F.adaptive_avg_pool2d(x, 1)
        return x * torch.sigmoid(self.fc2(F.relu(self.fc1(s))))


class EEM(nn.Module):
    """Edge Extraction Method (paper 3.1, Fig. 2): fixed 3x3 Gaussian blur; DoG = x - blur(x) and LoG = fixed 3x3 LoG
    (training-free filters, depthwise over the input channels); each edge map -> own 1x1 conv; the two are multiplied,
    3x3 max-pool (stride 1), 1x1 conv; SE on the result; residual add to the DSC feature stem (see forward)."""

    def __init__(self, cin, c, sigma=1.0):
        super().__init__()
        g = torch.tensor(_gauss3(sigma), dtype=torch.float32)
        l = torch.tensor(_log3(sigma), dtype=torch.float32)
        self.register_buffer("g", g.expand(cin, 1, 3, 3).clone())
        self.register_buffer("l", l.expand(cin, 1, 3, 3).clone())
        self.cin = cin
        self.c_dog = nn.Conv2d(cin, c, 1)
        self.c_log = nn.Conv2d(cin, c, 1)
        self.pool = nn.MaxPool2d(3, 1, 1)
        self.c_out = nn.Conv2d(c, c, 1)
        self.se = SE(c)

    def forward(self, x):
        blur = F.conv2d(x, self.g, padding=1, groups=self.cin)
        dog = x - blur
        log = F.conv2d(x, self.l, padding=1, groups=self.cin)
        e = self.c_dog(dog) * self.c_log(log)
        return self.se(self.c_out(self.pool(e)))


class ULSAM(nn.Module):
    """Ultra-Lightweight Subspace Attention (paper 3.2, Eqs. 3-5): split into g groups; per group
    A = softmax(PW1(maxpool3x3(DW1x1(F_g)))) over the spatial positions, F_g' = A*F_g + F_g; concat.
    Deviation: softmax output is multiplied by H*W (mean attention = 1) so the term does not vanish at 256^2 tiles."""

    def __init__(self, c, g=4):
        super().__init__()
        assert c % g == 0
        self.g, self.G = g, c // g
        self.dw = nn.ModuleList([nn.Conv2d(self.G, self.G, 1, groups=self.G) for _ in range(g)])   # DW 1x1 = per-channel affine
        self.pool = nn.MaxPool2d(3, 1, 1)
        self.pw = nn.ModuleList([nn.Conv2d(self.G, 1, 1) for _ in range(g)])

    def forward(self, x):
        b, c, h, w = x.shape
        outs = []
        for i, f in enumerate(torch.split(x, self.G, dim=1)):
            a = self.pw[i](self.pool(self.dw[i](f)))
            a = torch.softmax(a.reshape(b, 1, h * w), dim=-1).reshape(b, 1, h, w) * float(h * w)
            outs.append(a * f + f)
        return torch.cat(outs, 1)


class MViTBlock(nn.Module):
    """MobileViT block (paper 3.3, Eq. 6): local rep (dw3x3 + pw -> d), unfold into 2x2 patches, `depth` pre-LN
    transformer layers across patches (per within-patch position), fold, pw d->c, concat with input, DSC merge.
    Unfold/fold are plain Reshape/Transpose with static shapes so cv2.dnn can run them."""

    def __init__(self, c, d, depth=1, heads=2, ffn=2, patch=2):
        super().__init__()
        self.p, self.d, self.heads = patch, d, heads
        self.local = nn.Sequential(nn.Conv2d(c, c, 3, 1, 1, groups=c, bias=False), nn.BatchNorm2d(c), nn.ReLU(),
                                   nn.Conv2d(c, d, 1, bias=False))
        self.layers = nn.ModuleList([_TLayer(d, heads, ffn) for _ in range(depth)])
        self.norm = nn.LayerNorm(d)
        self.proj = nn.Sequential(nn.Conv2d(d, c, 1, bias=False), nn.BatchNorm2d(c), nn.ReLU())
        self.fuse = DSC(2 * c, c)

    def forward(self, x):
        b, c, h, w = x.shape
        p, d = self.p, self.d
        y = self.local(x)                                                    # b d h w
        y = y.reshape(b, d, h // p, p, w // p, p).permute(0, 3, 5, 2, 4, 1)  # b p p h/p w/p d
        y = y.reshape(b * p * p, (h // p) * (w // p), d)
        for l in self.layers:
            y = l(y)
        y = self.norm(y)
        y = y.reshape(b, p, p, h // p, w // p, d).permute(0, 5, 3, 1, 4, 2).reshape(b, d, h, w)
        return self.fuse(torch.cat([x, self.proj(y)], 1))


class _TLayer(nn.Module):
    def __init__(self, d, heads, ffn):
        super().__init__()
        self.h, self.dh = heads, d // heads
        self.n1 = nn.LayerNorm(d)
        self.qkv = nn.Linear(d, 3 * d)
        self.o = nn.Linear(d, d)
        self.n2 = nn.LayerNorm(d)
        self.f1 = nn.Linear(d, ffn * d)
        self.f2 = nn.Linear(ffn * d, d)

    def forward(self, x):
        b, n, d = x.shape
        q, k, v = self.qkv(self.n1(x)).reshape(b, n, 3, self.h, self.dh).permute(2, 0, 3, 1, 4)
        a = torch.softmax(q @ k.transpose(-1, -2) * (self.dh ** -0.5), dim=-1)
        x = x + self.o((a @ v).transpose(1, 2).reshape(b, n, d))
        h = self.f1(self.n2(x))
        return x + self.f2(h * torch.sigmoid(h))                            # SiLU


class Up(nn.Module):
    """Upsample x2 (nearest, exact in cv2.dnn) + concat skip + DSC (+ ULSAM) (+ MobileViT)."""

    def __init__(self, cin, cskip, cout, ulsam=True, mvit=None, g=4):
        super().__init__()
        self.dsc = DSC(cin + cskip, cout)
        self.att = ULSAM(cout, g) if ulsam else nn.Identity()
        self.mv = MViTBlock(cout, **mvit) if mvit else nn.Identity()

    def forward(self, x, skip):
        x = F.interpolate(x, scale_factor=2, mode="nearest")
        return self.mv(self.att(self.dsc(torch.cat([x, skip], 1))))


class EfficientCrackNet(nn.Module):
    """U-Net (4 down / 4 up) of DSC + EEM + ULSAM + MobileViT.  Input RGB 0..1 (N,3,H,W), output crack probability."""

    def __init__(self, ch=(16, 24, 40, 64, 96), d=(0, 0, 0, 48, 64), g=(2, 4, 4, 4, 4), heads=2):
        super().__init__()
        c1, c2, c3, c4, c5 = ch
        self.register_buffer("mean", torch.tensor(MEAN).reshape(1, 3, 1, 1))
        self.register_buffer("std", torch.tensor(STD).reshape(1, 3, 1, 1))
        self.stem = DSC(3, c1)
        self.eem = EEM(3, c1)
        self.e1 = DSC(c1, c1)
        self.e2 = nn.Sequential(DSC(c1, c2, stride=2), DSC(c2, c2), ULSAM(c2, g[1]))
        self.e3 = nn.Sequential(DSC(c2, c3, stride=2), DSC(c3, c3), ULSAM(c3, g[2]))
        self.e4 = nn.Sequential(DSC(c3, c4, stride=2), DSC(c4, c4), ULSAM(c4, g[3]), MViTBlock(c4, d[3], 1, heads))
        self.e5 = nn.Sequential(DSC(c4, c5, stride=2), DSC(c5, c5), MViTBlock(c5, d[4], 2, heads))
        self.u4 = Up(c5, c4, c4, ulsam=True, mvit=dict(d=d[3], depth=1, heads=heads), g=g[3])
        self.u3 = Up(c4, c3, c3, ulsam=True, g=g[2])
        self.u2 = Up(c3, c2, c2, ulsam=True, g=g[1])
        self.u1 = Up(c2, c1, c1, ulsam=False)
        self.head = nn.Conv2d(c1, 1, 1)

    def forward(self, x, logits=False):
        z = (x - self.mean) / self.std
        s1 = self.e1(self.stem(z) + self.eem(z))
        s2 = self.e2(s1)
        s3 = self.e3(s2)
        s4 = self.e4(s3)
        s5 = self.e5(s4)
        y = self.u1(self.u2(self.u3(self.u4(s5, s4), s3), s2), s1)
        y = self.head(y)
        return y if logits else torch.sigmoid(y)


def count_params(m) -> int:
    return sum(p.numel() for p in m.parameters())


def count_macs(m, size=256) -> float:
    """Multiply-accumulates (conv, linear, attention matmuls) for one (1,3,size,size) forward, via forward hooks."""
    tot = [0.0]
    hooks = []

    def conv_h(mod, i, o):
        tot[0] += o.numel() * (mod.in_channels // mod.groups) * mod.kernel_size[0] * mod.kernel_size[1]

    def lin_h(mod, i, o):
        tot[0] += o.numel() * mod.in_features

    def att_h(mod, i, o):                                    # q@k^T and a@v in _TLayer
        b, n, d = i[0].shape
        tot[0] += 2 * b * n * n * d

    for mod in m.modules():
        if isinstance(mod, nn.Conv2d):
            hooks.append(mod.register_forward_hook(conv_h))
        elif isinstance(mod, nn.Linear):
            hooks.append(mod.register_forward_hook(lin_h))
        elif isinstance(mod, _TLayer):
            hooks.append(mod.register_forward_hook(att_h))
    was = m.training
    m.eval()
    with torch.no_grad():
        m(torch.zeros(1, 3, size, size))
    m.train(was)
    for h in hooks:
        h.remove()
    return tot[0]


# ----------------------------------------------------------------------------- data


def load_split(name: str, split: str, limit: int | None = None, max_side: int | None = None):
    """Preload (image RGB uint8, mask uint8 0/1) pairs of an official split into RAM."""
    from prohori import datasets as D
    out = []
    for s in D.iter_samples(name, split, limit=limit, max_side=max_side):
        out.append((s.image[:, :, ::-1].copy(), s.mask.astype(np.uint8)))
    return out


def _pad_to(img, m, size):
    h, w = m.shape
    ph, pw = max(0, size - h), max(0, size - w)
    if ph or pw:
        import cv2
        img = cv2.copyMakeBorder(img, 0, ph, 0, pw, cv2.BORDER_REFLECT_101)
        m = cv2.copyMakeBorder(m, 0, ph, 0, pw, cv2.BORDER_REFLECT_101)
    return img, m


def augment(img, m, size, rng):
    """Random crop + flips/rot90 + photometric jitter (paper 4.2 list: flip .7, rotate .7, brightness/contrast .2,
    blur .2, shift-scale-rotate .2, noise .2, colour inversion .2), implemented with cv2/numpy for speed."""
    import cv2
    img, m = _pad_to(img, m, size)
    h, w = m.shape
    # shift-scale-rotate (p=.2) done on a crop slightly larger than needed
    if rng.random() < 0.2:
        s = rng.uniform(0.8, 1.25)
        ang = rng.uniform(-25, 25)
        cs = int(size * 1.5)
        y0 = rng.integers(0, max(1, h - min(cs, h) + 1))
        x0 = rng.integers(0, max(1, w - min(cs, w) + 1))
        ci, cm = img[y0:y0 + cs, x0:x0 + cs], m[y0:y0 + cs, x0:x0 + cs]
        c = (ci.shape[1] / 2, ci.shape[0] / 2)
        M = cv2.getRotationMatrix2D(c, ang, s)
        M[:, 2] += (size / 2 - c[0], size / 2 - c[1])
        img = cv2.warpAffine(ci, M, (size, size), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)
        m = cv2.warpAffine(cm, M, (size, size), flags=cv2.INTER_NEAREST, borderMode=cv2.BORDER_REFLECT_101)
    else:
        y0 = rng.integers(0, h - size + 1)
        x0 = rng.integers(0, w - size + 1)
        img, m = img[y0:y0 + size, x0:x0 + size], m[y0:y0 + size, x0:x0 + size]
    if rng.random() < 0.7:
        k = rng.integers(0, 4)
        img, m = np.rot90(img, k), np.rot90(m, k)
    if rng.random() < 0.7:
        img, m = img[:, ::-1], m[:, ::-1]
    img = np.ascontiguousarray(img)
    m = np.ascontiguousarray(m)
    x = img.astype(np.float32) / 255.0
    if rng.random() < 0.2:                                   # brightness / contrast
        x = np.clip((x - 0.5) * rng.uniform(0.75, 1.25) + 0.5 + rng.uniform(-0.15, 0.15), 0, 1)
    if rng.random() < 0.2:
        x = cv2.GaussianBlur(x, (0, 0), rng.uniform(0.5, 1.5))
    if rng.random() < 0.2:
        x = np.clip(x + rng.normal(0, rng.uniform(0.01, 0.05), x.shape).astype(np.float32), 0, 1)
    if rng.random() < 0.2:
        x = 1.0 - x
    return x.transpose(2, 0, 1), m


class Loader(threading.Thread):
    """One background thread building batches (cv2 releases the GIL), so the 4 torch threads stay busy."""

    def __init__(self, sets, weights, size, bs, seed, depth=6):
        super().__init__(daemon=True)
        self.sets, self.p, self.size, self.bs = sets, np.array(weights, float) / np.sum(weights), size, bs
        self.rng = np.random.default_rng(seed)
        self.q = queue.Queue(depth)
        self.stop = False

    def run(self):
        while not self.stop:
            xs, ys = [], []
            for _ in range(self.bs):
                si = self.rng.choice(len(self.sets), p=self.p)
                img, m = self.sets[si][self.rng.integers(len(self.sets[si]))]
                x, y = augment(img, m, self.size, self.rng)
                xs.append(x)
                ys.append(y)
            self.q.put((torch.from_numpy(np.stack(xs)), torch.from_numpy(np.stack(ys)).float().unsqueeze(1)))

    def get(self):
        return self.q.get()


# ----------------------------------------------------------------------------- loss / eval


def dice_loss(p, g, eps=1.0):
    """Paper Eq. 9, pooled over the batch (a per-image Dice is undefined on crack-free crops)."""
    return 1 - (2 * (p * g).sum() + eps) / ((p * p).sum() + (g * g).sum() + eps)


def skeleton_recall(p, skel_tube, eps=1.0):
    """Skeleton Recall loss (S9): soft recall of the prediction on the dilated GT skeleton."""
    return 1 - ((p * skel_tube).sum() + eps) / (skel_tube.sum() + eps)


def tube_of(g: torch.Tensor) -> torch.Tensor:
    """Cheap GT 'tubed skeleton' for Skeleton Recall: cv2 thinning per sample, dilated with a radius-2 diamond (S9)."""
    import cv2
    out = np.zeros(g.shape, np.float32)
    k = cv2.getStructuringElement(cv2.MORPH_CROSS, (5, 5))
    for i in range(g.shape[0]):
        m = (g[i, 0].numpy() > 0.5).astype(np.uint8) * 255
        if m.any():
            sk = cv2.ximgproc.thinning(m) if hasattr(cv2, "ximgproc") else m
            out[i, 0] = cv2.dilate(sk, k) > 0
    return torch.from_numpy(out)


@torch.no_grad()
def tiled_eval(model, data, tile, thr=0.5, stride_frac=0.75):
    """Pooled F1 on full images with overlapped tiles (fast validation); returns dict(f1, p, r, iou)."""
    model.eval()
    tp = fp = fn = 0
    for img, m in data:
        prob = tiled_predict(model, img, tile, stride_frac)
        pred = prob >= thr
        g = m > 0
        tp += int((pred & g).sum())
        fp += int((pred & ~g).sum())
        fn += int((~pred & g).sum())
    f1 = 2 * tp / max(2 * tp + fp + fn, 1)
    return {"f1": f1, "precision": tp / max(tp + fp, 1), "recall": tp / max(tp + fn, 1), "iou": tp / max(tp + fp + fn, 1)}


@torch.no_grad()
def tiled_predict(model, img_rgb, tile, stride_frac=0.75):
    """Overlap-blend tiled inference with the torch model (reflection padding up to one tile)."""
    import cv2
    h, w = img_rgb.shape[:2]
    ph, pw = max(0, tile - h), max(0, tile - w)
    im = cv2.copyMakeBorder(img_rgb, 0, ph, 0, pw, cv2.BORDER_REFLECT_101) if (ph or pw) else img_rgb
    H, W = im.shape[:2]
    st = max(1, int(tile * stride_frac))
    ys = list(range(0, max(H - tile, 0) + 1, st))
    xs = list(range(0, max(W - tile, 0) + 1, st))
    if ys[-1] != H - tile:
        ys.append(H - tile)
    if xs[-1] != W - tile:
        xs.append(W - tile)
    win = np.outer(np.hanning(tile + 2)[1:-1], np.hanning(tile + 2)[1:-1]).astype(np.float32) + 1e-3
    acc = np.zeros((H, W), np.float32)
    wt = np.zeros((H, W), np.float32)
    x = torch.from_numpy(im.astype(np.float32).transpose(2, 0, 1) / 255.0)
    for y0 in ys:
        for x0 in xs:
            p = model(x[None, :, y0:y0 + tile, x0:x0 + tile])[0, 0].numpy()
            acc[y0:y0 + tile, x0:x0 + tile] += p * win
            wt[y0:y0 + tile, x0:x0 + tile] += win
    return (acc / wt)[:h, :w]


# ----------------------------------------------------------------------------- training


def build(variant: str = "base") -> EfficientCrackNet:
    return EfficientCrackNet()


def cmd_train(a):
    torch.set_num_threads(4)
    torch.manual_seed(a.seed)
    np.random.seed(a.seed)
    out = ROOT / "runs" / a.recipe if not a.out else Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    tile = a.tile
    t_load = time.time()
    if a.recipe == "crack500":
        tr = [load_split("crack500", "train")]
        w = [1.0]
        va = load_split("crack500", "val", limit=a.val_n)
        va_name = "crack500-val"
    elif a.recipe == "joint":
        tr = [load_split("crack500", "train"), load_split("deepcrack", "train")]
        w = [a.w_crack500, a.w_deepcrack]
        va = load_split("crack500", "val", limit=a.val_n)
        va += load_split("deepcrack", "train", limit=0)           # no DeepCrack val exists; hold out below
        va_name = "crack500-val"
    else:
        raise SystemExit("recipe must be crack500 or joint")
    dc_hold = []
    if a.recipe == "joint":
        # DeepCrack has no official val split: hold out every 10th train image (30) for early stopping, train on the rest
        full = tr[1]
        dc_hold = full[::10]
        tr[1] = [x for i, x in enumerate(full) if i % 10 != 0]
        va = va[:a.val_n] + dc_hold
        va_name = "crack500-val+deepcrack-heldout"
    print(f"data loaded in {time.time() - t_load:.0f}s: train {[len(t) for t in tr]}, val {len(va)} ({va_name})", flush=True)

    model = build()
    if a.init:
        sd = torch.load(a.init, map_location="cpu")
        model.load_state_dict(sd["model"] if "model" in sd else sd)
    print(f"params {count_params(model):,}", flush=True)
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=1e-4)
    loader = Loader(tr, w, tile, a.bs, a.seed)
    loader.start()

    budget = a.hours * 3600
    t0 = time.time()
    log = out / "log.tsv"
    if not log.exists() or not a.resume:
        log.write_text("epoch\titers\tseconds\tlr\ttrain_loss\tval_f1\tval_precision\tval_recall\tval_iou\n")
    ipe = a.iters_per_epoch
    step, best, ep = 0, -1.0, 0
    if a.resume and (out / "last.pt").exists():
        ck = torch.load(out / "last.pt", map_location="cpu")
        model.load_state_dict(ck["model"])
        opt.load_state_dict(ck["opt"])
        step, best, ep = ck["step"], ck["best"], ck["epoch"]
        t0 -= ck.get("elapsed", 0)
        print(f"resumed at epoch {ep}", flush=True)
    est_total_steps = None
    while True:
        elapsed = time.time() - t0
        if elapsed > budget or ep >= a.max_epochs:
            break
        model.train()
        losses = []
        for _ in range(ipe):
            # cosine schedule over the wall-clock budget (time-based, so the run always ends annealed)
            frac = min((time.time() - t0) / budget, 1.0)
            lr = a.lr_min + 0.5 * (a.lr - a.lr_min) * (1 + math.cos(math.pi * frac))
            if step < a.warmup:
                lr *= (step + 1) / a.warmup
            for gp in opt.param_groups:
                gp["lr"] = lr
            x, y = loader.get()
            p = model(x)
            loss = dice_loss(p, y) + a.bce * F.binary_cross_entropy(p, y)
            if a.skel > 0:
                loss = loss + a.skel * skeleton_recall(p, tube_of(y))
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            opt.step()
            losses.append(loss.item())
            step += 1
        ep += 1
        vm = tiled_eval(model, va, tile)
        el = time.time() - t0
        with open(log, "a") as f:
            f.write(f"{ep}\t{step}\t{el:.0f}\t{lr:.2e}\t{np.mean(losses):.4f}\t{vm['f1']:.4f}\t{vm['precision']:.4f}\t"
                    f"{vm['recall']:.4f}\t{vm['iou']:.4f}\n")
        print(f"ep {ep} step {step} t={el / 60:.1f}min lr={lr:.2e} loss={np.mean(losses):.4f} val F1={vm['f1']:.4f} "
              f"P={vm['precision']:.3f} R={vm['recall']:.3f}", flush=True)
        ck = {"model": model.state_dict(), "opt": opt.state_dict(), "step": step, "best": best, "epoch": ep, "elapsed": el,
              "args": vars(a)}
        if vm["f1"] > best:
            best = vm["f1"]
            ck["best"] = best
            torch.save({"model": model.state_dict(), "val_f1": best, "epoch": ep, "args": vars(a)}, out / "best.pt")
        torch.save(ck, out / "last.pt")
    loader.stop = True
    print("done", flush=True)


# ----------------------------------------------------------------------------- export


def cmd_export(a):
    import onnx
    torch.set_num_threads(2)
    model = build()
    sd = torch.load(a.ckpt, map_location="cpu")
    model.load_state_dict(sd["model"] if "model" in sd else sd)
    model.eval()
    x = torch.rand(1, 3, a.tile, a.tile)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    kw = dict(input_names=["image"], output_names=["prob"], opset_version=a.opset)
    try:
        torch.onnx.export(model, (x,), str(out), dynamo=False, **kw)
    except TypeError:
        torch.onnx.export(model, (x,), str(out), **kw)
    m = onnx.load(str(out))
    onnx.checker.check_model(m)
    ops = sorted({n.op_type for n in m.graph.node})
    print("exported", out, out.stat().st_size, "bytes; ops:", ops)


def cmd_count(a):
    m = build().eval()
    print(f"params {count_params(m):,}")
    for s in (256, 512):
        mac = count_macs(m, s)
        print(f"size {s}: {mac / 1e9:.3f} GMACs = {2 * mac / 1e9:.3f} GFLOPs")


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("count")
    t = sp.add_parser("train")
    t.add_argument("--recipe", default="crack500", choices=["crack500", "joint"])
    t.add_argument("--hours", type=float, default=2.5)
    t.add_argument("--tile", type=int, default=256)
    t.add_argument("--bs", type=int, default=8)
    t.add_argument("--lr", type=float, default=2e-3)
    t.add_argument("--lr-min", dest="lr_min", type=float, default=1e-5)
    t.add_argument("--warmup", type=int, default=100)
    t.add_argument("--bce", type=float, default=0.5)
    t.add_argument("--skel", type=float, default=0.0)
    t.add_argument("--seed", type=int, default=0)
    t.add_argument("--iters-per-epoch", dest="iters_per_epoch", type=int, default=250)
    t.add_argument("--max-epochs", dest="max_epochs", type=int, default=10000)
    t.add_argument("--val-n", dest="val_n", type=int, default=120)
    t.add_argument("--init", default=None)
    t.add_argument("--out", default=None)
    t.add_argument("--resume", action="store_true")
    t.add_argument("--w-crack500", dest="w_crack500", type=float, default=1.0)
    t.add_argument("--w-deepcrack", dest="w_deepcrack", type=float, default=1.0)
    e = sp.add_parser("export")
    e.add_argument("--ckpt", required=True)
    e.add_argument("--out", required=True)
    e.add_argument("--tile", type=int, default=256)
    e.add_argument("--opset", type=int, default=17)
    a = ap.parse_args()
    {"train": cmd_train, "export": cmd_export, "count": cmd_count}[a.cmd](a)


if __name__ == "__main__":
    main()
