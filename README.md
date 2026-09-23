# Fusion Backend (the cloud tier)

The brain (laptop + webcam) `POST`s what it saw; the body (ESP32) `GET`s what to do.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

## Run

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

`0.0.0.0` is required so the ESP32 can reach it. Docs: http://127.0.0.1:8000/docs

## API

| Method | Path       | Body / response |
|--------|------------|-----------------|
| POST   | `/fingers` | `{"count": 0-5, "brightness"?: 0-255, "gesture"?: str, "sos"?: bool}`; 422 if out of range |
| GET    | `/fingers` | `{"count","brightness","gesture","sos","stale","event"}`; all zero after 3 s of silence |
| GET    | `/history?limit=50` | recent reports with timestamps |
| GET    | `/health`  | `{"ok": true}` |

Env vars: `STALE_SECONDS` (default 3), `HISTORY_SIZE` (default 500).

## Testing without an ESP32

```bash
pytest -q                                # unit tests
python tools/fake_esp32.py               # terminal 2: polls 5x/s like the chip
python tools/fake_brain.py               # terminal 3: type counts (or --auto)
```

## Hosting on Render (no shared network needed)

1. Push this folder to a **private** GitHub repo (the sketch contains your WiFi password).
2. On render.com: New > Blueprint > pick the repo (uses `render.yaml`).
3. Copy the service URL and the generated `API_KEY` (Environment tab).
4. Brain: `python vision.py --url https://<app>.onrender.com/fingers --key <API_KEY>`
5. Body: set `BACKEND_URL = "https://<app>.onrender.com/fingers"` in the sketch.

The free plan sleeps after 15 min without requests; the first request then takes ~1 min.
