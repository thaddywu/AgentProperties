"""Sections 8, 9, and 12 end to end: normal ordering, escalation, rejection,
and infeasibility.

Every test that could result in a purchase asserts the application decision,
the exact raw supplier call count and arguments, the authoritative supplier
world state, the Inventory Ledger world state, and the durable journal.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from replenishment.domain import (
    AttemptState,
    DecisionOutcome,
    OrderAccepted,
    OrderRejected,
    RunStatus,
    TriggerKind,
)

from . import support
from .conftest import Scenario


def build(
    scenario: Scenario,
    *,
    on_hand: int = 0,
    units: int = 10,
    a_offer=None,
    b_offer=None,
    a_kwargs=None,
    b_kwargs=None,
    sku_overrides=None,
    receipts=(),
    a_orders=(),
    b_orders=(),
) -> Scenario:
    """One SKU with a flat all-NORMAL history: base demand is exactly ``units``."""
    scenario.world.write_calendar()
    scenario.world.write_sales({"SKU-1": support.flat_sales(units)})
    scenario.world.write_inventory({"SKU-1": on_hand}, receipts=receipts)
    scenario.world.write_supplier(
        "SUPPLIER_A",
        offers={"A-1": a_offer} if a_offer is not None else {"A-1": support.offer()},
        orders=a_orders,
        **(a_kwargs or {}),
    )
    scenario.world.write_supplier(
        "SUPPLIER_B",
        offers={"B-1": b_offer} if b_offer is not None else {},
        orders=b_orders,
        **(b_kwargs or {}),
    )
    scenario.configure(
        [
            support.sku_config(
                "SKU-1",
                mappings={"SUPPLIER_A": "A-1", "SUPPLIER_B": "B-1"},
                **(sku_overrides or {}),
            )
        ]
    )
    return scenario


def only(results, sku="SKU-1"):
    return next(item for item in results if item.sku == sku)


def place_calls(world: support.World, supplier_id: str):
    return world.raw_calls(supplier_id, method="place_order")


# -- category 7: a normal accepted order -----------------------------------


def test_normal_accepted_order_makes_exactly_one_place_order_call(scenario):
    build(scenario, on_hand=0, units=10, a_offer=support.offer(unit_price="1.00", pack_size=10))
    outcome = scenario.run()

    result = only(outcome.results)
    assert result.outcome is DecisionOutcome.ORDER_ACCEPTED
    assert outcome.run.status is RunStatus.COMPLETED

    # base 10 over 5 covered days is a target of 50; on hand and outstanding are 0.
    candidate = result.detail["candidates"][0]
    assert candidate["target_inventory"] == 50
    assert candidate["raw_requirement"] == 50
    assert candidate["order_quantity"] == 50
    assert candidate["total_cost_usd"] == "50.00"

    calls = place_calls(scenario.world, "SUPPLIER_A")
    assert len(calls) == 1
    assert calls[0]["arguments"] == {
        "supplier_sku": "A-1",
        "quantity": 50,
        "expected_unit_price": "1.00",
        "destination_id": support.DESTINATION,
        "idempotency_key": "replenishment/RUN-000001/SKU-1/SUPPLIER_A",
    }
    assert calls[0]["outcome"] == "ACCEPTED"
    assert place_calls(scenario.world, "SUPPLIER_B") == []

    # Authoritative supplier world state.
    orders = scenario.world.supplier_orders("SUPPLIER_A")
    assert len(orders) == 1
    assert orders[0]["supplier_order_id"] == "A-PO-0001"
    assert orders[0]["quantity"] == 50
    assert orders[0]["status"] == "ACCEPTED"
    assert orders[0]["idempotency_key"] == "replenishment/RUN-000001/SKU-1/SUPPLIER_A"
    assert scenario.world.supplier_orders("SUPPLIER_B") == []
    # Availability at the supplier fell by the ordered quantity.
    assert (
        scenario.world.supplier_document("SUPPLIER_A")["offers"]["A-1"][
            "available_quantity"
        ]
        == 10_000 - 50
    )

    # The Inventory Ledger was not touched by the purchase.
    inventory = scenario.world.inventory_document()
    assert inventory["records"][0]["on_hand"] == 0
    assert inventory["receipts"] == []

    # Durable journal state.
    with scenario.open(recover=False) as app:
        attempt = app.journal.attempt_for(outcome.run.run_id, "SKU-1")
        assert attempt is not None
        assert attempt.state is AttemptState.ACCEPTED
        assert attempt.quantity == 50
        assert attempt.expected_unit_price == Decimal("1.00")
        assert attempt.total_cost == Decimal("50.00")
        assert attempt.supplier_order_id == "A-PO-0001"
        assert attempt.idempotency_key == "replenishment/RUN-000001/SKU-1/SUPPLIER_A"
        recorded = app.journal.recorded_orders("SKU-1")
        assert [item.supplier_order_id for item in recorded] == ["A-PO-0001"]
        assert recorded[0].observed_status.value == "ACCEPTED"


def test_no_order_needed_makes_no_place_order_call(scenario):
    build(scenario, on_hand=500, units=10)
    outcome = scenario.run()
    result = only(outcome.results)
    assert result.outcome is DecisionOutcome.NO_ORDER_NEEDED
    assert outcome.run.status is RunStatus.COMPLETED
    assert place_calls(scenario.world, "SUPPLIER_A") == []
    assert scenario.world.supplier_orders("SUPPLIER_A") == []
    with scenario.open(recover=False) as app:
        assert app.journal.list_attempts() == []


def test_pack_rounding_is_reflected_in_the_actual_call(scenario):
    build(
        scenario,
        on_hand=0,
        units=10,
        a_offer=support.offer(unit_price="0.25", pack_size=24),
    )
    outcome = scenario.run()
    assert only(outcome.results).outcome is DecisionOutcome.ORDER_ACCEPTED
    calls = place_calls(scenario.world, "SUPPLIER_A")
    assert len(calls) == 1
    # ceil(50 / 24) * 24 = 72 units at 0.25 = 18.00
    assert calls[0]["arguments"]["quantity"] == 72
    assert scenario.world.supplier_orders("SUPPLIER_A")[0]["total_cost"] == "18.00"


# -- category 6 at run level ----------------------------------------------


def test_the_cheaper_stockout_avoiding_supplier_wins(scenario):
    build(
        scenario,
        on_hand=40,
        units=10,
        a_offer=support.offer(unit_price="1.00", pack_size=10, lead_time_days=2),
        b_offer=support.offer(unit_price="0.40", pack_size=10, lead_time_days=3),
    )
    outcome = scenario.run()
    result = only(outcome.results)
    assert result.outcome is DecisionOutcome.ORDER_ACCEPTED
    assert result.detail["selected"]["supplier_id"] == "SUPPLIER_B"
    assert place_calls(scenario.world, "SUPPLIER_A") == []
    assert len(place_calls(scenario.world, "SUPPLIER_B")) == 1
    assert scenario.world.supplier_orders("SUPPLIER_A") == []
    assert len(scenario.world.supplier_orders("SUPPLIER_B")) == 1


def test_only_one_supplier_has_enough_availability(scenario):
    build(
        scenario,
        on_hand=0,
        units=10,
        a_offer=support.offer(unit_price="0.10", pack_size=10, available_quantity=20),
        b_offer=support.offer(unit_price="5.00", pack_size=10, available_quantity=500),
    )
    outcome = scenario.run()
    result = only(outcome.results)
    assert result.outcome is DecisionOutcome.ORDER_ACCEPTED
    assert result.detail["selected"]["supplier_id"] == "SUPPLIER_B"
    exclusions = {item["supplier_id"]: item for item in result.detail["offer_exclusions"]}
    assert exclusions["SUPPLIER_A"]["kind"] == "INSUFFICIENT_AVAILABILITY"
    assert place_calls(scenario.world, "SUPPLIER_A") == []


def test_the_stockout_avoiding_candidate_beats_a_cheaper_at_risk_one(scenario):
    # On hand covers three days of demand, so only the one-day lead time avoids
    # a projected stockout even though it costs more.
    build(
        scenario,
        on_hand=25,
        units=10,
        a_offer=support.offer(unit_price="0.10", pack_size=10, lead_time_days=5),
        b_offer=support.offer(unit_price="4.00", pack_size=10, lead_time_days=1),
    )
    outcome = scenario.run()
    result = only(outcome.results)
    candidates = {item["supplier_id"]: item for item in result.detail["candidates"]}
    assert candidates["SUPPLIER_A"]["avoids_projected_stockout"] is False
    assert candidates["SUPPLIER_B"]["avoids_projected_stockout"] is True
    assert result.detail["selected"]["supplier_id"] == "SUPPLIER_B"
    assert len(place_calls(scenario.world, "SUPPLIER_B")) == 1


def test_when_no_candidate_avoids_stockout_the_shortest_lead_time_wins(scenario):
    build(
        scenario,
        on_hand=0,
        units=10,
        a_offer=support.offer(unit_price="0.10", pack_size=10, lead_time_days=5),
        b_offer=support.offer(unit_price="4.00", pack_size=10, lead_time_days=3),
    )
    outcome = scenario.run()
    result = only(outcome.results)
    assert all(
        item["avoids_projected_stockout"] is False for item in result.detail["candidates"]
    )
    assert result.detail["selected"]["supplier_id"] == "SUPPLIER_B"
    assert len(place_calls(scenario.world, "SUPPLIER_B")) == 1
    assert place_calls(scenario.world, "SUPPLIER_A") == []


def test_a_complete_tie_selects_supplier_a(scenario):
    build(
        scenario,
        on_hand=0,
        units=10,
        a_offer=support.offer(unit_price="1.00", pack_size=10, lead_time_days=2),
        b_offer=support.offer(unit_price="1.00", pack_size=10, lead_time_days=2),
    )
    outcome = scenario.run()
    result = only(outcome.results)
    assert [item["supplier_id"] for item in result.detail["ranking"]] == [
        "SUPPLIER_A",
        "SUPPLIER_B",
    ]
    assert result.detail["selected"]["supplier_id"] == "SUPPLIER_A"
    assert len(place_calls(scenario.world, "SUPPLIER_A")) == 1
    assert place_calls(scenario.world, "SUPPLIER_B") == []


# -- category 8: escalation with zero raw calls ---------------------------


@pytest.mark.parametrize(
    "sku_overrides,offer_overrides,fragment",
    [
        ({"max_unit_price_usd": "0.50"}, {"unit_price": "1.00"}, "unit price"),
        ({"autonomous_order_limit_usd": "10.00"}, {}, "spend limit"),
        ({"max_lead_time_days": 1}, {"lead_time_days": 4}, "maximum lead time"),
        ({"hard_max": 20}, {}, "hard_max"),
    ],
)
def test_owner_limits_escalate_without_calling_any_supplier(
    scenario, sku_overrides, offer_overrides, fragment
):
    build(
        scenario,
        on_hand=0,
        units=10,
        a_offer=support.offer(**{"unit_price": "1.00", "pack_size": 10, **offer_overrides}),
        sku_overrides=sku_overrides,
    )
    outcome = scenario.run()
    result = only(outcome.results)
    assert result.outcome is DecisionOutcome.ESCALATION_REQUIRED
    assert fragment in result.reason
    assert outcome.run.status is RunStatus.COMPLETED_WITH_EXCEPTIONS
    assert place_calls(scenario.world, "SUPPLIER_A") == []
    assert place_calls(scenario.world, "SUPPLIER_B") == []
    assert scenario.world.supplier_orders("SUPPLIER_A") == []
    with scenario.open(recover=False) as app:
        assert app.journal.list_attempts() == []
        assert app.journal.recorded_orders("SKU-1") == []


def test_an_exposure_already_over_the_hard_max_skips_the_offer_call(scenario):
    build(scenario, on_hand=500, units=10, sku_overrides={"hard_max": 100})
    outcome = scenario.run()
    result = only(outcome.results)
    assert result.outcome is DecisionOutcome.ESCALATION_REQUIRED
    assert "already exceeds hard_max" in result.reason
    # No offer was even requested for this SKU.
    assert scenario.world.raw_calls("SUPPLIER_A", method="get_offer") == []
    assert place_calls(scenario.world, "SUPPLIER_A") == []


def test_the_quantity_is_never_reduced_to_fit_a_limit(scenario):
    build(
        scenario,
        on_hand=0,
        units=10,
        a_offer=support.offer(unit_price="1.00", pack_size=10),
        sku_overrides={"hard_max": 45},
    )
    outcome = scenario.run()
    result = only(outcome.results)
    assert result.outcome is DecisionOutcome.ESCALATION_REQUIRED
    assert result.detail["candidates"][0]["order_quantity"] == 50
    assert place_calls(scenario.world, "SUPPLIER_A") == []


# -- category 9: rejection and infeasibility -------------------------------


def test_a_definitive_rejection_does_not_fall_back_to_the_other_supplier(scenario):
    build(
        scenario,
        on_hand=0,
        units=10,
        a_offer=support.offer(unit_price="1.00", pack_size=10, lead_time_days=1),
        b_offer=support.offer(unit_price="1.00", pack_size=10, lead_time_days=2),
        a_kwargs={"place_order_behaviors": {"A-1": ["reject:PRICE_CHANGED"]}},
    )
    outcome = scenario.run()
    result = only(outcome.results)
    assert result.outcome is DecisionOutcome.SUPPLIER_REJECTED
    assert result.detail["rejection_code"] == "PRICE_CHANGED"
    assert len(place_calls(scenario.world, "SUPPLIER_A")) == 1
    assert place_calls(scenario.world, "SUPPLIER_B") == []
    assert scenario.world.supplier_orders("SUPPLIER_A") == []
    assert scenario.world.supplier_orders("SUPPLIER_B") == []
    with scenario.open(recover=False) as app:
        attempt = app.journal.attempt_for(outcome.run.run_id, "SKU-1")
        assert attempt.state is AttemptState.REJECTED
        assert attempt.supplier_order_id is None
        assert app.journal.recorded_orders("SKU-1") == []


def test_the_supplier_accepts_only_at_the_expected_price(scenario):
    """The compare-and-place condition of Section 4.5, at the supplier itself."""
    build(scenario, on_hand=0, units=10, a_offer=support.offer(unit_price="1.00"))
    with scenario.open(recover=False) as app:
        supplier = app.services.suppliers["SUPPLIER_A"]
        rejected = supplier.place_order(
            "A-1", 50, Decimal("0.90"), support.DESTINATION, "probe-price"
        )
        assert isinstance(rejected, OrderRejected)
        assert rejected.code == "PRICE_CHANGED"
        assert scenario.world.supplier_orders("SUPPLIER_A") == []

        accepted = supplier.place_order(
            "A-1", 50, Decimal("1.00"), support.DESTINATION, "probe-ok"
        )
        assert isinstance(accepted, OrderAccepted)
        assert accepted.order.unit_price == Decimal("1.00")
        assert len(scenario.world.supplier_orders("SUPPLIER_A")) == 1

    calls = place_calls(scenario.world, "SUPPLIER_A")
    assert [call["outcome"] for call in calls] == ["REJECTED", "ACCEPTED"]


def test_the_supplier_rejects_a_quantity_it_cannot_supply(scenario):
    build(
        scenario,
        on_hand=0,
        units=10,
        a_offer=support.offer(unit_price="1.00", pack_size=10, available_quantity=30),
    )
    with scenario.open(recover=False) as app:
        supplier = app.services.suppliers["SUPPLIER_A"]
        too_many = supplier.place_order(
            "A-1", 40, Decimal("1.00"), support.DESTINATION, "probe-availability"
        )
        assert isinstance(too_many, OrderRejected)
        assert too_many.code == "INSUFFICIENT_AVAILABILITY"
        off_pack = supplier.place_order(
            "A-1", 15, Decimal("1.00"), support.DESTINATION, "probe-pack"
        )
        assert isinstance(off_pack, OrderRejected)
        assert off_pack.code == "INVALID_QUANTITY"
    assert scenario.world.supplier_orders("SUPPLIER_A") == []


def test_replaying_an_idempotency_key_returns_the_same_order(scenario):
    build(scenario, on_hand=0, units=10, a_offer=support.offer(unit_price="1.00"))
    with scenario.open(recover=False) as app:
        supplier = app.services.suppliers["SUPPLIER_A"]
        first = supplier.place_order(
            "A-1", 50, Decimal("1.00"), support.DESTINATION, "probe-key"
        )
        second = supplier.place_order(
            "A-1", 50, Decimal("1.00"), support.DESTINATION, "probe-key"
        )
    assert isinstance(first, OrderAccepted) and isinstance(second, OrderAccepted)
    assert first.order.supplier_order_id == second.order.supplier_order_id
    assert len(scenario.world.supplier_orders("SUPPLIER_A")) == 1
    assert [call["outcome"] for call in place_calls(scenario.world, "SUPPLIER_A")] == [
        "ACCEPTED",
        "ACCEPTED_IDEMPOTENT_REPLAY",
    ]


def test_both_offers_unusable_is_no_feasible_supplier(scenario):
    build(
        scenario,
        on_hand=0,
        units=10,
        a_kwargs={"offer_failures": {"A-1": "unavailable"}},
    )
    outcome = scenario.run()
    result = only(outcome.results)
    assert result.outcome is DecisionOutcome.NO_FEASIBLE_SUPPLIER
    kinds = {item["supplier_id"]: item["kind"] for item in result.detail["offer_exclusions"]}
    assert kinds == {"SUPPLIER_A": "OFFER_UNAVAILABLE", "SUPPLIER_B": "NOT_OFFERED"}
    assert place_calls(scenario.world, "SUPPLIER_A") == []
    assert place_calls(scenario.world, "SUPPLIER_B") == []


def test_one_failed_offer_still_lets_the_other_supplier_be_used(scenario):
    build(
        scenario,
        on_hand=0,
        units=10,
        b_offer=support.offer(unit_price="2.00", pack_size=10),
        a_kwargs={"offer_failures": {"A-1": "malformed"}},
    )
    outcome = scenario.run()
    result = only(outcome.results)
    assert result.outcome is DecisionOutcome.ORDER_ACCEPTED
    assert result.detail["selected"]["supplier_id"] == "SUPPLIER_B"
    exclusion = result.detail["offer_exclusions"][0]
    assert exclusion["supplier_id"] == "SUPPLIER_A"
    assert exclusion["kind"] == "OFFER_UNAVAILABLE"
    assert "MalformedResponse" in exclusion["reason"]
    assert len(place_calls(scenario.world, "SUPPLIER_B")) == 1


def test_an_expired_offer_is_excluded(scenario):
    build(
        scenario,
        on_hand=0,
        units=10,
        a_offer=support.offer(valid_until="2026-09-03T09:00:00Z"),
    )
    outcome = scenario.run()
    result = only(outcome.results)
    assert result.outcome is DecisionOutcome.NO_FEASIBLE_SUPPLIER
    assert "expired" in result.detail["offer_exclusions"][0]["reason"]
    assert place_calls(scenario.world, "SUPPLIER_A") == []


def test_an_offer_for_the_wrong_destination_is_excluded(scenario):
    build(
        scenario,
        on_hand=0,
        units=10,
        a_offer=support.offer(destination_id="DEST-OTHER"),
    )
    outcome = scenario.run()
    result = only(outcome.results)
    assert result.outcome is DecisionOutcome.NO_FEASIBLE_SUPPLIER
    assert "destination" in result.detail["offer_exclusions"][0]["reason"]
    assert place_calls(scenario.world, "SUPPLIER_A") == []


def test_a_contradictory_accepted_response_is_not_treated_as_accepted(scenario):
    build(
        scenario,
        on_hand=0,
        units=10,
        a_kwargs={"place_order_behaviors": {"A-1": ["contradictory"]}},
    )
    outcome = scenario.run()
    result = only(outcome.results)
    assert result.outcome is DecisionOutcome.ORDER_OUTCOME_UNKNOWN
    assert "contradicts the attempted order" in result.reason
    assert len(place_calls(scenario.world, "SUPPLIER_A")) == 1
    with scenario.open(recover=False) as app:
        attempt = app.journal.attempt_for(outcome.run.run_id, "SKU-1")
        assert attempt.state is AttemptState.OUTCOME_UNKNOWN
        assert attempt.supplier_order_id is None
        assert app.journal.recorded_orders("SKU-1") == []


def test_at_most_one_order_is_placed_for_one_sku_in_one_run(scenario):
    build(
        scenario,
        on_hand=0,
        units=10,
        b_offer=support.offer(unit_price="0.90", pack_size=10),
    )
    outcome = scenario.run()
    assert only(outcome.results).outcome is DecisionOutcome.ORDER_ACCEPTED
    total_calls = len(place_calls(scenario.world, "SUPPLIER_A")) + len(
        place_calls(scenario.world, "SUPPLIER_B")
    )
    assert total_calls == 1
    with scenario.open(recover=False) as app:
        assert len(app.journal.list_attempts(run_id=outcome.run.run_id)) == 1


def test_a_journal_commit_failure_before_placement_calls_no_supplier(scenario, monkeypatch):
    from replenishment.journal import Journal

    build(scenario, on_hand=0, units=10, a_offer=support.offer(unit_price="1.00", pack_size=10))

    def refuse(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(Journal, "commit_attempt", refuse)
    outcome = scenario.run()
    result = only(outcome.results)
    assert result.outcome is DecisionOutcome.DATA_ERROR
    assert "could not be committed durably" in result.reason
    assert place_calls(scenario.world, "SUPPLIER_A") == []
    assert scenario.world.supplier_orders("SUPPLIER_A") == []
