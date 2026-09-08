"""Section 12 and policy Section 5: missing, stale, malformed, duplicated, and
contradictory data blocks a SKU or a run instead of being guessed."""

from __future__ import annotations

from decimal import Decimal

from replenishment.domain import DecisionOutcome, RunStatus

from . import support
from .conftest import Scenario


def build(
    scenario: Scenario,
    *,
    inventory=None,
    sales=None,
    calendar=None,
    a_kwargs=None,
    skus=None,
) -> Scenario:
    scenario.world.write_calendar(**(calendar or {}))
    scenario.world.write_sales(sales or {"SKU-1": support.flat_sales(10)})
    if inventory is None:
        scenario.world.write_inventory({"SKU-1": 0})
    else:
        scenario.world.write_inventory(**inventory)
    supplier_a = {"offers": {"A-1": support.offer(unit_price="1.00", pack_size=10)}}
    supplier_a.update(a_kwargs or {})
    scenario.world.write_supplier("SUPPLIER_A", **supplier_a)
    scenario.world.write_supplier("SUPPLIER_B")
    scenario.configure(
        skus or [support.sku_config("SKU-1", mappings={"SUPPLIER_A": "A-1"})]
    )
    return scenario


def only(results, sku="SKU-1"):
    return next(item for item in results if item.sku == sku)


def no_calls(scenario: Scenario) -> None:
    assert scenario.world.raw_calls("SUPPLIER_A", method="place_order") == []
    assert scenario.world.raw_calls("SUPPLIER_B", method="place_order") == []


# -- inventory -------------------------------------------------------------


def test_an_unavailable_inventory_service_fails_the_whole_run(scenario):
    build(scenario, inventory={"on_hand": {"SKU-1": 0}, "failure": "unavailable"})
    outcome = scenario.run()
    assert outcome.run.status is RunStatus.FAILED
    assert outcome.results == ()
    assert "Inventory Ledger snapshot could not be obtained" in outcome.fatal_reason
    no_calls(scenario)


def test_a_stale_inventory_snapshot_fails_the_run(scenario):
    build(
        scenario,
        inventory={"on_hand": {"SKU-1": 0}, "as_of_offset_seconds": -16 * 60},
    )
    outcome = scenario.run()
    assert outcome.run.status is RunStatus.FAILED
    assert "older than the" in outcome.fatal_reason
    no_calls(scenario)


def test_an_inventory_snapshot_from_the_future_fails_the_run(scenario):
    build(scenario, inventory={"on_hand": {"SKU-1": 0}, "as_of_offset_seconds": 60})
    outcome = scenario.run()
    assert outcome.run.status is RunStatus.FAILED
    assert "after the run start" in outcome.fatal_reason
    no_calls(scenario)


def test_a_snapshot_for_the_wrong_store_fails_the_run(scenario):
    build(
        scenario,
        inventory={
            "records": [
                {
                    "store_id": "STORE-OTHER",
                    "sku": "SKU-1",
                    "base_unit": "EACH",
                    "active": True,
                    "on_hand": 5,
                }
            ]
        },
    )
    outcome = scenario.run()
    assert outcome.run.status is RunStatus.FAILED
    assert "STORE-OTHER" in outcome.fatal_reason
    no_calls(scenario)


def test_a_missing_inventory_record_is_not_a_zero(scenario):
    build(scenario, inventory={"records": []})
    outcome = scenario.run()
    result = only(outcome.results)
    assert result.outcome is DecisionOutcome.DATA_ERROR
    assert "missing record is not a zero quantity" in result.reason
    no_calls(scenario)


def test_duplicate_inventory_records_block_the_sku(scenario):
    record = {
        "store_id": support.STORE,
        "sku": "SKU-1",
        "base_unit": "EACH",
        "active": True,
        "on_hand": 5,
    }
    build(scenario, inventory={"records": [record, dict(record, on_hand=9)]})
    result = only(scenario.run().results)
    assert result.outcome is DecisionOutcome.DATA_ERROR
    assert "2 records" in result.reason
    no_calls(scenario)


