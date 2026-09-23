"""The one truth the backend remembers, guarded by a lock."""

import threading
import time
from collections import deque
from datetime import datetime

from app import config
from app.schemas import HistoryItem, Report, Snapshot


class State:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.count = 0
        self.brightness = 0
        self.gesture = "none"
        self.sos = False
        self.event = "No SOS event yet"
        self.updated = 0.0  # monotonic; 0 means "never reported", so stale at start
        self.history: deque[HistoryItem] = deque(maxlen=config.HISTORY_SIZE)

    def apply(self, report: Report) -> None:
        with self._lock:
            if report.sos is not None and report.sos != self.sos:
                clock = datetime.now().strftime("%H:%M:%S")
                self.event = f"{clock} - SOS switched {'ON' if report.sos else 'OFF'}"

            self.count = report.count
            if report.brightness is not None:
                self.brightness = report.brightness
            if report.gesture is not None:
                self.gesture = report.gesture
            if report.sos is not None:
                self.sos = report.sos
            self.updated = time.monotonic()

            self.history.append(
                HistoryItem(
                    at=datetime.now().isoformat(timespec="milliseconds"),
                    count=self.count,
                    brightness=self.brightness,
                    gesture=self.gesture,
                    sos=self.sos,
                )
            )

    def snapshot(self) -> Snapshot:
        with self._lock:
            stale = time.monotonic() - self.updated > config.STALE_SECONDS
            return Snapshot(
                count=0 if stale else self.count,
                brightness=0 if stale else self.brightness,
                gesture="none" if stale else self.gesture,
                sos=False if stale else self.sos,
                stale=stale,
                event=self.event,
            )

    def recent(self, limit: int) -> list[HistoryItem]:
        with self._lock:
            return list(self.history)[-limit:]

    def reset(self) -> None:
        self.__init__()


state = State()
