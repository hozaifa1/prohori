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
