#!/usr/bin/env python
"""Build the final Prohori demo video: docs/video/Prohori_demo.mp4 (+ Prohori_demo.srt).

Re-runnable. The whole edit is data at the top of this file:
  * AUDIO knobs (lead-in, pause shortening, cuts),
  * SHOTS  : the visual timeline, in SOURCE seconds of docs/video/raw/voice.m4a,
  * WORD_EDITS : caption corrections (token level, matched by start time),
  * caption layout constants.
Source times are mapped to output times through the audio edit (leading trim, shortened pauses, optional cuts),
so changing the audio edit never breaks the visuals or captions.

Usage:
  python tools/make_video.py                 # full build (audio, captions, video, srt)
  python tools/make_video.py --snap 5,40,95  # write PNG snapshots at those OUTPUT seconds (no encode) for layout checks
  python tools/make_video.py --audio-only    # just rebuild the processed audio + print the time map

Needs: numpy, opencv, soundfile, Pillow, ffmpeg on PATH, playwright (only to draw the two face compositions).
The raw voice and the photos (docs/video/raw/) are git-ignored and never leave the machine.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
import soundfile as sf
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
VID = ROOT / "docs" / "video"
RAW = VID / "raw"
ASSETS = VID / "assets"
BUILD = ASSETS / "tmp" / "build"  # git-ignored intermediates (contains face compositions: never commit)
OUT_MP4 = VID / "Prohori_demo.mp4"
OUT_SRT = VID / "Prohori_demo.srt"
W, H, FPS = 1920, 1080, 30

# --------------------------------------------------------------------------------------------- AUDIO (source seconds)
LEAD_SILENCE = 0.40          # seconds of silence before the first word in the output
PAUSE_MAX = 1.50             # any gap between words longer than this ...
PAUSE_KEEP = 0.90            # ... is shortened to this
PAUSE_XFADE = 0.04           # crossfade length used at pause cuts (silence on both sides)
EXTRA_CUTS: list[tuple[float, float, float]] = []   # manual (cut_start, cut_end, crossfade) in source seconds.
# The planned " random errors." cut is NOT made: re-transcribing 124.0-125.7 s in short windows reads
# "and against" / "random" / "choices" only; the "errors. random" in the first transcript was a whisper hallucination.
HOLD_AFTER_VOICE = 2.5       # seconds of closing card after the last word
LAST_WORD_END = 227.05       # source seconds (end of "Thank you.")
LUFS, TRUE_PEAK = -16.0, -1.8  # target; the AAC encode adds a little, spec limit is -1.5 dBTP

# ------------------------------------------------------------------------------------------------------- VISUAL PLAN
# kind: still (fit = scale of the picture inside the frame, 0.85 leaves the bottom free for captions)
#       clip  (in = start time in the screen recording, speed = playback speed)
# t is the SOURCE second at which the shot starts (a 0.3 s crossfade is centred on it).
# views = optional list of (source_second, (x0, y0, x1, y1)) keyframes of a 16:9 window on the still (slow zooms/pans).
FIT = 0.83
C, G, S = "assets/cards/", "assets/charts/", "assets/screens/"
SHOTS: list[dict] = [
    # 1: intro, title, Rana Plaza, comparator
    dict(t=0.00, kind="still", src="@face_intro", fit=1.0),
    dict(t=9.00, kind="still", src=C + "rana_plaza.png", fit=FIT),
    dict(t=14.35, kind="still", src=C + "crack_comparator.png", fit=1.0),
    dict(t=18.60, kind="still", src=C + "title.png", fit=1.0),
    dict(t=21.30, kind="clip", src=S + "a_certified.mp4", **{"in": 17.9}, speed=1.0, fit=FIT),     # green Certified result
    # 2: how it works
    dict(t=26.82, kind="clip", src=S + "a_certified.mp4", **{"in": 0.5}, speed=1.0, fit=FIT),      # viewfinder, capture tap
    dict(t=32.40, kind="clip", src=S + "a_certified.mp4", **{"in": 14.2}, speed=1.5, fit=FIT),     # Measuring...
    dict(t=35.00, kind="clip", src=S + "a_certified.mp4", **{"in": 24.5}, speed=1.0, fit=FIT),     # overlay: board + crack outlines
    dict(t=38.60, kind="clip", src=S + "a_certified.mp4", **{"in": 32.0}, speed=1.0, fit=FIT),     # rectified zoom, px/mm
    dict(t=43.00, kind="still", src=G + "rectified_profile.png", fit=FIT,
         views=[(43.0, (0, 0, 1920, 1080)), (45.0, (0, 0, 1920, 1080)), (57.0, (60, 0, 1860, 1012.5))]),
    # 3: the gate
    dict(t=59.65, kind="clip", src=S + "c_indicative.mp4", **{"in": 17.8}, speed=1.0, fit=FIT),
    dict(t=64.00, kind="clip", src=S + "c_indicative.mp4", **{"in": 27.0}, speed=1.0, fit=FIT),    # corners, sharpness, tilt, glare
    dict(t=67.90, kind="still", src=G + "gate_risk_coverage.png", fit=FIT),
    dict(t=79.70, kind="clip", src=S + "b_agent_loop.mp4", **{"in": 13.4}, speed=1.0, fit=FIT),    # refused: Move closer
    # 4: the agent
    dict(t=85.80, kind="still", src=G + "agent_workflow_full.png", fit=FIT),
    dict(t=90.00, kind="still", src=G + "agent_workflow_zoom_perception.png", fit=FIT),
    dict(t=94.50, kind="still", src=G + "agent_workflow_zoom_action.png", fit=FIT),
    dict(t=108.80, kind="clip", src=S + "d_trace.mp4", **{"in": 33.1}, speed=1.0, fit=FIT),        # trace: numbers -> instruction
    dict(t=112.10, kind="clip", src=S + "b_agent_loop.mp4", **{"in": 15.0}, speed=1.0, fit=FIT),   # "the photo was too far"
    dict(t=114.70, kind="clip", src=S + "b_agent_loop.mp4", **{"in": 37.06}, speed=1.5, fit=FIT),  # certified lands at ~117.8 s
    dict(t=118.80, kind="still", src=G + "ablation_v2.png", fit=FIT),
    dict(t=125.60, kind="still", src=G + "faithfulness.png", fit=FIT),
    dict(t=131.55, kind="still", src=G + "ablation_v2.png", fit=FIT,
         views=[(131.55, (0, 0, 1920, 1080)), (133.5, (0, 0, 1920, 1080)), (137.0, (180, 120, 1780, 1020))]),
    # 5: AWS + COOL
    dict(t=141.40, kind="still", src=G + "architecture_full.png", fit=FIT),
    dict(t=144.40, kind="still", src=G + "architecture_zoom_left.png", fit=FIT,
         views=[(144.4, (0, 0, 1920, 1080)), (145.4, (270, 40, 1470, 715))]),
    dict(t=148.90, kind="still", src=G + "architecture_zoom_right.png", fit=FIT,
         views=[(148.9, (0, 0, 1920, 1080)), (149.7, (590, 268, 1390, 718)), (159.9, (590, 268, 1390, 718)),
                (160.8, (560, 475, 1360, 925))]),
    dict(t=166.40, kind="still", src=C + "cool_vs_pip.png", fit=FIT),
    dict(t=177.00, kind="still", src=G + "cool_latency.png", fit=FIT),
    dict(t=178.90, kind="still", src=G + "cool_pareto.png", fit=FIT),
    dict(t=180.60, kind="still", src=C + "crash.png", fit=FIT),
    # 6: results
    dict(t=186.80, kind="still", src=G + "width_error.png", fit=FIT),
    dict(t=199.60, kind="still", src=C + "published_comparison.png", fit=FIT),
    dict(t=206.00, kind="still", src=G + "failure_gallery.png", fit=FIT),
    # 7: outro
    dict(t=210.40, kind="still", src="@face_outro", fit=1.0),
    dict(t=215.60, kind="still", src=C + "closing.png", fit=1.0),
]
XFADE = 0.30
KB_ZOOM = 0.04   # slow Ken Burns on stills without explicit views (<= 5 %)

# ------------------------------------------------------------------------------------------------- CAPTION CORRECTIONS
# (word start time in the whisper file, old word stripped of punctuation, new text incl. punctuation and leading space)
WORD_EDITS: list[tuple[float, str, str]] = [
    (170.01, "kool", " COOL,"), (184.13, "kool", " COOL"),
    (186.89, "results", " Results."),
    (189.25, "no", " known"),
    (190.03, "held", " held-"), (190.23, "out", "out"),     # "held-out" (second token glued on)
    (120.24, "held", " held-"), (120.52, "out", "out"),
    (194.71, "millimeter", " millimetre,"),
    (171.61, "optimized", " optimised"),
    (122.08, "-rule", " rule"),                              # "fixed rule list"
    (216.77, "number", " number,"), (217.17, "how", " how"),  # "a number, how sure that number is, ..."
    (94.02, "actions", " actions:"),
    (115.42, "move", ' "move'), (115.92, "closer", ' closer,"'),
]
# regex fixes on a joined caption text (applied after the token edits)
TEXT_FIXES = [
    (r"\bwith intolerance\b", "within tolerance"),
    (r"\bpixels per millimetres\b", "pixels per millimetre"),
    (r"\bper millimetres\b", "per millimetre"),
]
LIST_LOWER = (95.0, 107.3)   # the action list: lower-case normally
LIST_REPLACE = {"replace": "re-place"}
DROP_TOKENS = [(124.66, "random"), (125.0, "errors")]
SKIP_SEGMENT_STARTS = {94.74}  # whisper duplicate segment

# caption layout
CAP_FONT = "C:/Windows/Fonts/seguisb.ttf"   # Segoe UI Semibold
CAP_PT, CAP_LINE, CAP_PAD_X, CAP_PAD_Y, CAP_BOTTOM, CAP_RADIUS = 46, 56, 28, 14, 30, 20
CAP_ALPHA = 0.66
MAX_LINE, MAX_CUE_CHARS, MAX_CUE_SEC = 42, 82, 5.6


# ---------------------------------------------------------------------------------------------------------- helpers
def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def load_tokens() -> list[dict]:
    data = json.loads((RAW / "transcript_words.json").read_text(encoding="utf-8"))
    toks: list[dict] = []
    for seg in data["segments"]:
        if round(seg["start"], 2) in SKIP_SEGMENT_STARTS:
            continue
        for w in seg["words"]:
            toks.append(dict(text=w["word"], start=float(w["start"]), end=float(w["end"])))
    toks.sort(key=lambda t: t["start"])
    # whisper's hallucinated "random errors." (first pass) is not in the audio: drop it from the captions
    toks = [t for t in toks if not any(abs(t["start"] - ds) < 0.03 and re.sub(r"\W", "", t["text"]).lower() == dw
                                       for ds, dw in DROP_TOKENS)]
    # repair zero/negative durations (whisper emits some)
    for i, t in enumerate(toks):
        nxt = toks[i + 1]["start"] if i + 1 < len(toks) else t["start"] + 0.3
        t["end"] = max(t["end"], t["start"] + 0.06)
    return toks


def apply_word_edits(toks: list[dict]) -> list[dict]:
    used = set()
    for t in toks:
        core = re.sub(r"[^\w'-]", "", t["text"]).lower()
        for i, (ts, old, new) in enumerate(WORD_EDITS):
            if abs(t["start"] - ts) < 0.03 and core == old:
                t["text"] = new
                used.add(i)
        if LIST_LOWER[0] <= t["start"] <= LIST_LOWER[1]:
            core2 = re.sub(r"[^\w'-]", "", t["text"]).lower()
            t["text"] = t["text"].lower()
            if core2 in LIST_REPLACE:
                t["text"] = t["text"].replace(core2, LIST_REPLACE[core2])
    missed = [WORD_EDITS[i] for i in range(len(WORD_EDITS)) if i not in used]
    if missed:
        print("WARNING: word edits not matched:", missed)
    return toks


# ----------------------------------------------------------------------------------------------------------- audio

SIL_DB = -45.0       # below this (10 ms rms, dBFS) counts as silence
def frame_db(x: np.ndarray, sr: int) -> np.ndarray:
    fr = int(0.01 * sr)
    n = len(x) // fr
    r = np.sqrt((x[: n * fr].reshape(n, fr) ** 2).mean(axis=1))
    return 20 * np.log10(r + 1e-9)


def silence_runs(db: np.ndarray, min_s: float) -> list[tuple[float, float]]:
    runs, k, n = [], 0, len(db)
    while k < n:
        if db[k] < SIL_DB:
            j = k
            while j < n and db[j] < SIL_DB:
                j += 1
            if (j - k) / 100 >= min_s:
                runs.append((k / 100, j / 100))
            k = j
        else:
            k += 1
    return runs


def refine_onsets(toks: list[dict], db: np.ndarray) -> None:
    for t in toks:
        t["start0"] = t["start"]
    """whisper gives a sentence-initial word its start somewhere in the pause before it; move such starts to the real
    speech onset (end of the first silence run >= 120 ms that follows the previous word)."""
    runs = silence_runs(db, 0.12)
    for i, t in enumerate(toks):
        prev_end = toks[i - 1]["end"] if i else 0.0
        cand = [e for (b, e) in runs if e >= prev_end + 0.05 and e > t["start"] - 0.1 and e <= t["start"] + 1.2 and b <= t["start"] + 0.3]
        if cand:
            new = min(cand)
            if new > t["start"]:
                t["end"] = max(t["end"], new + 0.06)
                t["start"] = new

class TimeMap:
    """source seconds -> output seconds, given the leading trim and the removed intervals."""

    def __init__(self, start: float, removals: list[tuple[float, float, float]]):
        self.start, self.removals = start, sorted(removals)

    def __call__(self, t: float) -> float:
        out = t - self.start
        for c0, c1, _ in self.removals:
            out -= min(max(t - c0, 0.0), c1 - c0)
        return max(out, 0.0)


def plan_audio(toks: list[dict], x: np.ndarray, sr: int, db: np.ndarray) -> TimeMap:
    first = toks[0]["start"]
    start = max(first - LEAD_SILENCE, 0.0)
    rem: list[tuple[float, float, float]] = []
    for r0, r1 in silence_runs(db, PAUSE_MAX):
        if r0 < start or r1 > LAST_WORD_END + 1.0:
            continue
        half = PAUSE_KEEP / 2
        c0, c1 = r0 + half, r1 - half
        seg = x[int(c0 * sr):int(c1 * sr)]
        d = 20 * math.log10(float(np.sqrt((seg ** 2).mean())) + 1e-9)
        print(f"  pause {r0:.2f}-{r1:.2f} ({r1 - r0:.2f}s): cut {c0:.2f}-{c1:.2f}, rms {d:.1f} dBFS")
        rem.append((c0, c1, PAUSE_XFADE))
    rem += [tuple(c) for c in EXTRA_CUTS]
    return TimeMap(start, rem)


def edit_audio(x: np.ndarray, sr: int, tm: TimeMap) -> np.ndarray:
    """Apply the removals with equal-power crossfades."""
    pieces: list[np.ndarray] = []
    a = tm.start
    segs: list[tuple[float, float, float]] = []   # (a, b, xf_to_next)
    for c0, c1, xf in tm.removals:
        segs.append((a, c0 + xf / 2, xf))
        a = c1 - xf / 2
    segs.append((a, len(x) / sr, 0.0))
    out = np.zeros(0, dtype=np.float32)
    prev_xf = 0
    for (a, b, xf) in segs:
        chunk = x[int(a * sr):int(b * sr)].astype(np.float32).copy()
        if prev_xf > 0 and len(out) >= prev_xf and len(chunk) >= prev_xf:
            n = prev_xf
            ramp = np.linspace(0, math.pi / 2, n, dtype=np.float32)
            out[-n:] = out[-n:] * np.cos(ramp) + chunk[:n] * np.sin(ramp)
            chunk = chunk[n:]
        out = np.concatenate([out, chunk])
        prev_xf = int(xf * sr)
    return out


def process_audio(tm: TimeMap, total: float) -> Path:
    BUILD.mkdir(parents=True, exist_ok=True)
    mono = BUILD / "voice_mono.wav"
    if not mono.exists():
        run(["ffmpeg", "-v", "error", "-y", "-i", str(RAW / "voice.m4a"), "-ac", "1", "-ar", "48000",
             "-c:a", "pcm_f32le", str(mono)])
    x, sr = sf.read(str(mono), dtype="float32")
    edited = edit_audio(x, sr, tm)
    ed = BUILD / "voice_edited.wav"
    sf.write(str(ed), edited, sr, subtype="FLOAT")
    pre = "highpass=f=80,afftdn=nr=9:nf=-55:tn=0"
    m = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(ed), "-af",
             f"{pre},loudnorm=I={LUFS}:TP={TRUE_PEAK}:LRA=11:print_format=json", "-f", "null", "-"])
    js = json.loads(m.stderr[m.stderr.rindex("{"):m.stderr.rindex("}") + 1])
    ln = (f"loudnorm=I={LUFS}:TP={TRUE_PEAK}:LRA=11:measured_I={js['input_i']}:measured_TP={js['input_tp']}:"
          f"measured_LRA={js['input_lra']}:measured_thresh={js['input_thresh']}:offset={js['target_offset']}:linear=true")
    outp = BUILD / "voice_final.wav"
    run(["ffmpeg", "-v", "error", "-y", "-i", str(ed), "-af", f"{pre},{ln},apad=whole_dur={total:.3f}",
         "-ar", "48000", "-c:a", "pcm_s16le", "-t", f"{total:.3f}", str(outp)])
    print(f"audio: edited {len(edited) / sr:.2f}s, measured {js['input_i']} LUFS / {js['input_tp']} dBTP -> {LUFS} LUFS")
    return outp


# ------------------------------------------------------------------------------------------------------- captions
def split_lines(text: str) -> list[str]:
    if len(text) <= MAX_LINE:
        return [text]
    words = text.split(" ")
    best, best_score = None, 1e9
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        if len(a) > MAX_LINE or len(b) > MAX_LINE:
            continue
        score = abs(len(a) - len(b)) - (8 if a.endswith((",", ".", ":", "?")) else 0)
        if score < best_score:
            best, best_score = [a, b], score
    if best is None:
        raise ValueError("caption too long: " + text)
    return best


NO_BREAK_AFTER = {"a", "an", "the", "of", "to", "and", "if", "with", "that", "than", "in", "on", "by", "only", "or", "is", "are", "its", "as", "for", "it", "we"}
CLAUSE_START = {"that", "with", "because", "and", "or", "but", "which", "who", "against", "before"}
NO_BREAK_BEFORE = {"the", "a", "an", "of", "to", "in", "on", "by", "is", "are", "its", "it", "than", "as", "for"}


def build_cues(toks: list[dict]) -> list[dict]:
    """Sentence-first captioning: one cue per sentence; tiny sentences merge with a neighbour, long ones split."""

    def text_of(ts):
        txt = re.sub(r"\s+", " ", "".join(t["text"] for t in ts)).strip()
        for pat, rep in TEXT_FIXES:
            txt = re.sub(pat, rep, txt)
        return txt

    def dur(ts):
        return ts[-1]["end"] - ts[0]["start"]

    sents, cur = [], []
    for t in toks:
        cur.append(t)
        if t["text"].rstrip().endswith((".", "?", "!", ":")):
            sents.append(cur)
            cur = []
    if cur:
        sents.append(cur)

    def fits(ts):
        if len(text_of(ts)) > MAX_CUE_CHARS or dur(ts) > MAX_CUE_SEC:
            return False
        try:
            split_lines(text_of(ts))
        except ValueError:
            return False
        return True

    def split(ts):
        if fits(ts):
            return [ts]
        total = len(text_of(ts))
        best, best_score = None, 1e9
        for i in range(2, len(ts) - 1):
            l, r = ts[:i], ts[i:]
            score = abs(len(text_of(l)) - total / 2) * 1.0 + abs(dur(l) - dur(ts) / 2) * 4
            if l[-1]["text"].rstrip().endswith((",", ";")):
                score -= 12
            nxt_w = re.sub(r"\W", "", ts[i]["text"]).lower()
            if nxt_w in NO_BREAK_BEFORE:
                score += 12
            if nxt_w in CLAUSE_START:
                score -= 6
            if re.sub(r"\W", "", l[-1]["text"]).lower() in NO_BREAK_AFTER:
                score += 14
            if ts[i]["start"] - l[-1]["end"] > 0.3:
                score -= 8
            if score < best_score:
                best, best_score = i, score
        return split(ts[:best]) + split(ts[best:])

    groups: list[list[dict]] = []
    for sn in sents:
        parts = split(sn)
        for part in parts:
            if groups and (len(text_of(part)) < 22 or len(text_of(groups[-1])) < 22)                     and part[0]["start"] - groups[-1][-1]["end"] < 0.8 and fits(groups[-1] + part):
                groups[-1] = groups[-1] + part
            else:
                groups.append(part)
    return [dict(start=g[0]["start"], end=g[-1]["end"], text=text_of(g)) for g in groups]


def retime_cues(cues: list[dict], tm: TimeMap, total: float) -> list[dict]:
    out = []
    for i, c in enumerate(cues):
        s = tm(c["start"]) - 0.04
        e = tm(c["end"]) + 0.30
        out.append(dict(start=max(s, 0.05), end=e, text=c["text"], lines=split_lines(c["text"])))
    for i, c in enumerate(out):
        nxt = out[i + 1]["start"] if i + 1 < len(out) else total
        c["end"] = min(c["end"], nxt - 0.02)
        if c["end"] - c["start"] < 1.0:
            c["end"] = min(c["start"] + 1.0, nxt - 0.02)
        c["end"] = min(c["end"], c["start"] + 6.0)
    return out


def srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def write_srt(cues: list[dict]) -> None:
    lines = []
    for i, c in enumerate(cues, 1):
        lines += [str(i), f"{srt_time(c['start'])} --> {srt_time(c['end'])}", *c["lines"], ""]
    OUT_SRT.write_text("\n".join(lines), encoding="utf-8")


class CaptionRenderer:
    def __init__(self):
        self.font = ImageFont.truetype(CAP_FONT, CAP_PT)
        self.cache: dict[int, tuple] = {}

    def prerender(self, idx: int, lines: list[str]):
        if idx in self.cache:
            return self.cache[idx]
        widths = [self.font.getlength(l) for l in lines]
        bw = int(max(widths)) + 2 * CAP_PAD_X
        bh = CAP_LINE * len(lines) + 2 * CAP_PAD_Y - 6
        scale = 2
        img = Image.new("RGBA", (bw * scale, bh * scale), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([0, 0, bw * scale - 1, bh * scale - 1], radius=CAP_RADIUS * scale, fill=(0, 0, 0, int(255 * CAP_ALPHA)))
        img = img.resize((bw, bh), Image.LANCZOS)
        txt = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
        td = ImageDraw.Draw(txt)
        for k, l in enumerate(lines):
            w = self.font.getlength(l)
            td.text(((bw - w) / 2, CAP_PAD_Y - 4 + k * CAP_LINE), l, font=self.font, fill=(255, 255, 255, 255))
        img = Image.alpha_composite(img, txt)
        arr = np.asarray(img).astype(np.float32)
        a = arr[..., 3:4] / 255.0
        pm = arr[..., :3][..., ::-1] * a   # BGR premultiplied
        self.cache[idx] = (pm, a, bw, bh)
        return self.cache[idx]

    def draw(self, frame: np.ndarray, idx: int, lines: list[str]):
        pm, a, bw, bh = self.prerender(idx, lines)
        x0 = (W - bw) // 2
        y1 = H - CAP_BOTTOM
        y0 = y1 - bh
        reg = frame[y0:y1, x0:x0 + bw].astype(np.float32)
        frame[y0:y1, x0:x0 + bw] = np.clip(reg * (1 - a) + pm, 0, 255).astype(np.uint8)


# ------------------------------------------------------------------------------------------------------ face comps
def render_faces() -> dict[str, Path]:
    sys.path.insert(0, str(ROOT / "tools"))
    from playwright.sync_api import sync_playwright
    from video_cards import page, b64

    BUILD.mkdir(parents=True, exist_ok=True)

    def comp(photo: Path, right_html: str) -> str:
        uri = b64(photo, "image/jpeg")
        return page(f"""
