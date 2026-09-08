"""Section 4.2 and policy Section 3: the ledger is authoritative and the
application never mutates it."""

from __future__ import annotations

import hashlib
from datetime import timedelta

from replenishment.domain import DecisionOutcome

from . import support
from .conftest import Scenario


def build(scenario: Scenario, on_hand: int, *, receipts=(), orders=()) -> Scenario:
    scenario.world.write_calendar()
    scenario.world.write_sales({"SKU-1": support.flat_sales(10)})
    scenario.world.write_inventory({"SKU-1": on_hand}, receipts=receipts)
    scenario.world.write_supplier(
        "SUPPLIER_A",
        offers={"A-1": support.offer(unit_price="1.00", pack_size=10)},
        orders=orders,
    )
    scenario.world.write_supplier("SUPPLIER_B")
    scenario.configure(
        [support.sku_config("SKU-1", mappings={"SUPPLIER_A": "A-1"})]
    )
    return scenario


def digest(scenario: Scenario) -> str:
    return hashlib.sha256(
        (scenario.world.root / "inventory.json").read_bytes()
    ).hexdigest()


def only(results):
    return results[0]


def test_the_application_never_writes_to_the_inventory_ledger(scenario):
    build(scenario, on_hand=0)
    before = digest(scenario)
    outcome = scenario.run()
    assert only(outcome.results).outcome is DecisionOutcome.ORDER_ACCEPTED
    assert digest(scenario) == before


def test_placing_an_order_does_not_raise_on_hand(scenario):
    build(scenario, on_hand=5)
    scenario.run()
    document = scenario.world.inventory_document()
    assert document["records"][0]["on_hand"] == 5


def test_external_pos_sales_lower_the_next_run_s_position(scenario):
    build(scenario, on_hand=50)
    first = scenario.run()
    assert only(first.results).outcome is DecisionOutcome.NO_ORDER_NEEDED
    assert scenario.world.supplier_orders("SUPPLIER_A") == []

    # The POS sells nine units outside this application; the next day's run
    # sees the lower authoritative on-hand quantity and orders one pack.
    scenario.world.write_inventory({"SKU-1": 41})
    scenario.set_instant("2026-09-04T09:05:00Z")
    scenario.world.write_sales(
        {"SKU-1": support.flat_sales(10, run_date=support.RUN_DATE + timedelta(days=1))}
    )
    second = scenario.run()
    result = only(second.results)
    assert result.detail["on_hand"] == 41
    assert result.detail["candidates"][0]["raw_requirement"] == 9
    assert result.detail["candidates"][0]["order_quantity"] == 10
    assert result.outcome is DecisionOutcome.ORDER_ACCEPTED


def test_a_posted_receipt_moves_an_order_into_on_hand(scenario):
    outstanding_order = support.order(
        supplier_id="SUPPLIER_A",
        supplier_order_id="A-PO-0100",
        supplier_sku="A-1",
        quantity=50,
        status="DELIVERED",
    )
    build(scenario, on_hand=0, orders=[outstanding_order])
    first = scenario.run()
    assert only(first.results).outcome is DecisionOutcome.NO_ORDER_NEEDED
    assert only(first.results).detail["outstanding_quantity"] == 50

    # The receiving clerk posts the receipt in the ledger and stock arrives.
    scenario.world.write_inventory(
        {"SKU-1": 50},
        receipts=[
            support.receipt(
                receipt_id="RCPT-9",
                supplier_id="SUPPLIER_A",
                supplier_order_id="A-PO-0100",
                sku="SKU-1",
                quantity=50,
            )
        ],
    )
    second = scenario.run()
    result = only(second.results)
    assert result.detail["on_hand"] == 50
    assert result.detail["outstanding_quantity"] == 0
    assert result.outcome is DecisionOutcome.NO_ORDER_NEEDED


def test_an_authorized_manual_stock_adjustment_is_respected(scenario):
    build(scenario, on_hand=0)
    scenario.world.write_inventory({"SKU-1": 500})
    outcome = scenario.run()
    result = only(outcome.results)
    assert result.detail["on_hand"] == 500
    assert result.outcome is DecisionOutcome.NO_ORDER_NEEDED
    assert scenario.world.raw_calls("SUPPLIER_A", method="place_order") == []
