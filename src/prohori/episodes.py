"""Episodic capture-degradation simulator for the Prohori triage-agent ablation.

Specification: research/AGENT_PREREG.md (sections 2-6). This module is that
specification in code. Nothing here calls OpenCV or a model: a latent capture
state is turned into the same numeric observation vector and gate result that
``measure.analyze`` returns, policies choose one of the seven agent actions,
a simulated operator carries the action out (10% of the time nothing happens),
and the loop repeats until the capture is certified, the policy gives up, or
the turn limit is reached.

Calibration: the nominal-capture marginals (px/mm, obliquity) and the blur and
corner models are anchored to eval/results/panel_photos_2026-10-19.csv, see
``calibration_report``. Glare, severe obliquity and px/mm below the gate are
NOT present in that panel; their distributions are assumptions (flagged in the
pre-registration).

Everything is expressed relative to the gate thresholds, which are read from
``prohori.agent.GATE_THRESHOLDS`` unless a dict is passed in, so the simulator
stays valid if the gate is refitted.

Common random numbers: transitions are drawn from a generator seeded by
(episode seed, turn, action id), observation noise by (episode seed, turn).
Every policy therefore faces identical luck for identical choices.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field, replace
from typing import Callable

import numpy as np

from .agent import ACTIONS, GATE_THRESHOLDS

T_MAX = 6            # maximum number of actions per episode
K_PRIMARY = 3        # recovery horizon for the primary metric
ABANDON_AFTER = 3    # label rule: abandon on the (ABANDON_AFTER+1)-th consecutive failed capture
PPM_FIT = 22.0       # px/mm at which board + crack stop fitting the 4000 px frame
NO_BOARD_BLUR_SPLIT = 100.0   # whole-frame blur_var separating blurred from sharp no-board frames
P_COMPLY = 0.90
CRACK_LEN_MM = 80.0
MIN_FOUND_CORNERS = 7
HIDING_CORNERS = 12  # label rule 6a: glare is plausibly hiding the board below this many corners

CAUSES = ["low_res", "blur", "glare", "oblique", "board_partial", "no_crack"]
CONFLICT_PAIRS = [("glare", "oblique"), ("oblique", "blur"), ("glare", "blur"),
                  ("blur", "low_res"), ("oblique", "low_res")]
HOPELESS_KINDS = ["damaged_board", "impossible_light", "unreachable"]
CLASSES = ["S", "X", "C2", "C3", "H", "M"]
COMPOUND = {"X", "C2", "C3"}
RECOVERABLE = {"S", "X", "C2", "C3"}
CORRECT_TERMINAL = {"S": "certified", "X": "certified", "C2": "certified", "C3": "certified",
                    "H": "abandoned", "M": "widened"}

# class counts per block, and the split definitions (seeds and block sizes) from the pre-registration
BLOCKS = {
    "dev": {"S": 3, "X": 4, "C2": 3, "C3": 4, "H": 3, "M": 3},     # 20
    "test": {"S": 5, "X": 5, "C2": 3, "C3": 4, "H": 4, "M": 4},    # 25
    "check": {"S": 5, "X": 5, "C2": 3, "C3": 4, "H": 4, "M": 4},   # 25
    "big": {"S": 5, "X": 5, "C2": 3, "C3": 4, "H": 4, "M": 4},     # 25 (free-policy secondary run)
}
SPLIT_SEED0 = {"check": 900000, "dev": 1000, "test": 50000, "big": 70000}
SPLIT_N = {"check": 100, "dev": 200, "test": 100, "big": 1000}

ACTION_ID = {a: i + 1 for i, a in enumerate(ACTIONS)}


def _block_order(split: str) -> list[str]:
    cls = [c for c, n in BLOCKS[split].items() for _ in range(n)]
    random.Random(f"prohori-block-{split}").shuffle(cls)
    return cls


def split_episodes(split: str, n: int | None = None) -> list[tuple[int, str]]:
    """[(seed, class), ...] for a split. Fixed order, balanced blocks."""
    order = _block_order(split)
    n = SPLIT_N[split] if n is None else n
    return [(SPLIT_SEED0[split] + i, order[i % len(order)]) for i in range(n)]


# --------------------------------------------------------------------------- latent state
@dataclass
class State:
    ppm0: float
    theta: float
    blur: float
    glare: float
    vis: float
    framed: bool
    dim: bool
    glare_susc: float = 0.0
    ppm_cap: float = math.inf
    glare_floor: float = 0.0
    vis_cap: float = 1.0
    causes: tuple = ()
    kind: str = ""


def _u(rng, a, b):
    return float(rng.uniform(a, b))


def _lu(rng, a, b):
    return float(math.exp(rng.uniform(math.log(a), math.log(b))))


def _nominal(rng, T) -> State:
    return State(
        ppm0=T["min_px_per_mm"] * _u(rng, 1.25, 2.4),
        theta=min(40.0, 9.0 * math.exp(rng.normal(0, 0.8))),
        blur=T["min_blur_var"] * _u(rng, 1.1, 2.5),
        glare=0.0, vis=1.0, framed=True, dim=bool(rng.random() < 0.25))


def _apply_cause(st: State, c: str, rng, T) -> None:
    if c == "low_res":
        st.ppm0 = T["min_px_per_mm"] * _u(rng, 0.35, 0.90)
    elif c == "blur":
        st.blur = T["min_blur_var"] * _lu(rng, 0.25, 0.92)
    elif c == "glare":
        st.glare = T["max_glare_frac"] * _lu(rng, 1.6, 8.0)
        st.glare_susc = st.glare
    elif c == "oblique":
        st.theta = _u(rng, T["max_obliquity_deg"] * 1.04, T["max_obliquity_deg"] * 1.5)
    elif c == "board_partial":
        st.vis = _u(rng, 0.10, 0.31)
    elif c == "no_crack":
        st.framed = False
    else:
        raise ValueError(c)


def initial_state(seed: int, klass: str, T: dict | None = None) -> State:
    T = T or GATE_THRESHOLDS
    rng = np.random.default_rng([seed, 999999])
    st = _nominal(rng, T)
    causes: list[str] = []
    if klass == "S":
        causes = [CAUSES[int(rng.integers(len(CAUSES)))]]
    elif klass == "X":
        causes = list(CONFLICT_PAIRS[int(rng.integers(len(CONFLICT_PAIRS)))])
    elif klass == "C2":
        pairs = [tuple(sorted(p)) for p in __import__("itertools").combinations(CAUSES, 2)]
        conflict = {tuple(sorted(p)) for p in CONFLICT_PAIRS}
        pairs = [p for p in pairs if p not in conflict]
        causes = list(pairs[int(rng.integers(len(pairs)))])
    elif klass == "C3":
        triples = list(__import__("itertools").combinations(CAUSES, 3))
        causes = list(triples[int(rng.integers(len(triples)))])
    elif klass == "H":
        kind = HOPELESS_KINDS[int(rng.integers(len(HOPELESS_KINDS)))]
        st.kind = kind
        if kind == "damaged_board":
            st.vis_cap = _u(rng, 0.10, 0.28)
            st.vis = st.vis_cap
        elif kind == "impossible_light":
            st.glare_floor = T["max_glare_frac"] * _u(rng, 2.5, 6.0)
            st.glare = st.glare_floor * _u(rng, 1.0, 1.6)
            st.glare_susc = st.glare
        else:  # unreachable
            st.ppm_cap = T["min_px_per_mm"] * _u(rng, 0.4, 0.8)
            st.ppm0 = st.ppm_cap * _u(rng, 0.7, 1.0)
        if rng.random() < 0.30:
            causes = ["blur"]
    elif klass == "M":
        st.ppm_cap = T["min_px_per_mm"] * _u(rng, 0.85, 0.97)
        st.ppm0 = st.ppm_cap * _u(rng, 0.8, 1.0)
        st.theta = _u(rng, 0.0, 12.0)
    else:
        raise ValueError(klass)
    for c in causes:
        _apply_cause(st, c, rng, T)
    st.causes = tuple(causes)
    return st


# --------------------------------------------------------------------------- observation model
def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def capture(st: State, rng, T: dict | None = None) -> tuple[dict, dict, list]:
    """Latent state -> (observation, gate, cracks), same shapes as measure.analyze."""
    T = T or GATE_THRESHOLDS
    vis_eff = min(st.vis, min(1.0, (PPM_FIT / max(st.ppm0, 1e-6)) ** 2))
    f_glare = 1.0 - 0.85 * float(np.clip((st.glare - 0.03) / 0.17, 0, 1))
    f_blur = _sigmoid((math.log(max(st.blur, 1e-3)) - math.log(45.0)) / 0.3)
    f_tilt = 1.0 - 0.7 * float(np.clip((st.theta - 45.0) / 25.0, 0, 1))
    f_res = _sigmoid((st.ppm0 - 3.0) / 0.8)
    p = float(np.clip(0.97 * f_glare * f_blur * f_tilt * f_res, 0.0, 1.0))
    corners = int(rng.binomial(int(round(24 * vis_eff)), p))
    found = corners >= MIN_FOUND_CORNERS
    obs = {"corners": corners, "corners_total": 24, "blur_var": 0.0, "px_per_mm": 0.0, "obliquity_deg": 0.0,
           "glare_frac": 0.0, "crack_px_extent": 0, "image_w": 4000, "image_h": 3000}
    cracks: list = []
    reasons: list[str] = []
    if not found:
        obs["blur_var"] = round(float(st.blur * math.exp(rng.normal(math.log(1.4), 0.35))), 1)
        gate = {"certified": False, "reasons": ["too_few_corners"]}
        return obs, gate, cracks
    ppm_obs = st.ppm0 * math.sqrt(max(math.cos(math.radians(min(st.theta, 89.0))), 1e-3)) * math.exp(rng.normal(0, 0.04))
    obs["px_per_mm"] = round(float(ppm_obs), 2)
    obs["obliquity_deg"] = round(float(max(0.0, st.theta + rng.normal(0, 1.2))), 2)
    obs["blur_var"] = round(float(st.blur * math.exp(rng.normal(0, 0.12))), 1)
    obs["glare_frac"] = round(float(st.glare * math.exp(rng.normal(0, 0.10))), 4)
    crack_ok = st.framed and ppm_obs >= 3.0 and (st.glare < 0.1 or rng.random() < 0.6)
    if crack_ok:
        obs["crack_px_extent"] = int(round(CRACK_LEN_MM * ppm_obs))
        cracks = [{"id": "c1", "width_mm": round(float(0.30 + 0.5 * rng.random()), 3),
                   "uncertainty_mm": round(float(0.5 / max(ppm_obs, 1.0)), 3), "length_mm": CRACK_LEN_MM}]
    if obs["corners"] < T["min_corners"]:
        reasons.append("too_few_corners")
    if obs["px_per_mm"] < T["min_px_per_mm"]:
        reasons.append("low_resolution")
    if obs["blur_var"] < T["min_blur_var"]:
        reasons.append("blurry")
    if obs["obliquity_deg"] > T["max_obliquity_deg"]:
        reasons.append("oblique")
    if obs["glare_frac"] > T["max_glare_frac"]:
        reasons.append("glare")
    gate = {"certified": (not reasons) and bool(cracks), "reasons": reasons}
    return obs, gate, cracks


# --------------------------------------------------------------------------- action transitions
def transition(st: State, action: str, rng, T: dict | None = None) -> State:
    """Operator carries out ``action``; returns the new latent state (st is not mutated)."""
    T = T or GATE_THRESHOLDS
    s = replace(st)
    if action in ("accept", "accept_with_widened_uncertainty", "abandon_and_log"):
        return s
    if rng.random() > P_COMPLY:
        return s  # operator did not comply
    if action == "move_closer":
        new = max(1.3 * s.ppm0 * math.exp(rng.normal(0, 0.15)), T["min_px_per_mm"] * _u(rng, 1.1, 1.8))
        s.ppm0 = min(s.ppm_cap, new)
        s.blur *= math.exp(rng.normal(math.log(0.85), 0.2))
    elif action == "reshoot_steadier":
        s.blur = T["min_blur_var"] * _u(rng, 1.1, 2.5) * (0.8 if s.dim else 1.0)
    elif action == "relight":
        s.glare = max(s.glare_floor, T["max_glare_frac"] * _u(rng, 0.0, 0.8))
        if s.dim and rng.random() < 0.5:
            s.blur *= math.exp(rng.normal(math.log(0.6), 0.15))
    elif action == "reposition_marker":
        s.vis = min(s.vis_cap, _u(rng, 0.9, 1.0))
        s.framed = True
        if s.theta > 20.0:
            s.theta = min(s.theta, abs(float(rng.normal(10.0, 7.0))))
        # viewpoint change re-rolls the viewpoint-dependent nuisances
        if rng.random() < 0.5:
            s.glare = max(s.glare_floor, s.glare_susc * math.exp(rng.normal(0, 0.7))) if s.glare_susc > 0 else s.glare_floor
        if rng.random() < 0.5:
            s.blur *= math.exp(rng.normal(0, 0.35))
            s.ppm0 = min(s.ppm_cap, s.ppm0 * math.exp(rng.normal(0, 0.10)))
    else:
        raise ValueError(action)
    return s


# --------------------------------------------------------------------------- labelling rule (pre-registered, section 6)
def _fail_sev(reason: str, o: dict, T: dict) -> float:
    """Distance past the threshold in the failing direction: 0 = at threshold, 0.2 = 20% past."""
    if reason == "too_few_corners":
        return 1 - o["corners"] / T["min_corners"]
    if reason == "low_resolution":
        return 1 - o["px_per_mm"] / T["min_px_per_mm"] if o["px_per_mm"] > 0 else 1.0
    if reason == "blurry":
        return 1 - o["blur_var"] / T["min_blur_var"]
    if reason == "oblique":
        return o["obliquity_deg"] / T["max_obliquity_deg"] - 1
    if reason == "glare":
        return o["glare_frac"] / T["max_glare_frac"] - 1
    return 1.0


def _exceed(reason: str, o: dict, T: dict) -> float:
    """Log-exceedance |ln(value/T)| in the failing direction."""
    eps = 1e-6
    if reason == "too_few_corners":
        return abs(math.log(max(o["corners"], 1) / T["min_corners"]))
    if reason == "low_resolution":
        return abs(math.log(max(o["px_per_mm"], eps) / T["min_px_per_mm"]))
    if reason == "blurry":
        return abs(math.log(max(o["blur_var"], eps) / T["min_blur_var"]))
    if reason == "oblique":
        return abs(math.log(max(o["obliquity_deg"], eps) / T["max_obliquity_deg"]))
    if reason == "glare":
        return abs(math.log(max(o["glare_frac"], eps) / T["max_glare_frac"]))
    return 0.0


_REASON_ACTION = {"glare": "relight", "oblique": "reposition_marker", "blurry": "reshoot_steadier",
                  "low_resolution": "move_closer", "too_few_corners": "reposition_marker"}
_TIE = ["glare", "oblique", "blurry", "low_resolution", "too_few_corners"]


def _trailing_fails(history: list[dict]) -> int:
    n = 0
    for s in reversed(history or []):
        if (s.get("gate") or {}).get("certified"):
            break
        n += 1
    return n


def label(obs: dict, gate: dict, cracks: list, history: list[dict], T: dict | None = None) -> tuple[set, str]:
    """(acceptable action set A, primary action) per research/AGENT_PREREG.md section 6."""
    T = T or GATE_THRESHOLDS
    if gate.get("certified"):
        return {"accept"}, "accept"
    reasons = list(gate.get("reasons") or [])
    F = _trailing_fails(history)
    if reasons and cracks and F >= 2 and all(_fail_sev(r, obs, T) <= 0.2 for r in reasons):
        return {"accept_with_widened_uncertainty"}, "accept_with_widened_uncertainty"
    if F >= ABANDON_AFTER:
        return {"abandon_and_log"}, "abandon_and_log"
    if not obs.get("px_per_mm"):  # board not found
        if obs.get("blur_var", 1e9) < NO_BOARD_BLUR_SPLIT:
            return {"reshoot_steadier"}, "reshoot_steadier"
        prev = ((history[-1].get("decision") or {}).get("action") if history else None)
        a = "relight" if prev == "reposition_marker" else "reposition_marker"
        return {a}, a
    if not reasons:  # board found, crack not measured
        return {"reposition_marker"}, "reposition_marker"
    C = [r for r in reasons if r in _REASON_ACTION]
    if "glare" in C and obs["corners"] < HIDING_CORNERS:
        return {"relight"}, "relight"
    if "oblique" in C and len(C) >= 2:
        return {"reposition_marker"}, "reposition_marker"
    primary_reason = sorted(C, key=lambda r: (-_exceed(r, obs, T), _TIE.index(r)))[0]
    return {_REASON_ACTION[r] for r in C}, _REASON_ACTION[primary_reason]


def oracle_decide(obs: dict, gate: dict, cracks: list, history: list[dict], T: dict | None = None) -> dict:
    """P*: the labelling rule used as a policy (a ceiling for rules in this simulator, not a competitor)."""
    A, primary = label(obs, gate, cracks, history, T)
    return {"action": primary, "instruction": f"(label policy) {primary.replace('_', ' ')}", "rationale": "labelling rule",
            "policy": "oracle", "model": None, "input_tokens": None, "output_tokens": None, "fallback_reason": None}


# --------------------------------------------------------------------------- episode runner
PolicyFn = Callable[[dict, dict, list, list], dict]


def run_episode(seed: int, klass: str, policy: PolicyFn, T: dict | None = None, t_max: int = T_MAX) -> dict:
    """Run one episode. Returns a full trace.

    policy(observation, gate, cracks, history) -> decision dict with at least ``action``.
    History entries mirror what the service stores: observation, gate, cracks, decision.
    """
    T = T or GATE_THRESHOLDS
    st = initial_state(seed, klass, T)
    history: list[dict] = []
    steps: list[dict] = []
    outcome, outcome_idx = "timeout", t_max
    for t in range(t_max + 1):
        obs, gate, cracks = capture(st, np.random.default_rng([seed, t, 777]), T)
        step = {"t": t, "observation": obs, "gate": gate, "cracks": cracks,
                "latent": {"ppm0": round(st.ppm0, 2), "theta": round(st.theta, 1), "blur": round(st.blur, 1),
                           "glare": round(st.glare, 4), "vis": round(st.vis, 2), "framed": st.framed, "dim": st.dim}}
        if gate["certified"]:
            outcome, outcome_idx = "certified", t
            steps.append(step)
            break
        if t == t_max:
            steps.append(step)
            break
        A, primary = label(obs, gate, cracks, history, T)
        decision = policy(obs, gate, cracks, history)
        action = decision.get("action")
        step.update({"label_A": sorted(A), "label_primary": primary, "decision": decision, "action": action})
        steps.append(step)
        history.append({"observation": obs, "gate": gate, "cracks": cracks, "decision": decision})
        if action == "abandon_and_log":
            outcome, outcome_idx = "abandoned", t + 1
            break
        if action == "accept_with_widened_uncertainty" and cracks:
            outcome, outcome_idx = "widened", t + 1
            break
        st = transition(st, action, np.random.default_rng([seed, t, ACTION_ID.get(action, 99)]), T)
    return {"seed": seed, "class": klass, "causes": list(initial_state(seed, klass, T).causes),
            "kind": initial_state(seed, klass, T).kind, "outcome": outcome, "outcome_idx": outcome_idx,
            "n_actions": sum(1 for s in steps if "action" in s), "steps": steps}


# --------------------------------------------------------------------------- calibration against the real panel
def calibration_report(csv_path: str | None = None, n: int = 4000, seed: int = 0) -> dict:
    """Compare simulated nominal-capture marginals with the real panel photos (KS statistic and medians)."""
    import csv
    from pathlib import Path

    from scipy.stats import ks_2samp

    p = Path(csv_path) if csv_path else Path(__file__).resolve().parents[2] / "eval" / "results" / "panel_photos_2026-10-19.csv"
    seen = {}
    for r in csv.DictReader(open(p, encoding="utf-8")):
        seen.setdefault(r["file"], r)
    real = [r for r in seen.values() if float(r["px_per_mm"]) > 0]
    T = GATE_THRESHOLDS
    rng = np.random.default_rng(seed)
    nom = [_nominal(rng, T) for _ in range(n)]
    r_ppm = np.array([float(r["px_per_mm"]) for r in real])
    s_ppm = np.array([s.ppm0 * math.sqrt(math.cos(math.radians(s.theta))) for s in nom])
    r_th = np.array([float(r["obliquity_deg"]) for r in real])
    s_th = np.array([s.theta for s in nom])
    r_blur = np.array([float(r["blur_var"]) for r in real])
    # real board-found photos are a mixture of sharp and blur-failing frames (13 of 22 failed blur)
    frac_fail = float((r_blur < T["min_blur_var"]).mean())
    s_blur = np.array([T["min_blur_var"] * _lu(rng, 0.25, 0.92) if rng.random() < frac_fail else s.blur for s in nom])
    out = {"n_real": len(real), "n_sim": n, "frac_real_blur_fail": round(frac_fail, 3)}
    for name, a, b in (("px_per_mm", r_ppm, s_ppm), ("obliquity_deg", r_th, s_th), ("blur_var", r_blur, s_blur)):
        ks = ks_2samp(a, b)
        out[name] = {"real_median": round(float(np.median(a)), 2), "sim_median": round(float(np.median(b)), 2),
                     "ks_stat": round(float(ks.statistic), 3), "ks_p": round(float(ks.pvalue), 3)}
    return out