<div style="position:absolute;left:120px;top:50px;width:640px;height:860px;border-radius:40px;overflow:hidden;
  box-shadow:0 40px 90px -20px #000, 0 0 0 2px #263648"><img src="{uri}" style="width:100%;height:100%;object-fit:cover;object-position:50% 8%"></div>
{right_html}""")

    intro = """
<div style="position:absolute;left:880px;top:150px;width:940px">
  <div style="font:750 150px/1 Geist;letter-spacing:.12em">PROHORI</div>
  <div class=rule style="margin:34px 0 34px"></div>
  <div style="font:600 56px/1.2 Geist">Crack width in millimetres<br>from a phone photo</div>
</div>
<div style="position:absolute;left:880px;top:660px;width:900px;padding:22px 34px;border-left:8px solid var(--amber);
  background:#111c27cc;border-radius:0 18px 18px 0">
  <div style="font:750 54px/1.1 Geist">Hozaifa</div>
  <div style="font:500 34px/1.3 Geist;color:var(--muted);margin-top:8px">EEE, University of Dhaka &nbsp;&middot;&nbsp; solo entrant</div>
</div>"""
    outro = """
<div style="position:absolute;left:880px;top:200px;width:940px">
  <div class=tag>Prohori</div>
  <div class=rule style="margin:30px 0 40px"></div>
  <div style="font:750 78px/1.12 Geist">Prohori doesn't decide whether a building is safe.</div>
  <div style="font:750 78px/1.12 Geist;margin-top:34px;color:var(--amber)">That's an engineer's job.</div>
