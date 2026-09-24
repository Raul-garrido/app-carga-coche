from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from app.calculator import charge_plan, session_summary
from app.models import (
    ReadingCreateIn,
    ReadingOut,
    SessionCreateIn,
    SessionFinishIn,
    SessionOut,
    SessionUpdateIn,
)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _to_session_out(session: dict) -> SessionOut:
    accumulated_kwh = session["readings"][-1]["kwh"] if session["readings"] else 0.0

    summary = session_summary(
        capacity_kwh=session["battery_capacity_kwh"],
        initial_percent=session["initial_percent"],
        accumulated_kwh=accumulated_kwh,
        price_per_kwh=session["price_per_kwh"],
    )
    plan = charge_plan(
        capacity_kwh=session["battery_capacity_kwh"],
        initial_percent=session["initial_percent"],
        target_percent=session["target_percent"],
        price_per_kwh=session["price_per_kwh"],
    )

    return SessionOut(
        id=session["id"],
        status=session["status"],
        started_at=session["started_at"],
        ended_at=session["ended_at"],
        battery_capacity_kwh=session["battery_capacity_kwh"],
        initial_percent=session["initial_percent"],
        target_percent=session["target_percent"],
        final_percent=session["final_percent"],
        price_per_kwh=session["price_per_kwh"],
        accumulated_kwh=summary.accumulated_kwh,
        accumulated_cost=summary.accumulated_cost,
        estimated_final_percent=summary.estimated_final_percent,
        target_kwh=plan.target_kwh,
        remaining_kwh_to_target=plan.remaining_kwh,
        estimated_cost_to_target=plan.estimated_cost,
        readings=[ReadingOut(**r) for r in session["readings"]],
    )


@router.post("", response_model=SessionOut)
def create_session(payload: SessionCreateIn, request: Request) -> SessionOut:
    store = request.app.state.store
    cfg = store.get_config()
    capacity = payload.battery_capacity_kwh or cfg["battery_capacity_kwh"]

    session_id = store.create_session(
        battery_capacity_kwh=capacity,
        initial_percent=payload.initial_percent,
        target_percent=payload.target_percent,
        price_per_kwh=payload.price_per_kwh,
    )
    return _to_session_out(store.get_session(session_id))


@router.get("", response_model=list[SessionOut])
def list_sessions(request: Request) -> list[SessionOut]:
    store = request.app.state.store
    return [_to_session_out(s) for s in store.list_sessions()]


@router.get("/active", response_model=Optional[SessionOut])
def get_active_session(request: Request) -> Optional[SessionOut]:
    """Lets the frontend pick up a session it didn't itself start — e.g.
    one opened automatically by the MyAudi auto-session poller — instead
    of relying only on the id it remembers locally."""
    store = request.app.state.store
    session = store.get_active_session()
    return _to_session_out(session) if session else None


@router.get("/{session_id}", response_model=SessionOut)
def get_session(session_id: int, request: Request) -> SessionOut:
    store = request.app.state.store
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return _to_session_out(session)


@router.post("/{session_id}/readings", response_model=SessionOut)
def add_reading(session_id: int, payload: ReadingCreateIn, request: Request) -> SessionOut:
    store = request.app.state.store
    charge_source = request.app.state.charge_source
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["status"] != "active":
        raise HTTPException(status_code=409, detail="Session already finished")

    timestamp = payload.timestamp.isoformat() if payload.timestamp else None
    charge_source.record_reading(session_id, payload.kwh, timestamp)
    return _to_session_out(store.get_session(session_id))


@router.patch("/{session_id}", response_model=SessionOut)
def update_session(session_id: int, payload: SessionUpdateIn, request: Request) -> SessionOut:
    store = request.app.state.store
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    store.update_session(session_id, **payload.model_dump(exclude_none=True))
    return _to_session_out(store.get_session(session_id))


@router.delete("/{session_id}", status_code=204)
def delete_session(session_id: int, request: Request) -> None:
    store = request.app.state.store
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    store.delete_session(session_id)


@router.post("/{session_id}/finish", response_model=SessionOut)
def finish_session(session_id: int, payload: SessionFinishIn, request: Request) -> SessionOut:
    store = request.app.state.store
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["status"] != "active":
        raise HTTPException(status_code=409, detail="Session already finished")

    final_percent = payload.final_percent
    if final_percent is None:
        out = _to_session_out(session)
        final_percent = out.estimated_final_percent

    store.finish_session(session_id, final_percent)
    return _to_session_out(store.get_session(session_id))
