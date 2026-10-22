import json

import pytest

from prohori import agent
from prohori.agent import ACTIONS, decide, random_decide, rules_decide

GOOD = dict(corners=24, corners_total=24, blur_var=420.0, px_per_mm=17.0, obliquity_deg=8.0,
            glare_frac=0.0, crack_px_extent=900, image_w=4000, image_h=3000)
CRACK = [{"id": "c1", "width_mm": 0.34, "uncertainty_mm": 0.06, "true_width_mm": 0.35,
          "length_mm": 80.0, "polyline_px": [[1, 2], [3, 4]]}]


def gate(*reasons):
    return {"certified": not reasons, "reasons": list(reasons)}


def obs(**kw):
    return {**GOOD, **kw}


CASES = {
    "good": (obs(), gate(), "accept"),
    "far": (obs(px_per_mm=6.0), gate("low_resolution"), "move_closer"),
    "blurry": (obs(blur_var=30.0), gate("blurry"), "reshoot_steadier"),
    "glare": (obs(glare_frac=0.2), gate("glare"), "relight"),
    "oblique": (obs(obliquity_deg=58.0), gate("oblique"), "reposition_marker"),
    "glare+oblique": (obs(glare_frac=0.15, obliquity_deg=52.0), gate("glare", "oblique"), "relight"),
    "no_board": (obs(corners=0, px_per_mm=None, obliquity_deg=None, blur_var=None),
                 gate("too_few_corners"), "reposition_marker"),
}


@pytest.mark.parametrize("name", list(CASES))
def test_rules_cases(name):
    o, g, expected = CASES[name]
    r = rules_decide(o, g, CRACK, [])
    assert r["action"] == expected, r
    assert r["policy"] == "rules" and r["model"] is None
    assert 0 < len(r["instruction"]) <= 140
    assert r["fallback_reason"] is None and r["latency_ms"] >= 0


def test_rules_instruction_mentions_number():
    r = rules_decide(*CASES["far"][:2], CRACK, [])
    assert "6" in r["instruction"] and "8" in r["instruction"]


def test_rules_glare_oblique_low_res_goes_geometry_first():
    o = obs(glare_frac=0.15, obliquity_deg=60.0, px_per_mm=4.0)
    r = rules_decide(o, gate("glare", "oblique", "low_resolution"), CRACK, [])
    assert r["action"] == "reposition_marker"


def _hist(n, action="relight", reasons=("glare",), o=None):
    return [{"observation": o or obs(glare_frac=0.2), "gate": gate(*reasons), "decision": {"action": action}}
            for _ in range(n)]


def test_rules_escalates_to_abandon():
    r = rules_decide(*CASES["glare"][:2], CRACK, _hist(3))
    assert r["action"] == "abandon_and_log"


def test_rules_widened_uncertainty_when_marginal_after_retries():
    o = obs(px_per_mm=7.5)
    r = rules_decide(o, gate("low_resolution"), CRACK, _hist(2, "move_closer", ("low_resolution",), obs(px_per_mm=7.4)))
    assert r["action"] == "accept_with_widened_uncertainty"
    # but never without a measured crack
    r2 = rules_decide(o, gate("low_resolution"), [], _hist(2, "move_closer", ("low_resolution",)))
    assert r2["action"] != "accept_with_widened_uncertainty"


def test_rules_does_not_repeat_failed_action_twice():
    o = obs(glare_frac=0.2, blur_var=40.0)
    h = _hist(2, "relight", ("glare", "blurry"), o)
    r = rules_decide(o, gate("glare", "blurry"), CRACK, h)
    assert r["action"] == "reshoot_steadier"


def test_failed_attempts_counts_trailing():
    h = _hist(1) + [{"gate": gate(), "decision": {"action": "accept"}}] + _hist(2)
    assert agent.failed_attempts(h) == 2


