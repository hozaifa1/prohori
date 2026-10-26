"""Unit tests for the deterministic guardrail on LLM output (agent.validate_decision / agent._llm)."""
import json

import pytest

from prohori import agent, episodes as E
from prohori.agent import check_action, check_instruction, template_instruction, validate_decision

from test_agent import CRACK, FakeClient, GOOD, _hist, crack, crc_gate, crc_obs, gate, obs, tool_resp

REFUSED = {"tier": "refused", "tier_reasons": []}


def crc_refused(*reasons, certified_cracks=0, total=1):
    return {**crc_gate(*reasons), **REFUSED, "cracks_certified": certified_cracks, "cracks_total": total}


def tier_gate(tier, tier_reasons=(), certified_cracks=1, total=2):
    return {**crc_gate(certified=tier != "refused"), "tier": tier, "tier_reasons": list(tier_reasons),
            "cracks_certified": certified_cracks, "cracks_total": total}


def issues(action, text, o, g, cr, h=None):
    return check_instruction(action, text, o, g, cr, h or [])[0]


# ------------------------------------------------------------------ numbers
def test_number_must_match_measurement_with_rounding():
    o, g, cr = crc_obs(px_per_mm=2.71), crc_refused("low_resolution"), [crack(0.5, 2.71, 3.0)]
    assert not issues("move_closer", "Move closer: only 2.7 px/mm here, a 0.5 mm crack needs about 10.", o, g, cr)
    assert not issues("move_closer", "Move closer: only 2.71 px/mm here, a 0.5 mm crack needs about 10.", o, g, cr)
    assert not issues("move_closer", "Move closer: only 3 px/mm here, a 0.5 mm crack needs about 10.", o, g, cr)  # rounds to 3
    bad = issues("move_closer", "Move closer: only 2.5 px/mm here, a 0.5 mm crack needs about 10.", o, g, cr)
    assert any("2.5 px/mm" in x for x in bad)


def test_review_example_wrong_requirement_is_caught():
    # "a 1.58 mm crack needs about 2.5 px/mm" next to a measured 2.71 px/mm (a wide crack has no px/mm requirement)
    o, g, cr = crc_obs(px_per_mm=2.71), crc_refused("low_resolution"), [crack(1.58, 2.71, 3.0)]
    bad = issues("move_closer", "Move closer: a 1.58 mm crack needs about 2.5 px/mm, you have 2.71.", o, g, cr)
    assert any(x.startswith("cites 2.5 px/mm") for x in bad) and not any(x.startswith(("cites 2.71", "cites 1.58")) for x in bad)
    # the guidance table value for the measured width is allowed, another one is not
    thin = [crack(0.3, 2.71, 3.0)]
    assert not issues("move_closer", "Move closer: a 0.3 mm crack needs about 20 px/mm, you have 2.7.", o, g, thin)
    assert issues("move_closer", "Move closer: a 0.3 mm crack needs about 10 px/mm, you have 2.7.", o, g, thin)


def test_width_unit_and_units_are_kept_apart():
    o, g, cr = crc_obs(px_per_mm=9.0, glare_frac=0.04, obliquity_deg=30.0), crc_refused("glare"), [crack(0.62, 9.0, 3.0)]
    assert not issues("relight", "Cut the glare: 4% is blown out. Crack is 0.62 mm.", o, g, cr)
    assert issues("relight", "Cut the glare: 9% is blown out.", o, g, cr)          # 9 is a px/mm value, not a glare percent
    assert issues("relight", "Cut the glare: tilt is 9 degrees.", o, g, cr)         # 9 px/mm is not an angle
    assert not issues("relight", "Cut the glare: tilt is 30 degrees, shade the wall for 3 seconds.", o, g, cr)  # advice units ignored


def test_counts_and_advice_numbers():
    o, g = crc_obs(corners=9), crc_refused("too_few_corners")
    assert not issues("reposition_marker", "Show the whole board: only 9 of 24 corners found.", o, g, [crack()])
    assert issues("reposition_marker", "Show the whole board: only 12 of 24 corners found.", o, g, [crack()])
    assert issues("reposition_marker", "Retake it, about 3 more shots to go.", o, g, [crack()])  # invented count


