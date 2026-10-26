"""P0 / P1 / P2 triage-agent ablation on the simulated capture episodes.

Pre-registration: research/AGENT_PREREG.md.  Simulator: src/prohori/episodes.py.

    # free policies (no model calls)
    python eval/agent_ablation.py run --split dev  --policies p0,p1,pstar
    python eval/agent_ablation.py run --split test --policies p0,p1,pstar
    python eval/agent_ablation.py run --split big  --policies p0,p1,pstar

    # LLM policy (Bedrock, Nova Lite).  Counts every call in eval/runs/agent_ablation/llm_ledger.jsonl
    python eval/agent_ablation.py run --split dev  --policies p2 --n 20 --tag dev_v0
    python eval/agent_ablation.py run --split test --policies p2 --tag test_final

    # Addendum B (research/AGENT_PREREG.md): guardrail variants, prompt v2 of the legacy gate, one run each
    python eval/agent_ablation.py run --split dev  --policies p2g --n 20 --tag p2g_devfmt     # format check only
    python eval/agent_ablation.py run --split test --policies p2g,p3 --workers 3

    python eval/agent_ablation.py probe-claude         # ONE call to the Claude model, for availability
    python eval/agent_ablation.py report               # md + csv + figure from the run files

Traces (full observation -> action -> instruction per step) go to eval/runs/agent_ablation/ (gitignored).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import inspect
import json
import math
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

RUNS = ROOT / "eval" / "runs" / "agent_ablation"
RESULTS = ROOT / "eval" / "results"
LEDGER = RUNS / "llm_ledger.jsonl"
PREREG = ROOT / "research" / "AGENT_PREREG.md"

# Private counter directory so other agents' calls cannot trip the local daily cap; cap raised as instructed.
os.environ["PROHORI_LLM_DAILY_CAP"] = "1000"
os.environ["PROHORI_DATA_DIR"] = str(RUNS / "cap_counter")
NOVA = "us.amazon.nova-lite-v1:0"
HAIKU45 = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
CLAUDE_PROBE = "us.anthropic.claude-haiku-5-5"
os.environ["PROHORI_BEDROCK_MODEL"] = NOVA
os.environ["PROHORI_BEDROCK_FALLBACK_MODELS"] = ""   # no hidden second model
os.environ["PROHORI_AWS_REGION"] = "us-east-1"
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")  # the `aws login` credential provider needs a region to refresh

import numpy as np  # noqa: E402

from prohori import agent, episodes as E  # noqa: E402

TOTAL_CALL_CAP = 600                 # section 8 budget (P2, closed)
ADD_B_CALL_CAP, ADD_B_USD_CAP = 1500, 5.0   # Addendum B.6 budget (tags starting p2g / p3)
ADD_B_TAGS = ("p2g", "p3")
PRICE_IN, PRICE_OUT = 0.06 / 1e6, 0.24 / 1e6   # Nova Lite
PRICES = {NOVA: (0.06 / 1e6, 0.24 / 1e6), HAIKU45: (1.0 / 1e6, 5.0 / 1e6)}   # USD per token (in, out)
V2_PROMPT = ROOT / "research" / "prompts" / "agent_prompt_v2_legacy_gate.txt"
POLICY_MODEL = {"p2": NOVA, "p2g": NOVA, "p3": HAIKU45}
LLM_POLICIES = tuple(POLICY_MODEL)
BOOT_B, BOOT_SEED = 10000, 20261019


class BudgetExhausted(BaseException):
    """BaseException on purpose: agent.decide() catches Exception and would silently fall back to rules."""


# --------------------------------------------------------------------------- ledger + counting client proxy
_ledger_lock = threading.Lock()


def ledger_rows() -> list[dict]:
    if not LEDGER.exists():
        return []
    return [json.loads(x) for x in LEDGER.read_text(encoding="utf-8").splitlines() if x.strip()]


def _is_add_b(tag: str) -> bool:
    return str(tag).startswith(ADD_B_TAGS)


def calls_used(add_b: bool = False) -> int:
    """Model calls started. add_b=False: the section 8 budget (everything that is not an Addendum B tag)."""
    return sum(1 for r in ledger_rows() if r.get("kind") == "start" and _is_add_b(r.get("tag")) == add_b)


def usd_of(rows) -> float:
    t = 0.0
    for r in rows:
        if r.get("kind") == "done" and r.get("ok"):
            pi, po = PRICES.get(r.get("model"), PRICES[NOVA])
            t += (r.get("in") or 0) * pi + (r.get("out") or 0) * po
    return t


class CountingClient:
    def __init__(self, inner, tag: str, cap: int | None = None):
        self.inner, self.tag = inner, tag
        self.add_b = _is_add_b(tag)
        self.cap = cap if cap is not None else (ADD_B_CALL_CAP if self.add_b else TOTAL_CALL_CAP)

    def converse(self, **kw):
        with _ledger_lock:
            if calls_used(self.add_b) >= self.cap:
                raise BudgetExhausted(f"model-call budget of {self.cap} reached")
            if self.add_b and usd_of([r for r in ledger_rows() if _is_add_b(r.get("tag"))]) >= ADD_B_USD_CAP:
                raise BudgetExhausted(f"dollar budget of {ADD_B_USD_CAP} reached")
            RUNS.mkdir(parents=True, exist_ok=True)
            with open(LEDGER, "a", encoding="utf-8") as f:
                f.write(json.dumps({"kind": "start", "ts": time.time(), "tag": self.tag, "model": kw.get("modelId")}) + "\n")
        t0 = time.perf_counter()
        try:
            resp = self.inner.converse(**kw)
        except Exception as e:
            with _ledger_lock, open(LEDGER, "a", encoding="utf-8") as f:
                f.write(json.dumps({"kind": "done", "ts": time.time(), "tag": self.tag, "model": kw.get("modelId"),
                                    "ok": False, "error": f"{type(e).__name__}: {e}"[:200]}) + "\n")
            raise
        u = resp.get("usage") or {}
        with _ledger_lock, open(LEDGER, "a", encoding="utf-8") as f:
            f.write(json.dumps({"kind": "done", "ts": time.time(), "tag": self.tag, "model": kw.get("modelId"), "ok": True,
                                "in": u.get("inputTokens"), "out": u.get("outputTokens"),
                                "ms": round((time.perf_counter() - t0) * 1000)}) + "\n")
        return resp


_REAL_GET_CLIENT = agent._get_client


def install_counting_client(tag: str) -> None:
    real = _REAL_GET_CLIENT()
    agent._get_client = lambda: CountingClient(real, tag)  # type: ignore[assignment]


def ledger_summary() -> dict:
    rows = ledger_rows()
    started = [r for r in rows if r["kind"] == "start"]
    done = [r for r in rows if r["kind"] == "done"]
    ok = [r for r in done if r.get("ok")]
    tin = sum(r.get("in") or 0 for r in ok)
    tout = sum(r.get("out") or 0 for r in ok)
    by_tag: dict = {}
    for r in started:
        by_tag.setdefault(r["tag"], {"calls": 0, "in": 0, "out": 0, "errors": 0})["calls"] += 1
    for r in done:
        d = by_tag.setdefault(r["tag"], {"calls": 0, "in": 0, "out": 0, "errors": 0})
        if r.get("ok"):
            d["in"] += r.get("in") or 0
            d["out"] += r.get("out") or 0
        else:
            d["errors"] += 1
    for r in done:
        if r.get("ok"):
            pi, po = PRICES.get(r.get("model"), PRICES[NOVA])
            by_tag[r["tag"]]["usd"] = by_tag[r["tag"]].get("usd", 0.0) + (r.get("in") or 0) * pi + (r.get("out") or 0) * po
            by_tag[r["tag"]].setdefault("ms", []).append(r.get("ms") or 0)
        by_tag[r["tag"]]["model"] = r.get("model")
    for d in by_tag.values():
        d.setdefault("usd", 0.0)
    return {"calls": len(started), "errors": len(done) - len(ok), "in": tin, "out": tout,
            "usd": usd_of(rows), "by_tag": by_tag,
            "calls_b": sum(1 for r in started if _is_add_b(r["tag"])), "usd_b": usd_of([r for r in rows if _is_add_b(r.get("tag"))])}


# --------------------------------------------------------------------------- policies
def fingerprint_p1() -> str:
    parts = [inspect.getsource(getattr(agent, n)) for n in
             ("_failures", "_board_missing", "_rule_text", "_marginal", "rules_decide", "_rules",
              "failed_attempts", "_last_actions")]
    parts.append(json.dumps([agent.MAX_FAILED_ATTEMPTS, agent.MARGINAL_FACTOR], sort_keys=True))
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def prompt_fingerprint() -> str:
    return hashlib.sha256((agent.SYSTEM_PROMPT + json.dumps(agent.TOOL_CONFIG, sort_keys=True)).encode()).hexdigest()


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def make_policy(name: str, seed: int):
    if name == "p0":
        return lambda o, g, c, h: agent.random_decide(o, g, c, h, seed=seed)
    if name == "p1":
        return lambda o, g, c, h: agent.rules_decide(o, g, c, h)
    if name == "pstar":
        return lambda o, g, c, h: E.oracle_decide(o, g, c, h)
    if name == "p2":      # as run on 2026-10-19: Nova Lite, prompt v2, no guardrail
        return lambda o, g, c, h: agent.decide(o, g, c, h, policy="llm", guardrail=False)
    if name in ("p2g", "p3"):
        return lambda o, g, c, h: agent.decide(o, g, c, h, policy="llm", guardrail=True)
    raise ValueError(name)


def use_llm_config(policy: str) -> None:
    """Pin the model and the legacy-gate prompt v2 (the prompt the P2 test run used) for an LLM policy."""
    os.environ["PROHORI_BEDROCK_MODEL"] = POLICY_MODEL[policy]
    os.environ["PROHORI_BEDROCK_FALLBACK_MODELS"] = ""
    agent.SYSTEM_PROMPT = V2_PROMPT.read_text(encoding="utf-8")


def run_split(split: str, policy: str, n: int | None, tag: str, workers: int) -> Path:
    eps = E.split_episodes(split, n)
    out = RUNS / (f"{tag}.jsonl" if tag.startswith(split + "_") else f"{split}_{tag}.jsonl")
    T = dict(agent.GATE_THRESHOLDS)

    def one(e):
        seed, klass = e
        tr = E.run_episode(seed, klass, make_policy(policy, seed), T)
        tr["policy"] = policy
        return tr

    RUNS.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    if policy in LLM_POLICIES:
        use_llm_config(policy)
        install_counting_client(tag)
        with ThreadPoolExecutor(workers) as ex:
            traces = list(ex.map(one, eps))
    else:
        traces = [one(e) for e in eps]
    meta = {"kind": "meta", "split": split, "policy": policy, "tag": tag, "n": len(eps), "thresholds": T,
            "prereg_sha256": sha256_file(PREREG), "episodes_py_sha256": sha256_file(ROOT / "src" / "prohori" / "episodes.py"),
            "p1_fingerprint": fingerprint_p1(), "prompt_fingerprint": prompt_fingerprint(),
            "model": os.environ["PROHORI_BEDROCK_MODEL"] if policy in LLM_POLICIES else None, "seconds": round(time.time() - t0, 1),
            "git_head": _git_head(), "guardrail": policy in ("p2g", "p3"),
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
    with open(out, "w", encoding="utf-8") as f:
        f.write(json.dumps(meta) + "\n")
        for tr in traces:
            f.write(json.dumps(tr) + "\n")
    return out


def _git_head() -> str:
    import subprocess
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return "unknown"


def load_run(path: Path) -> tuple[dict, list[dict]]:
    lines = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    return lines[0], lines[1:]


# --------------------------------------------------------------------------- metrics
_REASON_ACTION = E._REASON_ACTION
SUBSETS = {
    "single (S)": lambda k: k == "S",
    "compound (X+C2+C3)": lambda k: k in E.COMPOUND,
    "recoverable (S+X+C2+C3)": lambda k: k in E.RECOVERABLE,
    "hopeless (H)": lambda k: k == "H",
    "constrained (M)": lambda k: k == "M",
    "all": lambda k: True,
}


def episode_stats(tr: dict) -> dict:
    k = tr["class"]
    cert = tr["outcome"] == "certified"
    d = {"class": k, "seed": tr["seed"], "rec3": float(cert and tr["outcome_idx"] <= E.K_PRIMARY), "rec6": float(cert),
         "turns": float(tr["outcome_idx"]) if cert else float("nan"),
         "usable3": float((cert or tr["outcome"] == "widened") and tr["outcome_idx"] <= E.K_PRIMARY),
         "correct_outcome": float(tr["outcome"] == E.CORRECT_TERMINAL[k]),
         "abandoned": float(tr["outcome"] == "abandoned"), "widened": float(tr["outcome"] == "widened"),
         "dec": 0, "strict": 0, "accept_ok": 0, "addr": 0, "fallbacks": 0, "llm_steps": 0,
         "esc_pred": 0, "esc_pos": 0, "esc_tp": 0, "instr_n": 0, "instr_len": 0, "instr_num": 0, "instr_cons": 0,
         "faithful": 0, "instr_viol": 0, "instr_nonum": 0, "rule_viol": 0, "g_n": 0, "g_first": 0, "g_reask": 0, "g_fixed": 0, "g_repaired": 0,
         "g_rejected": 0, "g_rationale": 0, "calls": 0, "lat_ms": []}
    hist: list[dict] = []
    for s in tr["steps"]:
        if "action" not in s:
            continue
        h_before = list(hist)
        hist.append({"observation": s["observation"], "gate": s["gate"], "cracks": s["cracks"], "decision": s["decision"]})
        a, A, prim = s["action"], set(s["label_A"]), s["label_primary"]
        d["dec"] += 1
        d["strict"] += int(a == prim)
        d["accept_ok"] += int(a in A)
        reasons = s["gate"].get("reasons") or []
        d["addr"] += int(a in A or a in {_REASON_ACTION.get(r) for r in reasons})
        pos = A == {"abandon_and_log"}
        d["esc_pred"] += int(a == "abandon_and_log")
        d["esc_pos"] += int(pos)
        d["esc_tp"] += int(pos and a == "abandon_and_log")
        dec = s["decision"]
        if dec.get("policy") == "llm":
            d["llm_steps"] += 1
        if dec.get("fallback_reason"):
            d["fallbacks"] += 1
        ins = dec.get("instruction") or ""
        # Addendum B: validator-based metrics, applied identically to every policy's final output
        av = agent.check_action(a, s["observation"], s["gate"], s["cracks"], h_before)
        iv, st_ = agent.check_instruction(a, ins, s["observation"], s["gate"], s["cracks"], h_before)
        d["rule_viol"] += int(bool(av))
        wrong = [x for x in iv if not x.startswith("cites no measured number")]
        d["instr_viol"] += int(bool(wrong))
        d["instr_nonum"] += int(st_["measured"] == 0)
        d["faithful"] += int((not iv) and st_["measured"] >= 1)
        gr = dec.get("guardrail")
        if gr is not None:
            d["g_n"] += 1
            d["g_first"] += int(bool(gr.get("violations")))
            d["g_reask"] += int(bool(gr.get("reask")))
            d["g_fixed"] += int(bool(gr.get("reask")) and not gr.get("final_violations") and not gr.get("action_rejected"))
            d["g_repaired"] += int(bool(gr.get("repaired")))
            d["g_rejected"] += int(bool(gr.get("action_rejected")))
            d["g_rationale"] += int(bool(gr.get("rationale_withheld")))
        if dec.get("policy") == "llm" or gr is not None:
            d["calls"] += int(dec.get("llm_calls") or 1)
            if dec.get("latency_ms") is not None:
                d["lat_ms"].append(float(dec["latency_ms"]))
        d["instr_n"] += 1
        d["instr_len"] += int(0 < len(ins) <= 140)
        d["instr_num"] += int(bool(re.search(r"\d", ins)))
        d["instr_cons"] += int(bool(_CONSIST[a].search(ins)))
    return d


_CONSIST = {
    "move_closer": re.compile(r"closer|nearer|approach|forward|step in", re.I),
    "reshoot_steadier": re.compile(r"steady|still|brace|blur|sharp|focus|hold|shake", re.I),
    "relight": re.compile(r"glare|light|shade|tilt|reflect|flash|angle|shadow", re.I),
    "reposition_marker": re.compile(r"board|square|angle|frame|position|centre|center|whole|marker|crack|wall|retake", re.I),
    "accept": re.compile(r"certif|accept|next|good|done", re.I),
    "accept_with_widened_uncertainty": re.compile(r"widen|error bar|close enough|accept|keep|uncertain", re.I),
    "abandon_and_log": re.compile(r"log|stop|give up|abandon|not measurable|cannot|can't|skip|unable", re.I),
}


_IDX_CACHE: dict = {}


def _idx(n: int, rng: np.random.Generator, B: int = BOOT_B) -> np.ndarray:
    """Bootstrap index matrix (B x n), cached per n so every metric in a table shares resamples."""
    key = (n, id(rng))
    if key not in _IDX_CACHE:
        _IDX_CACHE[key] = rng.integers(0, n, (B, n))
    return _IDX_CACHE[key]


def boot_ratio(num: np.ndarray, den: np.ndarray | None, rng: np.random.Generator):
    """Percentile bootstrap over episodes of sum(num)/sum(den) (or mean(num) if den is None)."""
    n = len(num)
    den = np.ones(n) if den is None else den
    if den.sum() == 0:
        return float("nan"), float("nan"), float("nan")
    I = _idx(n, rng)
    d = den[I].sum(1)
    with np.errstate(invalid="ignore", divide="ignore"):
        bs = num[I].sum(1) / d
    bs = bs[d > 0]
    return float(num.sum() / den.sum()), float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))


def boot_nan_stat(t: np.ndarray, fn, rng: np.random.Generator):
    """Bootstrap of a statistic over the non-NaN entries of t (resampling all episodes)."""
    n = len(t)
    I = _idx(n, rng)
    M = t[I]
    with np.errstate(all="ignore"):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            bs = fn(M, axis=1)
    bs = bs[~np.isnan(bs)]
    return float(fn(t[~np.isnan(t)])), float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))


def _ratio(num, den):  # kept for the report code that builds ratios directly
    return None


def summarize(stats_by_policy: dict[str, list[dict]]) -> list[dict]:
    """Rows: policy, subset, metric, estimate, lo, hi, n."""
    rows = []
    rng = np.random.default_rng(BOOT_SEED)
    nan = float("nan")
    for pol, stats in stats_by_policy.items():
        for sname, sel in SUBSETS.items():
            sub = [s for s in stats if sel(s["class"])]
            n = len(sub)
            if n == 0:
                continue
            arr = lambda key: np.array([s[key] for s in sub], float)  # noqa: E731
            for metric, key in (("recovery@3", "rec3"), ("recovery@6", "rec6"), ("correct_outcome", "correct_outcome"),
                                ("abandon_rate", "abandoned"), ("widen_rate", "widened")):
                est, lo, hi = boot_ratio(arr(key), None, rng)
                rows.append(dict(policy=pol, subset=sname, metric=metric, estimate=est, lo=lo, hi=hi, n=n))
            t = arr("turns")
            for metric, fn in (("turns_to_certified_median", np.nanmedian), ("turns_to_certified_mean", np.nanmean)):
                if np.isnan(t).all():
                    rows.append(dict(policy=pol, subset=sname, metric=metric, estimate=nan, lo=nan, hi=nan, n=n))
                    continue
                est, lo, hi = boot_nan_stat(t, fn, rng)
                rows.append(dict(policy=pol, subset=sname, metric=metric, estimate=est, lo=lo, hi=hi, n=int((~np.isnan(t)).sum())))
            dec = arr("dec")
            if dec.sum() > 0:
                for metric, key in (("action_acc_acceptable", "accept_ok"), ("action_acc_strict", "strict"), ("addresses_a_failure", "addr")):
                    est, lo, hi = boot_ratio(arr(key), dec, rng)
                    rows.append(dict(policy=pol, subset=sname, metric=metric, estimate=est, lo=lo, hi=hi, n=int(dec.sum())))
                est, lo, hi = boot_ratio(arr("accept_ok"), dec, rng)
                rows.append(dict(policy=pol, subset=sname, metric="wrong_action_rate", estimate=1 - est, lo=1 - hi, hi=1 - lo, n=int(dec.sum())))
            pred, pos, tp = arr("esc_pred"), arr("esc_pos"), arr("esc_tp")
            for metric, den in (("escalation_precision_vs_rule", pred), ("escalation_recall_vs_rule", pos)):
                est, lo, hi = boot_ratio(tp, den, rng)
                rows.append(dict(policy=pol, subset=sname, metric=metric, estimate=est, lo=lo, hi=hi, n=int(den.sum())))
            # post-hoc (not pre-registered): a usable result of any kind (certified, or widened with a crack measured) within 3 actions
            rows.append(dict(policy=pol, subset=sname, metric="usable@3_posthoc", n=n,
                             **dict(zip(("estimate", "lo", "hi"), boot_ratio(arr("usable3"), None, rng)))))
        ab = np.array([s["abandoned"] for s in stats], float)
        hl = np.array([float(s["class"] == "H") for s in stats])
        rc = np.array([float(s["class"] in E.RECOVERABLE) for s in stats])
        for metric, num, den in (("escalation_precision_vs_truth", ab * hl, ab), ("escalation_recall_vs_truth", ab * hl, hl),
                                 ("false_abandon_of_recoverable", ab * rc, rc)):
            est, lo, hi = boot_ratio(num, den, rng)
            rows.append(dict(policy=pol, subset="all", metric=metric, estimate=est, lo=lo, hi=hi, n=int(den.sum())))
        ins_n = sum(s["instr_n"] for s in stats)
        if ins_n:
            den = np.array([s["instr_n"] for s in stats], float)
            for metric, key in (("instr_within_140", "instr_len"), ("instr_cites_number", "instr_num"), ("instr_matches_action", "instr_cons")):
                est, lo, hi = boot_ratio(np.array([s[key] for s in stats], float), den, rng)
                rows.append(dict(policy=pol, subset="all", metric=metric, estimate=est, lo=lo, hi=hi, n=ins_n))
        dn = np.array([s["dec"] for s in stats], float)
        if dn.sum() > 0:
            for metric, key in (("instr_faithful", "faithful"), ("instr_violation_rate", "instr_viol"), ("instr_no_measured_number", "instr_nonum"), ("rule_violation_rate", "rule_viol")):
                est, lo, hi = boot_ratio(np.array([s[key] for s in stats], float), dn, rng)
                rows.append(dict(policy=pol, subset="all", metric=metric, estimate=est, lo=lo, hi=hi, n=int(dn.sum())))
        gn = np.array([s["g_n"] for s in stats], float)
        if gn.sum() > 0:
            for metric, key in (("guard_first_pass_violation", "g_first"), ("guard_reask", "g_reask"), ("guard_fixed_by_reask", "g_fixed"),
                                ("guard_repaired", "g_repaired"), ("guard_action_rejected", "g_rejected"), ("guard_rationale_withheld", "g_rationale")):
                est, lo, hi = boot_ratio(np.array([s[key] for s in stats], float), gn, rng)
                rows.append(dict(policy=pol, subset="all", metric=metric, estimate=est, lo=lo, hi=hi, n=int(gn.sum())))
        rows.append(dict(policy=pol, subset="all", metric="fallback_steps", estimate=float(sum(s["fallbacks"] for s in stats)),
                         lo=nan, hi=nan, n=int(sum(s["dec"] for s in stats))))
    return rows


def paired_diff(a: list[dict], b: list[dict], subset: str, key: str = "rec3"):
    """mean(a - b) over matched episodes in a subset, with a paired bootstrap CI."""
    sel = SUBSETS[subset]
    bm = {s["seed"]: s for s in b}
    d = np.array([s[key] - bm[s["seed"]][key] for s in a if sel(s["class"]) and s["seed"] in bm], float)
    rng = np.random.default_rng(BOOT_SEED + 1)
    est, lo, hi = boot_ratio(d, None, rng)
    return est, lo, hi, len(d)


# --------------------------------------------------------------------------- CLI: run / probe
def cmd_run(a):
    pols = [p.strip() for p in a.policies.split(",") if p.strip()]
    for pol in pols:
        tag = a.tag or pol
        if pol == "p2" and not a.tag:
            sys.exit("--tag is required for p2 (it labels the ledger rows)")
        if pol in LLM_POLICIES:
            ls0 = ledger_summary()
            print(f"[budget] section 8: {calls_used()}/{TOTAL_CALL_CAP} calls; addendum B: {ls0['calls_b']}/{ADD_B_CALL_CAP} calls, ${ls0['usd_b']:.4f}/${ADD_B_USD_CAP}", flush=True)
        path = run_split(a.split, pol, a.n, tag if pol == "p2" else (a.tag or pol), a.workers)
        meta, trs = load_run(path)
        st = [episode_stats(t) for t in trs]
        comp = [s for s in st if s["class"] in E.COMPOUND]
        print(f"{path.name}: n={len(trs)} recovery@3 all-recoverable="
              f"{np.mean([s['rec3'] for s in st if s['class'] in E.RECOVERABLE]):.3f} compound={np.mean([s['rec3'] for s in comp]):.3f} "
              f"decisions={sum(s['dec'] for s in st)} fallbacks={sum(s['fallbacks'] for s in st)} ({meta['seconds']}s)", flush=True)
        if pol in LLM_POLICIES:
            ls = ledger_summary()
            print(f"[budget] addendum B: {ls['calls_b']}/{ADD_B_CALL_CAP} calls, ${ls['usd_b']:.4f}/${ADD_B_USD_CAP}", flush=True)
            reasons = {}
            for t in trs:
                for s_ in t["steps"]:
                    fr = (s_.get("decision") or {}).get("fallback_reason")
                    if fr:
                        reasons[fr[:80]] = reasons.get(fr[:80], 0) + 1
            if reasons:
                print("[fallbacks]", json.dumps(reasons), flush=True)


def cmd_probe(a):
    install_counting_client("probe_claude")
    obs = dict(corners=24, corners_total=24, blur_var=420.0, px_per_mm=6.0, obliquity_deg=8.0, glare_frac=0.0,
               crack_px_extent=480, image_w=4000, image_h=3000)
    gate = {"certified": False, "reasons": ["low_resolution"]}
    t0 = time.perf_counter()
    try:
        resp = agent._get_client().converse(
            modelId=CLAUDE_PROBE, system=[{"text": agent.SYSTEM_PROMPT}],
            messages=[{"role": "user", "content": [{"text": json.dumps(agent.build_user_payload(obs, gate, [], []), separators=(",", ":"))}]}],
            inferenceConfig={"maxTokens": 400, "temperature": 0.0}, toolConfig=agent.TOOL_CONFIG)
        args, it, ot = agent._extract_tool_use(resp)
        print(json.dumps({"claude_probe": "ok", "model": CLAUDE_PROBE, "action": args.get("action"), "tokens": [it, ot],
                          "ms": round((time.perf_counter() - t0) * 1000)}))
    except Exception as e:
        code = getattr(e, "response", {}).get("Error", {}).get("Code") if hasattr(e, "response") else None
        print(json.dumps({"claude_probe": "failed", "model": CLAUDE_PROBE, "code": code, "error": f"{type(e).__name__}: {e}"[:400]}))


# --------------------------------------------------------------------------- report
INTERPRETATION = """**Verdict on the pre-registered criterion.** On the compound subset P2 beat P1 by +22.9 points of recovery within 3 actions (95% CI +8.3 to +37.5, n = 48 episodes). The point estimate clears the +10 bar; the lower end of the interval does not, so at the stated precision the bar is not demonstrated. On single-cause failures the difference is +5.0 [0, +15], inside the pre-registered "|diff| < 10" expectation, though the interval touches its limit.