def test_random_is_seeded_and_valid():
    a = random_decide(GOOD, gate(), CRACK, [])
    b = random_decide(GOOD, gate(), CRACK, [])
    assert a["action"] == b["action"] and a["action"] in ACTIONS and a["policy"] == "random"
    seen = {random_decide(GOOD, gate(), CRACK, _hist(i))["action"] for i in range(40)}
    assert len(seen) > 1


# ------------------------------------------------------------------ LLM path
class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def converse(self, **kw):
        self.calls.append(kw)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def tool_resp(action="move_closer", instruction="Move closer: the board is only 6 px/mm, need 8 or more.",
              rationale="px/mm 6 < 8.", name="choose_action"):
    return {"output": {"message": {"role": "assistant", "content": [
        {"toolUse": {"toolUseId": "t1", "name": name,
                     "input": {"action": action, "instruction": instruction, "rationale": rationale}}}]}},
            "stopReason": "tool_use", "usage": {"inputTokens": 800, "outputTokens": 60, "totalTokens": 860}}


def client_error(code):
    from botocore.exceptions import ClientError
    return ClientError({"Error": {"Code": code, "Message": "x"}}, "Converse")


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.delenv("PROHORI_BEDROCK_MODEL", raising=False)
    monkeypatch.delenv("PROHORI_BEDROCK_FALLBACK_MODELS", raising=False)

    def install(*responses):
        c = FakeClient(responses)
        monkeypatch.setattr(agent, "_get_client", lambda: c)
        return c
    return install


def test_llm_happy_path(fake):
    c = fake(tool_resp())
    o, g, _ = CASES["far"]
    r = decide(o, g, CRACK, [], policy="llm")
    assert r["action"] == "move_closer" and r["policy"] == "llm"
    assert r["model"] == agent.DEFAULT_MODEL and r["fallback_reason"] is None
    assert r["input_tokens"] == 800 and r["output_tokens"] == 60
    kw = c.calls[0]
    assert kw["toolConfig"]["toolChoice"] == {"tool": {"name": "choose_action"}}
    schema = kw["toolConfig"]["tools"][0]["toolSpec"]["inputSchema"]["json"]
    assert schema["properties"]["action"]["enum"] == ACTIONS
    sent = kw["messages"][0]["content"][0]["text"]
    assert "polyline_px" not in sent and "true_width_mm" not in sent  # no ground truth / geometry leaks
    assert json.loads(sent)["current_capture"]["gate"]["reasons"] == ["low_resolution"]


def test_llm_truncates_instruction(fake):
    fake(tool_resp(instruction="Move closer " + "please " * 60))
    r = decide(*CASES["far"][:2], CRACK, [], policy="llm")
    assert r["policy"] == "llm" and len(r["instruction"]) <= 140


@pytest.mark.parametrize("bad", [
    Exception("boom"),
    client_error("ThrottlingException"),
    {"output": {"message": {"content": [{"text": "no tool"}]}}},
    tool_resp(action="dance"),
    tool_resp(action="accept"),  # accept on uncertified gate
])
def test_llm_failure_falls_back_to_rules(fake, bad):
    fake(bad)
    o, g, expected = CASES["far"]
    r = decide(o, g, CRACK, [], policy="llm")
    assert r["policy"] == "rules" and r["fallback_reason"]
    assert r["action"] == expected


def test_llm_certified_must_accept(fake):
    fake(tool_resp(action="move_closer"))
    r = decide(obs(), gate(), CRACK, [], policy="llm")
    assert r["policy"] == "rules" and r["action"] == "accept" and "guard" in r["fallback_reason"]


def test_llm_model_fallthrough(fake):
    c = fake(client_error("AccessDeniedException"), tool_resp())
    r = decide(*CASES["far"][:2], CRACK, [], policy="llm")
    assert r["policy"] == "llm" and r["model"] == "us.amazon.nova-lite-v1:0"
    assert [k["modelId"] for k in c.calls] == [agent.DEFAULT_MODEL, "us.amazon.nova-lite-v1:0"]


