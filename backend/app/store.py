"""SQLite persistence for config, battery state, and charging sessions.

Single-user personal app: one file-based DB, one connection guarded by a
lock is plenty and keeps deployment to "copy the folder, run it".
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS battery_state (
    key TEXT PRIMARY KEY,
    percent REAL NOT NULL,
    source TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    battery_capacity_kwh REAL NOT NULL,
    initial_percent REAL NOT NULL,
    target_percent REAL NOT NULL,
    final_percent REAL,
    price_per_kwh REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    kwh REAL NOT NULL,
    source TEXT NOT NULL,
    timestamp TEXT NOT NULL
);
"""

_DEFAULTS = {
    "battery_capacity_kwh": "14.4",
    "default_target_percent": "100",
    "default_price_per_kwh": "",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, db_path: str | Path):
        self._db_path = str(db_path)
        self._local = threading.local()
        self._lock = threading.Lock()
        with self._lock:
            conn = self._connect()
            conn.executescript(SCHEMA)
            for key, value in _DEFAULTS.items():
                conn.execute(
                    "INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)",
                    (key, value),
                )
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn"):
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return self._local.conn

    # ---- config ----------------------------------------------------

    def get_config(self) -> dict:
        with self._lock:
            rows = self._connect().execute("SELECT key, value FROM config").fetchall()
        raw = {row["key"]: row["value"] for row in rows}
        return {
            "battery_capacity_kwh": float(raw.get("battery_capacity_kwh", 14.4)),
            "default_target_percent": float(raw.get("default_target_percent", 100)),
            "default_price_per_kwh": (
                float(raw["default_price_per_kwh"])
                if raw.get("default_price_per_kwh")
                else None
            ),
        }

    def update_config(self, **kwargs) -> dict:
        with self._lock:
            conn = self._connect()
            for key, value in kwargs.items():
                if value is None:
                    continue
                conn.execute(
                    "INSERT INTO config (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, str(value)),
                )
            conn.commit()
        return self.get_config()

    # ---- manual battery state ---------------------------------------

    def set_manual_soc(self, percent: float) -> dict:
        with self._lock:
            conn = self._connect()
            conn.execute(
                "INSERT INTO battery_state (key, percent, source, updated_at) "
                "VALUES ('current', ?, 'manual', ?) "
                "ON CONFLICT(key) DO UPDATE SET percent = excluded.percent, "
                "source = excluded.source, updated_at = excluded.updated_at",
                (percent, _now()),
            )
            conn.commit()
        return self.get_manual_soc()

    def get_manual_soc(self) -> Optional[dict]:
        with self._lock:
            row = self._connect().execute(
                "SELECT percent, source, updated_at FROM battery_state WHERE key = 'current'"
            ).fetchone()
        if row is None:
            return None
        return dict(row)

    # ---- sessions ----------------------------------------------------

    def create_session(
        self,
        battery_capacity_kwh: float,
        initial_percent: float,
        target_percent: float,
        price_per_kwh: float,
    ) -> int:
        with self._lock:
            conn = self._connect()
            cur = conn.execute(
                "INSERT INTO sessions "
                "(started_at, battery_capacity_kwh, initial_percent, target_percent, "
                " price_per_kwh, status) VALUES (?, ?, ?, ?, ?, 'active')",
                (_now(), battery_capacity_kwh, initial_percent, target_percent, price_per_kwh),
            )
            conn.commit()
            return cur.lastrowid

    def add_reading(self, session_id: int, kwh: float, source: str, timestamp: Optional[str]) -> int:
        with self._lock:
            conn = self._connect()
            cur = conn.execute(
                "INSERT INTO readings (session_id, kwh, source, timestamp) VALUES (?, ?, ?, ?)",
                (session_id, kwh, source, timestamp or _now()),
            )
            conn.commit()
            return cur.lastrowid

    def finish_session(self, session_id: int, final_percent: Optional[float]) -> None:
        with self._lock:
            conn = self._connect()
            conn.execute(
                "UPDATE sessions SET status = 'finished', ended_at = ?, final_percent = ? "
                "WHERE id = ?",
                (_now(), final_percent, session_id),
            )
            conn.commit()

    def delete_session(self, session_id: int) -> None:
        with self._lock:
            conn = self._connect()
            conn.execute("DELETE FROM readings WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            conn.commit()

    def update_session(
        self,
        session_id: int,
        initial_percent: Optional[float] = None,
        target_percent: Optional[float] = None,
        price_per_kwh: Optional[float] = None,
        final_percent: Optional[float] = None,
        total_kwh: Optional[float] = None,
    ) -> None:
        with self._lock:
            conn = self._connect()
            fields = {
                "initial_percent": initial_percent,
                "target_percent": target_percent,
                "price_per_kwh": price_per_kwh,
                "final_percent": final_percent,
            }
            set_clauses = [f"{key} = ?" for key, value in fields.items() if value is not None]
            values = [value for value in fields.values() if value is not None]
            if set_clauses:
                conn.execute(
                    f"UPDATE sessions SET {', '.join(set_clauses)} WHERE id = ?",
                    (*values, session_id),
                )
            if total_kwh is not None:
                # A single cumulative reading replaces the log: the history
                # row shows one aggregate number, so "editing the kWh" means
                # correcting that number, not any particular reading.
                conn.execute("DELETE FROM readings WHERE session_id = ?", (session_id,))
                conn.execute(
                    "INSERT INTO readings (session_id, kwh, source, timestamp) VALUES (?, ?, 'manual', ?)",
                    (session_id, total_kwh, _now()),
                )
            conn.commit()

    def get_active_session(self) -> Optional[dict]:
        with self._lock:
            conn = self._connect()
            row = conn.execute(
                "SELECT id FROM sessions WHERE status = 'active' ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return self.get_session(row["id"])

    def get_session(self, session_id: int) -> Optional[dict]:
        with self._lock:
            conn = self._connect()
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if row is None:
                return None
            readings = conn.execute(
                "SELECT * FROM readings WHERE session_id = ? ORDER BY id", (session_id,)
            ).fetchall()
        session = dict(row)
        session["readings"] = [dict(r) for r in readings]
        return session

    # ---- MyAudi credentials (set from the PWA, not just .env) ---------

    _MYAUDI_KEYS = ("myaudi_username", "myaudi_password", "myaudi_spin")

    def get_myaudi_credentials(self) -> Optional[dict]:
        with self._lock:
            rows = self._connect().execute(
                "SELECT key, value FROM config WHERE key IN (?, ?, ?)", self._MYAUDI_KEYS
            ).fetchall()
        raw = {row["key"]: row["value"] for row in rows}
        username = raw.get("myaudi_username")
        password = raw.get("myaudi_password")
        if not username or not password:
            return None
        return {"username": username, "password": password, "spin": raw.get("myaudi_spin") or None}

    def set_myaudi_credentials(self, username: str, password: str, spin: Optional[str]) -> None:
        with self._lock:
            conn = self._connect()
            for key, value in (
                ("myaudi_username", username),
                ("myaudi_password", password),
                ("myaudi_spin", spin or ""),
            ):
                conn.execute(
                    "INSERT INTO config (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, value),
                )
            conn.commit()

    def clear_myaudi_credentials(self) -> None:
        with self._lock:
            conn = self._connect()
            conn.execute(
                "DELETE FROM config WHERE key IN (?, ?, ?)", self._MYAUDI_KEYS
            )
            conn.commit()

    def list_sessions(self) -> list[dict]:
        with self._lock:
            conn = self._connect()
            rows = conn.execute("SELECT * FROM sessions ORDER BY id DESC").fetchall()
            result = []
            for row in rows:
                session = dict(row)
                readings = conn.execute(
                    "SELECT * FROM readings WHERE session_id = ? ORDER BY id", (session["id"],)
                ).fetchall()
                session["readings"] = [dict(r) for r in readings]
                result.append(session)
        return result
