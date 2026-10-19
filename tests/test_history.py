"""Uncertainty-aware change detection and trend (src/prohori/history.py)."""
import math
from datetime import datetime, timedelta, timezone

import pytest

from prohori import history as H

T0 = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)


def rec(day, w, u=0.02, sess=None, px=12.0):
    t = T0 + timedelta(days=day)
    return {"ts": t.isoformat(timespec="seconds"), "width_mm": w, "uncertainty_mm": u,
            "px_per_mm": px, "inspection_session": sess or f"s{day}", "crack_id": 1}


def test_coverage_factor_matches_normal_quantiles():
    assert H.coverage_factor(0.90) == pytest.approx(1.6449, abs=1e-3)
    assert H.coverage_factor(0.95) == pytest.approx(1.9600, abs=1e-3)


def test_change_beyond_combined_uncertainty_is_significant():
    c = H.significant_change(0.30, 0.05, 0.50, 0.05, level=0.90, uncertainty_kind_="standard")
    assert c["u_combined_mm"] == pytest.approx(math.hypot(0.05, 0.05), abs=1e-4)
    assert c["threshold_mm"] == pytest.approx(1.6449 * 0.0707, abs=2e-3)
    assert c["delta_mm"] == pytest.approx(0.20)
    assert c["significant"] and c["direction"] == "wider"


def test_change_inside_uncertainty_is_not_significant():
    c = H.significant_change(0.30, 0.05, 0.38, 0.05, level=0.90, uncertainty_kind_="standard")
    assert not c["significant"] and c["direction"] == "none"
    assert "no change" in c["verdict"]


def test_narrowing_and_symmetry():
    c = H.significant_change(0.60, 0.03, 0.30, 0.03, level=0.90, uncertainty_kind_="standard")
    assert c["significant"] and c["direction"] == "narrower" and c["delta_mm"] == pytest.approx(-0.30)
    # the same pair in the other order flips the direction, not the significance
    d = H.significant_change(0.30, 0.03, 0.60, 0.03, level=0.90, uncertainty_kind_="standard")
    assert d["significant"] and d["direction"] == "wider"


def test_rule_is_strict_at_the_threshold():
    k = H.coverage_factor(0.90)
    u = 0.04
    thr = k * math.hypot(u, u)
    assert not H.significant_change(0.30, u, 0.30 + thr - 1e-9, u, level=0.90, uncertainty_kind_="standard")["significant"]
    assert H.significant_change(0.30, u, 0.30 + thr + 1e-6, u, level=0.90, uncertainty_kind_="standard")["significant"]


def test_larger_uncertainty_needs_larger_change():
    small = H.significant_change(0.30, 0.02, 0.40, 0.02, level=0.90, uncertainty_kind_="standard")
    big = H.significant_change(0.30, 0.10, 0.40, 0.10, level=0.90, uncertainty_kind_="standard")
    assert small["significant"] and not big["significant"]


def test_expanded_uncertainty_kind_uses_plain_quadrature():
    c = H.significant_change(0.30, 0.10, 0.50, 0.10, level=0.90, uncertainty_kind_="expanded")
    assert c["threshold_mm"] == pytest.approx(math.hypot(0.10, 0.10), abs=1e-3)
    assert c["significant"]
    c2 = H.significant_change(0.30, 0.10, 0.42, 0.10, level=0.90, uncertainty_kind_="expanded")
    assert not c2["significant"]


@pytest.mark.parametrize("w1,u1,w2,u2", [(None, 0.1, 0.3, 0.1), (0.3, None, 0.5, 0.1), (0.3, -1, 0.5, 0.1),
                                          ("x", 0.1, 0.3, 0.1), (0.3, float("nan"), 0.5, 0.1)])
def test_missing_inputs_never_claim_a_change(w1, u1, w2, u2):
    c = H.significant_change(w1, u1, w2, u2, level=0.90)
    assert c["significant"] is False and c["direction"] == "none"


def test_visits_collapse_to_latest_per_session_and_sort():
    recs = [rec(5, 0.40, sess="b"), rec(0, 0.30, sess="a"), {**rec(0.01, 0.32, sess="a")},
            {"ts": "garbage", "width_mm": 0.5}, {"ts": rec(2, 0)["ts"], "width_mm": None}]
    vs = H.visits_from_records(recs)
    assert [v["inspection_session"] for v in vs] == ["a", "b"]
    assert vs[0]["width_mm"] == 0.32  # the later capture of session "a" wins


