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