def test_legacy_thresholds_are_allowed_only_for_the_legacy_gate():
    g = gate("low_resolution")
    assert not issues("move_closer", "Move closer: the board is only 6 px/mm, need 8 or more.", obs(px_per_mm=6.0), g, CRACK)
    assert issues("move_closer", "Move closer: the board is only 6 px/mm, need 12 or more.", obs(px_per_mm=6.0), g, CRACK)
    # a refit (CRC) gate has no single-feature thresholds: a quoted 150 sharpness limit is fine only as the "soft" guidance value
    assert issues("reshoot_steadier", "Hold steady: sharpness is 90, need 200 or more.", crc_obs(blur_var=90.0), crc_refused("blurry"), [crack()])


def test_history_values_may_be_compared():
    h = _hist(1, "move_closer", ("low_resolution",), crc_obs(px_per_mm=3.1))
    assert not issues("move_closer", "Closer still: 4.2 px/mm now, was 3.1.", crc_obs(px_per_mm=4.2), crc_refused("low_resolution"), [crack(0.5, 4.2)], h)


# ------------------------------------------------------------------ certification claims
def test_all_cracks_certified_claim_must_be_true():
    g = {**crc_refused("blurry"), "cracks_certified": 3, "cracks_total": 8}
    cr = [crack() for _ in range(8)]
    assert any("3 of 8" in x for x in issues("move_closer", "All cracks certified, move closer to finish.", crc_obs(), g, cr))
    assert not issues("move_closer", "3 of 8 cracks certified; move closer to the rest.", crc_obs(), {**g, "certified": True, "tier": "certified"}, cr)
    assert any("says" in x for x in issues("move_closer", "Certified 5 of 8 cracks. Move closer.", crc_obs(), {**g, "certified": True, "tier": "certified"}, cr))
    assert any("8 cracks" in x or "of 9" in x for x in issues("move_closer", "Certified 3 of 9 cracks. Move closer.", crc_obs(), {**g, "certified": True, "tier": "certified"}, cr))
    ok = {**g, "certified": True, "tier": "certified", "cracks_certified": 8}
    assert not issues("accept", "All 8 cracks certified. Move on.", crc_obs(), ok, cr)
    assert issues("accept", "No cracks certified. Move on.", crc_obs(), ok, cr)


def test_tier_words_must_match_the_gate():
    cr = [crack(0.8, 9.0, 0.4, True)]
    refused = crc_refused("blurry")
    assert any("certified" in x for x in issues("reshoot_steadier", "This capture is certified, hold steady anyway.", crc_obs(), refused, cr))
    # "certified" as a purpose or a negation is not a claim
    assert not issues("reshoot_steadier", "Hold steady and retake: sharpness is 40, needed to get certified.", crc_obs(blur_var=40.0), refused, cr)
    assert not issues("reshoot_steadier", "Not certified yet: hold steady, sharpness is 40.", crc_obs(blur_var=40.0), refused, cr)
    ind = tier_gate("indicative", ["blurry"])
    assert any("indicative" in x for x in issues("accept", "Capture certified. Move on.", crc_obs(), ind, cr))
    assert not issues("accept", "Indicative reading, usable with its range of 0.7 to 0.9 mm. Move on.", crc_obs(), ind, cr)
    assert not issues("move_closer", "Usable as is. For a certified reading: move closer, 6.5 px/mm now.", crc_obs(px_per_mm=6.5), tier_gate("indicative", ["low_resolution"]), cr)
    cert = tier_gate("certified")
    assert any("indicative" in x for x in issues("accept", "Indicative reading, move on.", crc_obs(), cert, cr))
    assert any("not certified" in x for x in issues("accept", "Not certified but fine, move on.", crc_obs(), cert, cr))


def test_instruction_must_cite_a_measured_number():
    o, g = crc_obs(blur_var=40.0), crc_refused("blurry")
    assert any("no measured number" in i for i in issues("reshoot_steadier", "Hold steady and retake.", o, g, [crack()]))
    assert not any("no measured number" in i for i in issues("reshoot_steadier", "Hold steady and retake: sharpness is 40.", o, g, [crack()]))
    # a constant alone (the 150 guidance value) is not a measurement
    assert any("no measured number" in i for i in issues("reshoot_steadier", "Hold steady: you need 150.", o, g, [crack()]))


def test_instruction_must_describe_the_chosen_action():
    o, g = crc_obs(), crc_refused("blurry")
    assert issues("reshoot_steadier", "Walk to the next crack.", o, g, [crack()])