**Why P2 won, and why that is weaker than it looks.**
1. P2's final prompt was written with the dev traces in front of us. It contains explicit ordering rules (tilt before everything else, glare first only when it is hiding the board, a try-reposition-then-relight chain when the board is lost) and deterministic helper numbers (`failing_checks`, `widen_now_allowed`, `abandon_now_allowed`). These match the labelling rule, which was written from the same reasoning as the simulator. P1 received no tuning (frozen by pre-registration).
2. P*, the label rule written as plain code, reaches 88% on compound (P2: 85%, intervals overlap almost entirely). The secondary 1,000-episode run puts P* above P1 by +10.0 points [+6.5, +13.5] on compound episodes. **So the P2 gain over P1 is about what a tuned if/else cascade also gets. This run does not show that an LLM reasons better than a well-tuned rule set; it shows that an LLM following a written rule set recovers about as well as that rule set in code, and better than the shipped P1.** Nova Lite does not reach the ceiling by following the rules faithfully: its action matches the label set 73% of the time on compound states (P* 100%, P1 69%), and it often fixes blur before tilt.
3. P1 loses mostly by giving up too often: it abandons 33% of compound episodes (P2 15%, P*  6%) because its fixed priority order spends attempts in the wrong order, and the product rule abandons on the fourth failed capture. Wrong order costs attempts only when the simulator's coupling bites (a reposition re-rolls glare and shake half the time). That coupling is our assumption.
4. P2 never chose `accept_with_widened_uncertainty` on a recoverable episode (0%) although the helper flag allowed it. It kept retrying, which in this simulator usually works. This helps its recovery number and departs from the written rule. It did choose it correctly on 15 of 16 constrained episodes.

