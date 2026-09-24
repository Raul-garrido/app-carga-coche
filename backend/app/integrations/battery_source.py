"""Where the current battery % (MyAudi's number) comes from.

The rest of the app only ever talks to `BatterySource.get_soc()`. Swapping
the automatic MyAudi client for manual entry (or back) is a config change,
not a rewrite — see docs/ARCHITECTURE.md for why this indirection exists.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from app.store import Store


@dataclass(frozen=True)
class BatteryReading:
    percent: float
    source: str
    updated_at: datetime


class BatterySource(ABC):
    @abstractmethod
    async def get_soc(self) -> BatteryReading:
        """Return the latest known state of charge."""


class ManualBatterySource(BatterySource):
    """Fallback (and, for v1, primary) source: the user types the % shown
    by the MyAudi app."""

    def __init__(self, store: Store):
        self._store = store

    async def get_soc(self) -> BatteryReading:
        row = self._store.get_manual_soc()
        if row is None:
            raise LookupError(
                "No manual SoC set yet. POST /api/battery/manual with the "
                "percentage shown in MyAudi."
            )
        return BatteryReading(
            percent=row["percent"],
            source="manual",
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )


class MyAudiBatterySource(BatterySource):
    """Automatic source backed by the isolated MyAudi client.

    Falls back to the manual source on any failure (expired session,
    rate limit, Audi backend change, etc.) so a broken integration never
    takes the whole app down with it.
    """

    def __init__(self, store: Store, myaudi_client, fallback: BatterySource):
        self._store = store
        self._client = myaudi_client
        self._fallback = fallback

    async def get_soc(self) -> BatteryReading:
        try:
            percent = await self._client.fetch_soc()
        except Exception:
            return await self._fallback.get_soc()
        return BatteryReading(percent=percent, source="myaudi", updated_at=datetime.now())
