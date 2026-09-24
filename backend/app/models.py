"""Pydantic request/response models for the API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

ReadingSource = Literal["manual", "policharger_auto"]
BatterySourceKind = Literal["manual", "myaudi"]


class ConfigOut(BaseModel):
    battery_capacity_kwh: float
    default_target_percent: float
    default_price_per_kwh: Optional[float] = None
    myaudi_auto_enabled: bool


class ConfigUpdate(BaseModel):
    battery_capacity_kwh: Optional[float] = Field(default=None, gt=0)
    default_target_percent: Optional[float] = Field(default=None, ge=0, le=100)
    default_price_per_kwh: Optional[float] = Field(default=None, ge=0)


class BatteryStatusOut(BaseModel):
    percent: float
    source: BatterySourceKind
    updated_at: datetime
    charging: Optional[bool] = None
    remaining_minutes: Optional[int] = None


class ManualSocIn(BaseModel):
    percent: float = Field(ge=0, le=100)


class PlanOut(BaseModel):
    capacity_kwh: float
    initial_percent: float
    target_percent: float
    charged_kwh: float
    target_kwh: float
    remaining_kwh: float
    estimated_cost: float


class SessionCreateIn(BaseModel):
    initial_percent: float = Field(ge=0, le=100)
    target_percent: float = Field(default=100, ge=0, le=100)
    price_per_kwh: float = Field(ge=0)
    battery_capacity_kwh: Optional[float] = Field(default=None, gt=0)


class ReadingCreateIn(BaseModel):
    kwh: float = Field(ge=0, description="Cumulative kWh reported for this session so far")
    source: ReadingSource = "manual"
    timestamp: Optional[datetime] = None


class SessionFinishIn(BaseModel):
    final_percent: Optional[float] = Field(default=None, ge=0, le=100)


class SessionUpdateIn(BaseModel):
    initial_percent: Optional[float] = Field(default=None, ge=0, le=100)
    target_percent: Optional[float] = Field(default=None, ge=0, le=100)
    price_per_kwh: Optional[float] = Field(default=None, ge=0)
    final_percent: Optional[float] = Field(default=None, ge=0, le=100)
    total_kwh: Optional[float] = Field(default=None, ge=0)


class ReadingOut(BaseModel):
    id: int
    kwh: float
    source: ReadingSource
    timestamp: datetime


class SessionOut(BaseModel):
    id: int
    status: Literal["active", "finished"]
    started_at: datetime
    ended_at: Optional[datetime]
    battery_capacity_kwh: float
    initial_percent: float
    target_percent: float
    final_percent: Optional[float]
    price_per_kwh: float
    accumulated_kwh: float
    accumulated_cost: float
    estimated_final_percent: float
    target_kwh: float
    remaining_kwh_to_target: float
    estimated_cost_to_target: float
    readings: list[ReadingOut] = []