# ------------------------------------------------------------------ actions
def test_accept_only_when_certified():
    o, cr = crc_obs(), [crack()]
    assert check_action("accept", o, crc_refused("blurry"), cr, [])
    assert check_action("accept", o, tier_gate("refused"), cr, [])
    assert not check_action("accept", o, tier_gate("certified"), cr, [])
    assert check_action("move_closer", o, tier_gate("certified"), cr, [])
    assert check_action("accept", o, gate("blurry"), CRACK, [])


def test_indicative_gets_one_retake_that_fixes_the_first_tier_reason():
    o, cr = crc_obs(px_per_mm=6.0), [crack()]
    g = tier_gate("indicative", ["low_resolution"])
    assert not check_action("accept", o, g, cr, [])
    assert not check_action("move_closer", o, g, cr, [])
    assert check_action("relight", o, g, cr, [])
    assert check_action("abandon_and_log", o, g, cr, [])
    assert check_action("accept_with_widened_uncertainty", o, g, cr, [])
    again = _hist(1, "move_closer", ("low_resolution",), o)
    again[0]["gate"] = g
    assert check_action("move_closer", o, g, cr, again)       # second indicative capture in a row: accept only
    assert not check_action("accept", o, g, cr, again)


def test_widen_and_abandon_flags():
    thr = agent.cert_risk_ratio()
    near, far = [crack(0.5, 8.0, thr * 1.1)], [crack(0.5, 8.0, thr * 2.0)]
    o = crc_obs(blur_var=300.0)
    g = crc_refused("unstable_width")
    h2 = _hist(2, "reshoot_steadier", ("unstable_width",), o)
    h3 = _hist(3, "reshoot_steadier", ("unstable_width",), o)
    assert check_action("accept_with_widened_uncertainty", o, g, near, [])     # first shot: not allowed
    assert not check_action("accept_with_widened_uncertainty", o, g, near, h2)
    assert check_action("reshoot_steadier", o, g, near, h2)                    # 3a: must widen when allowed
    assert check_action("abandon_and_log", o, g, far, h2)                      # 3b: not yet
    assert not check_action("abandon_and_log", o, g, far, h3)
    assert check_action("reshoot_steadier", o, g, far, h3)                     # 3b: must abandon when allowed
    assert not check_action("accept_with_widened_uncertainty", o, g, near, h3)  # 3a beats 3b


def test_board_not_found_chain():
    nb = crc_obs(corners=2, px_per_mm=0.0, obliquity_deg=0.0, glare_frac=0.0, blur_var=400.0, board_found=False)
    g = crc_refused("too_few_corners")
    assert not check_action("reposition_marker", nb, g, [], [])
    assert check_action("reshoot_steadier", nb, g, [], [])
    assert check_action("move_closer", nb, g, [], [])
    soft = {**nb, "blur_var": 40.0}
    assert not check_action("reshoot_steadier", soft, g, [], [])
    assert any("reposition_marker" in x for x in check_action("reposition_marker", soft, g, [], []))  # the review's example
    h = _hist(1, "reposition_marker", ("too_few_corners",), nb)
    assert not check_action("relight", nb, g, [], h)
    assert check_action("reposition_marker", nb, g, [], h)


def test_compound_ordering_rules():
    cr = [crack()]
    # 2a: glare while few corners are found -> relight first
    o = crc_obs(corners=10, glare_frac=0.2, blur_var=50.0)
    g = crc_refused("blurry", "glare")
    assert not check_action("relight", o, g, cr, [])
    assert check_action("reshoot_steadier", o, g, cr, [])
    # 2b: oblique together with any other reason -> reposition_marker first
    o = crc_obs(obliquity_deg=60.0, px_per_mm=4.0)
    g = crc_refused("low_resolution", "oblique")
    assert not check_action("reposition_marker", o, g, [crack(0.5, 4.0)], [])
    assert check_action("move_closer", o, g, [crack(0.5, 4.0)], [])
    # 2c: independent reasons -> any action that fixes one of them
    o = crc_obs(px_per_mm=4.0, blur_var=50.0)
    g = crc_refused("low_resolution", "blurry")
    assert not check_action("move_closer", o, g, [crack(0.5, 4.0)], [])
    assert not check_action("reshoot_steadier", o, g, [crack(0.5, 4.0)], [])
    assert check_action("relight", o, g, [crack(0.5, 4.0)], [])
    # no reason at all = no crack found
    assert not check_action("reposition_marker", crc_obs(), crc_refused(), [], [])
    assert check_action("relight", crc_obs(), crc_refused(), [], [])


