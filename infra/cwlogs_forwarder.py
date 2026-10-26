"""Lightweight journald -> CloudWatch Logs forwarder for the Prohori service (no CloudWatch agent needed).

Follows `journalctl -u prohori -o cat` (the service's structured JSON access lines, plus tracebacks), batches the lines
and ships them with PutLogEvents to log group /prohori/service, stream <instance-id>.  A journald cursor file makes
restarts lossless and duplicate-free.  uvicorn's plain access lines (they carry client IPs) are dropped; the JSON
`evt=request` lines carry no IP.  Runs as root (to read the journal) under systemd unit prohori-logs, with the
instance role's credentials (logs:CreateLogStream / PutLogEvents / DescribeLogStreams on that one log group only).
Usage: python cwlogs_forwarder.py [--group /prohori/service] [--unit prohori] [--cursor FILE]
"""
from __future__ import annotations

import argparse
import os
import queue
import re
import subprocess
import sys
import threading
import time
import urllib.request

import boto3

ACCESS = re.compile(r"^INFO:\s+\d+\.\d+\.\d+\.\d+")   # uvicorn plain access line (has a client IP): not shipped
MAX_BATCH, MAX_WAIT_S, MAX_BYTES = 200, 2.0, 200_000


def instance_id() -> str:
    try:
        req = urllib.request.Request("http://169.254.169.254/latest/api/token", method="PUT",
                                     headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"})
        tok = urllib.request.urlopen(req, timeout=2).read().decode()
        req2 = urllib.request.Request("http://169.254.169.254/latest/meta-data/instance-id",
                                      headers={"X-aws-ec2-metadata-token": tok})
        return urllib.request.urlopen(req2, timeout=2).read().decode().strip()
    except Exception:
        return "unknown"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", default="/prohori/service")
    ap.add_argument("--unit", default="prohori")
    ap.add_argument("--cursor", default="/opt/prohori/data/cwlogs.cursor")
    a = ap.parse_args()
    logs = boto3.client("logs", region_name=os.environ.get("PROHORI_AWS_REGION") or os.environ.get("AWS_REGION"))   # botocore ignores AWS_REGION
    stream = instance_id()
    try:
        logs.create_log_stream(logGroupName=a.group, logStreamName=stream)
    except logs.exceptions.ResourceAlreadyExistsException:
        pass
    start = [] if os.path.exists(a.cursor) else ["-n", "0"]   # first run: only new lines; later runs resume at the cursor
    proc = subprocess.Popen(["journalctl", "-u", a.unit, "-o", "cat", "-f", *start, f"--cursor-file={a.cursor}"],
                            stdout=subprocess.PIPE, text=True, bufsize=1, errors="replace")
    batch: list[dict] = []
    size, t_first = 0, time.monotonic()

    def flush() -> None:
        nonlocal batch, size, t_first
        if batch:
            for attempt in range(5):
                try:
                    logs.put_log_events(logGroupName=a.group, logStreamName=stream, logEvents=batch)
                    break
                except Exception as e:   # throttling / transient: back off, keep the batch
                    print(f"put_log_events failed ({e}); retry {attempt + 1}", file=sys.stderr, flush=True)
                    time.sleep(2 ** attempt)
        batch, size, t_first = [], 0, time.monotonic()

    lines: queue.Queue = queue.Queue()
    threading.Thread(target=lambda: [lines.put(ln.rstrip()) for ln in proc.stdout], daemon=True).start()
    while proc.poll() is None or not lines.empty():
        try:
            line = lines.get(timeout=0.5)
            if line and not ACCESS.match(line):
                if not batch:
                    t_first = time.monotonic()
                batch.append({"timestamp": int(time.time() * 1000), "message": line[:8000]})
                size += len(line) + 26
        except queue.Empty:
            pass
        if batch and (len(batch) >= MAX_BATCH or size >= MAX_BYTES or time.monotonic() - t_first >= MAX_WAIT_S):
            flush()
    flush()
    return proc.returncode or 1


if __name__ == "__main__":
    sys.exit(main())
