import logging
import tempfile
from pathlib import Path

import pytest

from app.integrations.battery_source import ManualBatterySource
from app.integrations.myaudi_manager import DynamicBatterySource, MyAudiManager
from app.store import Store


class FakeMyAudiClient:
    """Stands in for the real carconnectivity-backed client so tests never
    touch the network. `status_sequence[-1]` controls what get_status()
    does: an Exception instance is raised, anything else is returned. If
    `log_message` is set, it's logged via the "carconnectivity" logger
    before raising — simulating what the real connector does when it hits
    a real auth/HTTP error worth surfacing verbatim."""

    #: Class-level defaults new instances start from — tests override these
    #: *before* calling into the manager, since MyAudiManager.test() always
    #: constructs a fresh client from the stored credentials.
    next_status_sequence = [RuntimeError("No vehicles on this MyAudi account yet (still fetching?)")]
    next_log_message = None

    def __init__(self, credentials, tokenstore_file, cache_file, poll_interval_seconds=300):
        self.credentials = credentials
        self.started = False
        self.stopped = False
        self.status_sequence = list(FakeMyAudiClient.next_status_sequence)
        self.log_message = FakeMyAudiClient.next_log_message

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def get_status(self):
        outcome = self.status_sequence[-1] if self.status_sequence else RuntimeError("exhausted")
        if isinstance(outcome, Exception):
            if self.log_message:
                logging.getLogger("carconnectivity").error(self.log_message)
            raise outcome
        return outcome


class FakeMyAudiStatus:
    def __init__(self, percent=55.0, charging=True, remaining_minutes=30):
        self.percent = percent
        self.charging = charging
        self.remaining_minutes = remaining_minutes


@pytest.fixture()
def store():
    tmpdir = tempfile.mkdtemp()
    return Store(Path(tmpdir) / "test.db")


@pytest.fixture(autouse=True)
def reset_fake_client_defaults():
    FakeMyAudiClient.next_status_sequence = [
        RuntimeError("No vehicles on this MyAudi account yet (still fetching?)")
    ]
    FakeMyAudiClient.next_log_message = None
    yield


@pytest.fixture()
def manager(store, tmp_path, monkeypatch):
    monkeypatch.setattr("app.integrations.myaudi_source.MyAudiClient", FakeMyAudiClient)
    manual = ManualBatterySource(store)
    dynamic = DynamicBatterySource(manual)
    return MyAudiManager(store, dynamic, manual, tmp_path, test_attempts=1, test_interval_seconds=0)


def test_store_round_trips_credentials(store):
    assert store.get_myaudi_credentials() is None
    store.set_myaudi_credentials("user@example.com", "hunter2", "1234")
    creds = store.get_myaudi_credentials()
    assert creds == {"username": "user@example.com", "password": "hunter2", "spin": "1234"}

    store.clear_myaudi_credentials()
    assert store.get_myaudi_credentials() is None


def test_store_credentials_optional_spin(store):
    store.set_myaudi_credentials("user@example.com", "hunter2", None)
    assert store.get_myaudi_credentials()["spin"] is None


@pytest.mark.asyncio
async def test_enable_and_test_reports_failure(manager, store):
    result = await manager.enable_and_test("user@example.com", "wrongpass", None)

    assert result.ok is False
    assert result.message == "No vehicles on this MyAudi account yet (still fetching?)"
    # Credentials are still saved even though the connection failed, so the
    # user doesn't have to retype them just to hit "Probar conexión" again.
    assert store.get_myaudi_credentials()["username"] == "user@example.com"
    status = manager.status()
    assert status.enabled is True
    assert status.connected is False
    assert status.last_error == result.message


@pytest.mark.asyncio
async def test_prefers_real_library_error_over_generic_exception(manager):
    real_message = '400 Client Error: Bad Request {"error":"invalid assertion headers"}'
    FakeMyAudiClient.next_log_message = real_message
    FakeMyAudiClient.next_status_sequence = [RuntimeError("generic failure, ignored")]

    result = await manager.enable_and_test("user@example.com", "wrongpass", None)

    assert result.ok is False
    assert result.message == real_message


@pytest.mark.asyncio
async def test_enable_and_test_reports_success_once_reachable(manager):
    FakeMyAudiClient.next_status_sequence = [FakeMyAudiStatus(percent=61.5, charging=True)]

    result = await manager.enable_and_test("user@example.com", "correct", None)

    assert result.ok is True
    assert result.percent == 61.5
    assert manager.status().connected is True


@pytest.mark.asyncio
async def test_test_restarts_client_for_a_genuinely_fresh_attempt(manager):
    # First attempt fails (default fake behaviour)...
    first = await manager.enable_and_test("user@example.com", "correct", None)
    assert first.ok is False

    # ...even though nothing explicitly "fixed" the old (now dead) client,
    # pressing "Probar conexión" again must try a brand new one rather than
    # reusing the stale failure forever.
    FakeMyAudiClient.next_status_sequence = [FakeMyAudiStatus(percent=42.0, charging=False)]
    second = await manager.test()

    assert second.ok is True
    assert second.percent == 42.0


def test_disable_clears_credentials_and_reverts_to_manual(manager, store):
    store.set_myaudi_credentials("user@example.com", "pw", None)
    manager.restore_from_store()
    assert manager.status().enabled is True

    manager.disable()

    assert manager.status().enabled is False
    assert store.get_myaudi_credentials() is None


def test_status_username_is_masked(manager):
    manager._start_client("someone@example.com", "pw", None)
    assert manager.status().username == "so***@example.com"
