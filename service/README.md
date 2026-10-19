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
| `POST /api/measure` | multipart `image` (+ optional `session_id`, `policy` = `llm` or `rules`); returns measurement, agent decision, overlay JPEG (base64) |
| `GET /api/trace/{session_id}` | every step of an inspection (drives the Agent trace panel) |
| `GET /api/samples` | bundled demo images |

Limits: 15 MB upload, longest side capped at 4096 px, 30 requests per minute per IP (`PROHORI_RATE_LIMIT` to change).

Environment: `PROHORI_VERSION` (shown in `/health`), `PROHORI_INSTANCE` (skip the IMDS lookup).

## Tests

```bash
python -m pytest tests/test_service.py -q
```
