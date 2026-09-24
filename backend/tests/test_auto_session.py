import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from app.auto_session import AutoSessionManager
from app.integrations.battery_source import BatteryReading
from app.store import Store


class FakeBatterySource:
    """Returns readings from a fixed script, one per call to get_soc()."""

    def __init__(self, readings):
        self._readings = list(readings)

    async def get_soc(self):
        if not self._readings:
            raise LookupError("no more readings scripted")
        return self._readings.pop(0)


def reading(percent, charging):
    return BatteryReading(percent=percent, source="myaudi", updated_at=datetime.now(), charging=charging)


@pytest.fixture()
def store():
    tmpdir = tempfile.mkdtemp()
    return Store(Path(tmpdir) / "test.db")


@pytest.mark.asyncio
async def test_manual_source_is_a_no_op(store):
    source = FakeBatterySource([reading(50, None)])
    manager = AutoSessionManager(store, source)
    await manager._tick()
    assert store.get_active_session() is None


@pytest.mark.asyncio
async def test_starts_session_when_charging_begins(store):
    store.update_config(default_price_per_kwh=0.15)
    source = FakeBatterySource([reading(40, False), reading(40, True)])
    manager = AutoSessionManager(store, source)

    await manager._tick()  # not charging yet
    assert store.get_active_session() is None

    await manager._tick()  # charging starts
    active = store.get_active_session()
    assert active is not None
    assert active["initial_percent"] == 40
    assert active["price_per_kwh"] == 0.15


@pytest.mark.asyncio
async def test_does_not_start_session_without_default_price(store):
    source = FakeBatterySource([reading(40, False), reading(40, True)])
    manager = AutoSessionManager(store, source)
    await manager._tick()
    await manager._tick()
    assert store.get_active_session() is None


@pytest.mark.asyncio
async def test_does_not_duplicate_active_session_while_still_charging(store):
    store.update_config(default_price_per_kwh=0.15)
    source = FakeBatterySource([reading(40, False), reading(45, True), reading(60, True)])
    manager = AutoSessionManager(store, source)
    await manager._tick()
    await manager._tick()
    first_id = store.get_active_session()["id"]
    await manager._tick()
    assert store.get_active_session()["id"] == first_id
    assert len(store.list_sessions()) == 1


@pytest.mark.asyncio
async def test_finishes_session_when_charging_stops(store):
    store.update_config(default_price_per_kwh=0.15)
    source = FakeBatterySource([reading(40, False), reading(40, True), reading(90, False)])
    manager = AutoSessionManager(store, source)
    await manager._tick()
    await manager._tick()
    session_id = store.get_active_session()["id"]

    await manager._tick()
    assert store.get_active_session() is None
    finished = store.get_session(session_id)
    assert finished["status"] == "finished"
    assert finished["final_percent"] == 90
