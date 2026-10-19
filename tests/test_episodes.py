import collections
import json

import numpy as np
import pytest

from prohori import agent, episodes as E

T = dict(agent.GATE_THRESHOLDS)
GOOD = dict(corners=24, corners_total=24, blur_var=420.0, px_per_mm=17.0, obliquity_deg=8.0,
            glare_frac=0.0, crack_px_extent=900, image_w=4000, image_h=3000)
CRACK = [{"id": "c1", "width_mm": 0.34, "uncertainty_mm": 0.06, "length_mm": 80.0}]


def gate(*reasons, certified=None):
    return {"certified": (not reasons) if certified is None else certified, "reasons": list(reasons)}


def obs(**kw):
    return {**GOOD, **kw}


def hist(n, action="move_closer", reasons=("low_resolution",), o=None):
    return [{"observation": o or obs(), "gate": gate(*reasons), "cracks": CRACK, "decision": {"action": action}}
            for _ in range(n)]


# ------------------------------------------------------------------ splits
def test_split_blocks_are_balanced_and_deterministic():
    for split in ("dev", "test"):
        eps = E.split_episodes(split)
        assert eps == E.split_episodes(split)
        block = sum(E.BLOCKS[split].values())
        first = collections.Counter(k for _, k in eps[:block])
        assert dict(first) == E.BLOCKS[split]
    test = collections.Counter(k for _, k in E.split_episodes("test"))
    assert test == {"S": 20, "X": 20, "C2": 12, "C3": 16, "H": 16, "M": 16}
    assert sum(test[k] for k in E.COMPOUND) == 48
    dev_seeds = {s for s, _ in E.split_episodes("dev")}
    test_seeds = {s for s, _ in E.split_episodes("test")}
    check_seeds = {s for s, _ in E.split_episodes("check")}
    assert not (dev_seeds & test_seeds) and not (check_seeds & (dev_seeds | test_seeds))


# ------------------------------------------------------------------ initial states
@pytest.mark.parametrize("klass", E.CLASSES)
def test_initial_states_match_class(klass):
    for seed in range(500, 540):
        st = E.initial_state(seed, klass, T)
        n = len(st.causes)
        if klass == "S":
            assert n == 1
        elif klass in ("X", "C2"):
            assert n == 2
        elif klass == "C3":
            assert n == 3
        if klass == "X":
            assert tuple(st.causes) in E.CONFLICT_PAIRS or tuple(reversed(st.causes)) in E.CONFLICT_PAIRS
        if klass == "C2":
            assert tuple(st.causes) not in E.CONFLICT_PAIRS and tuple(reversed(st.causes)) not in E.CONFLICT_PAIRS
        if klass == "H":
            assert st.kind in E.HOPELESS_KINDS
        if klass == "M":
            assert T["min_px_per_mm"] * 0.85 <= st.ppm_cap <= T["min_px_per_mm"] * 0.97
        if "glare" in st.causes:
            assert st.glare > T["max_glare_frac"]
        if "oblique" in st.causes:
            assert st.theta > T["max_obliquity_deg"]
        if "blur" in st.causes:
            assert st.blur < T["min_blur_var"]


# ------------------------------------------------------------------ observation model
def test_capture_reproduces_real_pipeline_blind_spot():
    """Board lost -> px/mm, obliquity, glare and crack extent are all zero and the only reason is too_few_corners."""
    st = E.initial_state(1, "S", T)
    st.vis = 0.1
    st.glare = 0.4
    o, g, c = E.capture(st, np.random.default_rng(0), T)
    assert o["corners"] < E.MIN_FOUND_CORNERS
    assert o["px_per_mm"] == 0 and o["obliquity_deg"] == 0 and o["glare_frac"] == 0 and o["crack_px_extent"] == 0
    assert g == {"certified": False, "reasons": ["too_few_corners"]} and c == []


def test_gate_matches_thresholds_and_certification_needs_a_crack():
    st = E.State(ppm0=15.0, theta=5.0, blur=400.0, glare=0.0, vis=1.0, framed=True, dim=False)
    o, g, c = E.capture(st, np.random.default_rng(3), T)
    assert g["certified"] and g["reasons"] == [] and c
    st.framed = False
    o, g, c = E.capture(st, np.random.default_rng(3), T)
    assert not g["certified"] and g["reasons"] == [] and c == []
    st = E.State(ppm0=15.0, theta=5.0, blur=400.0, glare=0.2, vis=1.0, framed=True, dim=False)
    o, g, c = E.capture(st, np.random.default_rng(3), T)
    assert "glare" in g["reasons"] or o["corners"] < E.MIN_FOUND_CORNERS


