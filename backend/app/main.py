from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import config
from app.auto_session import AutoSessionManager
from app.integrations.battery_source import ManualBatterySource
from app.integrations.charge_source import ManualChargeSource
from app.integrations.myaudi_manager import DynamicBatterySource, MyAudiManager
from app.routers import battery, config as config_router, myaudi, sessions
from app.store import Store


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    store = Store(config.DB_PATH)
    manual_source = ManualBatterySource(store)
    dynamic_source = DynamicBatterySource(manual_source)

    myaudi_manager = MyAudiManager(store, dynamic_source, manual_source, config.DATA_DIR)
    # Credentials saved from the PWA settings screen (SQLite) take priority
    # over the legacy .env-only path, so switching accounts never needs a
    # server restart.
    restored_from_store = myaudi_manager.restore_from_store()
    if not restored_from_store and config.MYAUDI_AUTO_ENABLED:
        if not config.MYAUDI_USERNAME or not config.MYAUDI_PASSWORD:
            raise RuntimeError(
                "MYAUDI_AUTO_ENABLED=true requires MYAUDI_USERNAME and MYAUDI_PASSWORD"
            )
        myaudi_manager.enable_from_env(
            config.MYAUDI_USERNAME, config.MYAUDI_PASSWORD, config.MYAUDI_SPIN
        )

    app.state.store = store
    app.state.battery_source = dynamic_source
    app.state.myaudi_manager = myaudi_manager
    app.state.charge_source = ManualChargeSource(store)

    auto_session_manager = AutoSessionManager(store, dynamic_source)
    auto_session_manager.start()

    yield

    auto_session_manager.stop()
    myaudi_manager.shutdown()


app = FastAPI(title="Calculadora de coste de carga", lifespan=lifespan)

app.include_router(config_router.router)
app.include_router(battery.router)
app.include_router(sessions.router)
app.include_router(myaudi.router)

if config.FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=config.FRONTEND_DIR, html=True), name="frontend")