</div>"""
    outs = {}
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        for name, photo, html in [("face_intro", RAW / "face_intro.jpeg", intro), ("face_outro", RAW / "face_outro.jpeg", outro)]:
            pg.set_content(comp(photo, html), wait_until="load")
            pg.evaluate("document.fonts.ready")
            pg.wait_for_timeout(400)
            p = BUILD / f"{name}.png"
            pg.screenshot(path=str(p))
            outs[name] = p
        b.close()
    return outs


# ------------------------------------------------------------------------------------------------------ shot renderers
def smooth(u: float) -> float:
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


class Backdrop:
    """Bottom-padded canvas for scaled content: solid colour or the app vignette."""

    def __init__(self, color=None, image=None):
        self.img = image if image is not None else np.full((H, W, 3), color, np.uint8)


def fit_box(fit: float):
    bw, bh = W * fit, H * fit
    ox, oy = (W - bw) / 2, (6 if fit < 1 else 0)
    return bw, bh, ox, oy


class Still:
    def __init__(self, path: Path, fit: float, views, t0_out: float, dur: float, tm: TimeMap):
        img = cv2.imread(str(path), cv2.IMREAD_COLOR)
        assert img is not None, path
        self.img = img
        corners = np.concatenate([img[:12, :12].reshape(-1, 3), img[:12, -12:].reshape(-1, 3),
                                  img[-12:, :12].reshape(-1, 3), img[-12:, -12:].reshape(-1, 3)])
        self.bg = tuple(int(v) for v in np.median(corners, axis=0))
        self.fit, self.t0, self.dur = fit, t0_out, dur
        if views:
            self.keys = [(tm(t) - 0.0, np.array(r, np.float64)) for t, r in views]
        else:
            z = KB_ZOOM
            self.keys = [(t0_out, np.array([0, 0, W, H], np.float64)),
                         (t0_out + dur, np.array([W * z / 2, H * z / 2, W * (1 - z / 2), H * (1 - z / 2)], np.float64))]

    def rect_at(self, t: float) -> np.ndarray:
        ks = self.keys
        if t <= ks[0][0]:
            return ks[0][1]
        for (ta, ra), (tb, rb) in zip(ks, ks[1:]):
            if t <= tb:
                u = smooth((t - ta) / max(tb - ta, 1e-6))
                return ra + (rb - ra) * u
        return ks[-1][1]

    def frame(self, t: float) -> np.ndarray:
        x0, y0, x1, y1 = self.rect_at(t)
        bw, bh, ox, oy = fit_box(self.fit)
        s = bw / (x1 - x0)
        M = np.array([[s, 0, ox - x0 * s], [0, s, oy - y0 * s]], np.float64)
        out = cv2.warpAffine(self.img, M, (W, H), flags=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC,
                             borderMode=cv2.BORDER_CONSTANT, borderValue=self.bg)
        if self.fit < 1:   # zoomed windows must not spill outside the picture box (that area is kept free for captions)
            x0b, x1b, y0b, y1b = int(round(ox)), int(round(ox + bw)), int(round(oy)), int(round(oy + bh))
            out[:y0b] = self.bg
            out[y1b:] = self.bg
            out[:, :x0b] = self.bg
            out[:, x1b:] = self.bg
        return out


class Clip:
    def __init__(self, path: Path, tin: float, speed: float, fit: float, t0_out: float, bg: np.ndarray):
        self.path, self.tin, self.speed, self.fit, self.t0 = path, tin, speed, fit, t0_out
        self.cap = cv2.VideoCapture(str(path))
        self.n = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.pos = 0
        self.last = None
        self.bg = bg
        bw, bh, ox, oy = fit_box(fit)
        self.M = np.array([[fit, 0, ox], [0, fit, oy]], np.float64)
        mask = np.zeros((H, W), np.float32)
        x0, y0, x1, y1 = int(ox), int(oy), int(ox + bw), int(oy + bh)
        mask[y0:y1, x0:x1] = 1.0
        mask = cv2.GaussianBlur(mask, (0, 0), 14)
        self.mask = (mask[..., None])

    def frame(self, t: float) -> np.ndarray:
        idx = int(round((self.tin + max(t - self.t0, 0.0) * self.speed) * FPS))
        idx = min(max(idx, 0), self.n - 1)
        if idx != self.pos - 1 or self.last is None:
            if idx >= self.pos and idx - self.pos < 20:
                while self.pos < idx:
                    self.cap.grab()
                    self.pos += 1
            else:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                self.pos = idx
            ok, f = self.cap.read()
            self.pos += 1
            if not ok:
                f = self.last if self.last is not None else np.zeros((H, W, 3), np.uint8)
            self.last = f
        f = self.last
        if self.fit >= 1:
            return f
        sc = cv2.warpAffine(f, self.M, (W, H), flags=cv2.INTER_AREA, borderMode=cv2.BORDER_REPLICATE)
        out = sc.astype(np.float32) * self.mask + self.bg.astype(np.float32) * (1 - self.mask)
        return out.astype(np.uint8)


# ---------------------------------------------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snap", help="comma separated OUTPUT seconds; writes PNGs to the build dir, no encode")
    ap.add_argument("--audio-only", action="store_true")
    ap.add_argument("--crf", type=int, default=20)
    ap.add_argument("--preset", default="medium")
    args = ap.parse_args()

    BUILD.mkdir(parents=True, exist_ok=True)
    toks = apply_word_edits(load_tokens())
    mono = BUILD / "voice_mono.wav"
    if not mono.exists():
        run(["ffmpeg", "-v", "error", "-y", "-i", str(RAW / "voice.m4a"), "-ac", "1", "-ar", "48000",
             "-c:a", "pcm_f32le", str(mono)])
    x, sr = sf.read(str(mono), dtype="float32")
    db = frame_db(x, sr)
    refine_onsets(toks, db)
    # a shot that was planned on a sentence start follows that sentence's real speech onset
    for k, shot in enumerate(SHOTS):
        if k == 0:
            continue
        for t in toks:
            if shot["t"] - 0.05 <= t["start0"] <= shot["t"] + 0.4 and t["start"] > t["start0"] + 0.05:
                shot["t"] = round(t["start"] - 0.05, 2)
                break
    print("audio plan:")
    tm = plan_audio(toks, x, sr, db)
    total = tm(LAST_WORD_END) + HOLD_AFTER_VOICE
    print(f"output length {total:.2f}s ({int(total // 60)}:{total % 60:04.1f})")

    cues = retime_cues(build_cues(toks), tm, total)
    write_srt(cues)
    print(f"captions: {len(cues)} cues -> {OUT_SRT.name}")

    if not args.snap:
        wav = process_audio(tm, total)
        if args.audio_only:
            return
    faces = render_faces()

    # shots in output time
    starts = [tm(s["t"]) for s in SHOTS]
    starts[0] = 0.0
    ends = starts[1:] + [total]
    bgp = ASSETS / "tmp" / "bg_1080.png"
    clip_bg = cv2.imread(str(bgp)) if bgp.exists() else np.full((H, W, 3), (26, 18, 10), np.uint8)
    if clip_bg.shape[:2] != (H, W):
        clip_bg = cv2.resize(clip_bg, (W, H))
    objs = []
    for s, a, b in zip(SHOTS, starts, ends):
        if s["kind"] == "still":
            src = s["src"]
            path = faces[src[1:]] if src.startswith("@") else VID / src
            objs.append(Still(path, s["fit"], s.get("views"), a, b - a, tm))
        else:
            objs.append(Clip(VID / s["src"], s["in"], s["speed"], s["fit"], a, clip_bg))
    print("timeline (output seconds):")
    for s, a, b in zip(SHOTS, starts, ends):
        print(f"  {a:7.2f} - {b:7.2f}  {s['kind']:5s} {s['src']}" + (f"  in={s['in']}" if 'in' in s else ""))

    cap = CaptionRenderer()
    cue_starts = np.array([c["start"] for c in cues])

    def render(t: float) -> np.ndarray:
        # current shot index (a shot fades in over XFADE centred on its start)
        i = 0
        for k, a in enumerate(starts):
            if t >= a - XFADE / 2:
                i = k
        f = objs[i].frame(t)
        if i > 0:
            u = (t - (starts[i] - XFADE / 2)) / XFADE
            if u < 1.0:
                prev = objs[i - 1].frame(t)
                u = smooth(u)
                f = cv2.addWeighted(prev, 1 - u, f, u, 0)
        f = np.ascontiguousarray(f)
        j = int(np.searchsorted(cue_starts, t, side="right")) - 1
        if j >= 0 and t < cues[j]["end"]:
            cap.draw(f, j, cues[j]["lines"])
        return f

    nframes = int(round(total * FPS))
    if args.snap:
        for sv in args.snap.split(","):
            t = float(sv)
            p = BUILD / f"snap_{t:07.2f}.png"
            cv2.imwrite(str(p), render(t))
            print("snap", p)
        return

    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", str(wav), "-map", "0:v", "-map", "1:a",
           "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
           "-c:v", "libx264", "-preset", args.preset, "-crf", str(args.crf), "-profile:v", "high",
           "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
           "-r", str(FPS), "-movflags", "+faststart",
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-t", f"{total:.3f}", str(OUT_MP4)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for n in range(nframes):
        p.stdin.write(render(n / FPS).tobytes())
        if n % 300 == 0:
            print(f"  frame {n}/{nframes}", flush=True)
    p.stdin.close()
    p.wait()
    print("wrote", OUT_MP4, f"{OUT_MP4.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