def test_tilt_lowers_observed_scale():
    flat = E.State(ppm0=12.0, theta=0.0, blur=400.0, glare=0.0, vis=1.0, framed=True, dim=False)
    tilted = E.State(ppm0=12.0, theta=60.0, blur=400.0, glare=0.0, vis=1.0, framed=True, dim=False)
    a = np.mean([E.capture(flat, np.random.default_rng(i), T)[0]["px_per_mm"] for i in range(30)])
    b = np.mean([E.capture(tilted, np.random.default_rng(i), T)[0]["px_per_mm"] for i in range(30)])
    assert b < 0.8 * a


def test_gate_thresholds_are_parameterised():
    st = E.State(ppm0=15.0, theta=5.0, blur=400.0, glare=0.0, vis=1.0, framed=True, dim=False)
    strict = {**T, "min_px_per_mm": 40.0}
    _, g, _ = E.capture(st, np.random.default_rng(1), strict)
    assert "low_resolution" in g["reasons"]
    ep = E.initial_state(7, "S", strict)
    assert ep is not None


# ------------------------------------------------------------------ transitions
def test_transitions_do_not_mutate_and_respect_caps():
    st = E.State(ppm0=3.0, theta=5.0, blur=100.0, glare=0.3, vis=0.2, framed=True, dim=True,
                 glare_susc=0.3, ppm_cap=5.0, glare_floor=0.2, vis_cap=0.25)
    before = dict(st.__dict__)
    for a in agent.ACTIONS:
        for i in range(40):
            n = E.transition(st, a, np.random.default_rng([i, E.ACTION_ID[a]]), T)
            assert n.ppm0 <= 5.0 + 1e-9 and n.glare >= 0.2 - 1e-9 and n.vis <= 0.25 + 1e-9
    assert st.__dict__ == before


def test_actions_do_what_they_say():
    base = E.State(ppm0=4.0, theta=60.0, blur=40.0, glare=0.3, vis=0.2, framed=False, dim=False, glare_susc=0.3)
    ok = lambda a: [E.transition(base, a, np.random.default_rng([i, E.ACTION_ID[a]]), T) for i in range(60)]  # noqa: E731
    assert np.mean([s.ppm0 > 4.0 for s in ok("move_closer")]) > 0.8
    assert np.mean([s.blur > 100 for s in ok("reshoot_steadier")]) > 0.8
    assert np.mean([s.glare < 0.05 for s in ok("relight")]) > 0.8
    rep = ok("reposition_marker")
    assert np.mean([s.theta < 40 and s.framed and s.vis > 0.85 for s in rep]) > 0.8


def test_relight_in_dim_light_can_cost_sharpness():
    st = E.State(ppm0=12.0, theta=5.0, blur=300.0, glare=0.3, vis=1.0, framed=True, dim=True)
    out = [E.transition(st, "relight", np.random.default_rng([i, E.ACTION_ID["relight"]]), T).blur for i in range(200)]
    assert min(out) < 250 and max(out) == 300.0  # some runs lose sharpness, none gain
    st.dim = False
    out = [E.transition(st, "relight", np.random.default_rng([i, E.ACTION_ID["relight"]]), T).blur for i in range(100)]
    assert set(out) == {300.0}


def test_moving_too_close_loses_the_board():
    st = E.State(ppm0=60.0, theta=3.0, blur=400.0, glare=0.0, vis=1.0, framed=True, dim=False)
    o, g, _ = E.capture(st, np.random.default_rng(0), T)
    assert o["corners"] < T["min_corners"] and not g["certified"]


# ------------------------------------------------------------------ labelling rule
def test_label_rule_cases():
    A = lambda o, g, c=CRACK, h=(): E.label(o, g, c, list(h), T)  # noqa: E731
    assert A(obs(), gate()) == ({"accept"}, "accept")
    assert A(obs(px_per_mm=5.0), gate("low_resolution"))[0] == {"move_closer"}
    assert A(obs(blur_var=40.0), gate("blurry"))[0] == {"reshoot_steadier"}
    assert A(obs(glare_frac=0.2), gate("glare"))[0] == {"relight"}
    assert A(obs(obliquity_deg=60.0), gate("oblique"))[0] == {"reposition_marker"}
    # independent causes: either fix is acceptable, the larger exceedance is primary
    acc, prim = A(obs(blur_var=20.0, px_per_mm=7.0), gate("low_resolution", "blurry"))
    assert acc == {"move_closer", "reshoot_steadier"} and prim == "reshoot_steadier"
    # tilt is upstream
    assert A(obs(obliquity_deg=60.0, blur_var=20.0), gate("blurry", "oblique"))[0] == {"reposition_marker"}
    # glare hiding the board comes first, glare that is not hiding it yields to geometry
    assert A(obs(glare_frac=0.2, corners=9, obliquity_deg=60.0), gate("glare", "oblique"))[0] == {"relight"}
    assert A(obs(glare_frac=0.2, corners=22, obliquity_deg=60.0), gate("glare", "oblique"))[0] == {"reposition_marker"}