def test_an_inactive_sku_is_not_ordered(scenario):
    build(
        scenario,
        inventory={
            "records": [
                {
                    "store_id": support.STORE,
                    "sku": "SKU-1",
                    "base_unit": "EACH",
                    "active": False,
                    "on_hand": 0,
                }
            ]
        },
    )
    result = only(scenario.run().results)
    assert result.outcome is DecisionOutcome.DATA_ERROR
    assert "not active" in result.reason
    no_calls(scenario)


def test_a_wrong_base_unit_blocks_the_sku(scenario):
    build(
        scenario,
        inventory={
            "records": [
                {
                    "store_id": support.STORE,
                    "sku": "SKU-1",
                    "base_unit": "CASE",
                    "active": True,
                    "on_hand": 0,
                }
            ]
        },
    )
    result = only(scenario.run().results)
    assert result.outcome is DecisionOutcome.DATA_ERROR
    assert "base unit" in result.reason
    no_calls(scenario)


def test_a_negative_on_hand_quantity_blocks_the_sku(scenario):
    build(
        scenario,
        inventory={
            "records": [
                {
                    "store_id": support.STORE,
                    "sku": "SKU-1",
                    "base_unit": "EACH",
                    "active": True,
                    "on_hand": -3,
                }
            ]
        },
    )
    result = only(scenario.run().results)
    assert result.outcome is DecisionOutcome.DATA_ERROR
    assert "negative" in result.reason
    no_calls(scenario)


def test_an_undecodable_inventory_record_blocks_only_that_sku(scenario):
    build(
        scenario,
        sales={
            "SKU-1": support.flat_sales(10),
            "SKU-2": support.flat_sales(10),
        },
        inventory={
            "records": [
                {
                    "store_id": support.STORE,
                    "sku": "SKU-1",
                    "base_unit": "EACH",
                    "active": True,
                    "on_hand": "many",
                },
                {
                    "store_id": support.STORE,
                    "sku": "SKU-2",
                    "base_unit": "EACH",
                    "active": True,
                    "on_hand": 0,
                },
            ]
        },
        a_kwargs={
            "offers": {
                "A-1": support.offer(unit_price="1.00", pack_size=10),
                "A-2": support.offer(unit_price="1.00", pack_size=10),
            }
        },
        skus=[
            support.sku_config("SKU-1", mappings={"SUPPLIER_A": "A-1"}),
            support.sku_config("SKU-2", mappings={"SUPPLIER_A": "A-2"}),
        ],
    )
    outcome = scenario.run()
    assert only(outcome.results, "SKU-1").outcome is DecisionOutcome.DATA_ERROR
    assert "malformed" in only(outcome.results, "SKU-1").reason
    assert only(outcome.results, "SKU-2").outcome is DecisionOutcome.ORDER_ACCEPTED
    assert outcome.run.status is RunStatus.COMPLETED_WITH_EXCEPTIONS
    placed = scenario.world.raw_calls("SUPPLIER_A", method="place_order")
    assert [call["arguments"]["supplier_sku"] for call in placed] == ["A-2"]


# -- sales -----------------------------------------------------------------


def test_an_incomplete_sales_window_blocks_the_sku(scenario):
    series = support.flat_sales(10)
    del series[sorted(series)[5]]
    build(scenario, sales={"SKU-1": series})
    result = only(scenario.run().results)
    assert result.outcome is DecisionOutcome.DATA_ERROR
    assert "missing date is unknown, not zero" in result.reason
    no_calls(scenario)


def test_duplicate_sales_records_block_the_sku(scenario):
    series = support.flat_sales(10)
    listed = [{"date": day, "units_sold": units} for day, units in series.items()]
    listed.append({"date": listed[0]["date"], "units_sold": 99})
    build(scenario, sales={"SKU-1": listed})
    result = only(scenario.run().results)
    assert result.outcome is DecisionOutcome.DATA_ERROR
    assert "duplicate sales records" in result.reason
    no_calls(scenario)


def test_negative_sales_block_the_sku(scenario):
    series = support.flat_sales(10)
    series[sorted(series)[0]] = -1
    build(scenario, sales={"SKU-1": series})
    result = only(scenario.run().results)
    assert result.outcome is DecisionOutcome.DATA_ERROR
    assert "negative" in result.reason
    no_calls(scenario)


