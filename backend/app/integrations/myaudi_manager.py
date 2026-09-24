"""Runtime controller for the optional MyAudi integration.

Lets credentials be set and tested from the API (and therefore from the
PWA itself, in self-hosted mode) instead of only via `.env` + a server
restart, and hot-swaps the active `BatterySource` without restarting the
app. Credentials live in the SQLite store (`Store.set_myaudi_credentials`),
next to everything else this single-user app already persists there —
never in the browser, and never in the git repo.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.integrations.battery_source import BatteryReading, BatterySource, ManualBatterySource, MyAudiBatterySource
from app.store import Store


class _LastErrorCapture(logging.Handler):
    """Collects the concise ERROR-level messages logged by the
    carconnectivity loggers during a connection attempt (e.g. "Token
    exchange failed: ..." / "...invalid assertion headers..."), so the real
    failure reason reaches the API instead of the generic "no vehicles yet"
    that `MyAudiClient.get_status()` raises on its own.

    Skips CRITICAL on purpose: on a hard failure the connector logs one
    CRITICAL record with a full Python traceback baked into the message
    text itself (not exc_info) — showing that verbatim in the PWA would be
    unreadable, and the concise ERROR-level messages logged just before it
    already say what went wrong."""

    MAX_LENGTH = 600

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
        self._messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno >= logging.CRITICAL:
            return
        message = record.getMessage().strip()
        if not message:
            return
        # Defensive: if some other library embeds a multi-line traceback in
        # an ERROR-level message too, keep only the last line (the actual
        # "ExceptionType: reason"), not the whole stack.
        last_line = message.splitlines()[-1].strip()
        if last_line and last_line not in self._messages:
            self._messages.append(last_line)

    @property
    def last_message(self) -> Optional[str]:
        if not self._messages:
            return None
        combined = " | ".join(self._messages)
        if len(combined) > self.MAX_LENGTH:
            combined = combined[: self.MAX_LENGTH - 1] + "…"
        return combined


class DynamicBatterySource(BatterySource):
    """Delegates to whichever BatterySource is currently active. The rest
    of the app (routers, AutoSessionManager) holds one stable reference to
    this, while MyAudiManager swaps manual <-> MyAudi underneath it."""

    def __init__(self, initial: BatterySource):
        self._active = initial

    def set_active(self, source: BatterySource) -> None:
        self._active = source

    async def get_soc(self) -> BatteryReading:
        return await self._active.get_soc()


class MyAudiManager:
    def __init__(
        self,
        store: Store,
        dynamic_source: DynamicBatterySource,
        manual_source: ManualBatterySource,
        data_dir: Path,
        test_attempts: int = 12,
        test_interval_seconds: float = 1.0,
    ):
        self._store = store
        self._dynamic = dynamic_source
        self._manual = manual_source
        self._data_dir = data_dir
        self._test_attempts = test_attempts
        self._test_interval_seconds = test_interval_seconds
        self._client = None
        self._username: Optional[str] = None
        self._last_connected: Optional[bool] = None
        self._last_error: Optional[str] = None
        self._last_checked_at: Optional[datetime] = None

    def restore_from_store(self) -> bool:
        """Called once at startup. Returns True if credentials were found
        and a client was started (does not itself run the connection
        test — that happens on demand via POST /api/myaudi/test)."""
        creds = self._store.get_myaudi_credentials()
        if creds is None:
            return False
        try:
            self._start_client(creds["username"], creds["password"], creds.get("spin"))
            return True
        except ImportError:
            self._last_error = (
                "Faltan las dependencias de MyAudi en el servidor "
                "(pip install -r requirements-myaudi.txt)."
            )
            return False

    def enable_from_env(self, username: str, password: str, spin: Optional[str]) -> None:
        """Legacy startup path for the .env-only flow (MYAUDI_AUTO_ENABLED).
        Does not persist to the store or run a test — same fire-and-forget
        behaviour this had before the PWA settings screen existed."""
        self._start_client(username, password, spin)

    def status(self):
        from app.models import MyAudiStatusOut

        return MyAudiStatusOut(
            enabled=self._client is not None,
            username=_mask(self._username) if self._username else None,
            connected=self._last_connected,
            last_checked_at=self._last_checked_at,
            last_error=self._last_error,
        )

    def _start_client(self, username: str, password: str, spin: Optional[str]) -> None:
        from app.integrations.myaudi_source import MyAudiClient, MyAudiCredentials

        self._stop_client()
        client = MyAudiClient(
            MyAudiCredentials(username=username, password=password, spin=spin or None),
            tokenstore_file=self._data_dir / "myaudi_tokenstore.json",
            cache_file=self._data_dir / "myaudi_cache.json",
        )
        client.start()
        self._client = client
        self._username = username
        self._dynamic.set_active(MyAudiBatterySource(self._store, client, fallback=self._manual))

    def _stop_client(self) -> None:
        if self._client is not None:
            self._client.stop()
            self._client = None
        self._dynamic.set_active(self._manual)

    def disable(self) -> None:
        self._stop_client()
        self._store.clear_myaudi_credentials()
        self._username = None
        self._last_connected = None
        self._last_error = None
        self._last_checked_at = None

    def shutdown(self) -> None:
        self._stop_client()

    async def enable_and_test(self, username: str, password: str, spin: Optional[str]):
        self._store.set_myaudi_credentials(username, password, spin)
        return await self.test()

    async def test(self):
        """Starts a fresh client from the stored credentials and polls it
        for a real answer. Always restarts (rather than reusing whatever
        client is already running): once the connector's background thread
        dies after a hard auth failure, it does not retry on its own, so
        reusing it would just show the same stale error forever instead of
        a genuine new attempt each time the user presses "Probar
        conexión"."""
        from app.models import MyAudiTestOut

        creds = self._store.get_myaudi_credentials()
        if creds is None:
            return MyAudiTestOut(ok=False, message="No hay credenciales guardadas todavía.")

        try:
            self._start_client(creds["username"], creds["password"], creds.get("spin"))
        except ImportError:
            message = (
                "Faltan las dependencias de MyAudi en el servidor "
                "(pip install -r requirements-myaudi.txt)."
            )
            self._last_error = message
            self._last_connected = False
            return MyAudiTestOut(ok=False, message=message)

        capture = _LastErrorCapture()
        cc_logger = logging.getLogger("carconnectivity")
        cc_logger.addHandler(capture)
        last_exception_message: Optional[str] = None
        try:
            # The connector's background thread fetches on its own schedule;
            # poll get_status() for a while rather than assuming one shot is
            # enough (first login can take a few seconds).
            for _ in range(self._test_attempts):
                await asyncio.sleep(self._test_interval_seconds)
                try:
                    result = await asyncio.to_thread(self._client.get_status)
                except Exception as exc:
                    last_exception_message = str(exc)
                    continue
                self._last_connected = True
                self._last_error = None
                self._last_checked_at = datetime.now(timezone.utc)
                return MyAudiTestOut(
                    ok=True,
                    message="Conectado correctamente con MyAudi.",
                    percent=result.percent,
                    charging=result.charging,
                )

            # Prefer the underlying library's own error log (has the real
            # HTTP/auth detail, e.g. "invalid assertion headers") over the
            # generic exception get_status() raises when nothing's fetched
            # yet, and that over a last-resort generic message.
            message = capture.last_message or last_exception_message or (
                "No se ha podido conectar (sin más detalle disponible; puede que "
                "necesite más tiempo — prueba de nuevo en un minuto)."
            )
            self._last_connected = False
            self._last_error = message
            self._last_checked_at = datetime.now(timezone.utc)
            return MyAudiTestOut(ok=False, message=message)
        finally:
            cc_logger.removeHandler(capture)


def _mask(username: str) -> str:
    if "@" in username:
        local, _, domain = username.partition("@")
        visible = local[:2]
        return f"{visible}***@{domain}"
    return f"{username[:2]}***" if len(username) > 2 else "***"