def test_label_rule_board_not_found_chain_and_blur_split():
    nb = obs(corners=2, px_per_mm=0.0, obliquity_deg=0.0, glare_frac=0.0, crack_px_extent=0, blur_var=500.0)
    g = gate("too_few_corners")
    assert E.label(nb, g, [], [], T)[0] == {"reposition_marker"}
    assert E.label(nb, g, [], hist(1, "reposition_marker", ("too_few_corners",)), T)[0] == {"relight"}
    assert E.label({**nb, "blur_var": 25.0}, g, [], [], T)[0] == {"reshoot_steadier"}


def test_label_rule_escalation_and_widened():
    o = obs(px_per_mm=7.5)
    g = gate("low_resolution")
    assert E.label(o, g, CRACK, hist(1), T)[0] == {"move_closer"}
    assert E.label(o, g, CRACK, hist(2), T)[0] == {"accept_with_widened_uncertainty"}
    assert E.label(o, g, [], hist(2), T)[0] == {"move_closer"}          # no crack, no widening
    far = obs(px_per_mm=3.0)
    assert E.label(far, g, CRACK, hist(2), T)[0] == {"move_closer"}      # not marginal
    assert E.label(far, g, CRACK, hist(3), T)[0] == {"abandon_and_log"}
    assert E.label(obs(), gate(), CRACK, hist(5), T)[0] == {"accept"}   # certified beats everything
    assert E.label(obs(), gate(certified=False), [], [], T)[0] == {"reposition_marker"}  # board found, no crack


# ------------------------------------------------------------------ episodes
def test_episode_is_deterministic_and_jsonable():
    pol = lambda o, g, c, h: E.oracle_decide(o, g, c, h, T)  # noqa: E731
    a = E.run_episode(900003, "C3", pol, T)
    b = E.run_episode(900003, "C3", pol, T)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert a["outcome"] in ("certified", "abandoned", "widened", "timeout")
    assert a["n_actions"] <= E.T_MAX


def test_common_random_numbers_same_choice_same_luck():
    """Two policies that make the same first choice see the same next capture."""
    fixed = lambda o, g, c, h: {"action": "reposition_marker"}  # noqa: E731
    other = lambda o, g, c, h: {"action": "reposition_marker" if not h else "relight"}  # noqa: E731
    a = E.run_episode(900010, "C3", fixed, T)
    b = E.run_episode(900010, "C3", other, T)
    assert a["steps"][0]["observation"] == b["steps"][0]["observation"]
    assert a["steps"][1]["observation"] == b["steps"][1]["observation"]


def test_terminal_outcomes():
    ab = E.run_episode(900011, "S", lambda o, g, c, h: {"action": "abandon_and_log"}, T)
    assert ab["outcome"] == "abandoned" and ab["n_actions"] == 1
    # accepting an uncertified capture is a wasted turn, never a success
    acc = E.run_episode(900011, "H", lambda o, g, c, h: {"action": "accept"}, T)
    assert acc["outcome"] == "timeout" and acc["n_actions"] == E.T_MAX
    # widened needs a crack: with no crack measured it is also a wasted turn
    nocrack = E.run_episode(900011, "H", lambda o, g, c, h: {"action": "accept_with_widened_uncertainty"}, T)
    assert nocrack["outcome"] in ("widened", "timeout")
    if nocrack["outcome"] == "widened":
        assert nocrack["steps"][-1]["cracks"]


def test_oracle_recovers_singles_and_catches_hopeless():
    pol = lambda o, g, c, h: E.oracle_decide(o, g, c, h, T)  # noqa: E731
    eps = E.split_episodes("check", 100)
    res = collections.defaultdict(list)
    for s, k in eps:
        res[k].append(E.run_episode(s, k, pol, T))
    single = np.mean([r["outcome"] == "certified" and r["outcome_idx"] <= 3 for r in res["S"]])
    assert single >= 0.9
    assert np.mean([r["outcome"] == "abandoned" for r in res["H"]]) >= 0.85
    assert np.mean([r["outcome"] == "widened" for r in res["M"]]) >= 0.7
    assert all(r["outcome"] != "certified" for r in res["H"])


def test_random_policy_is_much_worse():
    eps = [e for e in E.split_episodes("check", 100) if e[1] in E.RECOVERABLE]
    orc = np.mean([E.run_episode(s, k, lambda o, g, c, h: E.oracle_decide(o, g, c, h, T), T)["outcome"] == "certified" for s, k in eps])
    rnd = np.mean([E.run_episode(s, k, lambda o, g, c, h, s=s: agent.random_decide(o, g, c, h, seed=s), T)["outcome"] == "certified" for s, k in eps])
    assert rnd < orc - 0.3


def test_calibration_against_real_panel():
    cal = E.calibration_report(n=3000)
    assert cal["n_real"] == 22
    assert cal["px_per_mm"]["ks_p"] > 0.05 and cal["obliquity_deg"]["ks_p"] > 0.05
    assert abs(cal["px_per_mm"]["sim_median"] - cal["px_per_mm"]["real_median"]) < 1.5