def test_llm_all_models_denied_falls_back(fake):
    fake(client_error("AccessDeniedException"), client_error("ValidationException"))
    r = decide(*CASES["far"][:2], CRACK, [], policy="llm")
    assert r["policy"] == "rules" and "ValidationException" in r["fallback_reason"]


def test_llm_env_models(monkeypatch):
    monkeypatch.setenv("PROHORI_BEDROCK_MODEL", "m1")
    monkeypatch.setenv("PROHORI_BEDROCK_FALLBACK_MODELS", "m2, m3")
    assert agent._models() == ["m1", "m2", "m3"]


def test_llm_with_botocore_stubber(monkeypatch):
    import boto3
    from botocore.stub import Stubber
    client = boto3.client("bedrock-runtime", region_name="us-east-1",
                          aws_access_key_id="x", aws_secret_access_key="x")
    stub = Stubber(client)
    resp = tool_resp(action="relight", instruction="Cut the glare: 20% blown out, max 5%.")
    resp["metrics"] = {"latencyMs": 100}
    stub.add_response("converse", resp)
    stub.activate()
    monkeypatch.setattr(agent, "_get_client", lambda: client)
    r = decide(*CASES["glare"][:2], CRACK, [], policy="llm")
    assert r["policy"] == "llm" and r["action"] == "relight"
    stub.assert_no_pending_responses()


def test_decide_never_raises_on_garbage():
    r = decide(None, None, None, None, policy="rules")
    assert r["action"] in ACTIONS
    r = decide({"corners": "x"}, {"reasons": 5}, [{"width_mm": "a"}], [{"gate": None}], policy="rules")
    assert r["action"] in ACTIONS
    r = decide(GOOD, gate("glare"), [], [], policy="nonsense")
    assert r["action"] in ACTIONS and r["fallback_reason"]


def test_decide_llm_without_credentials_is_safe(monkeypatch):
    def boom():
        raise RuntimeError("no creds")
    monkeypatch.setattr(agent, "_get_client", boom)
    r = decide(*CASES["blurry"][:2], CRACK, [], policy="llm")
    assert r["action"] == "reshoot_steadier" and r["policy"] == "rules" and "no creds" in r["fallback_reason"]


def test_rules_uncertified_without_reasons_means_no_crack():
    r = rules_decide(obs(), {"certified": False, "reasons": []}, [], [])
    assert r["action"] == "reposition_marker" and "crack" in r["instruction"].lower()


# ------------------------------------------------------------------ derived fields added for the P2 ablation
def test_payload_has_derived_margins_and_attempt_flags():
    o = obs(px_per_mm=7.2, blur_var=120.0)
    g = gate("low_resolution", "blurry")
    p = agent.build_user_payload(o, g, CRACK, [])
    cc = p["current_capture"]
    assert cc["board_found"] is True and cc["crack_measured"] is True and cc["all_failures_marginal"] is True
    checks = {c["check"]: c for c in cc["failing_checks"]}
    assert checks["low_resolution"]["percent_past_threshold"] == 10 and checks["blurry"]["percent_past_threshold"] == 20
    assert p["widen_now_allowed"] is False and p["abandon_now_allowed"] is False
    h = _hist(2, "move_closer", ("low_resolution",), obs(px_per_mm=7.4))
    assert agent.build_user_payload(o, g, CRACK, h)["widen_now_allowed"] is True
    h3 = _hist(3, "move_closer", ("low_resolution",), obs(px_per_mm=3.0))
    far = agent.build_user_payload(obs(px_per_mm=3.0), gate("low_resolution"), CRACK, h3)
    assert far["abandon_now_allowed"] is True and far["widen_now_allowed"] is False


def test_payload_board_not_found_has_no_fake_checks():
    o = obs(corners=2, px_per_mm=0.0, obliquity_deg=0.0, glare_frac=0.0, crack_px_extent=0, blur_var=500.0)
    cc = agent.build_user_payload(o, gate("too_few_corners"), [], [])["current_capture"]
    assert cc["board_found"] is False and cc["crack_measured"] is False
    assert "failing_checks" not in cc and "all_failures_marginal" not in cc