**What matched the pre-registered expectation.** P0 is far below everything (sanity check passed). P1 and P2 both catch every hopeless episode (escalation recall 100% against truth); P1's escalation precision against truth is only 47% because it also abandons a quarter of the recoverable episodes.

**Weaknesses of P2 visible here.** Only 57% of its instructions cite a number from the observation (P1: 91%), against its own prompt's instruction. The instruction checklist is automated; the human 1 to 5 rating is not done. Earlier prompt versions showed Nova Lite miscounting attempts and misreading thresholds (calling a blur_var of 313 blurry), which is why the helper fields exist.

**Prompt iteration on the dev-LLM set (20 episodes, 14 recoverable, the same episodes reused for every version; selection rule from the pre-registration).**

| version | change | recovery@3 recoverable | recovery@3 compound | action accuracy (in label set) | calls |
|---|---|---|---|---|---|
| v0 | prompt as in the repository before this work | 79% | 73% | 57% | 56 |
| v1 | observation semantics (zeros mean "not measured" when the board is lost), derived `failing_checks`, abandon/widen precedence | 71% | 64% | 65% | 49 |
| v2 | ordering rules, lost-board chain, `widen_now_allowed` / `abandon_now_allowed` flags | **100%** | **100%** | 82% | 50 |
| reference on the same 20 episodes | P1 / P* | 64% / 79% | 55% / 73% | 84% / 100% | free |

