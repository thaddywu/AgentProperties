"""Coverage horizon, order-up-to target, pack rounding, exposure, and the
projected-stockout test used for ranking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Mapping, Sequence

from .domain import CalendarLabel
from .forecast import aggregate_forecast, integer_demand

REVIEW_PERIOD_DAYS = 1


def coverage_days(lead_time_days: int, safety_days: int) -> int:
    """``L + 1 + S`` — lead time, the one-day review period, and safety days."""
    return lead_time_days + REVIEW_PERIOD_DAYS + safety_days


def coverage_window(run_date: date, lead_time_days: int, safety_days: int) -> list[date]:
    """The inclusive covered dates, beginning with the run's business date."""
    span = coverage_days(lead_time_days, safety_days)
    return [run_date + timedelta(days=offset) for offset in range(span)]


def pack_rounded_quantity(raw_requirement: int, pack_size: int) -> int:
    """Round a positive requirement up to the smallest whole pack containing it."""
    if pack_size <= 0:
        raise ValueError("pack size must be positive")
    if raw_requirement <= 0:
        return 0
    packs = -(-raw_requirement // pack_size)  # integer ceiling division
    return packs * pack_size


@dataclass(frozen=True)
class SupplierPlan:
    """The order-up-to computation for one supplier's offer."""

    lead_time_days: int
    safety_days: int
    coverage_days: int
    coverage_dates: tuple[date, ...]
    coverage_forecast: Decimal
    target_inventory: int
    on_hand: int
    outstanding_quantity: int
    inventory_position: int
    raw_requirement: int
    pack_size: int
    order_quantity: int
    exposure_after_order: int


def build_plan(
    *,
    run_date: date,
    base: Decimal,
    labels_by_date: Mapping[date, CalendarLabel],
    multipliers: Mapping[CalendarLabel, Decimal],
    lead_time_days: int,
    safety_days: int,
    on_hand: int,
    outstanding_quantity: int,
    pack_size: int,
) -> SupplierPlan:
    dates = coverage_window(run_date, lead_time_days, safety_days)
    coverage_total = aggregate_forecast(base, dates, labels_by_date, multipliers)
    target = integer_demand(coverage_total)
    position = on_hand + outstanding_quantity
    raw_requirement = max(0, target - position)
    order_quantity = pack_rounded_quantity(raw_requirement, pack_size)
    return SupplierPlan(
        lead_time_days=lead_time_days,
        safety_days=safety_days,
        coverage_days=len(dates),
        coverage_dates=tuple(dates),
        coverage_forecast=coverage_total,
        target_inventory=target,
        on_hand=on_hand,
        outstanding_quantity=outstanding_quantity,
        inventory_position=position,
        raw_requirement=raw_requirement,
        pack_size=pack_size,
        order_quantity=order_quantity,
        exposure_after_order=position + order_quantity,
    )


@dataclass(frozen=True)
class StockoutProjection:
    arrival_date: date
    demand_dates: tuple[date, ...]
    demand_forecast: Decimal
    expected_demand_before_arrival: int
    expected_supply_before_arrival: int
    avoids_stockout: bool


def project_stockout(
    *,
    run_date: date,
    lead_time_days: int,
    base: Decimal,
    labels_by_date: Mapping[date, CalendarLabel],
    multipliers: Mapping[CalendarLabel, Decimal],
    on_hand: int,
    arriving_before: Sequence[tuple[date, int]],
) -> StockoutProjection:
    """Rank-only projection of whether stock lasts until this offer arrives.

    ``arriving_before`` pairs each contributing outstanding order's promised
    delivery date with its quantity.  This never alters authoritative on-hand
    or outstanding quantity.
    """
    arrival = run_date + timedelta(days=lead_time_days)
    demand_dates = [
        run_date + timedelta(days=offset) for offset in range(lead_time_days)
    ]
    demand_total = aggregate_forecast(base, demand_dates, labels_by_date, multipliers)
    demand = integer_demand(demand_total)
    supply = on_hand + sum(
        quantity for promised, quantity in arriving_before if promised <= arrival
    )
    return StockoutProjection(
        arrival_date=arrival,
        demand_dates=tuple(demand_dates),
        demand_forecast=demand_total,
        expected_demand_before_arrival=demand,
        expected_supply_before_arrival=supply,
        avoids_stockout=supply >= demand,
    )