def test_certified_capture_never_allows_widen_or_abandon():
    p = agent.build_user_payload(obs(), gate(), CRACK, _hist(5))
    assert p["widen_now_allowed"] is False and p["abandon_now_allowed"] is False


# ------------------------------------------------------------------ deployed (CRC) gate
GATE_PARAMS = json.loads(agent.Path(agent.__file__).with_name("gate_params.json").read_text(encoding="utf-8"))


def test_guidance_table_agrees_with_gate_params():
    """GATE_GUIDANCE_PPM is quoted to the operator; it must match gate_params.json["required_px_per_mm"] (default level)."""
    req = GATE_PARAMS["required_px_per_mm"]["default"]
    assert agent.guidance_ppm(0.4) == pytest.approx(req["0.4"], abs=0.5)
    assert agent.guidance_ppm(0.5) == pytest.approx(req["0.5"], abs=0.5)
    for w in ("0.75", "1", "1.5", "2", "3"):  # "always passes" widths have no px/mm requirement
        assert req[w] == "always passes" and agent.guidance_ppm(float(w)) is None
    # 0.3 mm: the fit says "always passes" but the krkCMd recommendation (20 px/mm) is deliberately quoted instead
    assert agent.guidance_ppm(0.3) == 20.0
    assert agent.CERT_RISK_RATIO_FALLBACK == pytest.approx(agent.cert_risk_ratio({"level": GATE_PARAMS["default_level"]}), abs=2e-3)


def crc_gate(*reasons, certified=False):
    return {"certified": certified, "reasons": list(reasons), "mode": "crc", "level": "0.05",
            "cracks_certified": 1 if certified else 0, "cracks_total": 1}


def crack(width=0.5, ppm=8.0, rr=2.0, cert=False, reasons=()):
    return {"id": "C1", "width_mm": width, "uncertainty_mm": 0.1, "px_per_mm": ppm, "risk_ratio": rr,
            "certified": cert, "status": "certified" if cert else "flagged", "reasons": list(reasons),
            "interval_mm": [width - 0.1, width + 0.1]}


def crc_obs(**kw):
    return obs(**{"blur_sigma_mm": 0.08, "noise_sigma": 0.9, "crack_coverage": 1.0, "board_found": True, **kw})


def crc_decide(o, g, cr, h=None):
    r = agent.rules_policy(o, g, cr, h or [])
    assert 0 < len(r["instruction"]) <= 140, r
    assert r["policy"] == "rules"
    return r


@pytest.mark.parametrize("reason,o,expected", [
    ("too_few_corners", crc_obs(corners=9), "reposition_marker"),
    ("low_resolution", crc_obs(px_per_mm=3.0), "move_closer"),
    ("blurry", crc_obs(blur_var=40.0), "reshoot_steadier"),
    ("oblique", crc_obs(obliquity_deg=55.0), "reposition_marker"),
    ("glare", crc_obs(glare_frac=0.2), "relight"),
    ("noisy", crc_obs(noise_sigma=6.0), "relight"),
    ("low_coverage", crc_obs(crack_coverage=0.6), "reposition_marker"),
    ("mask_blowup", crc_obs(), "reshoot_steadier"),
    ("mask_holes", crc_obs(), "reshoot_steadier"),
    ("mask_fragmented", crc_obs(), "reposition_marker"),
    ("invalid_image", crc_obs(), "reposition_marker"),
])
def test_crc_reason_code_mapping(reason, o, expected):
    r = crc_decide(o, crc_gate(reason), [crack(ppm=o["px_per_mm"])])
    assert r["action"] == expected, r