v2 was selected and run once on the held-out split. Dev results are noisy at n = 20, and the 100% is almost certainly optimistic (held-out compound: 85%).

**Other limits.** About 100 held-out episodes, one cheap model, one annotator, a simulator whose glare, severe tilt and low-resolution distributions are assumptions (the real panel has none of them), and a perfectly cooperative operator model. `recovery@6` equals `recovery@3` for P1, P2 and P* because all three abandon at the fourth failed capture. The simulator takes the gate thresholds from `agent.GATE_THRESHOLDS` (the hand-set values); a refit gate will change the numbers. P2 ran on Nova Lite, not the production default model in `agent.py`. A usable-result metric (`usable@3_posthoc`, certified or widened within 3 actions) is in the CSV; it was added after seeing the results and is not part of the pre-registration.
"""


INTERPRETATION_B = """**P3 (Claude Haiku 4.5) was not run.** Bedrock refused every call with `ResourceNotFoundException: Model use case details have not been submitted for this account`, for the `us.` and the `global.` Haiku 4.5 profiles. That is an Anthropic form that only the account owner can submit. The 50 dev-format decisions all fell back to the rules policy (ledger tag `p3_devfmt`, 0 USD). So the pre-registered live-default rule ("P3 meets or beats P2 and has higher faithfulness") cannot be met, and the live model stays Nova Lite. Nothing below says anything about Claude models.

