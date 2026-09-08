"""Sections 9, 10, and 15: unknown outcomes, reconciliation, and recovery."""

from __future__ import annotations

from decimal import Decimal

from replenishment.domain import AttemptState, DecisionOutcome, RunStatus, TriggerKind

from . import support
from .conftest import Scenario


def build(
    scenario: Scenario,
    *,
    a_kwargs=None,
    b_offer=None,
    skus=None,
    on_hand: int = 0,
    sales=None,
) -> Scenario:
    scenario.world.write_calendar()
    scenario.world.write_sales(sales or {"SKU-1": support.flat_sales(10)})
    scenario.world.write_inventory(
        {sku["sku"]: on_hand for sku in (skus or [{"sku": "SKU-1"}])}
    )
    supplier_a = {
        "offers": {"A-1": support.offer(unit_price="1.00", pack_size=10, lead_time_days=1)}
    }
    supplier_a.update(a_kwargs or {})
    scenario.world.write_supplier("SUPPLIER_A", **supplier_a)
    scenario.world.write_supplier(
        "SUPPLIER_B",
        offers={"B-1": b_offer} if b_offer is not None else {},
    )
    scenario.configure(
        skus
        or [support.sku_config("SKU-1", mappings={"SUPPLIER_A": "A-1", "SUPPLIER_B": "B-1"})]
    )
    return scenario


def only(results, sku="SKU-1"):
    return next(item for item in results if item.sku == sku)


def place_calls(scenario: Scenario, supplier_id: str):
    return scenario.world.raw_calls(supplier_id, method="place_order")


# -- category 11: timeout and crash after dispatch ------------------------


def test_a_placement_timeout_is_unknown_and_creates_no_order(scenario):
    build(
        scenario,
        a_kwargs={"place_order_behaviors": {"A-1": ["timeout"]}},
        b_offer=support.offer(unit_price="1.50", pack_size=10, lead_time_days=1),
    )
    outcome = scenario.run()
    result = only(outcome.results)
    assert result.outcome is DecisionOutcome.ORDER_OUTCOME_UNKNOWN
    assert "SupplierTimeout" in result.reason
    assert outcome.run.status is RunStatus.COMPLETED_WITH_EXCEPTIONS

    # Exactly one call, and no fallback to the other supplier.
    assert len(place_calls(scenario, "SUPPLIER_A")) == 1
    assert place_calls(scenario, "SUPPLIER_B") == []
    assert scenario.world.supplier_orders("SUPPLIER_A") == []
    assert scenario.world.supplier_orders("SUPPLIER_B") == []
    assert scenario.world.inventory_document()["records"][0]["on_hand"] == 0

    with scenario.open(recover=False) as app:
        attempt = app.journal.attempt_for(outcome.run.run_id, "SKU-1")
        assert attempt.state is AttemptState.OUTCOME_UNKNOWN
        assert attempt.supplier_order_id is None
        assert app.journal.recorded_orders("SKU-1") == []


def test_a_lost_response_after_the_supplier_created_the_order_is_unknown(scenario):
    build(scenario, a_kwargs={"place_order_behaviors": {"A-1": ["lost_response"]}})
    outcome = scenario.run()
    result = only(outcome.results)
    assert result.outcome is DecisionOutcome.ORDER_OUTCOME_UNKNOWN
    assert len(place_calls(scenario, "SUPPLIER_A")) == 1
    # The supplier really did create the order.
    orders = scenario.world.supplier_orders("SUPPLIER_A")
    assert len(orders) == 1
    assert orders[0]["idempotency_key"] == "replenishment/RUN-000001/SKU-1/SUPPLIER_A"
    with scenario.open(recover=False) as app:
        attempt = app.journal.attempt_for(outcome.run.run_id, "SKU-1")
        assert attempt.state is AttemptState.OUTCOME_UNKNOWN
        # The application must not claim an order ID it cannot prove.
        assert attempt.supplier_order_id is None