def test_crc_unstable_width_and_low_confidence_split_by_cause():
    soft = crc_obs(blur_var=60.0)
    assert crc_decide(soft, crc_gate("unstable_width"), [crack()])["action"] == "reshoot_steadier"
    assert crc_decide(soft, crc_gate("low_confidence"), [crack()])["action"] == "reshoot_steadier"
    sharp_far = crc_obs(px_per_mm=4.0, blur_var=500.0)  # thin crack below its px/mm guidance
    assert crc_decide(sharp_far, crc_gate("unstable_width"), [crack(0.5, 4.0)])["action"] == "move_closer"
    assert crc_decide(sharp_far, crc_gate("low_confidence"), [crack(0.5, 4.0)])["action"] == "move_closer"
    sharp_ok = crc_obs(px_per_mm=20.0, blur_var=500.0)  # nothing to blame on distance or softness
    assert crc_decide(sharp_ok, crc_gate("low_confidence"), [crack(1.5, 20.0)])["action"] == "reshoot_steadier"


def test_crc_move_closer_quotes_px_per_mm_guidance():
    r = crc_decide(crc_obs(px_per_mm=3.0), crc_gate("low_resolution"), [crack(0.5, 3.0)])
    assert "3 px/mm" in r["instruction"] and "0.5 mm" in r["instruction"] and "about 18" in r["instruction"]
    r = crc_decide(crc_obs(px_per_mm=3.0), crc_gate("low_resolution"), [crack(0.4, 3.0)])
    assert "about 9" in r["instruction"]
    wide = crc_decide(crc_obs(px_per_mm=3.0), crc_gate("low_resolution"), [crack(1.5, 3.0)])
    assert "3 px/mm" in wide["instruction"] and "about" not in wide["instruction"]


def test_crc_compound_order():
    # 2a: glare plus few corners -> relight first, even though blur comes earlier in the plain order
    r = crc_decide(crc_obs(corners=10, glare_frac=0.2, blur_var=50.0), crc_gate("blurry", "glare"), [crack()])
    assert r["action"] == "relight"
    # 2b: oblique with any other reason -> reposition_marker, even with glare (corners fine)
    r = crc_decide(crc_obs(obliquity_deg=60.0, glare_frac=0.2), crc_gate("glare", "oblique"), [crack()])
    assert r["action"] == "reposition_marker"
    # 2c: otherwise glare, blurry, oblique, low_resolution, too_few_corners ... in that order
    r = crc_decide(crc_obs(px_per_mm=3.0, blur_var=50.0), crc_gate("low_resolution", "blurry"), [crack(0.5, 3.0)])
    assert r["action"] == "reshoot_steadier"
    r = crc_decide(crc_obs(px_per_mm=3.0, noise_sigma=6.0), crc_gate("noisy", "low_resolution"), [crack(0.5, 3.0)])
    assert r["action"] == "move_closer"


def test_crc_board_not_found_rule_2a():
    nb = obs(corners=0, px_per_mm=0.0, obliquity_deg=0.0, glare_frac=0.0, crack_px_extent=0, blur_var=500.0, board_found=False)
    g = {"certified": False, "reasons": ["too_few_corners"], "mode": "none"}
    assert crc_decide(nb, g, [])["action"] == "reposition_marker"
    assert crc_decide({**nb, "blur_var": 40.0}, g, [])["action"] == "reshoot_steadier"
    h = [{"observation": nb, "gate": g, "decision": {"action": "reposition_marker"}}]
    assert crc_decide(nb, g, [], h)["action"] == "relight"


def test_crc_accept_only_when_certified_and_mentions_flagged():
    cr = [crack(0.8, 9.0, 0.4, True), crack(0.3, 9.0, 1.4, False, ["unstable_width"])]
    g = {**crc_gate(certified=True), "cracks_certified": 1, "cracks_total": 2}
    r = crc_decide(crc_obs(), g, cr)
    assert r["action"] == "accept" and "1 of 2" in r["instruction"] and "0.80" in r["instruction"]
    for rs in (["blurry"], ["unstable_width"], ["low_confidence"], ["mask_holes"]):
        assert crc_decide(crc_obs(blur_var=40.0), crc_gate(*rs), [crack()])["action"] != "accept"
    # a certified capture can never be asked to retake, whatever the history says
    assert crc_decide(crc_obs(), g, cr, _hist(5))["action"] == "accept"


