"""Uncertainty-aware change detection and trend for one joint across visits.

Why this is not "new width > old width"
  Every certified measurement carries a standard uncertainty u (measure.py: five independent terms in
  quadrature, 1 sigma, in mm). Two visits measure the same crack independently, so the standard uncertainty
  of their difference is u_d = sqrt(u1^2 + u2^2) (GUM, JCGM 100:2008, law of propagation for a difference
  of independent quantities). A change is called *significant* only if

        |w2 - w1| > k * u_d ,      k = z_{(1+level)/2}   (two-sided normal quantile)

  with ``level`` = the interval level the system reports (default 0.90, the same level as the conformal
  width interval in research/METRICS.md section 2, so k = 1.645). This is a conformity-style decision rule:
  a difference inside the guard band k*u_d is reported as "within measurement uncertainty", never as growth
  or shrinkage (cf. JCGM 106:2012 on the role of uncertainty in decisions; this is the two-measurement
  analogue of a guard band). Treating the two uncertainties as independent is conservative for flagging:
  the scale-error term is partly common to both visits when the same board and phone are used.

  ``uncertainty_kind="expanded"`` is supported in case measure.py is changed to report an interval
  half-width at ``level`` instead of 1 sigma: then the rule becomes |dw| > sqrt(U1^2 + U2^2).

Trend (3 or more visits)
  Robust slope = Theil-Sen (median of pairwise slopes; Theil 1950, Sen 1968, JASA 63:1379), resistant to one
  bad visit. Its interval is the union of
    (a) the distribution-free Sen/Kendall interval (Gilbert 1987, ch. 17) - captures scatter between visits;
    (b) a seeded Monte-Carlo interval that perturbs every width by its own standard uncertainty and
        re-computes the Theil-Sen slope - captures measurement uncertainty.
  The union is deliberately conservative. A trend is "significant" only if that interval excludes zero.
  With few visits the interval is honestly wide: three visits can seldom prove a trend.

A "visit" is one inspection session: several certified captures of the same joint inside one session are
collapsed to the latest one, so a retake loop is not mistaken for a series of visits.

No crack re-identification is done (the operator asserts the joint via its id); see research/SERVICE_NOTES.md.
"""
from __future__ import annotations

import math
import os
from datetime import datetime, timezone
from statistics import NormalDist
from typing import Any

import numpy as np

DEFAULT_LEVEL = 0.90
MIN_PAIR_DT_DAYS = 1.0  # visits closer than a day apart do not define a slope (a 30-day extrapolation from hours would be noise)
MC_DRAWS = 2000
MC_SEED = 20261026
MAX_TREND_VISITS = 60


def change_level() -> float:
    try:
        v = float(os.environ.get("PROHORI_CHANGE_LEVEL", DEFAULT_LEVEL))
    except ValueError:
        v = DEFAULT_LEVEL
    return v if 0.5 < v < 1.0 else DEFAULT_LEVEL


def uncertainty_kind() -> str:
    k = os.environ.get("PROHORI_U_KIND", "standard").strip().lower()
    return k if k in ("standard", "expanded") else "standard"


def coverage_factor(level: float) -> float:
    """Two-sided normal quantile for ``level`` (0.90 -> 1.645, 0.95 -> 1.960)."""
    return NormalDist().inv_cdf((1.0 + level) / 2.0)