def test_a_process_interruption_after_the_dispatching_commit_recovers_as_unknown(
    scenario,
):
    build(scenario)
    with scenario.open(recover=False) as app:
        run = app.journal.create_run(
            TriggerKind.MANUAL, support.RUN_DATE, app.services.clock.now()
        )
        app.journal.commit_attempt(
            run_id=run.run_id,
            sku="SKU-1",
            supplier_id="SUPPLIER_A",
            supplier_sku="A-1",
            destination_id=support.DESTINATION,
            quantity=50,
            expected_unit_price=Decimal("1.00"),
            total_cost=Decimal("50.00"),
            idempotency_key="replenishment/RUN-000001/SKU-1/SUPPLIER_A",
            created_at=app.services.clock.now(),
        )
        # The process dies here, before the supplier response was handled.

    with scenario.open() as app:
        assert app.recovered["runs"] == ["RUN-000001"]
        assert app.recovered["attempts"] == ["1"]
        attempt = app.journal.get_attempt(1)
        assert attempt.state is AttemptState.OUTCOME_UNKNOWN
        assert "process interrupted" in attempt.reason
        assert app.journal.get_run("RUN-000001").status is RunStatus.FAILED
        history = app.journal.reconciliation_events(1)
        assert history[0].lookup_outcome == "RECOVERED_FROM_DISPATCHING"


def test_an_unknown_attempt_blocks_only_its_own_sku(scenario):
    skus = [
        support.sku_config("SKU-1", mappings={"SUPPLIER_A": "A-1"}),
        support.sku_config("SKU-2", mappings={"SUPPLIER_A": "A-2"}),
    ]
    build(
        scenario,
        skus=skus,
        sales={
            "SKU-1": support.flat_sales(10),
            "SKU-2": support.flat_sales(10),
        },
        a_kwargs={
            "offers": {
                "A-1": support.offer(unit_price="1.00", pack_size=10, lead_time_days=1),
                "A-2": support.offer(unit_price="1.00", pack_size=10, lead_time_days=1),
            },
            "place_order_behaviors": {"A-1": ["timeout"]},
            "lookup_behaviors": {"*": ["unknown"]},
        },
    )
    first = scenario.run()
    assert only(first.results, "SKU-1").outcome is DecisionOutcome.ORDER_OUTCOME_UNKNOWN
    assert only(first.results, "SKU-2").outcome is DecisionOutcome.ORDER_ACCEPTED

    second = scenario.run()
    blocked = only(second.results, "SKU-1")
    assert blocked.outcome is DecisionOutcome.BLOCKED_UNKNOWN_ATTEMPT
    assert blocked.detail["blocking_attempts"][0]["idempotency_key"] == (
        "replenishment/RUN-000001/SKU-1/SUPPLIER_A"
    )
    assert only(second.results, "SKU-2").outcome is DecisionOutcome.NO_ORDER_NEEDED
    # No new placement was attempted for the blocked SKU.
    placed = [
        call["arguments"]["supplier_sku"] for call in place_calls(scenario, "SUPPLIER_A")
    ]
    assert placed == ["A-1", "A-2"]


def test_a_blocked_sku_is_never_ordered_from_the_other_supplier(scenario):
    build(
        scenario,
        a_kwargs={
            "place_order_behaviors": {"A-1": ["timeout"]},
            "lookup_behaviors": {"*": ["unknown"]},
        },
        b_offer=support.offer(unit_price="1.50", pack_size=10, lead_time_days=1),
    )
    scenario.run()
    second = scenario.run()
    assert only(second.results).outcome is DecisionOutcome.BLOCKED_UNKNOWN_ATTEMPT
    assert place_calls(scenario, "SUPPLIER_B") == []
    assert scenario.world.supplier_orders("SUPPLIER_B") == []


# -- category 12: reconciliation ------------------------------------------


def test_reconciliation_finds_the_order_and_records_it_as_accepted(scenario):
    build(scenario, a_kwargs={"place_order_behaviors": {"A-1": ["lost_response"]}})
    first = scenario.run()
    assert only(first.results).outcome is DecisionOutcome.ORDER_OUTCOME_UNKNOWN

    second = scenario.run()
    with scenario.open(recover=False) as app:
        attempt = app.journal.get_attempt(1)
        assert attempt.state is AttemptState.ACCEPTED
        assert attempt.supplier_order_id == "A-PO-0001"
        history = app.journal.reconciliation_events(1)
        assert [event.lookup_outcome for event in history] == ["FOUND"]
        assert history[0].resulting_state is AttemptState.ACCEPTED
        recorded = app.journal.recorded_orders("SKU-1")
        assert [item.supplier_order_id for item in recorded] == ["A-PO-0001"]

    # The recovered order participates in outstanding quantity in the same run,
    # so no replacement order is generated.
    result = only(second.results)
    assert result.outcome is DecisionOutcome.NO_ORDER_NEEDED
    assert result.detail["outstanding_quantity"] == 40
    assert len(place_calls(scenario, "SUPPLIER_A")) == 1
    assert len(scenario.world.supplier_orders("SUPPLIER_A")) == 1


