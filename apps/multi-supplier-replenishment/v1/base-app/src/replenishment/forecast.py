"""The deterministic 28-day calendar-normalized exponential smoothing model.

There are no learned parameters, no imputation, no trend term, and no seasonal
term.  Twenty-eight complete daily observations are mandatory, including
explicit zero-sale days.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, localcontext
from typing import Mapping, Sequence

from .decimals import FORECAST_CONTEXT, ceil_to_int
from .domain import CalendarLabel

HISTORY_DAYS = 28


class ForecastInputError(ValueError):
    """The forecast inputs were incomplete or inconsistent."""


@dataclass(frozen=True)
class HistoryPoint:
    day: date
    units_sold: int
    label: CalendarLabel
    multiplier: Decimal
    normalized: Decimal
    smoothed: Decimal


@dataclass(frozen=True)
class BaseForecast:
    """The smoothed calendar-neutral daily demand for one SKU."""

    base: Decimal
    points: tuple[HistoryPoint, ...]

    @property
    def window_start(self) -> date:
        return self.points[0].day

    @property
    def window_end(self) -> date:
        return self.points[-1].day


def history_window(run_date: date) -> list[date]:
    """The 28 local business dates immediately preceding the run date."""
    return [
        run_date - timedelta(days=offset)
        for offset in range(HISTORY_DAYS, 0, -1)
    ]


def normalize(units_sold: int, multiplier: Decimal) -> Decimal:
    """Remove the calendar effect from one historical observation."""
    if multiplier <= 0:
        raise ForecastInputError("calendar multiplier must be positive")
    with localcontext(FORECAST_CONTEXT):
        return Decimal(units_sold) / multiplier


def compute_base(
    window: Sequence[date],
    sales_by_date: Mapping[date, int],
    labels_by_date: Mapping[date, CalendarLabel],
    multipliers: Mapping[CalendarLabel, Decimal],
    alpha: Decimal,
) -> BaseForecast:
    """Run the exact normalization and exponential smoothing of Section 6."""
    if len(window) != HISTORY_DAYS:
        raise ForecastInputError(
            f"exactly {HISTORY_DAYS} historical dates are required, got {len(window)}"
        )
    if not (Decimal(0) < alpha <= Decimal(1)):
        raise ForecastInputError("alpha must satisfy 0 < alpha <= 1")

    points: list[HistoryPoint] = []
    with localcontext(FORECAST_CONTEXT):
        one_minus_alpha = Decimal(1) - alpha
        smoothed: Decimal | None = None
        for day in window:
            if day not in sales_by_date:
                raise ForecastInputError(f"missing sales observation for {day}")
            if day not in labels_by_date:
                raise ForecastInputError(f"missing calendar label for {day}")
            label = labels_by_date[day]
            if label not in multipliers:
                raise ForecastInputError(f"no configured multiplier for label {label}")
            multiplier = multipliers[label]
            if multiplier <= 0:
                raise ForecastInputError(
                    f"calendar multiplier for {label} must be positive"
                )
            units = sales_by_date[day]
            normalized = Decimal(units) / multiplier
            if smoothed is None:
                smoothed = normalized
            else:
                smoothed = alpha * normalized + one_minus_alpha * smoothed
            points.append(
                HistoryPoint(
                    day=day,
                    units_sold=units,
                    label=label,
                    multiplier=multiplier,
                    normalized=normalized,
                    smoothed=smoothed,
                )
            )
        assert smoothed is not None
        base = smoothed
    return BaseForecast(base=base, points=tuple(points))


def daily_forecast(
    base: Decimal, label: CalendarLabel, multipliers: Mapping[CalendarLabel, Decimal]
) -> Decimal:
    """Unrounded expected demand for one future date."""
    if label not in multipliers:
        raise ForecastInputError(f"no configured multiplier for label {label}")
    with localcontext(FORECAST_CONTEXT):
        return base * multipliers[label]


def aggregate_forecast(
    base: Decimal,
    days: Sequence[date],
    labels_by_date: Mapping[date, CalendarLabel],
    multipliers: Mapping[CalendarLabel, Decimal],
) -> Decimal:
    """Exact sum of the unrounded daily forecasts over an inclusive sequence."""
    with localcontext(FORECAST_CONTEXT):
        total = Decimal(0)
        for day in days:
            if day not in labels_by_date:
                raise ForecastInputError(f"missing calendar label for {day}")
            total += base * multipliers[labels_by_date[day]]
        return total


def integer_demand(aggregate: Decimal) -> int:
    """Mathematical ceiling of an aggregate forecast, applied exactly once."""
    return ceil_to_int(aggregate)
