from __future__ import annotations

from fastapi import APIRouter, Request

from app.models import MyAudiCredentialsIn, MyAudiStatusOut, MyAudiTestOut

router = APIRouter(prefix="/api/myaudi", tags=["myaudi"])


@router.get("/status", response_model=MyAudiStatusOut)
def get_status(request: Request) -> MyAudiStatusOut:
    return request.app.state.myaudi_manager.status()


@router.put("/credentials", response_model=MyAudiTestOut)
async def set_credentials(payload: MyAudiCredentialsIn, request: Request) -> MyAudiTestOut:
    manager = request.app.state.myaudi_manager
    return await manager.enable_and_test(payload.username, payload.password, payload.spin)


@router.delete("/credentials", response_model=MyAudiStatusOut)
def clear_credentials(request: Request) -> MyAudiStatusOut:
    manager = request.app.state.myaudi_manager
    manager.disable()
    return manager.status()


@router.post("/test", response_model=MyAudiTestOut)
async def test_connection(request: Request) -> MyAudiTestOut:
    return await request.app.state.myaudi_manager.test()