def test_reconciliation_of_an_authoritative_absence_records_a_rejection(scenario):
    build(scenario, a_kwargs={"place_order_behaviors": {"A-1": ["timeout"]}})
    scenario.run()
    second = scenario.run()
    with scenario.open(recover=False) as app:
        attempt = app.journal.get_attempt(1)
        assert attempt.state is AttemptState.REJECTED
        assert "authoritative absence" in attempt.reason
        assert attempt.supplier_order_id is None
        events = app.journal.reconciliation_events(1)
        assert [event.lookup_outcome for event in events] == ["NOT_FOUND_FINAL"]
    # Once resolved, the SKU may be planned again in that same run.
    assert only(second.results).outcome is DecisionOutcome.ORDER_ACCEPTED
    assert len(place_calls(scenario, "SUPPLIER_A")) == 2
    assert len(scenario.world.supplier_orders("SUPPLIER_A")) == 1


def test_reconciliation_that_stays_unknown_keeps_the_sku_blocked(scenario):
    build(
        scenario,
        a_kwargs={
            "place_order_behaviors": {"A-1": ["timeout"]},
            "lookup_behaviors": {"*": ["unknown", "unknown"]},
        },
    )
    scenario.run()
    second = scenario.run()
    assert only(second.results).outcome is DecisionOutcome.BLOCKED_UNKNOWN_ATTEMPT
    with scenario.open(recover=False) as app:
        attempt = app.journal.get_attempt(1)
        assert attempt.state is AttemptState.OUTCOME_UNKNOWN
        assert [event.lookup_outcome for event in app.journal.reconciliation_events(1)] == [
            "UNKNOWN"
        ]
    assert len(place_calls(scenario, "SUPPLIER_A")) == 1


def test_a_lookup_service_failure_keeps_the_outcome_unknown(scenario):
    build(
        scenario,
        a_kwargs={
            "place_order_behaviors": {"A-1": ["timeout"]},
            "lookup_behaviors": {"*": ["unavailable"]},
        },
    )
    scenario.run()
    second = scenario.run()
    assert only(second.results).outcome is DecisionOutcome.BLOCKED_UNKNOWN_ATTEMPT
    with scenario.open(recover=False) as app:
        events = app.journal.reconciliation_events(1)
        assert events[0].lookup_outcome == "SERVICE_FAILURE"
        assert app.journal.get_attempt(1).state is AttemptState.OUTCOME_UNKNOWN


def test_reconciliation_runs_before_any_planning_input_is_read(scenario):
    build(scenario, a_kwargs={"place_order_behaviors": {"A-1": ["lost_response"]}})
    scenario.run()
    before = len(scenario.world.raw_calls("SUPPLIER_A"))
    scenario.run()
    calls = scenario.world.raw_calls("SUPPLIER_A")[before:]
    assert calls[0]["method"] == "lookup_by_idempotency_key"
    assert calls[0]["arguments"]["idempotency_key"] == (
        "replenishment/RUN-000001/SKU-1/SUPPLIER_A"
    )


def test_reconciliation_never_reuses_the_key_for_a_replacement_order(scenario):
    build(scenario, a_kwargs={"place_order_behaviors": {"A-1": ["timeout"]}})
    scenario.run()
    scenario.run()
    keys = [
        call["arguments"]["idempotency_key"]
        for call in place_calls(scenario, "SUPPLIER_A")
    ]
    assert keys == [
        "replenishment/RUN-000001/SKU-1/SUPPLIER_A",
        "replenishment/RUN-000002/SKU-1/SUPPLIER_A",
    ]
