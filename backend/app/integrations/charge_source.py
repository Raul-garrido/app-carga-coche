"""Where the in-session kWh (Policharger's number) comes from.

For v1 this is manual entry only: no public Policharger API or library was
found (see docs/ARCHITECTURE.md). The interface exists so an automatic
source — if one is ever reverse-engineered — plugs in without touching the
calculator or the session endpoints: both sources just call
`store.add_reading(session_id, kwh, source, timestamp)`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from app.store import Store


class ChargeReadingSource(ABC):
    """Not polled — readings are pushed in as they arrive."""

    @abstractmethod
    def record_reading(
        self, session_id: int, kwh: float, timestamp: Optional[str] = None
    ) -> int:
        """Store a cumulative kWh reading for the session and return its id."""


class ManualChargeSource(ChargeReadingSource):
    """The user reads the kWh/W counter off the Policharger app and types
    it in. This is the only implementation for v1."""

    source_name = "manual"

    def __init__(self, store: Store):
        self._store = store

    def record_reading(
        self, session_id: int, kwh: float, timestamp: Optional[str] = None
    ) -> int:
        return self._store.add_reading(session_id, kwh, self.source_name, timestamp)


# Future automatic source (sketch, not implemented):
#
# class PolichargerAutoSource(ChargeReadingSource):
#     source_name = "policharger_auto"
#
#     def __init__(self, store: Store, mqtt_client):
#         self._store = store
#         self._mqtt_client = mqtt_client
#         mqtt_client.on_message(self._handle_message)
#
#     def _handle_message(self, session_id: int, kwh: float, timestamp: str) -> None:
#         self.record_reading(session_id, kwh, timestamp)
#
#     def record_reading(self, session_id, kwh, timestamp=None):
#         return self._store.add_reading(session_id, kwh, self.source_name, timestamp)