def test_an_unavailable_sales_service_blocks_the_sku(scenario):
    scenario.world.write_calendar()
    scenario.world.write_sales(
        {"SKU-1": support.flat_sales(10)}, failures={"SKU-1": "unavailable"}
    )
    scenario.world.write_inventory({"SKU-1": 0})
    scenario.world.write_supplier("SUPPLIER_A", offers={"A-1": support.offer()})
    scenario.world.write_supplier("SUPPLIER_B")
    scenario.configure([support.sku_config("SKU-1", mappings={"SUPPLIER_A": "A-1"})])
    result = only(scenario.run().results)
    assert result.outcome is DecisionOutcome.DATA_ERROR
    assert "POS sales history is unusable" in result.reason
    no_calls(scenario)


def test_zero_sales_are_not_confused_with_missing_sales(scenario):
    build(scenario, sales={"SKU-1": support.flat_sales(0)})
    result = only(scenario.run().results)
    assert result.outcome is DecisionOutcome.NO_ORDER_NEEDED
    assert Decimal(result.detail["forecast"]["base_daily_demand"]) == Decimal(0)
    no_calls(scenario)


# -- calendar --------------------------------------------------------------


def test_a_missing_calendar_date_blocks_the_sku(scenario):
    labels = {
        day.isoformat(): "NORMAL"
        for day in support.date_span(support.CALENDAR_START, support.CALENDAR_END)
    }
    del labels["2026-08-20"]
    build(scenario, calendar={"labels": labels})
    result = only(scenario.run().results)
    assert result.outcome is DecisionOutcome.DATA_ERROR
    assert "2026-08-20" in result.reason
    no_calls(scenario)


def test_a_missing_future_calendar_date_blocks_the_sku(scenario):
    labels = {
        day.isoformat(): "NORMAL"
        for day in support.date_span(support.CALENDAR_START, support.CALENDAR_END)
    }
    del labels["2026-09-06"]  # inside the maximum coverage horizon
    build(scenario, calendar={"labels": labels})
    result = only(scenario.run().results)
    assert result.outcome is DecisionOutcome.DATA_ERROR
    assert "2026-09-06" in result.reason
    no_calls(scenario)


def test_an_unknown_calendar_label_blocks_the_sku(scenario):
    labels = {
        day.isoformat(): "NORMAL"
        for day in support.date_span(support.CALENDAR_START, support.CALENDAR_END)
    }
    labels["2026-08-25"] = "FESTIVAL"
    build(scenario, calendar={"labels": labels})
    result = only(scenario.run().results)
    assert result.outcome is DecisionOutcome.DATA_ERROR
    assert "recognized demand-day label" in result.reason
    no_calls(scenario)


def test_duplicate_calendar_records_block_the_sku(scenario):
    listed = [
        {"date": day.isoformat(), "label": "NORMAL"}
        for day in support.date_span(support.CALENDAR_START, support.CALENDAR_END)
    ]
    listed.append({"date": "2026-08-25", "label": "WEEKEND"})
    build(scenario, calendar={"days": listed})
    result = only(scenario.run().results)
    assert result.outcome is DecisionOutcome.DATA_ERROR
    assert "duplicate calendar records" in result.reason
    no_calls(scenario)


def test_an_unavailable_calendar_service_blocks_the_sku(scenario):
    build(scenario, calendar={"failure": "unavailable"})
    result = only(scenario.run().results)
    assert result.outcome is DecisionOutcome.DATA_ERROR
    assert "calendar data is unusable" in result.reason
    no_calls(scenario)


# -- supplier order state and receipts ------------------------------------


def test_an_unavailable_order_snapshot_blocks_the_dependent_sku(scenario):
    build(scenario, a_kwargs={"snapshot_failure": "unavailable"})
    outcome = scenario.run()
    result = only(outcome.results)
    assert result.outcome is DecisionOutcome.DATA_ERROR
    assert "order state is unusable" in result.reason
    no_calls(scenario)
    with scenario.open(recover=False) as app:
        events = app.journal.run_events(outcome.run.run_id)
        assert any(event["category"] == "SUPPLIER_ORDER_STATE" for event in events)


