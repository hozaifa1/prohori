"""Prohori persistence: decision traces (JSONL + DynamoDB) and evidence images (S3 or local disk).

Every function here is best-effort: AWS failures are logged as warnings and never raised
to the caller. Local files are always written, so the demo works with no AWS at all.

Infra constants (for CloudFormation / CDK / console setup)
  DynamoDB table  : name from env PROHORI_DDB_TABLE, BillingMode PAY_PER_REQUEST
                    pk (HASH)  "session_id" : S
                    sk (RANGE) "step"       : S   (zero-padded index, e.g. "0003")
                    TimeToLive attribute "ttl" (epoch seconds, 90 days after write)
  S3 bucket       : name from env PROHORI_S3_BUCKET, key evidence/{session_id}/{step:04d}.jpg,
                    SSE-S3 (AES256), block public access ON.
  Region          : env PROHORI_AWS_REGION (default us-east-1).
  Local override  : env PROHORI_DATA_DIR (default <repo>/data).
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import threading
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

log = logging.getLogger("prohori.store")

# ---- infra-friendly constants -------------------------------------------------
DDB_TABLE_SCHEMA = {
    "BillingMode": "PAY_PER_REQUEST",
    "KeySchema": [
        {"AttributeName": "session_id", "KeyType": "HASH"},
        {"AttributeName": "step", "KeyType": "RANGE"},
    ],
    "AttributeDefinitions": [
        {"AttributeName": "session_id", "AttributeType": "S"},
        {"AttributeName": "step", "AttributeType": "S"},
    ],
}
DDB_TTL_ATTRIBUTE = "ttl"
TTL_DAYS = 90
STEP_WIDTH = 4  # zero-padding of step index in the sort key and evidence key
EVIDENCE_PREFIX = "evidence"

ENV_TABLE = "PROHORI_DDB_TABLE"
ENV_BUCKET = "PROHORI_S3_BUCKET"
ENV_REGION = "PROHORI_AWS_REGION"
ENV_DATA_DIR = "PROHORI_DATA_DIR"

_lock = threading.Lock()
_aws_cache: dict[tuple, Any] = {}


# ---- paths --------------------------------------------------------------------
def _data_dir() -> Path:
    env = os.environ.get(ENV_DATA_DIR)
    return Path(env) if env else Path(__file__).resolve().parents[2] / "data"


def _safe_id(session_id: Any) -> str:
    s = re.sub(r"[^A-Za-z0-9_.-]", "_", str(session_id))
    return s.lstrip(".") or "_"


def _trace_path(session_id: Any) -> Path:
    return _data_dir() / "traces" / f"{_safe_id(session_id)}.jsonl"


def _sk(idx: int) -> str:
    return f"{int(idx):0{STEP_WIDTH}d}"


# ---- JSON / Decimal helpers -----------------------------------------------------
def to_json_safe(x: Any) -> Any:
    """Recursively convert to plain JSON types (numpy -> python, NaN/inf -> None, bytes dropped)."""
    if x is None or isinstance(x, (str, bool)):
        return x
    if isinstance(x, int):
        return int(x)
    if isinstance(x, float):
        return x if math.isfinite(x) else None
    if isinstance(x, Decimal):
        return to_json_safe(float(x)) if x % 1 else int(x)
    if isinstance(x, dict):
        return {str(k): to_json_safe(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, set)):
        return [to_json_safe(v) for v in x]
    if isinstance(x, (bytes, bytearray)):
        return f"<{len(x)} bytes>"
    if hasattr(x, "tolist"):  # numpy scalars / arrays
        return to_json_safe(x.tolist())
    if hasattr(x, "item"):
        return to_json_safe(x.item())
    return str(x)


def to_ddb(x: Any) -> Any:
    """JSON-safe structure with floats -> Decimal (DynamoDB rejects float)."""
    if isinstance(x, float):
        return Decimal(repr(x))
    if isinstance(x, dict):
        return {k: to_ddb(v) for k, v in x.items()}
    if isinstance(x, list):
        return [to_ddb(v) for v in x]
    return x


def from_ddb(x: Any) -> Any:
    """Decimal -> int/float, recursively."""
    if isinstance(x, Decimal):
        return int(x) if x % 1 == 0 else float(x)
    if isinstance(x, dict):
        return {k: from_ddb(v) for k, v in x.items()}
    if isinstance(x, list):
        return [from_ddb(v) for v in x]
    return x


# ---- AWS clients ------------------------------------------------------------------
def _boto_config():
    from botocore.config import Config

    return Config(connect_timeout=3, read_timeout=6, retries={"max_attempts": 2, "mode": "standard"})


def _ddb_table():
    name = os.environ.get(ENV_TABLE)
    if not name:
        return None
    region = os.environ.get(ENV_REGION, "us-east-1")
    key = ("ddb", region, name)
    with _lock:
        t = _aws_cache.get(key)
        if t is None:
            import boto3

            t = boto3.resource("dynamodb", region_name=region, config=_boto_config()).Table(name)
            _aws_cache[key] = t
        return t


def _s3_client():
    region = os.environ.get(ENV_REGION, "us-east-1")
    key = ("s3", region)
    with _lock:
        c = _aws_cache.get(key)
        if c is None:
            import boto3

            c = boto3.client("s3", region_name=region, config=_boto_config())
            _aws_cache[key] = c
        return c


def _reset_clients() -> None:
    """Drop cached AWS clients (tests / credential refresh)."""
    with _lock:
        _aws_cache.clear()


# ---- traces ---------------------------------------------------------------------------
def _read_local(session_id: Any) -> list[dict]:
    path = _trace_path(session_id)
    out: list[dict] = []
    if not path.exists():
        return out
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        log.warning("skipping corrupt trace line in %s", path)
    except OSError as e:
        log.warning("cannot read trace %s: %s", path, e)
    return out


def log_trace(session_id: str, step: dict) -> dict:
    """Append one agent step to the session trace. Never raises.

    If ``step`` has an integer "step" key it is the step index; otherwise the next index
    (count of local lines) is used. Returns the stored record (JSON-safe, with "step" int,
    "session_id" and "ts" added).
    """
    try:
        safe = to_json_safe(step if isinstance(step, dict) else {"value": step})
    except Exception as e:  # pragma: no cover
        log.warning("trace step not serialisable: %s", e)
        safe = {"error": "unserialisable step"}
    try:
        idx = safe.get("step")
        if not isinstance(idx, int) or isinstance(idx, bool):
            idx = len(_read_local(session_id))
    except Exception:
        idx = 0
    now = datetime.now(timezone.utc)
    record = {**safe, "session_id": session_id, "step": idx, "ts": now.isoformat(timespec="milliseconds")}

    try:
        path = _trace_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with _lock, path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, separators=(",", ":")) + "\n")
    except Exception as e:
        log.warning("local trace write failed: %s", e)

    try:
        table = _ddb_table()
        if table is not None:
            item = to_ddb({**record, "step": _sk(idx), "ttl": int(time.time()) + TTL_DAYS * 86400})
            table.put_item(Item=item)
    except Exception as e:
        log.warning("DynamoDB put_item failed (trace kept locally): %s", e)
    return record


def get_trace(session_id: str) -> list[dict]:
    """All steps of a session in step order (DynamoDB if configured, else local JSONL).

    If DynamoDB is configured but fails or returns nothing, falls back to the local file.
    """
    try:
        table = _ddb_table()
        if table is not None:
            from boto3.dynamodb.conditions import Key

            items: list[dict] = []
            kwargs: dict[str, Any] = {"KeyConditionExpression": Key("session_id").eq(session_id)}
            while True:
                resp = table.query(**kwargs)
                items.extend(resp.get("Items", []))
                lek = resp.get("LastEvaluatedKey")
                if not lek:
                    break
                kwargs["ExclusiveStartKey"] = lek
            if items:
                out = []
                for it in sorted(items, key=lambda i: i.get("step", "")):
                    d = from_ddb(it)
                    d.pop("ttl", None)
                    try:
                        d["step"] = int(d["step"])
                    except (KeyError, ValueError, TypeError):
                        pass
                    out.append(d)
                return out
    except Exception as e:
        log.warning("DynamoDB query failed, using local trace: %s", e)
    steps = _read_local(session_id)
    steps.sort(key=lambda d: d.get("step", 0) if isinstance(d.get("step"), int) else 0)
    return steps


# ---- evidence ---------------------------------------------------------------------------------
def save_evidence(session_id: str, step_idx: int, jpeg_bytes: bytes) -> str:
    """Store one evidence JPEG. Returns the S3 key (when PROHORI_S3_BUCKET is set and the
    upload works) or the local file path. Never raises (returns "" if even local write fails)."""
    rel = f"{EVIDENCE_PREFIX}/{_safe_id(session_id)}/{int(step_idx):0{STEP_WIDTH}d}.jpg"
    bucket = os.environ.get(ENV_BUCKET)
    if bucket:
        try:
            _s3_client().put_object(Bucket=bucket, Key=rel, Body=jpeg_bytes,
                                    ContentType="image/jpeg", ServerSideEncryption="AES256")
            return rel
        except Exception as e:
            log.warning("S3 put_object failed (saving locally): %s", e)
    try:
        path = _data_dir() / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(jpeg_bytes)
        return str(path)
    except Exception as e:
        log.warning("local evidence write failed: %s", e)
        return ""
