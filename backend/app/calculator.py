"""Core cost/energy calculations for a charging session.

Pure functions only: no I/O, no framework types. This is the one module in
the app that must stay correct no matter where the data (SoC, kWh readings)
ends up coming from, which is why it is tested in isolation with fixed
sample data instead of live devices.
"""

from __future__ import annotations

from dataclasses import dataclass


def kwh_from_percent(capacity_kwh: float, percent: float) -> float:
    """kWh represented by a battery percentage, given the pack capacity."""
    return capacity_kwh * percent / 100


def percent_from_kwh(capacity_kwh: float, kwh: float) -> float:
    """Inverse of kwh_from_percent, clamped to [0, 100]."""
    if capacity_kwh <= 0:
        raise ValueError("capacity_kwh must be positive")
    percent = kwh / capacity_kwh * 100
    return max(0.0, min(100.0, percent))


@dataclass(frozen=True)
class ChargePlan:
    capacity_kwh: float
    initial_percent: float
    target_percent: float
    charged_kwh: float
    target_kwh: float
    remaining_kwh: float
    estimated_cost: float


def charge_plan(
    capacity_kwh: float,
    initial_percent: float,
    target_percent: float,
    price_per_kwh: float,
) -> ChargePlan:
    """What it takes to go from initial_percent to target_percent.

    Mirrors the "estado inicial" + "coste estimado hasta el objetivo"
    requirements: kWh already in the pack, kWh missing to the target, and
    what completing that gap would cost at the given price.
    """
    if capacity_kwh <= 0:
        raise ValueError("capacity_kwh must be positive")
    if not 0 <= initial_percent <= 100:
        raise ValueError("initial_percent must be within [0, 100]")
    if not 0 <= target_percent <= 100:
        raise ValueError("target_percent must be within [0, 100]")

    charged_kwh = kwh_from_percent(capacity_kwh, initial_percent)
    target_kwh = kwh_from_percent(capacity_kwh, target_percent)
    remaining_kwh = max(target_kwh - charged_kwh, 0.0)
    estimated_cost = remaining_kwh * price_per_kwh

    return ChargePlan(
        capacity_kwh=capacity_kwh,
        initial_percent=initial_percent,
        target_percent=target_percent,
        charged_kwh=charged_kwh,
        target_kwh=target_kwh,
        remaining_kwh=remaining_kwh,
        estimated_cost=estimated_cost,
    )


def session_cost(accumulated_kwh: float, price_per_kwh: float) -> float:
    """Running cost of a charging session for the kWh delivered so far."""
    return accumulated_kwh * price_per_kwh


@dataclass(frozen=True)
class SessionSummary:
    accumulated_kwh: float
    accumulated_cost: float
    estimated_final_percent: float


def session_summary(
    capacity_kwh: float,
    initial_percent: float,
    accumulated_kwh: float,
    price_per_kwh: float,
) -> SessionSummary:
    """Live view of an in-progress (or just-finished) session."""
    estimated_final_percent = percent_from_kwh(
        capacity_kwh, kwh_from_percent(capacity_kwh, initial_percent) + accumulated_kwh
    )
    return SessionSummary(
        accumulated_kwh=accumulated_kwh,
        accumulated_cost=session_cost(accumulated_kwh, price_per_kwh),
        estimated_final_percent=estimated_final_percent,
    )