**P2g (Nova Lite + guardrail), compound subset, recovery within 3 actions.** 88% [77, 96], against 85% for P2 and 62% for P1. P2g - P1 is +25.0 points [+12.5, +37.5], so for the first time the lower end of the interval clears the +10 bar. P2g - P2 is +2.1 [-10.4, +14.6]: no detectable difference between the guarded and the unguarded model, as the pre-registered expectation (within 8 points) said. Single-cause episodes are unchanged (100%).

**What the guardrail did.**
1. Instruction faithfulness went from 54% [47, 61] (P2) to 99% [98, 100] (P2g); P1 is 91%. Most of P2's gap was text that cited no measured number (45% of its instructions), not wrong numbers (3% had a wrong number or claim). The wrong-number check caught few errors on this simulator because Nova's legacy-prompt text rarely mis-states a value; the review's errors came from the live CRC-gate prompt, which this study does not measure.
2. Decisions that break a hard prompt rule fell from 19% (P2) to 0%. The frozen P1 breaks them in 24% of decisions.
3. The first answer had a violation in 58% of decisions. A re-ask fixed 21% of all decisions; 36% still had a violation and got the rules template wording instead (the model's action was kept); 1% (2 decisions) had an action that stayed invalid and went to the rules policy. Nova Lite's own wording is therefore the operator's text in only about two thirds of decisions.
4. Cost: 392 model calls for 250 decisions (1.6 per decision), US$0.06 for the test run, call latency p50 about 1.0 s, p95 1.4 s; a re-asked decision takes two such calls in sequence.

**Why the recovery gain over P2 is small and what it means.** The action check is the prompt's own rule set, which is also what the label policy P* encodes. With it enforced, P2g's action matches the label set in 100% of decisions on uncertified captures and the primary label action in 97% (P2: 81% / 78%), and its recovery equals P* (88% compound). That is expected, not a discovery: the guardrail turns "LLM following the written rules" into "LLM whose answer is overridden by the written rules whenever it deviates". Nova Lite's contribution is the wording of the instruction (under a validator) and a policy that can still choose among the actions the rules allow; this study cannot show it reasons better than P*. False abandon of recoverable episodes dropped to 4% (P2 10%, P1 25%).

**Limits added by Addendum B.** The study measures the legacy-gate prompt on the simulator; the live service uses the CRC-gate prompt, whose guardrail checks are covered by unit tests only. The validator and P* share their source (the prompt's rules), so 0% rule violations for P2g and for P* is by construction. The 54% to 99% faithfulness gain is partly a property of the check "cites a measured number", which the template wording satisfies by design. Faithfulness says the numbers and claims in the text are right; it does not say the advice is good, and the human 1-to-5 rating is still not done."""


def fmt(r: dict, pct: bool = True) -> str:
    e, lo, hi = r["estimate"], r["lo"], r["hi"]
    if e is None or (isinstance(e, float) and math.isnan(e)):
        return "n/a"
    if pct:
        return f"{100 * e:.0f}% [{100 * lo:.0f}, {100 * hi:.0f}]"
    return f"{e:.1f} [{lo:.1f}, {hi:.1f}]"


def find_row(rows, pol, subset, metric):
    for r in rows:
        if r["policy"] == pol and r["subset"] == subset and r["metric"] == metric:
            return r
    return {"estimate": float("nan"), "lo": float("nan"), "hi": float("nan"), "n": 0}


def cmd_report(a):
    test_tag = a.test_tag
    agent.SYSTEM_PROMPT = V2_PROMPT.read_text(encoding="utf-8")   # the P2 / P2g / P3 prompt, for the fingerprint line
    names = {"P0 random": "p0", "P1 rules": "p1", "P2 LLM (Nova Lite)": test_tag, "P2g Nova Lite + guardrail": "p2g",
             "P3 Haiku 4.5 + guardrail": "p3", "P* label rule (ceiling)": "pstar"}
    runs, meta = {}, {}
    for label_, tag in names.items():
        p = RUNS / f"test_{tag}.jsonl"
        if p.exists():
            m, t = load_run(p)
            runs[label_] = [episode_stats(x) for x in t]
            meta[label_] = m
    if "P1 rules" not in runs:
        sys.exit("run the free policies on test first")
    rows = summarize(runs)
    # secondary: big free-policy run
    big_rows, big_runs = [], {}
    for label_, tag in (("P0 random", "p0"), ("P1 rules", "p1"), ("P* label rule (ceiling)", "pstar")):
        p = RUNS / f"big_{tag}.jsonl"
        if p.exists():
            big_runs[label_] = [episode_stats(x) for x in load_run(p)[1]]
    if big_runs:
        big_rows = summarize(big_runs)
    dev_rows, dev_runs = [], {}
    for label_, tag in (("P0 random", "p0"), ("P1 rules", "p1"), ("P* label rule (ceiling)", "pstar")):
        p = RUNS / f"dev_{tag}.jsonl"
        if p.exists():
            dev_runs[label_] = [episode_stats(x) for x in load_run(p)[1]]
    ledger = ledger_summary()
    T = next(iter(meta.values()))["thresholds"]

    # CSV
    RESULTS.mkdir(parents=True, exist_ok=True)
    with open(RESULTS / "agent_ablation.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["table", "policy", "subset", "metric", "estimate", "ci_lo", "ci_hi", "n"])
        for tname, rr in (("test", rows), ("secondary_big_free_policies", big_rows)):
            for r in rr:
                w.writerow([tname, r["policy"], r["subset"], r["metric"], f"{r['estimate']:.4f}", f"{r['lo']:.4f}", f"{r['hi']:.4f}", r["n"]])

    pols = list(runs)
    L = []
    P = L.append
    P("# Triage-agent ablation: P0 random vs P1 rules vs P2 LLM, and (Addendum B) P2g / P3 with a guardrail\n")
    P(f"*Generated {time.strftime('%Y-%m-%d %H:%M')}. Simulator study on {len(next(iter(runs.values())))} held-out episodes; see the pre-registration for the design and the limits.*\n")
    P("## Provenance\n")
    P(f"* Pre-registration `research/AGENT_PREREG.md`, sha256 `{sha256_file(PREREG)}`")
    P(f"* Simulator `src/prohori/episodes.py`, sha256 `{sha256_file(ROOT / 'src/prohori/episodes.py')}`")
    P(f"* P1 source fingerprint (rules code, frozen) `{fingerprint_p1()[:16]}`; P2 final prompt+tool fingerprint `{prompt_fingerprint()[:16]}`")
    P(f"* Gate thresholds used: corners >= {T['min_corners']}, px/mm >= {T['min_px_per_mm']}, blur_var >= {T['min_blur_var']}, obliquity <= {T['max_obliquity_deg']} deg, glare <= {T['max_glare_frac']}")
    P(f"* P2 model `{NOVA}` (us-east-1, temperature 0), forced tool call, no fallback model. Seeds: test 50000-50099, dev 1000-1199, paired common random numbers.")
    P("* **Addendum B** (research/AGENT_PREREG.md, written 2026-10-26 before any P2g/P3 decision; the sha256 of the pre-registration file above includes the addendum, the file before it was `91d0dd26575acb64f8dd826cd7e92635e6ed51ba468912f0b3f6a9dc67d3cac5`): "
      f"P2g = `{NOVA}` + guardrail, P3 = `{HAIKU45}` + guardrail, both with prompt v2 of the legacy gate (the prompt P2 used; text in `research/prompts/agent_prompt_v2_legacy_gate.txt`, sha256 `{sha256_file(V2_PROMPT)[:16]}`), temperature 0, no fallback model, one run each on the same seeds.")
    for lab_, m_ in meta.items():
        if m_.get("git_head"):
            P(f"* {lab_}: run at git `{m_['git_head'][:10]}`, prompt+tool fingerprint `{m_['prompt_fingerprint'][:16]}`, model `{m_.get('model')}`, {m_['seconds']} s")
    P(f"* Confidence intervals: 95% percentile bootstrap over episodes, {BOOT_B} resamples, seed {BOOT_SEED}.\n")

    P("## Headline: recovery within 3 actions (share of episodes certified by the 4th capture)\n")
    P("| subset | n | " + " | ".join(pols) + " |")
    P("|---|---|" + "---|" * len(pols))
    for s in ("single (S)", "compound (X+C2+C3)", "recoverable (S+X+C2+C3)"):
        n = find_row(rows, pols[0], s, "recovery@3")["n"]
        P(f"| {s} | {n} | " + " | ".join(fmt(find_row(rows, p, s, "recovery@3")) for p in pols) + " |")
    P("")
    if "P2 LLM (Nova Lite)" in runs:
        P("### Pre-registered test: P2 minus P1, recovery@3, paired by episode\n")
        P("| subset | n | P2 - P1 (points) | 95% CI | criterion |")
        P("|---|---|---|---|---|")
        for s in ("single (S)", "compound (X+C2+C3)", "recoverable (S+X+C2+C3)"):
            e, lo, hi, n = paired_diff(runs["P2 LLM (Nova Lite)"], runs["P1 rules"], s)
            crit = ""
            if s.startswith("compound"):
                crit = "MET (lower bound >= +10)" if lo * 100 >= 10 else ("point estimate >= +10 but CI includes smaller effects" if e * 100 >= 10 else "NOT MET")
            if s.startswith("single"):
                crit = "expected |diff| < 10" + (": holds" if abs(e) * 100 < 10 else ": does not hold")
            P(f"| {s} | {n} | {100 * e:+.1f} | [{100 * lo:+.1f}, {100 * hi:+.1f}] | {crit} |")
        P("")
        e, lo, hi, n = paired_diff(runs["P2 LLM (Nova Lite)"], runs["P1 rules"], "compound (X+C2+C3)", key="rec6")
        P(f"Recovery within all 6 actions, compound, P2 - P1: {100 * e:+.1f} points [{100 * lo:+.1f}, {100 * hi:+.1f}], n={n}.\n")
        new_ = [k for k in ("P2g Nova Lite + guardrail", "P3 Haiku 4.5 + guardrail") if k in runs]
        if new_:
            P("### Addendum B: guardrail variants, recovery@3, paired by episode (primary bar: point estimate >= +10 vs P1 on the compound subset)\n")
            P("| comparison | subset | n | difference (points) | 95% CI | bar vs P1 |")
            P("|---|---|---|---|---|---|")
            pairs = [(k, "P1 rules") for k in new_] + [(k, "P2 LLM (Nova Lite)") for k in new_]
            if len(new_) == 2:
                pairs.append(("P3 Haiku 4.5 + guardrail", "P2g Nova Lite + guardrail"))
            for a_, b_ in pairs:
                for s in ("single (S)", "compound (X+C2+C3)", "recoverable (S+X+C2+C3)"):
                    e, lo, hi, n = paired_diff(runs[a_], runs[b_], s)
                    bar = ""
                    if b_ == "P1 rules" and s.startswith("compound"):
                        bar = ("point estimate >= +10, lower bound >= +10: MET" if lo * 100 >= 10 else
                               ("point estimate >= +10, lower bound < +10: not demonstrated" if e * 100 >= 10 else "NOT MET"))
                    P(f"| {a_.split(' ')[0]} - {b_.split(' ')[0]} | {s} | {n} | {100 * e:+.1f} | [{100 * lo:+.1f}, {100 * hi:+.1f}] | {bar} |")
            P("")

    P("## All outcome metrics, held-out test split\n")
    for metric, title, pct in (("recovery@6", "Recovery within 6 actions", True), ("turns_to_certified_median", "Median actions to certified (episodes that were certified)", False),
                               ("correct_outcome", "Correct terminal outcome (certified / abandoned / widened as the class requires)", True)):
        P(f"### {title}\n")
        P("| subset | " + " | ".join(pols) + " |")
        P("|---|" + "---|" * len(pols))
        for s in SUBSETS:
            if metric.startswith("turns") and s in ("hopeless (H)", "constrained (M)"):
                continue
            P(f"| {s} | " + " | ".join(fmt(find_row(rows, p, s, metric), pct) for p in pols) + " |")
        P("")
    P("### Action accuracy at decision points on uncertified captures\n")
    P("| subset | metric | " + " | ".join(pols) + " |")
    P("|---|---|" + "---|" * len(pols))
    for s in ("single (S)", "compound (X+C2+C3)", "recoverable (S+X+C2+C3)", "all"):
        for m, nm in (("action_acc_acceptable", "acceptable (in label set)"), ("action_acc_strict", "strict (primary)"), ("addresses_a_failure", "addresses some failure")):
            P(f"| {s} | {nm} | " + " | ".join(fmt(find_row(rows, p, s, m)) for p in pols) + " |")
    P("")
    P("### Escalation (abandon_and_log)\n")
    P("| metric | " + " | ".join(pols) + " |")
    P("|---|" + "---|" * len(pols))
    for m, nm in (("escalation_precision_vs_truth", "precision vs truth (episode was hopeless)"), ("escalation_recall_vs_truth", "recall vs truth"),
                  ("false_abandon_of_recoverable", "false abandon of recoverable episodes"),
                  ("escalation_precision_vs_rule", "precision vs labelling rule (decision level)"), ("escalation_recall_vs_rule", "recall vs labelling rule")):
        P(f"| {nm} | " + " | ".join(fmt(find_row(rows, p, "all", m)) for p in pols) + " |")
    P("")
    P("### Instruction text: automated checklist (NOT the human 1-5 rating, which is pending)\n")
    ip = [k for k in ("P1 rules", "P2 LLM (Nova Lite)", "P2g Nova Lite + guardrail", "P3 Haiku 4.5 + guardrail") if k in runs]
    P("| check | " + " | ".join(ip) + " |")
    P("|---|" + "---|" * len(ip))
    for m, nm in (("instr_within_140", "within 140 characters"), ("instr_cites_number", "contains a digit (original checklist)"),
                  ("instr_matches_action", "wording matches the chosen action"),
                  ("instr_faithful", "**instruction faithfulness**: cites a measured number AND zero validator violations (Addendum B)"),
                  ("instr_violation_rate", "instructions with a wrong number or a wrong certification claim (validator)"),
                  ("instr_no_measured_number", "instructions that cite no measured number"),
                  ("rule_violation_rate", "decisions breaking a hard prompt rule (action check, on the output the operator sees)")):
        P(f"| {nm} | " + " | ".join(fmt(find_row(rows, p, "all", m)) for p in ip) + " |")
    P("")
    gp = [k for k in ("P2g Nova Lite + guardrail", "P3 Haiku 4.5 + guardrail") if k in runs]
    if gp:
        P("### Guardrail activity (share of LLM decisions)\n")
        P("| measure | " + " | ".join(gp) + " |")
        P("|---|" + "---|" * len(gp))
        for m, nm in (("guard_first_pass_violation", "first answer had any violation (action or instruction)"),
                      ("guard_reask", "re-asked"), ("guard_fixed_by_reask", "fixed by the re-ask"),
                      ("guard_repaired", "**instruction replaced by the rules template (repaired)**"),
                      ("guard_action_rejected", "action rejected, rules policy used"),
                      ("guard_rationale_withheld", "rationale withheld")):
            P(f"| {nm} | " + " | ".join(fmt(find_row(rows, p, "all", m)) for p in gp) + " |")
        P("")
        P("Pre-repair faithfulness was not stored per decision; \"first answer had any violation\" is the nearest quantity (it includes action violations).\n")

    if big_rows:
        bp = list(big_runs)
        P("## Secondary: free policies on 1,000 episodes (separate seeds 70000-70999, same generator)\n")
        P("No model calls. Shows how far a fixed if/else cascade is from the label-rule ceiling when the sample is large enough to see small differences.\n")
        P("| subset | metric | " + " | ".join(bp) + " |")
        P("|---|---|" + "---|" * len(bp))
        for s in ("single (S)", "compound (X+C2+C3)", "recoverable (S+X+C2+C3)"):
            for m, nm in (("recovery@3", "recovery@3"), ("action_acc_acceptable", "acceptable accuracy")):
                P(f"| {s} | {nm} | " + " | ".join(fmt(find_row(big_rows, p, s, m)) for p in bp) + " |")
        if "P1 rules" in big_runs and "P* label rule (ceiling)" in big_runs:
            e, lo, hi, n = paired_diff(big_runs["P* label rule (ceiling)"], big_runs["P1 rules"], "compound (X+C2+C3)")
            P(f"\nP* minus P1, recovery@3, compound, n={n}: {100 * e:+.1f} points [{100 * lo:+.1f}, {100 * hi:+.1f}].")
        P("")

    P("## Model calls, tokens and cost (all work, including prompt iteration and probes)\n")
    s8 = {tg: d for tg, d in ledger["by_tag"].items() if not _is_add_b(tg)}
    P(f"Section 8 total: calls **{sum(d['calls'] for d in s8.values())} of {TOTAL_CALL_CAP}** allowed ({sum(d['errors'] for d in s8.values())} returned an error), input tokens {sum(d['in'] for d in s8.values()):,}, output tokens {sum(d['out'] for d in s8.values()):,}, cost **${sum(d['usd'] for d in s8.values()):.4f}** at $0.06 / $0.24 per million tokens (Nova Lite; the Claude probe, if it succeeded, is priced at the same rate here and is one call).\n")
    P("| tag | calls | input tokens | output tokens | errors | USD |")
    P("|---|---|---|---|---|---|")
    for tg, d in s8.items():
        P(f"| {tg} | {d['calls']} | {d['in']:,} | {d['out']:,} | {d['errors']} | {d['usd']:.4f} |")
    P("")
    fb = find_row(rows, "P2 LLM (Nova Lite)", "all", "fallback_steps")
    if fb["n"]:
        P(f"P2 fallbacks to the rules policy on the test split: **{int(fb['estimate'])} of {fb['n']} decisions**.\n")
    if ledger["calls_b"]:
        P("### Addendum B: calls, tokens, cost and latency\n")
        P(f"Addendum B total: **{ledger['calls_b']} of {ADD_B_CALL_CAP}** calls allowed, **${ledger['usd_b']:.4f} of ${ADD_B_USD_CAP:.2f}** allowed (Nova Lite $0.06 / $0.24, Claude Haiku 4.5 $1.00 / $5.00 per million input / output tokens). The section 8 total above is unchanged.\n")
        P("| run | model | calls | input tokens | output tokens | errors | USD | call latency p50 / p95 (ms) |")
        P("|---|---|---|---|---|---|---|---|")
        for tg, d in ledger["by_tag"].items():
            if _is_add_b(tg):
                ms = sorted(d.get("ms") or [0])
                p50, p95 = ms[len(ms) // 2], ms[min(len(ms) - 1, int(0.95 * len(ms)))]
                P(f"| {tg} | `{d.get('model')}` | {d['calls']} | {d['in']:,} | {d['out']:,} | {d['errors']} | {d['usd']:.4f} | {p50} / {p95} |")
        P("")
        for lab_ in gp:
            st_ = runs[lab_]
            P(f"{lab_}: {sum(x['calls'] for x in st_)} model calls for {sum(x['dec'] for x in st_)} decisions, "
              f"{int(find_row(rows, lab_, 'all', 'fallback_steps')['estimate'])} fallbacks to the rules policy "
              f"(guardrail rejections among them: {int(sum(x['g_rejected'] for x in st_))}).\n")
    if dev_runs:
        P("## Dev split (free policies, 200 episodes)\n")
        P("| subset | " + " | ".join(dev_runs) + " |")
        P("|---|" + "---|" * len(dev_runs))
        dev_rows = summarize(dev_runs)
        for s in ("single (S)", "compound (X+C2+C3)", "recoverable (S+X+C2+C3)"):
            P(f"| recovery@3, {s} | " + " | ".join(fmt(find_row(dev_rows, p, s, "recovery@3")) for p in dev_runs) + " |")
        P("")
    P("## Reading these results: original run, P0/P1/P2 (written after those results were seen on 2026-10-19; not part of the pre-registration)\n")
    P(INTERPRETATION)
    if gp:
        P("\n## Reading the Addendum B results, P2g and P3 (written after seeing them, " + time.strftime("%Y-%m-%d") + "; not part of the pre-registration)\n")
        P(INTERPRETATION_B)
    (RESULTS / "agent_ablation.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    make_figure(rows, pols, runs)
    print(f"wrote {RESULTS / 'agent_ablation.md'}, .csv, .png")


def make_figure(rows, pols, runs):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colors = {"P0 random": "#9aa0a6", "P1 rules": "#2b6cb0", "P2 LLM (Nova Lite)": "#dd6b20", "P2g Nova Lite + guardrail": "#d69e2e",
              "P3 Haiku 4.5 + guardrail": "#805ad5", "P* label rule (ceiling)": "#2f855a"}
    subsets = ["single (S)", "compound (X+C2+C3)", "recoverable (S+X+C2+C3)"]
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6), constrained_layout=True)
    w = 0.8 / len(pols)
    for ax, (metric, title) in zip(axes[:2], (("recovery@3", "Recovery within 3 actions"), ("action_acc_acceptable", "Action accuracy (in label set)"))):
        for i, p in enumerate(pols):
            ests, errs = [], [[], []]
            for s in subsets:
                r = find_row(rows, p, s, metric)
                ests.append(100 * r["estimate"])
                errs[0].append(100 * (r["estimate"] - r["lo"]))
                errs[1].append(100 * (r["hi"] - r["estimate"]))
            ax.bar(np.arange(len(subsets)) + i * w - 0.4 + w / 2, ests, w, yerr=errs, capsize=2, label=p, color=colors.get(p))
        ax.set_xticks(range(len(subsets)))
        ax.set_xticklabels(["single", "compound", "all recoverable"])
        ax.set_ylim(0, 105)
        ax.set_ylabel("percent")
        ax.set_title(title)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].legend(fontsize=8, loc="lower left")
    ax = axes[2]
    cl = ["S", "X", "C2", "C3", "H", "M"]
    for i, p in enumerate(pols):
        vals = []
        for k in cl:
            sub = [s for s in runs[p] if s["class"] == k]
            vals.append(100 * np.mean([s["correct_outcome"] for s in sub]))
        ax.bar(np.arange(len(cl)) + i * w - 0.4 + w / 2, vals, w, color=colors.get(p), label=p)
    ax.set_xticks(range(len(cl)))
    ax.set_xticklabels(["single", "pair\nconflict", "pair\nother", "triple", "hopeless", "constrained"])
    ax.set_ylim(0, 105)
    ax.set_title("Correct terminal outcome by episode class")
    ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle("Triage agent ablation on simulated captures (held-out test split; bars show 95% bootstrap CIs over episodes)", fontsize=10)
    fig.savefig(RESULTS / "agent_ablation.png", dpi=150)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("run")
    r.add_argument("--split", required=True, choices=["check", "dev", "test", "big"])
    r.add_argument("--policies", default="p0,p1,pstar")
    r.add_argument("--n", type=int, default=None)
    r.add_argument("--tag", default=None)
    r.add_argument("--workers", type=int, default=4)
    r.set_defaults(fn=cmd_run)
    pr = sp.add_parser("probe-claude")
    pr.set_defaults(fn=cmd_probe)
    rp = sp.add_parser("report")
    rp.add_argument("--test-tag", default="final")
    rp.set_defaults(fn=cmd_report)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