def test_crc_history_rules_widen_and_abandon():
    thr = agent.cert_risk_ratio()
    near = [crack(0.5, 8.0, thr * 1.1)]       # within 20 % of the certify level
    far = [crack(0.5, 8.0, thr * 2.0)]
    o = crc_obs(blur_var=300.0)
    h2 = _hist(2, "reshoot_steadier", ("unstable_width",), o)
    g = crc_gate("unstable_width")
    assert crc_decide(o, g, near)["action"] != "accept_with_widened_uncertainty"  # first shot
    assert crc_decide(o, g, near, h2)["action"] == "accept_with_widened_uncertainty"
    assert crc_decide(o, g, far, h2)["action"] != "accept_with_widened_uncertainty"
    assert crc_decide(o, g, [], h2)["action"] != "accept_with_widened_uncertainty"
    # 3a: widening beats abandon at the fourth failure; 3b: otherwise abandon
    h3 = _hist(3, "reshoot_steadier", ("unstable_width",), o)
    assert crc_decide(o, g, near, h3)["action"] == "accept_with_widened_uncertainty"
    assert crc_decide(o, g, far, h3)["action"] == "abandon_and_log"
    # outline-QA failures are never marginal
    assert crc_decide(o, crc_gate("mask_holes"), near, h2)["action"] != "accept_with_widened_uncertainty"
    # 3: no third identical action in a row
    o2 = crc_obs(glare_frac=0.2, blur_var=40.0)
    h = _hist(2, "relight", ("glare", "blurry"), o2)
    assert crc_decide(o2, crc_gate("glare", "blurry"), far, h)["action"] == "reshoot_steadier"


def test_crc_payload_has_failing_checks_and_marginal_flags():
    thr = agent.cert_risk_ratio()
    o = crc_obs(px_per_mm=4.0)
    cc = agent.build_user_payload(o, crc_gate("low_resolution", "unstable_width"), [crack(0.5, 4.0, thr * 1.1)], [])["current_capture"]
    checks = {c["check"]: c for c in cc["failing_checks"]}
    assert checks["low_resolution"]["px_per_mm_guidance"] == 18.0 and checks["low_resolution"]["value"] == 4.0
    assert "unstable_width" in checks and cc["all_failures_marginal"] is True and cc["percent_past_certify_level"] == 10
    assert cc["measured_cracks"][0]["interval_mm"] and cc["measured_cracks"][0]["risk_ratio"]
    assert cc["observation"]["blur_sigma_mm"] == 0.08
    far = agent.build_user_payload(o, crc_gate("low_resolution"), [crack(0.5, 4.0, thr * 3)], [])["current_capture"]
    assert far["all_failures_marginal"] is False
    p = agent.build_user_payload(o, crc_gate("unstable_width"), [crack(0.5, 4.0, thr * 1.1)], _hist(2, "move_closer", ("unstable_width",), o))
    assert p["widen_now_allowed"] is True


def test_legacy_gate_dicts_keep_legacy_behaviour():
    assert not agent._is_crc(gate("low_resolution"), CRACK)
    assert agent.rules_policy(*CASES["far"][:2], CRACK, [])["instruction"].endswith("need 8 or more.")
    assert "failing_checks" in agent.build_user_payload(*CASES["far"][:2], CRACK, [])["current_capture"]
    assert "blur_sigma_mm" not in agent.build_user_payload(*CASES["far"][:2], CRACK, [])["current_capture"]["observation"]


def test_reason_short_covers_every_code():
    assert set(agent.REASON_SHORT) == set(agent.GATE_REASON_CODES)
