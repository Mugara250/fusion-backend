"""Runtime settings, overridable with environment variables."""

import os

# Seconds of camera silence before the backend reports everything as 0.
STALE_SECONDS = float(os.getenv("STALE_SECONDS", "3"))

# How many reports to keep in memory for GET /history.
HISTORY_SIZE = int(os.getenv("HISTORY_SIZE", "500"))

# If set, POST /fingers requires the header "X-API-Key: <value>". Leave empty on a LAN.
API_KEY = os.getenv("API_KEY", "")
