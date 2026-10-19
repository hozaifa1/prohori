"""Engineer escalation + human approval (src/prohori/escalate.py), SNS mocked with moto. No AWS calls."""
import json

import pytest

from prohori import escalate as E
from prohori import store

moto = pytest.importorskip("moto")
boto3 = pytest.importorskip("boto3")
from moto import mock_aws  # noqa: E402

CRACK = {"id": 1, "width_mm": 0.52, "uncertainty_mm": 0.06}
OBS = {"px_per_mm": 11.4}
SUMMARY = {
    "level": 0.9, "uncertainty_kind": "standard",
    "previous": {"width_mm": 0.30}, "latest": {"width_mm": 0.52},
    "change": {"delta_mm": 0.22, "days": 14.0, "threshold_mm": 0.14, "significant": True, "direction": "wider",
               "verdict": "wider than last visit, beyond measurement uncertainty"},
    "trend": {"n": 4, "slope_mm_per_30d": 0.11, "slope_lo_mm_per_30d": 0.03, "slope_hi_mm_per_30d": 0.2,
              "significant": True, "direction": "widening"},
}
DECISION = {"action": "accept", "instruction": "Accept."}


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("PROHORI_DATA_DIR", str(tmp_path))
    for k in ("PROHORI_DDB_TABLE", "PROHORI_S3_BUCKET", "PROHORI_SNS_TOPIC_ARN", "PROHORI_PUBLIC_URL",
              "PROHORI_ESCALATION_COOLDOWN_S"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("PROHORI_AWS_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    store._reset_clients()
    E._reset_clients()
    yield
    store._reset_clients()
    E._reset_clients()


@pytest.fixture
def sns(monkeypatch):
    """A moto SNS topic with an SQS subscriber so published messages can be read back."""
    with mock_aws():
        c = boto3.client("sns", region_name="us-east-1")
        arn = c.create_topic(Name="prohori-escalations")["TopicArn"]
        sqs = boto3.client("sqs", region_name="us-east-1")
        q = sqs.create_queue(QueueName="eng")["QueueUrl"]
        qarn = sqs.get_queue_attributes(QueueUrl=q, AttributeNames=["QueueArn"])["Attributes"]["QueueArn"]
        c.subscribe(TopicArn=arn, Protocol="sqs", Endpoint=qarn)
        monkeypatch.setenv("PROHORI_SNS_TOPIC_ARN", arn)
        monkeypatch.setenv("PROHORI_PUBLIC_URL", "https://prohori.example")
        E._reset_clients()

        def received():
            out = []
            while True:
                r = sqs.receive_message(QueueUrl=q, MaxNumberOfMessages=10, WaitTimeSeconds=0)
                if not r.get("Messages"):
                    return out
                for m in r["Messages"]:
                    out.append(json.loads(m["Body"]))
                    sqs.delete_message(QueueUrl=q, ReceiptHandle=m["ReceiptHandle"])
        yield received


def raise_one(**kw):
    base = dict(session_id="sess-1234567890", joint_id="wall-a1", why=["widening"], crack=CRACK, gate={"certified": True},
                observation=OBS, summary=SUMMARY, decision=DECISION, background=False)
    base.update(kw)
    return E.escalate(**base)


# ------------------------------------------------------------------ triggers
def test_triggers():
    assert E.triggers({"action": "abandon_and_log"}, None) == ["abandon_and_log"]
    assert E.triggers({"action": "accept"}, None) == []
    assert E.triggers({"action": "accept"}, {"change": {"significant": True, "direction": "wider"}}) == ["widening"]
    assert E.triggers({"action": "accept"}, {"change": {"significant": True, "direction": "narrower"}}) == []
    assert E.triggers({"action": "accept"}, {"change": {"significant": False, "direction": "none"}}) == []
    assert E.triggers({"action": "accept"}, {"trend": {"significant": True, "direction": "widening"}}) == ["trend"]
    both = E.triggers({"action": "abandon_and_log"}, {"change": {"significant": True, "direction": "wider"}})
    assert both == ["abandon_and_log", "widening"]


# ------------------------------------------------------------------ message
def test_message_content_is_plain_and_complete():
    subject, body = E.build_message(joint_id="wall-a1", session_id="sess-1234567890", why=["widening", "trend"],
                                    crack=CRACK, gate={}, observation=OBS, summary=SUMMARY, token="TOK", decision=DECISION)
    assert subject.isascii() and "\n" not in subject and len(subject) <= 100 and "wall-a1" in subject
    assert "wall-a1" in body
    assert "0.52 mm" in body and "0.06 mm" in body and "90% interval" in body
    assert "+0.22 mm over 14.0 days" in body
    assert "11.4 px/mm" in body
    assert "/api/trace/sess-1234567890" in body and "/api/approve/TOK" in body
    assert "durability-guidance reference, not a structural-capacity criterion" in body
    assert "qualified engineer" in body


def test_message_for_abandoned_capture_without_width():
    _, body = E.build_message(joint_id=None, session_id="abcdef123456", why=["abandon_and_log"], crack=None,
                              gate={"reasons": ["low_resolution", "blurry"]}, observation={"px_per_mm": 3.1},
                              summary=None, token="T", decision={"instruction": "Give up for now."})
    assert "no certified width" in body and "low resolution, blurry" in body and "3.1 px/mm" in body
    assert "session abcdef12" in body


# ------------------------------------------------------------------ publish + approval
def test_publish_to_sns_and_create_approval(sns):
    r = raise_one()
    assert r["escalated"] and r["sns"] == "published" and r["status"] == "pending" and r["why"] == ["widening"]
    assert "token" not in json.dumps(r) and "approve" not in json.dumps(r)  # the secret never leaves the server
    (m,) = sns()
    assert "wall-a1" in m["Subject"]
    assert "durability-guidance reference" in m["Message"]
    link = [ln for ln in m["Message"].splitlines() if "/api/approve/" in ln][0]
    assert link.split("Confirm you reviewed this: ")[1].startswith("https://prohori.example/api/approve/")
    token = link.rsplit("/", 1)[1]
    rec = E.get_review(token)
    assert rec["status"] == "pending" and rec["joint_id"] == "wall-a1" and rec["escalation_id"] == r["escalation_id"]
    assert rec["sns"] == "published"


def test_mark_reviewed_is_idempotent(sns):
    raise_one()
    token = [ln for ln in sns()[0]["Message"].splitlines() if "/api/approve/" in ln][0].rsplit("/", 1)[1]
    first = E.mark_reviewed(token)
    assert first["status"] == "reviewed" and first["reviewed"]
    again = E.mark_reviewed(token)
    assert again["reviewed"] == first["reviewed"]
    assert E.get_review(token)["status"] == "reviewed"


def test_unknown_or_malformed_tokens():
    assert E.get_review("nope") is None
    assert E.get_review("../../etc/passwd") is None
    assert E.get_review("x" * 200) is None
    assert E.mark_reviewed("nope") is None


def test_no_topic_logs_locally_only(tmp_path, caplog):
    with caplog.at_level("WARNING", logger="prohori.escalate"):
        r = raise_one()
    assert r["escalated"] and r["sns"] == "local_only"
    assert "ESCALATION" in caplog.text and "wall-a1" in caplog.text
    (f,) = list((tmp_path / "approvals").glob("*.json"))
    assert json.loads(f.read_text())["sns"] == "local_only"


def test_sns_failure_is_recorded_not_raised(monkeypatch):
    with mock_aws():  # topic does not exist
        monkeypatch.setenv("PROHORI_SNS_TOPIC_ARN", "arn:aws:sns:us-east-1:123456789012:missing")
        E._reset_clients()
        r = raise_one()
    assert r["escalated"] and r["sns"] == "failed"


# ------------------------------------------------------------------ rate limit
def test_one_escalation_per_joint_per_hour(sns):
    a = raise_one()
    b = raise_one()
    assert a["escalated"] and not b["escalated"] and b["suppressed"] == "rate_limit"
    assert b["escalation_id"] == a["escalation_id"] and 0 < b["retry_after_s"] <= 3600
    assert len(sns()) == 1
    other = raise_one(joint_id="wall-b2")
    assert other["escalated"]
    assert len(sns()) == 1


def test_rate_limit_expires(sns, monkeypatch):
    monkeypatch.setenv("PROHORI_ESCALATION_COOLDOWN_S", "0")
    assert raise_one()["escalated"] and raise_one()["escalated"]
    assert len(sns()) == 2


def test_without_joint_the_session_is_the_rate_limit_key(sns):
    assert raise_one(joint_id=None, why=["abandon_and_log"])["escalated"]
    assert not raise_one(joint_id=None, why=["abandon_and_log"])["escalated"]
    assert raise_one(joint_id=None, why=["abandon_and_log"], session_id="another-session-1")["escalated"]


def test_background_publish_completes(sns):
    r = raise_one(background=True, joint_id="wall-bg")
    assert r["sns"] == "queued"
    import time
    for _ in range(100):
        got = sns()
        if got:
            break
        time.sleep(0.05)
    assert len(got) == 1
