"""Uniform (image, mask) access to the public crack-segmentation datasets used by the segmentation eval.

    from prohori.datasets import iter_samples, list_datasets, available
    for s in iter_samples("deepcrack", "test"):
        s.image   # uint8 BGR (H, W, 3)
        s.mask    # bool (H, W), True = crack
        s.name    # stable sample id
        s.subset  # sub-dataset / scene tag where the dataset has one (else "")

Datasets live under ``data/datasets/<name>/`` (git-ignored; see research/DATASETS.md for sources, checksums, licences).
Splits are the OFFICIAL ones where the authors define them:

    crack500    train 1896 / val 348 / test 1124    (Yang et al. FPHB, TITS 2019: the 3,368-crop version)
    deepcrack   train 300 / test 237                (Liu et al., Neurocomputing 2019)
    tut         train 987 / val 139 / test 282      (Liu et al. CrackSCF, Eng. Structures 2026)
    facade390   test 390   (zero-shot set, no train/val: CrackSAM, CBM 2024)
    road420     test 420   (zero-shot set: CrackSAM, CBM 2024)
    cfd, ael, cracktree200, gaps384   test = all images with a ground-truth mask (evaluation-only benchmark sets,
                                      no official train/test split; they are OmniCrack30k constituents)
    crackseg9k  the authors' train/test lists (Kulkarni et al., CVPRW 2022; 10 merged sources)

OmniCrack30k itself is distributed on request only (see research/DATASETS.md); ``omni_public`` is the documented
substitute: the union of the public OmniCrack30k constituent sets above (cfd, ael, cracktree200, gaps384, crack500,
deepcrack) -- use ``iter_samples("omni_public", "test")``.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

import cv2
import numpy as np

ROOT = Path(os.environ.get("PROHORI_DATASETS", Path(__file__).resolve().parents[2] / "data" / "datasets"))


_INVERTED_ROOTS = (ROOT / "ael",)


@dataclass
class Sample:
    dataset: str
    split: str
    name: str
    image: np.ndarray      # uint8 BGR
    mask: np.ndarray       # bool
    subset: str = ""


# Each loader returns a list of (name, image_path, mask_path, subset) for a split.
_Entry = tuple[str, Path, Path, str]


def _read_pairs_txt(root: Path, txt: str) -> list[tuple[str, str]]:
    out = []
    for line in (root / txt).read_text().splitlines():
        parts = line.split()
        if len(parts) >= 2:
            out.append((parts[0], parts[1]))
    return out


def _crack500(split: str) -> list[_Entry]:
    root = ROOT / "crack500"
    return [(Path(i).stem, root / i, root / m, "") for i, m in _read_pairs_txt(root, f"{split}.txt")]


def _folder_split(name: str, splits: dict[str, tuple[str, str]], ext_mask: str = ".png"):
    def f(split: str) -> list[_Entry]:
        root = ROOT / name
        di, dm = splits[split]
        out = []
        for p in sorted((root / di).iterdir()):
            if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp"):
                m = root / dm / (p.stem + ext_mask)
                if m.exists():
                    out.append((p.stem, p, m, ""))
        return out
    return f


def _facade(split: str) -> list[_Entry]:
    return _images_masks("facade390")


def _road(split: str) -> list[_Entry]:
    return _images_masks("road420")


def _images_masks(name: str) -> list[_Entry]:
    """images/<id>.jpg  <->  masks/<id>.(png|jpg)  (CrackSAM zero-shot sets; masks are soft 0..255 jpg/png)."""
    root = ROOT / name
    out = []
    for p in sorted((root / "images").glob("*.jpg")):
        for ext in (".png", ".jpg"):
            m = root / "masks" / (p.stem + ext)
            if m.exists():
                out.append((p.stem, p, m, ""))
                break
    return out


def _cfd(split: str) -> list[_Entry]:
    root = ROOT / "cfd"
    return [(p.stem, p, root / "seg_gt" / (p.stem + ".png"), "") for p in sorted((root / "cfd_image").glob("*.jpg"))
            if (root / "seg_gt" / (p.stem + ".png")).exists()]


def _ael(split: str) -> list[_Entry]:
    """AEL: img/<sub>/Im_GT_<id>[c]or.jpg  <->  gt/<sub>/GT_<id>.png  (AIGLE_RN, ESAR, LCMS, LRIS, TEMPEST2)."""
    root = ROOT / "ael"
    out = []
    for p in sorted((root / "img").rglob("*.jpg")):
        sub = p.relative_to(root / "img").parts[0]
        core = p.stem[3:] if p.stem.startswith("Im_") else p.stem          # GT_<id>[c]or
        cands = [core, core[:-2] if core.endswith("or") else core, core[:-3] if core.endswith("cor") else core,
                 core[:-1] if core.endswith("c") else core]
        m = next((root / "gt" / sub / (c + ".png") for c in cands if (root / "gt" / sub / (c + ".png")).exists()), None)
        if m is not None:
            out.append((f"{sub}_{p.stem}", p, m, sub))
    return out


def _cracktree(split: str) -> list[_Entry]:
    root = ROOT / "cracktree200"
    return [(p.stem, p, root / "cracktree200_gt" / (p.stem + ".png"), "") for p in
            sorted((root / "cracktree200rgb").glob("*.jpg"))
            if (root / "cracktree200_gt" / (p.stem + ".png")).exists()]


def _gaps(split: str) -> list[_Entry]:
    root = ROOT / "gaps384"
    return [(p.stem, p, root / "croppedgt" / (p.stem + ".png"), "") for p in sorted((root / "croppedimg").glob("*.jpg"))
            if (root / "croppedgt" / (p.stem + ".png")).exists()]


def _cs9k_subset(stem: str) -> str:
    import re
    for pre in ("Rissbilder", "noncrack", "Volker", "DeepCrack", "cracktree", "CRACK", "GAPS", "CFD", "Ceramic"):
        if stem.startswith(pre):
            return pre
    return re.sub(r"[-_]?\d.*$", "", stem) or "other"


def _crackseg9k(split: str) -> list[_Entry]:
    """CrackSeg9k: Final-Dataset-Vol1/{Images,Final_Masks/Masks} + Vol2/Images-2, official train.txt / test.txt."""
    root = ROOT / "crackseg9k"
    base = root / "Final-Dataset-Vol1"
    names = [l.strip() for l in (base / "Final_Masks" / f"{split}.txt").read_text().splitlines() if l.strip()]
    imgdirs = [base / "Images", root / "Final-Dataset-Vol2" / "Images-2"]
    out = []
    for n in names:
        stem = Path(n.split()[0]).stem
        ip = next((d / (stem + e) for d in imgdirs for e in (".png", ".jpg") if (d / (stem + e)).exists()), None)
        mp = base / "Final_Masks" / "Masks" / (stem + ".png")
        if ip is not None and mp.exists():
            out.append((stem, ip, mp, _cs9k_subset(stem)))
    return out


@dataclass
class DatasetSpec:
    name: str
    splits: dict[str, Callable[[], list[_Entry]]]
    description: str = ""
    n_expected: dict | None = None      # official split sizes, for sanity checks


_SPECS: dict[str, DatasetSpec] = {}


def _reg(name, loader, splits, desc, expected=None):
    _SPECS[name] = DatasetSpec(name, {s: (lambda s=s, l=loader: l(s)) for s in splits}, desc, expected)


_reg("crack500", _crack500, ("train", "val", "test"), "Crack500 (FPHB crops), asphalt, phone", {"train": 1896, "val": 348, "test": 1124})
_reg("deepcrack", _folder_split("deepcrack", {"train": ("train_img", "train_lab"), "test": ("test_img", "test_lab")}),
     ("train", "test"), "DeepCrack, concrete/brick/asphalt", {"train": 300, "test": 237})
_reg("tut", _folder_split("tut", {"train": ("train_img", "train_lab"), "val": ("val_img", "val_lab"),
                                  "test": ("test_img", "test_lab")}),
     ("train", "val", "test"), "TUT, 8 cluttered scenes", {"train": 987, "val": 139, "test": 282})
_reg("facade390", _facade, ("test",), "Facade390 (CrackSAM), building facades, UAV", {"test": 390})
_reg("road420", _road, ("test",), "Road420 (CrackSAM), iPhone road cracks", {"test": 420})
_reg("cfd", _cfd, ("test",), "CFD, 118 pavement images (OmniCrack constituent)", {"test": 118})
_reg("ael", _ael, ("test",), "AEL pavement images (OmniCrack constituent)")
_reg("cracktree200", _cracktree, ("test",), "CrackTree200 (OmniCrack constituent)", {"test": 206})
_reg("gaps384", _gaps, ("test",), "GAPs384 cropped (OmniCrack constituent)", {"test": 509})
_reg("crackseg9k", _crackseg9k, ("train", "test"), "CrackSeg9k, 10 merged sources")

OMNI_PUBLIC = ("cfd", "ael", "cracktree200", "gaps384", "crack500", "deepcrack")


def list_datasets() -> list[str]:
    return sorted(_SPECS) + ["omni_public"]


def available(name: str) -> bool:
    return name == "omni_public" or (ROOT / name).exists() and (ROOT / name).is_dir()


def splits(name: str) -> list[str]:
    return ["test"] if name == "omni_public" else list(_SPECS[name].splits)


def entries(name: str, split: str) -> list[_Entry]:
    if name == "omni_public":
        out = []
        for n in OMNI_PUBLIC:
            if not available(n):
                continue
            sp = "test" if "test" in _SPECS[n].splits else splits(n)[-1]
            out += [(f"{n}/{e[0]}", e[1], e[2], n) for e in _SPECS[n].splits[sp]()]
        return out
    if name not in _SPECS:
        raise KeyError(f"unknown dataset {name!r}; known: {list_datasets()}")
    if split not in _SPECS[name].splits:
        raise KeyError(f"{name} has no split {split!r}; has {list(_SPECS[name].splits)}")
    return _SPECS[name].splits[split]()


def load_pair(img_path: Path, mask_path: Path, max_side: int | None = None) -> tuple[np.ndarray, np.ndarray]:
    img = cv2.imread(str(img_path), cv2.IMREAD_COLOR)
    m = cv2.imread(str(mask_path), cv2.IMREAD_UNCHANGED)
    if img is None or m is None:
        raise IOError(f"cannot read {img_path} / {mask_path}")
    if m.ndim == 3:
        m = m[:, :, 0] if m.shape[2] < 4 else m[:, :, :3].max(axis=2)
    if m.shape[:2] != img.shape[:2]:
        m = cv2.resize(m, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)
    mask = m > 127          # masks are 0/255 (soft-edged where the source was resized): binarise at mid-grey
    if _INVERTED_ROOTS and any(r in Path(mask_path).parents for r in _INVERTED_ROOTS):
        mask = ~mask        # AEL ground truth is stored crack = 0 (black), background = 255
    if max_side and max(img.shape[:2]) > max_side:
        s = max_side / max(img.shape[:2])
        img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        mask = cv2.resize(mask.astype(np.uint8), (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST) > 0
    return img, mask


def iter_samples(name: str, split: str = "test", limit: int | None = None, stride: int = 1,
                 max_side: int | None = None) -> Iterator[Sample]:
    """Yield ``Sample(image BGR uint8, mask bool, ...)`` for an official split.

    ``limit`` / ``stride`` take a deterministic subset (every ``stride``-th entry, at most ``limit``)."""
    ents = entries(name, split)[::stride]
    if limit is not None:
        ents = ents[:limit]
    for nm, ip, mp, sub in ents:
        img, mask = load_pair(ip, mp, max_side)
        yield Sample(name, split, nm, img, mask, sub)


def count(name: str, split: str) -> int:
    return len(entries(name, split))
