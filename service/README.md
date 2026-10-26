# Prohori service

FastAPI server plus the phone web app (PWA). The phone captures a frame, the server measures the crack and the triage agent says what to do next.

## Run locally

From the repo root:

```bash
pip install -r service/requirements.txt
uvicorn service.app:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000. `src/` is added to `sys.path` by `app.py`, so no install is needed.

The phone camera only works over **HTTPS** (localhost is exempt). For a phone on the same Wi-Fi use a tunnel (for example `cloudflared tunnel --url http://localhost:8000`) or put the server behind an HTTPS proxy. Without HTTPS the "Upload photo" and "Demo samples" buttons still work.

## API

| Route | What |
|---|---|
| `GET /health` | status, OpenCV version, CPU arch, EC2 instance type (or `local`), version |
| `POST /api/measure` | multipart `image` (+ optional `session_id`, `policy` = `llm` or `rules`, `joint_id` slug); returns measurement, agent decision, overlay JPEG (base64) |
| `GET /api/trace/{session_id}` | every step of an inspection (drives the Agent trace panel) |
| `GET /api/samples` | bundled demo images |
| `GET /api/joint/{joint_id}` | per-joint history of certified measurements, change vs last visit (uncertainty-aware), robust trend from 3 visits |
| `GET /api/approve/{token}` | page an engineer opens from the escalation message; `POST` records "I have reviewed this" |

Limits: 15 MB upload, longest side capped at 4096 px, 30 requests per minute per IP (`PROHORI_RATE_LIMIT` to change).

Environment: `PROHORI_VERSION` (shown in `/health`), `PROHORI_INSTANCE` (skip the IMDS lookup).

Agent settings (applied by `infra/push.sh` from `infra/agent.env`):

| Env var | Meaning |
|---|---|
| `PROHORI_DEFAULT_POLICY` | policy used when the request has no `policy` field: `llm` (default on the live box) or `rules` |
| `PROHORI_BEDROCK_MODEL` / `PROHORI_BEDROCK_FALLBACK_MODELS` | primary Bedrock model and comma-separated fallbacks, tried in order; then the rules policy |
| `PROHORI_LLM_DAILY_CAP` | LLM decisions per UTC day (default 200); the rules policy answers after that |
| `PROHORI_GUARDRAIL` | `0` turns the output checker off (default on; every LLM answer is validated by `agent.validate_decision` and the decision carries a `guardrail` record) |

History, escalation and privacy (see `research/SERVICE_NOTES.md`):

| Env var | Meaning |
|---|---|
| `PROHORI_SNS_TOPIC_ARN` | SNS topic for engineer escalations; unset = log locally only |
| `PROHORI_PUBLIC_URL` | base URL used in escalation links, e.g. `https://prohori.example` |
| `PROHORI_ESCALATION_COOLDOWN_S` | min seconds between escalations per joint (default 3600) |
| `PROHORI_CHANGE_LEVEL` | confidence level of the change rule (default 0.90, k = 1.645) |
| `PROHORI_U_KIND` | `standard` (default, uncertainties are 1 sigma) or `expanded` |
| `PROHORI_YUNET_MODEL` | override path of the face-detection model (default `models/face_detection_yunet_2023mar.onnx`) |
| `PROHORI_REDACT` | `off` disables face blur (tests only; evidence is stored unredacted) |

Evidence images are stored only after faces are blurred; if the face model is missing, nothing is persisted.

## Tests

```bash
python -m pytest tests/test_service.py tests/test_store.py tests/test_history.py tests/test_escalate.py tests/test_redact.py -q
```
