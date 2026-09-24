from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.calculator import charge_plan
from app.models import BatteryStatusOut, ManualSocIn, PlanOut

router = APIRouter(prefix="/api/battery", tags=["battery"])


@router.get("/status", response_model=BatteryStatusOut)
async def get_battery_status(request: Request) -> BatteryStatusOut:
    source = request.app.state.battery_source
    try:
        reading = await source.get_soc()
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return BatteryStatusOut(
        percent=reading.percent, source=reading.source, updated_at=reading.updated_at
    )


@router.post("/manual", response_model=BatteryStatusOut)
async def set_manual_soc(payload: ManualSocIn, request: Request) -> BatteryStatusOut:
    store = request.app.state.store
    row = store.set_manual_soc(payload.percent)
    return BatteryStatusOut(percent=row["percent"], source=row["source"], updated_at=row["updated_at"])


@router.get("/plan", response_model=PlanOut)
async def get_plan(
    request: Request,
    price_per_kwh: float = Query(..., ge=0),
    target_percent: float = Query(100, ge=0, le=100),
) -> PlanOut:
    """Quick "what would it cost to reach X%" check, without starting a
    session — covers requirements #1 and #2 on their own."""
    store = request.app.state.store
    source = request.app.state.battery_source
    cfg = store.get_config()
    try:
        reading = await source.get_soc()
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    plan = charge_plan(
        capacity_kwh=cfg["battery_capacity_kwh"],
        initial_percent=reading.percent,
        target_percent=target_percent,
        price_per_kwh=price_per_kwh,
    )
    return PlanOut(**plan.__dict__)
