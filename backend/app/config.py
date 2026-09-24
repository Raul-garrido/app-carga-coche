"""App-wide settings from environment variables. No credentials or secrets
are ever hardcoded — see .env.example at the repo root."""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("APP_DATA_DIR", BASE_DIR / "data"))
DB_PATH = DATA_DIR / "app.db"

MYAUDI_AUTO_ENABLED = os.environ.get("MYAUDI_AUTO_ENABLED", "false").lower() == "true"
MYAUDI_USERNAME = os.environ.get("MYAUDI_USERNAME")
MYAUDI_PASSWORD = os.environ.get("MYAUDI_PASSWORD")
MYAUDI_SPIN = os.environ.get("MYAUDI_SPIN")
MYAUDI_MIN_POLL_INTERVAL_SECONDS = int(os.environ.get("MYAUDI_MIN_POLL_INTERVAL_SECONDS", "900"))

FRONTEND_DIR = BASE_DIR.parent / "frontend"
