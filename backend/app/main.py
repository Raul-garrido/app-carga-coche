from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import config
from app.integrations.battery_source import ManualBatterySource, MyAudiBatterySource
from app.integrations.charge_source import ManualChargeSource
from app.routers import battery, config as config_router, sessions
from app.store import Store


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    store = Store(config.DB_PATH)
    manual_source = ManualBatterySource(store)

    battery_source = manual_source
    if config.MYAUDI_AUTO_ENABLED:
        from app.integrations.myaudi_source import MyAudiClient, MyAudiCredentials

        if not config.MYAUDI_USERNAME or not config.MYAUDI_PASSWORD:
            raise RuntimeError(
                "MYAUDI_AUTO_ENABLED=true requires MYAUDI_USERNAME and MYAUDI_PASSWORD"
            )
        client = MyAudiClient(
            MyAudiCredentials(
                username=config.MYAUDI_USERNAME,
                password=config.MYAUDI_PASSWORD,
                spin=config.MYAUDI_SPIN,
            ),
            min_poll_interval_seconds=config.MYAUDI_MIN_POLL_INTERVAL_SECONDS,
        )
        battery_source = MyAudiBatterySource(store, client, fallback=manual_source)

    app.state.store = store
    app.state.battery_source = battery_source
    app.state.charge_source = ManualChargeSource(store)

    yield


app = FastAPI(title="Calculadora de coste de carga", lifespan=lifespan)

app.include_router(config_router.router)
app.include_router(battery.router)
app.include_router(sessions.router)

if config.FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=config.FRONTEND_DIR, html=True), name="frontend")
