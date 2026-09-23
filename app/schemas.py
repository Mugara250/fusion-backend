"""The JSON contract shared by the brain (laptop) and the body (ESP32)."""

from pydantic import BaseModel, Field


class Report(BaseModel):
    """What the brain POSTs. Only `count` is required (Challenge 1).

    `brightness` (Challenge 3), `gesture` (Challenge 2) and `sos` are optional;
    fields left out keep their previous value.
    """

    count: int = Field(ge=0, le=5)
    brightness: int | None = Field(default=None, ge=0, le=255)
    gesture: str | None = Field(default=None, max_length=32)
    sos: bool | None = None


class Snapshot(BaseModel):
    """What the body GETs. Key order is kept compact for simple parsing on the chip."""

    count: int
    brightness: int
    gesture: str
    sos: bool
    stale: bool
    event: str


class HistoryItem(BaseModel):
    at: str
    count: int
    brightness: int
    gesture: str
    sos: bool
