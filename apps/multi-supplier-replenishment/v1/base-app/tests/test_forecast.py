"""Section 6: the exact 28-day normalization and exponential smoothing.

Expected values here are stated independently — by closed form, by hand, or by
integer arithmetic — never by calling the production helper a second time.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from replenishment.decimals import ceil_to_int
from replenishment.domain import CalendarLabel
from replenishment.forecast import (
    ForecastInputError,
    HISTORY_DAYS,
    aggregate_forecast,
    compute_base,
    daily_forecast,
    history_window,
    integer_demand,
    normalize,
)

ALPHA = Decimal("0.30")
MULTIPLIERS = {
    CalendarLabel.NORMAL: Decimal("1.00"),
    CalendarLabel.WEEKEND: Decimal("1.25"),
    CalendarLabel.PRE_HOLIDAY: Decimal("1.40"),
    CalendarLabel.HOLIDAY: Decimal("0.60"),
}
RUN_DATE = date(2026, 9, 3)


def _window() -> list[date]:
    return history_window(RUN_DATE)


def _labels(window, label=CalendarLabel.NORMAL):
    return {day: label for day in window}


def test_history_window_is_the_28_dates_before_the_run_date():
    window = _window()
    assert len(window) == HISTORY_DAYS == 28
    assert window[0] == date(2026, 8, 6)
    assert window[-1] == date(2026, 9, 2)
    assert window[-1] == RUN_DATE - timedelta(days=1)
    assert window == sorted(window)


def test_normalization_divides_by_the_configured_multiplier():
    # 10 units on a PRE_HOLIDAY with multiplier 1.40 is 10 / 1.4 units of
    # calendar-neutral demand, kept to 28 significant digits and not rounded
    # to a whole unit.
    value = normalize(10, Decimal("1.40"))
    assert isinstance(value, Decimal)
    assert value == Decimal("7.142857142857142857142857143")


def test_normalization_of_a_weekend_observation_is_exact():
    assert normalize(25, Decimal("1.25")) == Decimal("20")
    assert normalize(0, Decimal("1.25")) == Decimal("0")


def test_constant_normalized_series_smooths_to_that_constant():
    window = _window()
    forecast = compute_base(
        window,
        {day: 10 for day in window},
        _labels(window),
        MULTIPLIERS,
        ALPHA,
    )
    # Every normalized observation is 10, so every smoothed value is 10.
    assert forecast.base == Decimal("10")
    assert all(point.normalized == Decimal("10") for point in forecast.points)


def test_weekend_multipliers_are_removed_before_smoothing():
    window = _window()
    labels = {
        day: (CalendarLabel.WEEKEND if day.weekday() >= 5 else CalendarLabel.NORMAL)
        for day in window
    }
    # 25 units on a weekend and 20 on a weekday both normalize to exactly 20.
    sales = {day: (25 if day.weekday() >= 5 else 20) for day in window}
    forecast = compute_base(window, sales, labels, MULTIPLIERS, ALPHA)
    assert forecast.base == Decimal("20")


def test_zero_sale_days_are_observed_zeros_not_missing_data():
    window = _window()
    forecast = compute_base(
        window, {day: 0 for day in window}, _labels(window), MULTIPLIERS, ALPHA
    )
    assert forecast.base == Decimal("0")


def test_single_spike_on_the_newest_day():
    # smooth(d1..d27) = 0, so smooth(d28) = 0.30 * 10 + 0.70 * 0 = 3.00.
    window = _window()
    sales = {day: 0 for day in window}
    sales[window[-1]] = 10
    forecast = compute_base(window, sales, _labels(window), MULTIPLIERS, ALPHA)
    assert forecast.base == Decimal("3.00")


def test_single_spike_on_the_oldest_day_decays_by_seven_tenths_each_day():
    # smooth(d1) = 10 and smooth(dt) = 0.70 * smooth(d(t-1)) for the 27 later
    # days, so base = 10 * (7/10)**27 = 7**27 / 10**26 exactly.
    window = _window()
    sales = {day: 0 for day in window}
    sales[window[0]] = 10
    forecast = compute_base(window, sales, _labels(window), MULTIPLIERS, ALPHA)
    expected = Decimal(7**27).scaleb(-26)
    assert expected == Decimal("0.00065712362363534280139543")  # 7**27 = 65712362363534280139543
    assert forecast.base == expected


def test_alpha_of_one_makes_the_base_the_newest_normalized_observation():
    window = _window()
    sales = {day: 3 for day in window}
    sales[window[-1]] = 40
    labels = _labels(window)
    labels[window[-1]] = CalendarLabel.WEEKEND
    forecast = compute_base(window, sales, labels, MULTIPLIERS, Decimal("1"))
    assert forecast.base == Decimal("32")  # 40 / 1.25


def test_two_step_smoothing_matches_a_hand_computation():
    # Use a 28-day window that is zero except for the last two days so the
    # arithmetic can be written out: s27 = 0.3*10 = 3, s28 = 0.3*20 + 0.7*3 = 8.1
    window = _window()
    sales = {day: 0 for day in window}
    sales[window[-2]] = 10
    sales[window[-1]] = 20
    forecast = compute_base(window, sales, _labels(window), MULTIPLIERS, ALPHA)
    assert forecast.points[-2].smoothed == Decimal("3.000")
    assert forecast.base == Decimal("8.1000")


def test_missing_history_is_rejected_rather_than_imputed():
    window = _window()
    sales = {day: 5 for day in window}
    del sales[window[10]]
    with pytest.raises(ForecastInputError, match="missing sales observation"):
        compute_base(window, sales, _labels(window), MULTIPLIERS, ALPHA)


def test_missing_calendar_label_is_rejected():
    window = _window()
    labels = _labels(window)
    del labels[window[3]]
    with pytest.raises(ForecastInputError, match="missing calendar label"):
        compute_base(window, {day: 5 for day in window}, labels, MULTIPLIERS, ALPHA)


def test_a_short_window_is_rejected():
    window = _window()[:27]
    with pytest.raises(ForecastInputError, match="exactly 28"):
        compute_base(
            window, {day: 1 for day in window}, _labels(window), MULTIPLIERS, ALPHA
        )


@pytest.mark.parametrize("alpha", [Decimal("0"), Decimal("-0.1"), Decimal("1.01")])
def test_alpha_outside_its_range_is_rejected(alpha):
    window = _window()
    with pytest.raises(ForecastInputError, match="alpha"):
        compute_base(
            window, {day: 1 for day in window}, _labels(window), MULTIPLIERS, alpha
        )


def test_future_daily_forecast_applies_the_future_multiplier():
    assert daily_forecast(Decimal("8"), CalendarLabel.HOLIDAY, MULTIPLIERS) == Decimal(
        "4.80"
    )


def test_aggregate_is_summed_before_a_single_ceiling():
    base = Decimal("2.5")
    days = [RUN_DATE + timedelta(days=offset) for offset in range(3)]
    labels = {day: CalendarLabel.NORMAL for day in days}
    total = aggregate_forecast(base, days, labels, MULTIPLIERS)
    assert total == Decimal("7.500")
    assert integer_demand(total) == 8
    # Rounding each day first would have produced 3 + 3 + 3 = 9 units.
    assert sum(ceil_to_int(base) for _ in days) == 9


def test_aggregate_across_mixed_labels():
    base = Decimal("10")
    days = [RUN_DATE + timedelta(days=offset) for offset in range(4)]
    labels = {
        days[0]: CalendarLabel.NORMAL,
        days[1]: CalendarLabel.PRE_HOLIDAY,
        days[2]: CalendarLabel.WEEKEND,
        days[3]: CalendarLabel.HOLIDAY,
    }
    # 10 * (1.00 + 1.40 + 1.25 + 0.60) = 42.5
    total = aggregate_forecast(base, days, labels, MULTIPLIERS)
    assert total == Decimal("42.50")
    assert integer_demand(total) == 43


@pytest.mark.parametrize(
    "value,expected",
    [
        (Decimal("0"), 0),
        (Decimal("0.0001"), 1),
        (Decimal("7"), 7),
        (Decimal("7.000000000000000000000000001"), 8),
    ],
)
def test_integer_demand_is_a_mathematical_ceiling(value, expected):
    assert integer_demand(value) == expected