def test_an_incomplete_order_snapshot_blocks_the_dependent_sku(scenario):
    build(scenario, a_kwargs={"snapshot_complete": False})
    result = only(scenario.run().results)
    assert result.outcome is DecisionOutcome.DATA_ERROR
    assert "incomplete order snapshot" in result.reason
    no_calls(scenario)


def test_a_stale_order_snapshot_blocks_the_dependent_sku(scenario):
    build(scenario, a_kwargs={"as_of_offset_seconds": -20 * 60})
    result = only(scenario.run().results)
    assert result.outcome is DecisionOutcome.DATA_ERROR
    assert "older than the" in result.reason
    no_calls(scenario)


def test_an_unusable_supplier_does_not_block_a_sku_that_cannot_use_it(scenario):
    scenario.world.write_calendar()
    scenario.world.write_sales({"SKU-1": support.flat_sales(10)})
    scenario.world.write_inventory({"SKU-1": 0})
    scenario.world.write_supplier(
        "SUPPLIER_A", offers={"A-1": support.offer(unit_price="1.00", pack_size=10)}
    )
    scenario.world.write_supplier("SUPPLIER_B", snapshot_failure="unavailable")
    scenario.configure([support.sku_config("SKU-1", mappings={"SUPPLIER_A": "A-1"})])
    result = only(scenario.run().results)
    assert result.outcome is DecisionOutcome.ORDER_ACCEPTED


def test_a_malformed_authoritative_order_blocks_the_sku(scenario):
    bad = support.order(
        supplier_id="SUPPLIER_A",
        supplier_order_id="A-PO-0100",
        supplier_sku="A-1",
        quantity=10,
        unit_price="1.00",
        total_cost="999.00",
    )
    build(scenario, a_kwargs={"orders": [bad]})
    result = only(scenario.run().results)
    assert result.outcome is DecisionOutcome.DATA_ERROR
    assert "does not equal quantity" in result.reason
    no_calls(scenario)


def test_an_undecodable_order_makes_the_supplier_snapshot_unusable(scenario):
    build(scenario, a_kwargs={"orders": [{"supplier_order_id": "A-PO-0100"}]})
    result = only(scenario.run().results)
    assert result.outcome is DecisionOutcome.DATA_ERROR
    assert "MalformedResponse" in result.reason
    no_calls(scenario)


def test_a_mismatched_receipt_blocks_the_sku(scenario):
    outstanding = support.order(
        supplier_id="SUPPLIER_A",
        supplier_order_id="A-PO-0100",
        supplier_sku="A-1",
        quantity=50,
        status="DELIVERED",
    )
    scenario.world.write_calendar()
    scenario.world.write_sales({"SKU-1": support.flat_sales(10)})
    scenario.world.write_inventory(
        {"SKU-1": 0},
        receipts=[
            support.receipt(
                receipt_id="RCPT-1",
                supplier_id="SUPPLIER_A",
                supplier_order_id="A-PO-0100",
                sku="SKU-1",
                quantity=20,
            )
        ],
    )
    scenario.world.write_supplier(
        "SUPPLIER_A",
        offers={"A-1": support.offer(unit_price="1.00", pack_size=10)},
        orders=[outstanding],
    )
    scenario.world.write_supplier("SUPPLIER_B")
    scenario.configure([support.sku_config("SKU-1", mappings={"SUPPLIER_A": "A-1"})])
    result = only(scenario.run().results)
    assert result.outcome is DecisionOutcome.DATA_ERROR
    assert "partial receipt is not supported" in result.reason
    no_calls(scenario)


def test_an_open_order_with_no_mapping_blocks_the_supplier_s_skus(scenario):
    stray = support.order(
        supplier_id="SUPPLIER_A",
        supplier_order_id="A-PO-0900",
        supplier_sku="A-RETIRED",
        quantity=12,
        status="SHIPPED",
    )
    build(scenario, a_kwargs={"orders": [stray]})
    outcome = scenario.run()
    result = only(outcome.results)
    assert result.outcome is DecisionOutcome.DATA_ERROR
    assert "no configured store-SKU mapping" in result.reason
    no_calls(scenario)
    with scenario.open(recover=False) as app:
        events = app.journal.run_events(outcome.run.run_id)
        assert any(event["category"] == "UNMAPPED_ORDER" for event in events)
