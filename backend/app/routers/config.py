from __future__ import annotations

from fastapi import APIRouter, Request

from app import config as app_config
from app.models import ConfigOut, ConfigUpdate

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("", response_model=ConfigOut)
def get_config(request: Request) -> ConfigOut:
    store = request.app.state.store
    cfg = store.get_config()
    return ConfigOut(**cfg, myaudi_auto_enabled=app_config.MYAUDI_AUTO_ENABLED)


@router.put("", response_model=ConfigOut)
def update_config(payload: ConfigUpdate, request: Request) -> ConfigOut:
    store = request.app.state.store
    cfg = store.update_config(**payload.model_dump(exclude_none=True))
    return ConfigOut(**cfg, myaudi_auto_enabled=app_config.MYAUDI_AUTO_ENABLED)