def test_legacy_gate_actions():
    assert not check_action("move_closer", obs(px_per_mm=6.0), gate("low_resolution"), CRACK, [])
    assert check_action("relight", obs(px_per_mm=6.0), gate("low_resolution"), CRACK, [])
    assert check_action("reshoot_steadier", obs(glare_frac=0.15, obliquity_deg=52.0), gate("glare", "oblique"), CRACK, [])


# ------------------------------------------------------------------ consistency with the existing policies
def _walk(policy, split="dev", n=40):
    for seed, klass in E.split_episodes(split, n):
        tr = E.run_episode(seed, klass, policy, dict(agent.GATE_THRESHOLDS))
        hist = []
        for s in tr["steps"]:
            if "action" not in s:
                continue
            yield s, hist
            hist.append({"observation": s["observation"], "gate": s["gate"], "cracks": s["cracks"], "decision": s["decision"]})


def test_label_policy_never_violates_the_action_check():
    """P* is the pre-registered labelling rule; the action check is derived from the same prompt rules."""
    n = 0
    for s, hist in _walk(lambda o, g, c, h: E.oracle_decide(o, g, c, h)):
        assert not check_action(s["action"], s["observation"], s["gate"], s["cracks"], hist), (s["observation"], s["gate"], s["action"])
        n += 1
    assert n > 100


def test_rules_policy_text_is_always_faithful_and_templates_are_clean():
    seen = 0
    for s, hist in _walk(lambda o, g, c, h: agent.rules_decide(o, g, c, h)):
        d = s["decision"]
        iv, _ = check_instruction(d["action"], d["instruction"], s["observation"], s["gate"], s["cracks"], hist)
        iv = [i for i in iv if not i.startswith("cites no measured number")]   # P1's frozen widen text has no number
        assert not iv, (d["instruction"], iv)
        for a in agent.ACTIONS:
            if not check_action(a, s["observation"], s["gate"], s["cracks"], hist):
                t = template_instruction(a, s["observation"], s["gate"], s["cracks"], hist)
                iv, st = check_instruction(a, t, s["observation"], s["gate"], s["cracks"], hist)
                assert not iv, (a, t, iv)
                seen += 1
    assert seen > 100


@pytest.mark.parametrize("reason", list(agent.GATE_REASON_CODES))
def test_crc_templates_pass_the_validator(reason):
    o = crc_obs(corners=14, px_per_mm=3.0, blur_var=60.0, glare_frac=0.12, noise_sigma=6.0, crack_coverage=0.6, obliquity_deg=20.0)
    g = crc_refused(reason, certified_cracks=0, total=2)
    cr = [crack(0.5, 3.0, 2.5), crack(1.2, 3.0, 4.0)]
    for a in agent.ACTIONS:
        if check_action(a, o, g, cr, []):
            continue
        t = template_instruction(a, o, g, cr, [])
        assert not check_instruction(a, t, o, g, cr, [])[0], (reason, a, t)


def test_certified_templates_pass_the_validator():
    cr = [crack(0.8, 9.0, 0.4, True), crack(0.3, 9.0, 1.4, False, ["unstable_width"])]
    for tier in ("certified", "indicative"):
        g = tier_gate(tier, ["low_resolution"] if tier == "indicative" else [])
        o = crc_obs(px_per_mm=6.0)
        for a in ("accept", "move_closer"):
            if check_action(a, o, g, cr, []):
                continue
            t = template_instruction(a, o, g, cr, [])
            assert not check_instruction(a, t, o, g, cr, [])[0], (tier, a, t)


# ------------------------------------------------------------------ the guarded LLM call
@pytest.fixture
def fake(monkeypatch, tmp_path):
    monkeypatch.setenv("PROHORI_DATA_DIR", str(tmp_path))   # private daily-cap counter
    monkeypatch.delenv("PROHORI_BEDROCK_MODEL", raising=False)
    monkeypatch.delenv("PROHORI_BEDROCK_FALLBACK_MODELS", raising=False)
    monkeypatch.delenv("PROHORI_GUARDRAIL", raising=False)

    def install(*responses):
        c = FakeClient(responses)
        monkeypatch.setattr(agent, "_get_client", lambda: c)
        return c
    return install


FAR = (obs(px_per_mm=6.0), gate("low_resolution"))
GOOD_TEXT = "Move closer: the board is only 6 px/mm, need 8 or more."