def _num(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _std_u(u: float, level: float, kind: str) -> float:
    """Standard (1 sigma) uncertainty from the stored one."""
    return u if kind == "standard" else u / coverage_factor(level)


# --------------------------------------------------------------------------- pairwise change
def significant_change(w1: Any, u1: Any, w2: Any, u2: Any, *, level: float | None = None,
                       uncertainty_kind_: str | None = None) -> dict:
    """Change from visit 1 (older) to visit 2 (newer). Returns a JSON-safe dict:
    delta, u_combined (1 sigma), k, threshold, significant, direction ("wider"|"narrower"|"none"),
    verdict (short plain text)."""
    level = change_level() if level is None else level
    kind = uncertainty_kind_ or uncertainty_kind()
    a, b, ua, ub = _num(w1), _num(w2), _num(u1), _num(u2)
    if a is None or b is None:
        return {"delta_mm": None, "significant": False, "direction": "none", "verdict": "no width to compare",
                "level": level}
    delta = b - a
    out: dict[str, Any] = {"delta_mm": round(delta, 4), "level": level}
    if ua is None or ub is None or ua < 0 or ub < 0:
        out.update(u_combined_mm=None, k=None, threshold_mm=None, significant=False, direction="none",
                   verdict="uncertainty missing, change cannot be judged")
        return out
    k = coverage_factor(level)
    u_d = math.hypot(_std_u(ua, level, kind), _std_u(ub, level, kind))
    thr = k * u_d
    sig = abs(delta) > thr
    direction = ("wider" if delta > 0 else "narrower") if sig else "none"
    verdict = {"wider": "wider than last visit, beyond measurement uncertainty",
               "narrower": "narrower than last visit, beyond measurement uncertainty",
               "none": "no change beyond measurement uncertainty"}[direction]
    out.update(u_combined_mm=round(u_d, 4), k=round(k, 3), threshold_mm=round(thr, 4),
               significant=sig, direction=direction, verdict=verdict)
    return out


# --------------------------------------------------------------------------- visits
def _parse_ts(ts: Any) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def visits_from_records(records: list[dict]) -> list[dict]:
    """Valid records -> one per inspection session (the latest), sorted by time. Adds "t" (datetime)."""
    by_session: dict[str, dict] = {}
    anon = 0
    for r in records or []:
        w = _num(r.get("width_mm"))
        t = _parse_ts(r.get("ts") or r.get("sk"))
        if w is None or t is None:
            continue
        sid = r.get("inspection_session")
        if not sid:
            anon += 1
            sid = f"_anon{anon}"
        v = dict(r)
        v["t"] = t
        v["width_mm"] = w
        prev = by_session.get(sid)
        if prev is None or t >= prev["t"]:
            by_session[sid] = v
    return sorted(by_session.values(), key=lambda v: v["t"])


def public_visit(v: dict) -> dict:
    return {"ts": v["t"].isoformat(timespec="seconds"), "width_mm": v["width_mm"],
            "uncertainty_mm": _num(v.get("uncertainty_mm")), "px_per_mm": _num(v.get("px_per_mm")),
            "session": v.get("inspection_session"), "crack_id": v.get("crack_id")}


# --------------------------------------------------------------------------- trend
def _pairwise_slopes(t: np.ndarray, w: np.ndarray) -> np.ndarray:
    i, j = np.triu_indices(len(t), 1)
    dt = t[j] - t[i]
    ok = dt >= MIN_PAIR_DT_DAYS
    return (w[j][ok] - w[i][ok]) / dt[ok]


def theil_sen_trend(visits: list[dict], *, level: float | None = None, uncertainty_kind_: str | None = None,
                    draws: int = MC_DRAWS, seed: int = MC_SEED) -> dict | None:
    """Robust trend over ``visits`` (from ``visits_from_records``). None when fewer than 3 visits."""
    level = change_level() if level is None else level
    kind = uncertainty_kind_ or uncertainty_kind()
    vs = visits[-MAX_TREND_VISITS:]
    n = len(vs)
    if n < 3:
        return None
    t0 = vs[0]["t"]
    t = np.array([(v["t"] - t0).total_seconds() / 86400.0 for v in vs])
    w = np.array([v["width_mm"] for v in vs])
    span = float(t[-1] - t[0])
    slopes = _pairwise_slopes(t, w)
    if len(slopes) == 0:
        return {"n": n, "span_days": round(span, 3), "significant": False, "direction": "none",
                "note": "visits too close in time to estimate a slope", "level": level}
    slope = float(np.median(slopes))

    # (a) Sen / Kendall distribution-free interval
    z = coverage_factor(level)
    sigma_s = math.sqrt(n * (n - 1) * (2 * n + 5) / 18.0)
    c = z * sigma_s
    s_sorted = np.sort(slopes)
    N = len(s_sorted)
    lo_i = max(0, int(math.floor((N - c) / 2.0)) - 1)
    hi_i = min(N - 1, int(math.ceil((N + c) / 2.0)))
    sen_lo, sen_hi = float(s_sorted[lo_i]), float(s_sorted[hi_i])

    # (b) Monte-Carlo propagation of each visit's own measurement uncertainty
    us = [_num(v.get("uncertainty_mm")) for v in vs]
    mc_lo, mc_hi = sen_lo, sen_hi
    if all(u is not None and u >= 0 for u in us) and draws > 0:
        sig = np.array([_std_u(u, level, kind) for u in us])
        rng = np.random.default_rng(seed)
        i, j = np.triu_indices(n, 1)
        dt = t[j] - t[i]
        ok = dt >= MIN_PAIR_DT_DAYS
        i, j, dt = i[ok], j[ok], dt[ok]
        wd = w[None, :] + rng.standard_normal((draws, n)) * sig[None, :]
        sl = (wd[:, j] - wd[:, i]) / dt[None, :]
        meds = np.median(sl, axis=1)
        a = (1.0 - level) / 2.0
        mc_lo, mc_hi = (float(x) for x in np.quantile(meds, [a, 1.0 - a]))
    lo, hi = min(sen_lo, mc_lo), max(sen_hi, mc_hi)
    lo, hi = min(lo, slope), max(hi, slope)
    sig_trend = lo > 0 or hi < 0
    direction = ("widening" if slope > 0 else "narrowing") if sig_trend else "none"
    d30 = 30.0
    return {
        "n": n, "span_days": round(span, 2), "level": level, "method": "theil-sen + kendall/monte-carlo interval",
        "slope_mm_per_day": round(slope, 5), "slope_lo_mm_per_day": round(lo, 5), "slope_hi_mm_per_day": round(hi, 5),
        "slope_mm_per_30d": round(slope * d30, 4), "slope_lo_mm_per_30d": round(lo * d30, 4),
        "slope_hi_mm_per_30d": round(hi * d30, 4),
        "significant": bool(sig_trend), "direction": direction,
        "verdict": {"widening": "steady widening, interval excludes zero",
                    "narrowing": "steady narrowing, interval excludes zero",
                    "none": "no trend distinguishable from zero"}[direction],
    }


# --------------------------------------------------------------------------- summary
def summarize(records: list[dict], *, current_session: str | None = None, level: float | None = None,
              uncertainty_kind_: str | None = None) -> dict:
    """Everything the API and PWA need about one joint.

    ``current_session``: when given, "previous" is the latest visit from a *different* session than that one,
    and "latest" the visit of that session (if present) - so the card on a result screen compares today's
    capture with the previous visit. Without it, latest vs the visit before it.
    """
    level = change_level() if level is None else level
    kind = uncertainty_kind_ or uncertainty_kind()
    visits = visits_from_records(records)
    out: dict[str, Any] = {"n_visits": len(visits), "level": level, "uncertainty_kind": kind,
                           "visits": [public_visit(v) for v in visits[-MAX_TREND_VISITS:]],
                           "latest": None, "previous": None, "change": None, "change_vs_first": None, "trend": None}
    if not visits:
        return out
    latest = visits[-1]
    if current_session:
        cur = [v for v in visits if v.get("inspection_session") == current_session]
        latest = cur[-1] if cur else visits[-1]
    earlier = [v for v in visits if v["t"] < latest["t"] and v.get("inspection_session") != latest.get("inspection_session")]
    out["latest"] = public_visit(latest)
    if earlier:
        prev = earlier[-1]
        out["previous"] = public_visit(prev)
        out["change"] = significant_change(prev["width_mm"], prev.get("uncertainty_mm"), latest["width_mm"],
                                           latest.get("uncertainty_mm"), level=level, uncertainty_kind_=kind)
        out["change"]["days"] = round((latest["t"] - prev["t"]).total_seconds() / 86400.0, 3)
        first = earlier[0]
        if first is not prev:
            out["change_vs_first"] = significant_change(first["width_mm"], first.get("uncertainty_mm"),
                                                        latest["width_mm"], latest.get("uncertainty_mm"),
                                                        level=level, uncertainty_kind_=kind)
    upto = [v for v in visits if v["t"] <= latest["t"]]
    out["trend"] = theil_sen_trend(upto, level=level, uncertainty_kind_=kind)
    return out
