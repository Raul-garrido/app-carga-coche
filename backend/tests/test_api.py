import os
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    tmpdir = tempfile.mkdtemp()
    monkeypatch.setenv("APP_DATA_DIR", tmpdir)
    monkeypatch.delenv("MYAUDI_AUTO_ENABLED", raising=False)

    # Reload config/app so env vars above take effect for this test.
    import importlib

    from app import config as app_config

    importlib.reload(app_config)

    from app import main as app_main

    importlib.reload(app_main)

    with TestClient(app_main.app) as test_client:
        yield test_client


def test_config_defaults(client):
    resp = client.get("/api/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["battery_capacity_kwh"] == 14.4
    assert body["myaudi_auto_enabled"] is False


def test_battery_status_requires_manual_soc_first(client):
    resp = client.get("/api/battery/status")
    assert resp.status_code == 404


def test_manual_soc_and_plan_flow(client):
    resp = client.post("/api/battery/manual", json={"percent": 50})
    assert resp.status_code == 200
    assert resp.json()["percent"] == 50

    resp = client.get("/api/battery/status")
    assert resp.status_code == 200
    assert resp.json()["source"] == "manual"

    resp = client.get("/api/battery/plan", params={"price_per_kwh": 0.15, "target_percent": 100})
    assert resp.status_code == 200
    body = resp.json()
    assert body["charged_kwh"] == pytest.approx(7.2)
    assert body["remaining_kwh"] == pytest.approx(7.2)
    assert body["estimated_cost"] == pytest.approx(1.08)


def test_full_session_lifecycle(client):
    create = client.post(
        "/api/sessions",
        json={"initial_percent": 50, "target_percent": 100, "price_per_kwh": 0.15},
    )
    assert create.status_code == 200
    session = create.json()
    assert session["status"] == "active"
    assert session["remaining_kwh_to_target"] == pytest.approx(7.2)
    session_id = session["id"]

    add1 = client.post(f"/api/sessions/{session_id}/readings", json={"kwh": 2.0})
    assert add1.status_code == 200
    assert add1.json()["accumulated_kwh"] == pytest.approx(2.0)
    assert add1.json()["accumulated_cost"] == pytest.approx(0.30)

    add2 = client.post(f"/api/sessions/{session_id}/readings", json={"kwh": 5.5})
    assert add2.status_code == 200
    assert add2.json()["accumulated_cost"] == pytest.approx(0.825)

    finish = client.post(f"/api/sessions/{session_id}/finish", json={})
    assert finish.status_code == 200
    finished = finish.json()
    assert finished["status"] == "finished"
    assert finished["final_percent"] == pytest.approx(88.19444, rel=1e-3)

    history = client.get("/api/sessions")
    assert history.status_code == 200
    assert len(history.json()) == 1

    second_finish = client.post(f"/api/sessions/{session_id}/finish", json={})
    assert second_finish.status_code == 409
