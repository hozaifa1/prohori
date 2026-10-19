"""Run the triage agent on handcrafted observations.

    python eval/agent_smoke.py          # rules policy only (offline)
    python eval/agent_smoke.py --live   # also the Bedrock LLM policy (needs AWS creds + model access)
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from prohori.agent import decide  # noqa: E402

GOOD = dict(corners=24, corners_total=24, blur_var=420.0, px_per_mm=17.0, obliquity_deg=8.0,
            glare_frac=0.0, crack_px_extent=900, image_w=4000, image_h=3000)
CRACKS = [{"id": "c1", "width_mm": 0.34, "uncertainty_mm": 0.06, "true_width_mm": 0.35,
           "length_mm": 80.0, "polyline_px": [[10, 10], [20, 30]]}]


def case(name, reasons, **kw):
    return name, {**GOOD, **kw}, {"certified": not reasons, "reasons": reasons}


CASES = [
    case("good capture", []),
    case("too far (6 px/mm)", ["low_resolution"], px_per_mm=6.0),
    case("blurry", ["blurry"], blur_var=35.0),
    case("glare", ["glare"], glare_frac=0.22),
    case("oblique (57 deg)", ["oblique"], obliquity_deg=57.0),
    case("glare + oblique, blur ok", ["glare", "oblique"], glare_frac=0.14, obliquity_deg=53.0, px_per_mm=9.5),
    case("board missing", ["too_few_corners"], corners=0, px_per_mm=None, obliquity_deg=None, blur_var=None),
]


def run(policy):
    print(f"\n=== policy: {policy} ===")
    print(f"{'case':26} {'action':32} {'ms':>7}  instruction")
    for name, o, g in CASES:
        r = decide(o, g, CRACKS, [], policy=policy)
        tag = "" if r["policy"] == policy else f" [fallback->{r['policy']}: {r['fallback_reason']}]"
        print(f"{name:26} {r['action']:32} {r['latency_ms']:7.0f}  {r['instruction']}{tag}")
        if policy == "llm" and r["policy"] == "llm":
            print(f"{'':26} model={r['model']} tokens={r['input_tokens']}/{r['output_tokens']}  why: {r['rationale']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="also run the Bedrock LLM policy")
    args = ap.parse_args()
    run("rules")
    if args.live:
        run("llm")
