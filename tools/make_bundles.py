"""Build the two release data bundles from the author's working directory (needs the git-ignored data/ and eval/runs/ trees).

    python tools/make_bundles.py OUT_DIR [--synth-dir C:/path/to/data/synth/v1]

Writes OUT_DIR/prohori-panel-data-v1.zip, OUT_DIR/prohori-agent-ablation-v1.zip and OUT_DIR/SHA256SUMS.txt.
Reproducible: entries are sorted and carry a fixed timestamp.  Judges do not need this script; they download the bundles.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

README_A = """PROHORI data bundle A: panel photos and calibration data (v1, 2026-10-26)
License: CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). Attribution: "PROHORI panel photos, Hozaifa, 2026".

Unpack at the repository root (the paths below are relative to it):
  unzip prohori-panel-data-v1.zip

Contents
  data/raw/IMG2026101908*.jpg        29 phone photos (realme C75) of the printed test panel data/print/PRINT_ME_test_panel_A4.pdf,
                                     12 MP, original EXIF orientation kept. No people (checked with the YuNet face detector), no GPS tags.
  data/gatecal/manifest_shipped.jsonl, rows_shipped.parquet
                                     gate calibration set measured with the shipped estimator (2,584 degraded captures of 21 source-photo
                                     groups; eval/gate_make_dataset.py --cfg shipped). Enough for `gate_make_dataset.py --table-only`.
  data/gatecal/manifest.jsonl, rows.parquet
                                     the same set measured with the legacy estimator (the 2026-10-19 gate), for the old-vs-new comparison.
  eval/runs/width_autoresearch/      split.json (frozen tune/test split), toner_bleed.json, best.json, log.tsv (the autoresearch log)
  data/synth/v1/config.json          generator configuration of the 500 synthetic renders (python -m prohori.synth --n 500 --seed 0)
  data/synth/v1/synth_render_sha256.txt
                                     sha256 of each of the 500 renders as produced on the author's machine. The renders themselves are NOT
                                     included (1.1 GB; they are built from third-party textures and crack masks that are not redistributed).
                                     A regenerated render is expected to match only on the same OpenCV / numpy / libjpeg build.

Not included: third-party datasets (see README, "Acknowledgements and citations"), the krkCMd profile caches, pickled caches.
"""

README_B = """PROHORI data bundle B: triage-agent ablation runs (v1, 2026-10-26)
License: CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). Attribution: "PROHORI agent ablation runs, Hozaifa, 2026".

Unpack at the repository root:
  unzip prohori-agent-ablation-v1.zip

Contents: eval/runs/agent_ablation/ (episode logs of policies P0 random, P1 rules, P* label rule and P2 LLM per split, llm_ledger.jsonl with
every Bedrock call and its token counts, freeze.json with the pre-registration hashes, prompts/v0-v2.txt).
Regenerate the report from these files:    python eval/agent_ablation.py report
Re-run the free policies (no model calls): python eval/agent_ablation.py run --split test --policies p0,p1,pstar
The LLM runs (P2) need Amazon Bedrock access to us.amazon.nova-lite-v1:0 and cost about $0.06 in total; the stored logs are the record of
what the model answered.
"""


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def add(z: zipfile.ZipFile, arc: str, data: bytes) -> None:
    zi = zipfile.ZipInfo(arc, date_time=(2026, 10, 26, 0, 0, 0))
    zi.compress_type = zipfile.ZIP_DEFLATED
    zi.external_attr = 0o644 << 16
    z.writestr(zi, data)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--synth-dir", default=str(ROOT / "data" / "synth" / "v1"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    synth = Path(a.synth_dir)
    sums = []

    hashes = "".join(f"{sha256(p)}  data/synth/v1/{p.name}\n" for p in sorted(synth.glob("synth_*.jpg")))
    pa = out / "prohori-panel-data-v1.zip"
    with zipfile.ZipFile(pa, "w") as z:
        add(z, "BUNDLE_README.txt", README_A.encode())
        for p in sorted((ROOT / "data" / "raw").glob("*.jpg")):
            add(z, f"data/raw/{p.name}", p.read_bytes())
        for f in ("manifest_shipped.jsonl", "rows_shipped.parquet", "manifest.jsonl", "rows.parquet"):
            add(z, f"data/gatecal/{f}", (ROOT / "data" / "gatecal" / f).read_bytes())
        for f in ("split.json", "toner_bleed.json", "best.json", "log.tsv"):
            add(z, f"eval/runs/width_autoresearch/{f}", (ROOT / "eval" / "runs" / "width_autoresearch" / f).read_bytes())
        add(z, "data/synth/v1/config.json", (synth / "config.json").read_bytes())
        add(z, "data/synth/v1/synth_render_sha256.txt", hashes.encode())

    pb = out / "prohori-agent-ablation-v1.zip"
    base = ROOT / "eval" / "runs" / "agent_ablation"
    with zipfile.ZipFile(pb, "w") as z:
        add(z, "BUNDLE_README.txt", README_B.encode())
        for p in sorted(base.rglob("*")):
            if p.is_file():
                add(z, "eval/runs/agent_ablation/" + p.relative_to(base).as_posix(), p.read_bytes())

    with open(out / "SHA256SUMS.txt", "w", newline="\n") as f:
        for p in (pa, pb):
            line = f"{sha256(p)}  {p.name}"
            f.write(line + "\n")
            print(line, p.stat().st_size, "bytes")


if __name__ == "__main__":
    sys.exit(main())