def test_clean_answer_costs_one_call_and_logs_no_violation(fake):
    c = fake(tool_resp(instruction=GOOD_TEXT))
    r = agent.decide(*FAR, CRACK, [], policy="llm")
    assert len(c.calls) == 1 and r["llm_calls"] == 1
    assert r["guardrail"]["violations"] == [] and r["guardrail"]["repaired"] is False and r["guardrail"]["reask"] is False
    assert r["instruction"] == GOOD_TEXT


def test_violating_instruction_is_reasked_once_and_fixed(fake):
    c = fake(tool_resp(instruction="Move closer: the board is only 3 px/mm, need 8 or more."), tool_resp(instruction=GOOD_TEXT))
    r = agent.decide(*FAR, CRACK, [], policy="llm")
    assert len(c.calls) == 2 and r["policy"] == "llm" and r["instruction"] == GOOD_TEXT
    g = r["guardrail"]
    assert g["reask"] and g["repaired"] is False and g["final_violations"] == [] and any("3 px/mm" in v for v in g["violations"])
    assert r["input_tokens"] == 1600 and r["output_tokens"] == 120   # tokens of both calls are counted
    # the second request lists the violations and carries the first answer
    msgs = c.calls[1]["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert "3 px/mm" in msgs[2]["content"][0]["text"]


def test_still_violating_instruction_is_replaced_by_the_rules_template(fake):
    bad = "Move closer: the board is only 3 px/mm, need 8 or more."
    c = fake(tool_resp(instruction=bad), tool_resp(instruction="Move closer, only 4 px/mm."))
    r = agent.decide(*FAR, CRACK, [], policy="llm")
    assert len(c.calls) == 2 and r["policy"] == "llm" and r["action"] == "move_closer"
    assert r["instruction"] == agent.rules_decide(*FAR, CRACK, [])["instruction"]
    assert r["guardrail"]["repaired"] is True and r["guardrail"]["final_violations"]
    assert r["fallback_reason"] is None


def test_violating_action_after_reask_falls_back_to_rules_with_the_log(fake):
    fake(tool_resp(action="relight", instruction="Cut the glare."), tool_resp(action="relight", instruction="Cut the glare."))
    r = agent.decide(*FAR, CRACK, [], policy="llm")
    assert r["policy"] == "rules" and r["action"] == "move_closer" and r["fallback_reason"].startswith("GuardrailReject: guard")
    assert r["guardrail"]["action_rejected"] is True and r["guardrail"]["violations"]


def test_reask_can_fix_the_action(fake):
    c = fake(tool_resp(action="relight", instruction="Cut the glare."), tool_resp(instruction=GOOD_TEXT))
    r = agent.decide(*FAR, CRACK, [], policy="llm")
    assert r["policy"] == "llm" and r["action"] == "move_closer" and len(c.calls) == 2 and r["guardrail"]["final_violations"] == []


def test_reask_failure_uses_the_first_answer_when_its_action_is_fine(fake):
    fake(tool_resp(instruction="Move closer: the board is only 3 px/mm."), RuntimeError("timeout"))
    r = agent.decide(*FAR, CRACK, [], policy="llm")
    assert r["policy"] == "llm" and "reask_error" in r["guardrail"] and r["guardrail"]["repaired"] is True
    assert "6 px/mm" in r["instruction"]


def test_bad_rationale_is_withheld(fake):
    fake(tool_resp(instruction=GOOD_TEXT, rationale="The board is at 3 px/mm."))
    r = agent.decide(*FAR, CRACK, [], policy="llm")
    assert r["guardrail"]["rationale_withheld"] is True and "3 px/mm" not in r["rationale"]


def test_guardrail_can_be_switched_off(fake):
    c = fake(tool_resp(instruction="Move closer: the board is only 3 px/mm."))
    r = agent.decide(*FAR, CRACK, [], policy="llm", guardrail=False)
    assert len(c.calls) == 1 and "guardrail" not in r and r["instruction"].endswith("3 px/mm.")


def test_rules_policy_has_no_guardrail_field():
    assert "guardrail" not in agent.decide(*FAR, CRACK, [], policy="rules")


def test_guardrail_dict_is_json_serialisable(fake):
    fake(tool_resp(instruction="All cracks certified."), tool_resp(instruction="Move closer."))
    r = agent.decide(*FAR, CRACK, [], policy="llm")
    json.dumps(r)


def test_number_free_rationale_is_kept(fake):
    fake(tool_resp(instruction=GOOD_TEXT, rationale="The board is too far away."))
    r = agent.decide(*FAR, CRACK, [], policy="llm")
    assert r["guardrail"]["rationale_withheld"] is False and r["rationale"] == "The board is too far away."
