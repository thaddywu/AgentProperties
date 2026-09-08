"""Section 8: offer usability, owner limits, and the deterministic ranking."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from replenishment.config import SkuConfig
from replenishment.domain import CalendarLabel, Offer
from replenishment.planning import StockoutProjection, build_plan
from replenishment.selection import (
    Candidate,
    check_offer_usable,
    owner_limit_failures,
    rank_candidates,
)

RUN_STARTED_AT = datetime(2026, 9, 3, 9, 5, tzinfo=timezone.utc)
RUN_DATE = date(2026, 9, 3)
DESTINATION = "DEST-T"
MULTIPLIERS = {
    CalendarLabel.NORMAL: Decimal("1.00"),
    CalendarLabel.WEEKEND: Decimal("1.25"),
    CalendarLabel.PRE_HOLIDAY: Decimal("1.40"),
    CalendarLabel.HOLIDAY: Decimal("0.60"),
}
LABELS = {
    RUN_DATE + timedelta(days=offset): CalendarLabel.NORMAL for offset in range(30)
}


def make_offer(**overrides) -> Offer:
    values = dict(
        supplier_id="SUPPLIER_A",
        supplier_sku="A-1",
        destination_id=DESTINATION,
        unit_price=Decimal("1.00"),
        pack_size=10,
        available_quantity=1000,
        lead_time_days=2,
        valid_until=datetime(2026, 12, 31, tzinfo=timezone.utc),
    )
    values.update(overrides)
    return Offer(**values)


def make_sku(**overrides) -> SkuConfig:
    values = dict(
        sku="SKU-1",
        display_name="SKU 1",
        hard_max=10_000,
        safety_days=2,
        max_lead_time_days=5,
        max_unit_price_usd=Decimal("9.00"),
        autonomous_order_limit_usd=Decimal("9000.00"),
        supplier_mappings={"SUPPLIER_A": "A-1", "SUPPLIER_B": "B-1"},
    )
    values.update(overrides)
    return SkuConfig(**values)


def make_candidate(
    supplier_id: str,
    *,
    unit_price: str,
    quantity: int,
    lead_time_days: int,
    avoids_stockout: bool = True,
    limit_failures: tuple[str, ...] = (),
) -> Candidate:
    offer = make_offer(
        supplier_id=supplier_id,
        supplier_sku=f"{supplier_id[-1]}-1",
        unit_price=Decimal(unit_price),
        pack_size=quantity,
        lead_time_days=lead_time_days,
    )
    plan = build_plan(
        run_date=RUN_DATE,
        base=Decimal("10"),
        labels_by_date=LABELS,
        multipliers=MULTIPLIERS,
        lead_time_days=lead_time_days,
        safety_days=0,
        on_hand=0,
        outstanding_quantity=0,
        pack_size=quantity,
    )
    return Candidate(
        supplier_id=supplier_id,
        supplier_sku=offer.supplier_sku,
        offer=offer,
        plan=plan,
        total_cost=Decimal(unit_price) * quantity,
        limit_failures=limit_failures,
        projection=StockoutProjection(
            arrival_date=RUN_DATE + timedelta(days=lead_time_days),
            demand_dates=(),
            demand_forecast=Decimal("0"),
            expected_demand_before_arrival=0,
            expected_supply_before_arrival=0 if not avoids_stockout else 1,
            avoids_stockout=avoids_stockout,
        ),
    )


# -- offer usability -------------------------------------------------------


def test_a_well_formed_offer_is_usable():
    assert (
        check_offer_usable(
            make_offer(),
            supplier_id="SUPPLIER_A",
            supplier_sku="A-1",
            destination_id=DESTINATION,
            run_started_at=RUN_STARTED_AT,
        )
        == []
    )


@pytest.mark.parametrize(
    "overrides,fragment",
    [
        ({"supplier_id": "SUPPLIER_B"}, "reports supplier"),
        ({"supplier_sku": "A-OTHER"}, "supplier SKU"),
        ({"destination_id": "DEST-OTHER"}, "destination"),
        ({"currency": "EUR"}, "currency"),
        ({"unit_price": Decimal("0.00")}, "positive USD amount"),
        ({"unit_price": Decimal("1.001")}, "two decimals"),
        ({"pack_size": 0}, "pack size"),
        ({"available_quantity": -1}, "available quantity"),
        ({"lead_time_days": 0}, "lead time"),
        (
            {"valid_until": datetime(2026, 9, 3, 9, 0, tzinfo=timezone.utc)},
            "expired",
        ),
    ],
)
def test_unusable_offers_are_rejected_with_a_reason(overrides, fragment):
    problems = check_offer_usable(
        make_offer(**overrides),
        supplier_id="SUPPLIER_A",
        supplier_sku="A-1",
        destination_id=DESTINATION,
        run_started_at=RUN_STARTED_AT,
    )
    assert any(fragment in problem for problem in problems), problems


def test_an_offer_expiring_exactly_at_the_run_start_is_expired():
    problems = check_offer_usable(
        make_offer(valid_until=RUN_STARTED_AT),
        supplier_id="SUPPLIER_A",
        supplier_sku="A-1",
        destination_id=DESTINATION,
        run_started_at=RUN_STARTED_AT,
    )
    assert any("expired" in problem for problem in problems)


# -- owner limits ----------------------------------------------------------


def test_owner_limits_pass_for_a_candidate_inside_every_limit():
    offer = make_offer(unit_price=Decimal("1.00"))
    plan = build_plan(
        run_date=RUN_DATE,
        base=Decimal("10"),
        labels_by_date=LABELS,
        multipliers=MULTIPLIERS,
        lead_time_days=2,
        safety_days=0,
        on_hand=0,
        outstanding_quantity=0,
        pack_size=10,
    )
    assert (
        owner_limit_failures(
            sku_config=make_sku(),
            offer=offer,
            plan=plan,
            total_cost=Decimal("30.00"),
        )
        == []
    )


@pytest.mark.parametrize(
    "sku_overrides,total,fragment",
    [
        ({"max_unit_price_usd": Decimal("0.50")}, Decimal("30.00"), "unit price"),
        ({"autonomous_order_limit_usd": Decimal("10.00")}, Decimal("30.00"), "spend limit"),
        ({"hard_max": 5}, Decimal("30.00"), "hard_max"),
    ],
)
def test_each_owner_limit_is_reported_separately(sku_overrides, total, fragment):
    plan = build_plan(
        run_date=RUN_DATE,
        base=Decimal("10"),
        labels_by_date=LABELS,
        multipliers=MULTIPLIERS,
        lead_time_days=2,
        safety_days=0,
        on_hand=0,
        outstanding_quantity=0,
        pack_size=10,
    )
    failures = owner_limit_failures(
        sku_config=make_sku(**sku_overrides),
        offer=make_offer(),
        plan=plan,
        total_cost=total,
    )
    assert any(fragment in failure for failure in failures), failures


def test_a_limit_boundary_value_is_permitted():
    plan = build_plan(
        run_date=RUN_DATE,
        base=Decimal("10"),
        labels_by_date=LABELS,
        multipliers=MULTIPLIERS,
        lead_time_days=2,
        safety_days=0,
        on_hand=0,
        outstanding_quantity=0,
        pack_size=10,
    )
    assert plan.order_quantity == 30 and plan.exposure_after_order == 30
    assert (
        owner_limit_failures(
            sku_config=make_sku(
                hard_max=30,
                max_unit_price_usd=Decimal("1.00"),
                autonomous_order_limit_usd=Decimal("30.00"),
            ),
            offer=make_offer(unit_price=Decimal("1.00")),
            plan=plan,
            total_cost=Decimal("30.00"),
        )
        == []
    )


# -- ranking ---------------------------------------------------------------


def test_no_executable_candidate_ranks_to_nothing():
    blocked = make_candidate(
        "SUPPLIER_A", unit_price="1.00", quantity=10, lead_time_days=2,
        limit_failures=("over the spend limit",),
    )
    assert rank_candidates([blocked]) == []


def test_stockout_avoiding_candidates_displace_the_others():
    at_risk = make_candidate(
        "SUPPLIER_A", unit_price="0.10", quantity=10, lead_time_days=1,
        avoids_stockout=False,
    )
    safe = make_candidate(
        "SUPPLIER_B", unit_price="5.00", quantity=10, lead_time_days=4,
        avoids_stockout=True,
    )
    ranked = rank_candidates([at_risk, safe])
    assert [item.supplier_id for item in ranked] == ["SUPPLIER_B"]


def test_stockout_avoiding_set_ranks_by_lowest_total_cost_first():
    cheap = make_candidate(
        "SUPPLIER_B", unit_price="0.50", quantity=10, lead_time_days=4
    )
    dear = make_candidate("SUPPLIER_A", unit_price="2.00", quantity=10, lead_time_days=1)
    ranked = rank_candidates([dear, cheap])
    assert [item.supplier_id for item in ranked] == ["SUPPLIER_B", "SUPPLIER_A"]


def test_all_at_risk_set_ranks_by_shortest_lead_time_first():
    slow_cheap = make_candidate(
        "SUPPLIER_B", unit_price="0.50", quantity=10, lead_time_days=4,
        avoids_stockout=False,
    )
    fast_dear = make_candidate(
        "SUPPLIER_A", unit_price="2.00", quantity=10, lead_time_days=1,
        avoids_stockout=False,
    )
    ranked = rank_candidates([slow_cheap, fast_dear])
    assert [item.supplier_id for item in ranked] == ["SUPPLIER_A", "SUPPLIER_B"]


def test_equal_cost_breaks_to_the_shorter_lead_time():
    slow = make_candidate("SUPPLIER_A", unit_price="1.00", quantity=10, lead_time_days=4)
    fast = make_candidate("SUPPLIER_B", unit_price="1.00", quantity=10, lead_time_days=1)
    ranked = rank_candidates([slow, fast])
    assert [item.supplier_id for item in ranked] == ["SUPPLIER_B", "SUPPLIER_A"]


def test_equal_cost_and_lead_time_break_to_the_lower_unit_price():
    # 20 units at 0.50 and 10 units at 1.00 both total 10.00.
    coarse = make_candidate(
        "SUPPLIER_A", unit_price="1.00", quantity=10, lead_time_days=2
    )
    fine = make_candidate("SUPPLIER_B", unit_price="0.50", quantity=20, lead_time_days=2)
    assert coarse.total_cost == fine.total_cost == Decimal("10.00")
    ranked = rank_candidates([coarse, fine])
    assert [item.supplier_id for item in ranked] == ["SUPPLIER_B", "SUPPLIER_A"]


def test_a_complete_tie_breaks_to_supplier_a():
    first = make_candidate("SUPPLIER_B", unit_price="1.00", quantity=10, lead_time_days=2)
    second = make_candidate("SUPPLIER_A", unit_price="1.00", quantity=10, lead_time_days=2)
    ranked = rank_candidates([first, second])
    assert [item.supplier_id for item in ranked] == ["SUPPLIER_A", "SUPPLIER_B"]
    # The input order must not matter.
    assert [item.supplier_id for item in rank_candidates([second, first])] == [
        "SUPPLIER_A",
        "SUPPLIER_B",
    ]


def test_a_complete_tie_in_the_at_risk_path_also_breaks_to_supplier_a():
    first = make_candidate(
        "SUPPLIER_B", unit_price="1.00", quantity=10, lead_time_days=2,
        avoids_stockout=False,
    )
    second = make_candidate(
        "SUPPLIER_A", unit_price="1.00", quantity=10, lead_time_days=2,
        avoids_stockout=False,
    )
    assert [item.supplier_id for item in rank_candidates([first, second])] == [
        "SUPPLIER_A",
        "SUPPLIER_B",
    ]
