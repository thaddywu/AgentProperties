"""Section 7: coverage horizon, order-up-to target, pack rounding, exposure,
and the projected-stockout test used only for ranking."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from replenishment.domain import CalendarLabel
from replenishment.planning import (
    REVIEW_PERIOD_DAYS,
    build_plan,
    coverage_days,
    coverage_window,
    pack_rounded_quantity,
    project_stockout,
)

RUN_DATE = date(2026, 9, 3)
MULTIPLIERS = {
    CalendarLabel.NORMAL: Decimal("1.00"),
    CalendarLabel.WEEKEND: Decimal("1.25"),
    CalendarLabel.PRE_HOLIDAY: Decimal("1.40"),
    CalendarLabel.HOLIDAY: Decimal("0.60"),
}
LABELS = {
    RUN_DATE + timedelta(days=offset): CalendarLabel.NORMAL for offset in range(30)
}


def test_review_period_is_exactly_one_day():
    assert REVIEW_PERIOD_DAYS == 1


@pytest.mark.parametrize(
    "lead,safety,expected",
    [(1, 0, 2), (2, 2, 5), (3, 0, 4), (1, 14, 16), (14, 14, 29)],
)
def test_coverage_days_is_lead_plus_review_plus_safety(lead, safety, expected):
    assert coverage_days(lead, safety) == expected


def test_coverage_window_starts_on_the_run_date():
    window = coverage_window(RUN_DATE, lead_time_days=2, safety_days=2)
    assert window[0] == RUN_DATE
    assert len(window) == 5
    assert window[-1] == RUN_DATE + timedelta(days=4)


@pytest.mark.parametrize(
    "raw,pack,expected",
    [
        (0, 10, 0),
        (1, 10, 10),
        (9, 10, 10),
        (10, 10, 10),
        (11, 10, 20),
        (24, 24, 24),
        (25, 24, 48),
        (7, 1, 7),
    ],
)
def test_pack_rounding_uses_the_smallest_whole_pack(raw, pack, expected):
    assert pack_rounded_quantity(raw, pack) == expected


def test_pack_rounding_rejects_a_non_positive_pack_size():
    with pytest.raises(ValueError):
        pack_rounded_quantity(5, 0)


def test_order_up_to_target_and_exposure():
    # base 10 over 5 all-NORMAL covered days is a target of 50 units.
    plan = build_plan(
        run_date=RUN_DATE,
        base=Decimal("10"),
        labels_by_date=LABELS,
        multipliers=MULTIPLIERS,
        lead_time_days=2,
        safety_days=2,
        on_hand=7,
        outstanding_quantity=3,
        pack_size=12,
    )
    assert plan.coverage_days == 5
    assert plan.coverage_forecast == Decimal("50.00")
    assert plan.target_inventory == 50
    assert plan.inventory_position == 10
    assert plan.raw_requirement == 40
    assert plan.order_quantity == 48  # ceil(40 / 12) * 12
    assert plan.exposure_after_order == 58  # 7 + 3 + 48


def test_a_covered_position_produces_no_candidate():
    plan = build_plan(
        run_date=RUN_DATE,
        base=Decimal("10"),
        labels_by_date=LABELS,
        multipliers=MULTIPLIERS,
        lead_time_days=2,
        safety_days=2,
        on_hand=50,
        outstanding_quantity=0,
        pack_size=12,
    )
    assert plan.target_inventory == 50
    assert plan.raw_requirement == 0
    assert plan.order_quantity == 0


def test_outstanding_quantity_is_counted_once_in_the_position():
    common = dict(
        run_date=RUN_DATE,
        base=Decimal("10"),
        labels_by_date=LABELS,
        multipliers=MULTIPLIERS,
        safety_days=2,
        on_hand=0,
        pack_size=10,
    )
    without = build_plan(lead_time_days=2, outstanding_quantity=0, **common)
    with_outstanding = build_plan(lead_time_days=2, outstanding_quantity=20, **common)
    assert without.raw_requirement == 50
    assert with_outstanding.raw_requirement == 30


def test_a_longer_lead_time_raises_the_target():
    common = dict(
        run_date=RUN_DATE,
        base=Decimal("10"),
        labels_by_date=LABELS,
        multipliers=MULTIPLIERS,
        safety_days=1,
        on_hand=0,
        outstanding_quantity=0,
        pack_size=1,
    )
    assert build_plan(lead_time_days=1, **common).target_inventory == 30
    assert build_plan(lead_time_days=4, **common).target_inventory == 60


def test_calendar_multipliers_apply_to_the_future_horizon():
    labels = dict(LABELS)
    labels[RUN_DATE + timedelta(days=1)] = CalendarLabel.PRE_HOLIDAY
    labels[RUN_DATE + timedelta(days=2)] = CalendarLabel.HOLIDAY
    plan = build_plan(
        run_date=RUN_DATE,
        base=Decimal("10"),
        labels_by_date=labels,
        multipliers=MULTIPLIERS,
        lead_time_days=1,
        safety_days=1,
        on_hand=0,
        outstanding_quantity=0,
        pack_size=1,
    )
    # 10 * (1.00 + 1.40 + 0.60) = 30
    assert plan.coverage_days == 3
    assert plan.coverage_forecast == Decimal("30.00")
    assert plan.target_inventory == 30


def test_fractional_aggregate_is_ceiled_once():
    plan = build_plan(
        run_date=RUN_DATE,
        base=Decimal("2.5"),
        labels_by_date=LABELS,
        multipliers=MULTIPLIERS,
        lead_time_days=1,
        safety_days=1,
        on_hand=0,
        outstanding_quantity=0,
        pack_size=1,
    )
    assert plan.coverage_forecast == Decimal("7.50")
    assert plan.target_inventory == 8


def test_projection_counts_only_supply_arriving_before_the_candidate():
    projection = project_stockout(
        run_date=RUN_DATE,
        lead_time_days=3,
        base=Decimal("10"),
        labels_by_date=LABELS,
        multipliers=MULTIPLIERS,
        on_hand=5,
        arriving_before=(
            (RUN_DATE + timedelta(days=1), 20),  # arrives in time
            (RUN_DATE + timedelta(days=3), 7),   # arrives on the arrival date
            (RUN_DATE + timedelta(days=9), 100),  # too late to help
        ),
    )
    assert projection.arrival_date == RUN_DATE + timedelta(days=3)
    assert len(projection.demand_dates) == 3  # the run date and the two days after
    assert projection.expected_demand_before_arrival == 30
    assert projection.expected_supply_before_arrival == 32  # 5 + 20 + 7
    assert projection.avoids_stockout is True


def test_projection_detects_a_shortage_before_arrival():
    projection = project_stockout(
        run_date=RUN_DATE,
        lead_time_days=4,
        base=Decimal("10"),
        labels_by_date=LABELS,
        multipliers=MULTIPLIERS,
        on_hand=5,
        arriving_before=(),
    )
    assert projection.expected_demand_before_arrival == 40
    assert projection.expected_supply_before_arrival == 5
    assert projection.avoids_stockout is False


def test_projection_boundary_when_supply_exactly_meets_demand():
    projection = project_stockout(
        run_date=RUN_DATE,
        lead_time_days=2,
        base=Decimal("10"),
        labels_by_date=LABELS,
        multipliers=MULTIPLIERS,
        on_hand=20,
        arriving_before=(),
    )
    assert projection.expected_demand_before_arrival == 20
    assert projection.avoids_stockout is True
