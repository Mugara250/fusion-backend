"""The cloud tier: the brain POSTs what it saw, the body GETs what to do.

Run:  uvicorn app.main:app --host 0.0.0.0 --port 8000
Hosted (Render etc.): uvicorn app.main:app --host 0.0.0.0 --port $PORT
"""

import logging

from fastapi import FastAPI, Header, HTTPException, Query

from app import config

from app.schemas import HistoryItem, Report, Snapshot
from app.state import state

log = logging.getLogger("uvicorn.error")

app = FastAPI(title="Fusion Backend", version="1.0.0")


@app.get("/health")
def health() -> dict:
    # The ESP32 looks for "fusion-backend" when searching the network for this laptop.
    return {"ok": True, "service": "fusion-backend"}


@app.post("/fingers")
def report(data: Report, x_api_key: str | None = Header(default=None)) -> dict:
    """The camera tells. Counts outside 0..5 are refused with 422."""
    if config.API_KEY and x_api_key != config.API_KEY:
        raise HTTPException(status_code=401, detail="Missing or wrong X-API-Key")
    previous_event = state.event
    state.apply(data)
    if state.event != previous_event:
        log.info(state.event)
    return {"ok": True}


@app.get("/fingers", response_model=Snapshot)
def current() -> Snapshot:
    """The board asks. Goes to all zeros after STALE_SECONDS of camera silence."""
    return state.snapshot()


@app.get("/history", response_model=list[HistoryItem])
def history(limit: int = Query(50, ge=1, le=500)) -> list[HistoryItem]:
    """Recent reports with timestamps: tomorrow's training data."""
    return state.recent(limit)