def test_trend_needs_three_visits():
    assert H.theil_sen_trend(H.visits_from_records([rec(0, 0.3), rec(10, 0.4)])) is None
    assert H.summarize([rec(0, 0.3), rec(10, 0.4)])["trend"] is None
    assert H.summarize([rec(0, 0.3), rec(10, 0.4), rec(20, 0.5)])["trend"] is not None


def test_clean_linear_growth_is_a_significant_widening_trend():
    recs = [rec(d, 0.30 + 0.01 * d, u=0.005) for d in (0, 10, 20, 30, 40)]
    tr = H.theil_sen_trend(H.visits_from_records(recs), level=0.90, uncertainty_kind_="standard")
    assert tr["n"] == 5 and tr["span_days"] == pytest.approx(40, abs=0.01)
    assert tr["slope_mm_per_day"] == pytest.approx(0.01, abs=1e-4)
    assert tr["slope_lo_mm_per_day"] <= 0.01 <= tr["slope_hi_mm_per_day"]
    assert tr["slope_lo_mm_per_day"] > 0
    assert tr["significant"] and tr["direction"] == "widening"
    assert tr["slope_mm_per_30d"] == pytest.approx(0.30, abs=0.01)


def test_flat_noisy_series_has_no_trend():
    ws = [0.40, 0.43, 0.38, 0.42, 0.39, 0.41]
    recs = [rec(10 * i, w, u=0.03) for i, w in enumerate(ws)]
    tr = H.theil_sen_trend(H.visits_from_records(recs), level=0.90, uncertainty_kind_="standard")
    assert not tr["significant"] and tr["direction"] == "none"
    assert tr["slope_lo_mm_per_day"] < 0 < tr["slope_hi_mm_per_day"]


def test_three_visits_with_large_uncertainty_cannot_prove_a_trend():
    recs = [rec(0, 0.30, u=0.15), rec(30, 0.40, u=0.15), rec(60, 0.50, u=0.15)]
    tr = H.theil_sen_trend(H.visits_from_records(recs), level=0.90, uncertainty_kind_="standard")
    assert tr["slope_mm_per_day"] > 0
    assert not tr["significant"]  # honest: three noisy visits do not establish growth


def test_trend_is_robust_to_one_bad_visit():
    ws = [0.30, 0.31, 0.90, 0.33, 0.34, 0.35, 0.36]  # visit 3 is a gross outlier
    recs = [rec(10 * i, w, u=0.01) for i, w in enumerate(ws)]
    tr = H.theil_sen_trend(H.visits_from_records(recs), level=0.90, uncertainty_kind_="standard")
    assert tr["slope_mm_per_day"] == pytest.approx(0.0010, abs=0.0004)  # bulk slope, not dragged by the outlier


def test_trend_is_deterministic():
    recs = [rec(10 * i, 0.3 + 0.02 * i + (0.01 if i % 2 else -0.01), u=0.01) for i in range(6)]
    vs = H.visits_from_records(recs)
    assert H.theil_sen_trend(vs) == H.theil_sen_trend(vs)


def test_visits_too_close_in_time_give_a_note_not_a_crash():
    recs = [rec(0, 0.3), rec(0.001, 0.31), rec(0.002, 0.32)]
    tr = H.theil_sen_trend(H.visits_from_records(recs))
    assert tr["significant"] is False and "too close" in tr["note"]


def test_summarize_compares_current_session_with_previous_visit():
    recs = [rec(0, 0.30, u=0.03, sess="a"), rec(14, 0.32, u=0.03, sess="b"), rec(28, 0.55, u=0.03, sess="c")]
    s = H.summarize(recs, current_session="c")
    assert s["n_visits"] == 3 and s["latest"]["session"] == "c" and s["previous"]["session"] == "b"
    assert s["change"]["significant"] and s["change"]["direction"] == "wider"
    assert s["change"]["days"] == pytest.approx(14, abs=0.01)
    assert s["change_vs_first"]["significant"]
    # looking at an older session as "current" ignores later visits in the trend and change
    s2 = H.summarize(recs, current_session="b")
    assert s2["latest"]["session"] == "b" and s2["previous"]["session"] == "a"
    assert not s2["change"]["significant"]


def test_summarize_empty_and_single():
    e = H.summarize([])
    assert e["n_visits"] == 0 and e["latest"] is None and e["change"] is None
    one = H.summarize([rec(0, 0.3)])
    assert one["n_visits"] == 1 and one["previous"] is None and one["change"] is None and one["trend"] is None
