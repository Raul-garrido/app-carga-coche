import pytest

from app.calculator import (
    charge_plan,
    kwh_from_percent,
    percent_from_kwh,
    session_cost,
    session_summary,
)


def test_kwh_from_percent_basic():
    # 50% of a 14.4 kWh pack -> 7.2 kWh, as in the spec example.
    assert kwh_from_percent(14.4, 50) == pytest.approx(7.2)


def test_percent_from_kwh_is_inverse():
    assert percent_from_kwh(14.4, 7.2) == pytest.approx(50.0)


def test_percent_from_kwh_clamps_to_100():
    assert percent_from_kwh(14.4, 999) == 100.0


def test_charge_plan_to_full():
    plan = charge_plan(capacity_kwh=14.4, initial_percent=50, target_percent=100, price_per_kwh=0.15)
    assert plan.charged_kwh == pytest.approx(7.2)
    assert plan.remaining_kwh == pytest.approx(7.2)
    assert plan.estimated_cost == pytest.approx(1.08)


def test_charge_plan_to_partial_target():
    plan = charge_plan(capacity_kwh=14.4, initial_percent=50, target_percent=80, price_per_kwh=0.20)
    # 80% - 50% = 30% of 14.4 kWh = 4.32 kWh
    assert plan.remaining_kwh == pytest.approx(4.32)
    assert plan.estimated_cost == pytest.approx(0.864)


def test_charge_plan_already_past_target_has_zero_remaining():
    plan = charge_plan(capacity_kwh=14.4, initial_percent=90, target_percent=80, price_per_kwh=0.20)
    assert plan.remaining_kwh == 0.0
    assert plan.estimated_cost == 0.0


@pytest.mark.parametrize("capacity", [0, -1])
def test_charge_plan_rejects_invalid_capacity(capacity):
    with pytest.raises(ValueError):
        charge_plan(capacity_kwh=capacity, initial_percent=50, target_percent=100, price_per_kwh=0.15)


@pytest.mark.parametrize("percent", [-1, 101])
def test_charge_plan_rejects_invalid_percent(percent):
    with pytest.raises(ValueError):
        charge_plan(capacity_kwh=14.4, initial_percent=percent, target_percent=100, price_per_kwh=0.15)


def test_session_cost():
    assert session_cost(5.5, 0.18) == pytest.approx(0.99)


def test_session_summary_tracks_progress():
    summary = session_summary(
        capacity_kwh=14.4, initial_percent=50, accumulated_kwh=3.6, price_per_kwh=0.15
    )
    # 3.6 kWh added on top of 7.2 kWh charged = 10.8 kWh -> 75%
    assert summary.estimated_final_percent == pytest.approx(75.0)
    assert summary.accumulated_cost == pytest.approx(0.54)
