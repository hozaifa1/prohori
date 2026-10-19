from decimal import Decimal

import pytest

from prohori import store

STEP = {"observation": {"px_per_mm": 6.5, "blur_var": float("nan")}, "gate": {"certified": False},
        "decision": {"action": "move_closer", "latency_ms": 812.4}}


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("PROHORI_DATA_DIR", str(tmp_path))
    for k in ("PROHORI_DDB_TABLE", "PROHORI_S3_BUCKET"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("PROHORI_AWS_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    store._reset_clients()
    yield
    store._reset_clients()


def test_local_roundtrip_in_order(tmp_path):
    for i in range(3):
        store.log_trace("s1", {**STEP, "i": i})
    steps = store.get_trace("s1")
    assert [s["i"] for s in steps] == [0, 1, 2]
    assert [s["step"] for s in steps] == [0, 1, 2]
    assert steps[0]["observation"]["blur_var"] is None  # NaN made JSON-safe
    assert "ts" in steps[0] and steps[0]["session_id"] == "s1"
    assert (tmp_path / "traces" / "s1.jsonl").exists()
    assert store.get_trace("missing") == []


def test_explicit_step_and_numpy():
    np = pytest.importorskip("numpy")
    store.log_trace("s2", {"step": 5, "v": np.float32(1.5), "a": np.arange(3)})
    (s,) = store.get_trace("s2")
    assert s["step"] == 5 and s["v"] == 1.5 and s["a"] == [0, 1, 2]


def test_session_id_cannot_escape(tmp_path):
    store.log_trace("../../evil", {"x": 1})
    assert not (tmp_path.parent / "evil.jsonl").exists()
    assert len(store.get_trace("../../evil")) == 1


def test_evidence_local():
    p = store.save_evidence("s1", 3, b"\xff\xd8jpeg")
    assert p.endswith("0003.jpg")
    with open(p, "rb") as f:
        assert f.read() == b"\xff\xd8jpeg"


def test_to_ddb_decimal():
    d = store.to_ddb({"a": 1.5, "b": [0.1, {"c": 2}]})
    assert d == {"a": Decimal("1.5"), "b": [Decimal("0.1"), {"c": 2}]}


pytest.importorskip("moto")


@pytest.fixture
def aws(monkeypatch):
    import boto3
    from moto import mock_aws
    with mock_aws():
        ddb = boto3.client("dynamodb", region_name="us-east-1")
        ddb.create_table(TableName="prohori-traces", BillingMode="PAY_PER_REQUEST",
                         KeySchema=store.DDB_TABLE_SCHEMA["KeySchema"],
                         AttributeDefinitions=store.DDB_TABLE_SCHEMA["AttributeDefinitions"])
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="prohori-evidence")
        monkeypatch.setenv("PROHORI_DDB_TABLE", "prohori-traces")
        monkeypatch.setenv("PROHORI_S3_BUCKET", "prohori-evidence")
        store._reset_clients()
        yield


def test_ddb_roundtrip(aws, tmp_path):
    for i in range(12):  # >10 checks zero-padded sort order
        store.log_trace("sess", {"i": i, "decision": {"latency_ms": 10.5 + i}})
    (tmp_path / "traces" / "sess.jsonl").unlink()  # prove the read comes from DynamoDB
    steps = store.get_trace("sess")
    assert [s["i"] for s in steps] == list(range(12))
    assert steps[3]["decision"]["latency_ms"] == 13.5 and isinstance(steps[3]["decision"]["latency_ms"], float)
    assert steps[0]["step"] == 0 and "ttl" not in steps[0]
    import boto3
    raw = boto3.resource("dynamodb", region_name="us-east-1").Table("prohori-traces").get_item(
        Key={"session_id": "sess", "step": "0007"})["Item"]
    assert raw["ttl"] > 0 and raw["ts"]


def test_s3_evidence(aws):
    import boto3
    key = store.save_evidence("sess", 2, b"jpegbytes")
    assert key == "evidence/sess/0002.jpg"
    obj = boto3.client("s3", region_name="us-east-1").get_object(Bucket="prohori-evidence", Key=key)
    assert obj["Body"].read() == b"jpegbytes" and obj["ServerSideEncryption"] == "AES256"


def test_aws_failures_never_raise(monkeypatch):
    from moto import mock_aws
    with mock_aws():  # table/bucket do not exist
        monkeypatch.setenv("PROHORI_DDB_TABLE", "nope")
        monkeypatch.setenv("PROHORI_S3_BUCKET", "nobucket")
        store._reset_clients()
        rec = store.log_trace("s9", {"a": 1})
        assert rec["step"] == 0
        assert [s["a"] for s in store.get_trace("s9")] == [1]  # falls back to local
        p = store.save_evidence("s9", 0, b"x")  # S3 fails -> local
        assert p.endswith("0000.jpg")
        with open(p, "rb") as f:
            assert f.read() == b"x"


# ---- per-joint history, escalation log, approvals ---------------------------------------------------
def test_normalize_joint_id():
    assert store.normalize_joint_id("  Wall-A1_2 ") == "wall-a1_2"
    for bad in ("", " ", "a b", "../x", "a#b", "x" * 65, "-lead", None, "ü"):
        assert store.normalize_joint_id(bad) is None


def test_joint_history_local_roundtrip(tmp_path):
    for i, w in enumerate((0.30, 0.35, 0.41)):
        store.log_measurement("j1", {"ts": f"2026-09-0{i + 1}T09:00:00+00:00", "width_mm": w,
                                     "session_id": f"sess{i}", "step": i})
    store.log_measurement("j2", {"width_mm": 9.9})
    h = store.get_joint_history("j1")
    assert [r["width_mm"] for r in h] == [0.30, 0.35, 0.41]
    assert all(r["joint_id"] == "j1" and r["pk"] == "joint#j1" for r in h)
    # caller fields that collide with the table's key names are preserved under src_*
    assert h[0]["src_session_id"] == "sess0" and h[0]["src_step"] == 0
    assert store.get_joint_history("j2")[0]["width_mm"] == 9.9
    assert store.get_joint_history("never") == []
    assert (tmp_path / "records" / "joint__j1.jsonl").exists()
    assert len(store.get_joint_history("j1", limit=2)) == 2


def test_approval_roundtrip_local(tmp_path):
    assert store.get_approval("tok") is None
    assert store.put_approval("tok", {"status": "pending", "x": 1.5})
    assert store.get_approval("tok") == {"status": "pending", "x": 1.5}
    store.put_approval("tok", {"status": "reviewed"})
    assert store.get_approval("tok")["status"] == "reviewed"


def test_joint_history_ddb_roundtrip(aws, tmp_path):
    import boto3
    for i in range(3):
        store.log_measurement("wall-1", {"width_mm": 0.3 + 0.05 * i, "uncertainty_mm": 0.02,
                                         "session_id": f"s{i}"})
    for p in (tmp_path / "records").glob("*.jsonl"):
        p.unlink()  # prove the read comes from DynamoDB
    h = store.get_joint_history("wall-1")
    assert [round(r["width_mm"], 2) for r in h] == [0.30, 0.35, 0.40]
    assert isinstance(h[0]["width_mm"], float) and h[0]["pk"] == "joint#wall-1" and "ttl" not in h[0]
    assert h[0]["sk"] < h[1]["sk"] < h[2]["sk"]
    raw = boto3.resource("dynamodb", region_name="us-east-1").Table("prohori-traces").query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key("session_id").eq("joint#wall-1"))["Items"]
    assert len(raw) == 3 and raw[0]["ttl"] > 0 and raw[0]["src_session_id"] == "s0"
    # newest first + limit
    assert store.list_records("joint#wall-1", newest_first=True, limit=1)[0]["src_session_id"] == "s2"
    # joint records live in their own partition: they are not part of any session trace
    assert store.get_trace("wall-1") == []


def test_approval_ddb_roundtrip(aws, tmp_path):
    store.put_approval("secret-token", {"status": "pending", "message": "m", "n": 2.5})
    for p in (tmp_path / "approvals").glob("*.json"):
        p.unlink()
    got = store.get_approval("secret-token")
    assert got == {"status": "pending", "message": "m", "n": 2.5}
    store.put_approval("secret-token", {**got, "status": "reviewed"})
    assert store.get_approval("secret-token")["status"] == "reviewed"
    assert store.get_approval("other") is None


def test_joint_functions_never_raise_when_ddb_is_broken(monkeypatch):
    from moto import mock_aws
    with mock_aws():  # table does not exist
        monkeypatch.setenv("PROHORI_DDB_TABLE", "nope")
        store._reset_clients()
        rec = store.log_measurement("j9", {"width_mm": 0.4})
        assert rec["pk"] == "joint#j9"
        assert [r["width_mm"] for r in store.get_joint_history("j9")] == [0.4]  # local fallback
        assert store.put_approval("t9", {"status": "pending"})
        assert store.get_approval("t9")["status"] == "pending"
