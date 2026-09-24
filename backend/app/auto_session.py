"""Opens and closes a charging session on its own, based on MyAudi's
charging state, so that with MYAUDI_AUTO_ENABLED=true you don't have to
tap "Iniciar sesión" / "Finalizar sesión" by hand — only the Policharger
kWh readings stay manual, since there is no automatic source for those.

No-ops entirely when the active battery source doesn't report a
`charging` flag (i.e. manual SoC mode): there's nothing to poll.
"""

from __future__ import annotations

import asyncio
import logging

from app.integrations.battery_source import BatterySource
from app.store import Store

LOG = logging.getLogger(__name__)


class AutoSessionManager:
    def __init__(self, store: Store, battery_source: BatterySource, check_interval_seconds: int = 30):
        self._store = store
        self._battery_source = battery_source
        self._check_interval = check_interval_seconds
        self._task: asyncio.Task | None = None
        self._was_charging = False

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await self._tick()
            except Exception:
                LOG.exception("auto-session check failed")
            await asyncio.sleep(self._check_interval)

    async def _tick(self) -> None:
        try:
            reading = await self._battery_source.get_soc()
        except LookupError:
            return  # no SoC known at all yet

        if reading.charging is None:
            return  # manual source: no charging signal to act on

        active = self._store.get_active_session()

        if reading.charging and not self._was_charging and active is None:
            self._try_start_session(reading.percent)
        elif not reading.charging and self._was_charging and active is not None:
            self._store.finish_session(active["id"], reading.percent)
            LOG.info("Auto-finished charging session %s at %.1f%%", active["id"], reading.percent)

        self._was_charging = reading.charging

    def _try_start_session(self, initial_percent: float) -> None:
        cfg = self._store.get_config()
        if cfg["default_price_per_kwh"] is None:
            LOG.warning(
                "MyAudi reports charging has started, but no default price/kWh is "
                "configured (PUT /api/config) — cannot auto-open a session without one."
            )
            return
        session_id = self._store.create_session(
            battery_capacity_kwh=cfg["battery_capacity_kwh"],
            initial_percent=initial_percent,
            target_percent=cfg["default_target_percent"],
            price_per_kwh=cfg["default_price_per_kwh"],
        )
        LOG.info("Auto-started charging session %s at %.1f%%", session_id, initial_percent)
