"""Section 5.4 and policy Section 6: authoritative outstanding quantity."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from replenishment.config import SkuConfig
from replenishment.domain import OrderSnapshot, OrderStatus, PurchaseOrder, Receipt
from replenishment.outstanding import (
    SupplierOrderState,
    compute_outstanding,
    unmapped_open_orders,
    validate_order,
)

STORE = "STORE-T"
DESTINATION = "DEST-T"
CREATED = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


def sku_config(**overrides) -> SkuConfig:
    values = dict(
        sku="SKU-1",
        display_name="SKU 1",
        hard_max=1000,
        safety_days=2,
        max_lead_time_days=5,
        max_unit_price_usd=Decimal("9.00"),
        autonomous_order_limit_usd=Decimal("900.00"),
        supplier_mappings={"SUPPLIER_A": "A-1", "SUPPLIER_B": "B-1"},
    )
    values.update(overrides)
    return SkuConfig(**values)


def make_order(**overrides) -> PurchaseOrder:
    values = dict(
        supplier_id="SUPPLIER_A",
        supplier_order_id="A-PO-0001",
        idempotency_key="key-1",
        destination_id=DESTINATION,
        supplier_sku="A-1",
        quantity=10,
        unit_price=Decimal("1.00"),
        total_cost=Decimal("10.00"),
        status=OrderStatus.ACCEPTED,
        created_at=CREATED,
        promised_delivery_date=date(2026, 9, 5),
    )
    values.update(overrides)
    return PurchaseOrder(**values)


def make_receipt(**overrides) -> Receipt:
    values = dict(
        receipt_id="RCPT-1",
        store_id=STORE,
        supplier_id="SUPPLIER_A",
        supplier_order_id="A-PO-0001",
        sku="SKU-1",
        quantity=10,
        posted_at=CREATED,
    )
    values.update(overrides)
    return Receipt(**values)


def state(
    supplier_id: str = "SUPPLIER_A",
    orders=(),
    receipts=(),
    *,
    usable: bool = True,
    error: str | None = None,
) -> SupplierOrderState:
    grouped: dict[str, tuple[Receipt, ...]] = {}
    for item in receipts:
        grouped.setdefault(item.supplier_order_id, ())
        grouped[item.supplier_order_id] = grouped[item.supplier_order_id] + (item,)
    return SupplierOrderState(
        supplier_id=supplier_id,
        usable=usable,
        error=error,
        snapshot=OrderSnapshot(
            supplier_id=supplier_id,
            destination_id=DESTINATION,
            as_of=CREATED,
            complete=True,
            orders=tuple(orders),
        )
        if usable
        else None,
        receipts_by_order=grouped,
    )


def outstanding(states, config=None):
    return compute_outstanding(
        store_id=STORE,
        destination_id=DESTINATION,
        sku_config=config or sku_config(),
        supplier_states=states,
    )


def both(a_state, b_state=None):
    return {"SUPPLIER_A": a_state, "SUPPLIER_B": b_state or state("SUPPLIER_B")}


# -- lifecycle -------------------------------------------------------------


@pytest.mark.parametrize(
    "status,expected",
    [
        (OrderStatus.ACCEPTED, 10),
        (OrderStatus.SHIPPED, 10),
        (OrderStatus.DELIVERED, 10),
        (OrderStatus.CANCELLED, 0),
    ],
)
def test_each_lifecycle_state_contributes_correctly(status, expected):
    result = outstanding(both(state(orders=[make_order(status=status)])))
    assert result.usable
    assert result.quantity == expected


def test_a_delivered_order_still_counts_until_the_receipt_is_posted():
    result = outstanding(both(state(orders=[make_order(status=OrderStatus.DELIVERED)])))
    assert result.quantity == 10
    assert result.contributions[0].note.startswith("DELIVERED")


def test_a_fully_received_order_contributes_zero():
    result = outstanding(
        both(
            state(
                orders=[make_order(status=OrderStatus.DELIVERED)],
                receipts=[make_receipt()],
            )
        )
    )
    assert result.quantity == 0
    assert result.contributions[0].receipt_id == "RCPT-1"


def test_orders_from_both_suppliers_are_summed():
    result = outstanding(
        both(
            state(orders=[make_order(quantity=10, unit_price=Decimal("1.00"),
                                     total_cost=Decimal("10.00"))]),
            state(
                "SUPPLIER_B",
                orders=[
                    make_order(
                        supplier_id="SUPPLIER_B",
                        supplier_order_id="B-PO-0001",
                        supplier_sku="B-1",
                        quantity=25,
                        unit_price=Decimal("2.00"),
                        total_cost=Decimal("50.00"),
                    )
                ],
            ),
        )
    )
    assert result.quantity == 35


def test_an_externally_created_order_is_included():
    external = make_order(
        supplier_order_id="A-PO-9000",
        idempotency_key="manual/clerk/2026-09-01",
        quantity=48,
        unit_price=Decimal("0.50"),
        total_cost=Decimal("24.00"),
        status=OrderStatus.SHIPPED,
    )
    result = outstanding(both(state(orders=[external])))
    assert result.quantity == 48
    assert result.contributions[0].supplier_order_id == "A-PO-9000"


def test_an_order_for_another_store_sku_is_ignored():
    other = make_order(supplier_sku="A-OTHER", supplier_order_id="A-PO-0002")
    result = outstanding(
        both(state(orders=[other])),
        config=sku_config(supplier_mappings={"SUPPLIER_A": "A-1"}),
    )
    assert result.quantity == 0
    assert result.contributions == ()


# -- inconsistencies -------------------------------------------------------


def test_a_partial_receipt_blocks_the_sku():
    result = outstanding(
        both(state(orders=[make_order()], receipts=[make_receipt(quantity=4)]))
    )
    assert not result.usable
    assert any("partial receipt" in problem for problem in result.problems)


def test_duplicate_receipts_block_the_sku():
    result = outstanding(
        both(
            state(
                orders=[make_order()],
                receipts=[make_receipt(), make_receipt(receipt_id="RCPT-2")],
            )
        )
    )
    assert not result.usable
    assert any("receipts are posted" in problem for problem in result.problems)


def test_a_receipt_for_a_cancelled_order_blocks_the_sku():
    result = outstanding(
        both(
            state(
                orders=[make_order(status=OrderStatus.CANCELLED)],
                receipts=[make_receipt()],
            )
        )
    )
    assert not result.usable
    assert any("cancelled order" in problem for problem in result.problems)


def test_a_receipt_for_a_different_sku_blocks_the_sku():
    result = outstanding(
        both(state(orders=[make_order()], receipts=[make_receipt(sku="SKU-OTHER")]))
    )
    assert not result.usable
    assert any("posts SKU" in problem for problem in result.problems)


def test_an_unusable_supplier_snapshot_blocks_every_sku_it_could_supply():
    result = outstanding(
        both(state(usable=False, error="the snapshot service is unavailable"))
    )
    assert not result.usable
    assert any("unusable" in problem for problem in result.problems)


def test_an_unusable_snapshot_for_an_unmapped_supplier_does_not_block():
    result = outstanding(
        {
            "SUPPLIER_A": state(orders=[make_order()]),
            "SUPPLIER_B": state("SUPPLIER_B", usable=False, error="down"),
        },
        config=sku_config(supplier_mappings={"SUPPLIER_A": "A-1"}),
    )
    assert result.usable
    assert result.quantity == 10


# -- order-level validation ------------------------------------------------


@pytest.mark.parametrize(
    "overrides,fragment",
    [
        ({"destination_id": "DEST-OTHER"}, "not the configured destination"),
        ({"quantity": 0}, "positive integer"),
        ({"total_cost": Decimal("99.00")}, "does not equal quantity"),
        ({"supplier_id": "SUPPLIER_B"}, "reports supplier"),
        ({"promised_delivery_date": None}, "no promised delivery date"),
        ({"currency": "EUR"}, "not USD"),
    ],
)
def test_a_malformed_authoritative_order_blocks_the_sku(overrides, fragment):
    problems = validate_order(
        make_order(**overrides), supplier_id="SUPPLIER_A", destination_id=DESTINATION
    )
    assert any(fragment in problem for problem in problems), problems
    result = outstanding(both(state(orders=[make_order(**overrides)])))
    assert not result.usable


def test_a_cancelled_order_needs_no_promised_date():
    problems = validate_order(
        make_order(status=OrderStatus.CANCELLED, promised_delivery_date=None),
        supplier_id="SUPPLIER_A",
        destination_id=DESTINATION,
    )
    assert problems == []


# -- unmapped supplier SKUs ------------------------------------------------


def test_an_open_order_with_no_configured_mapping_is_reported():
    unmapped = make_order(supplier_order_id="A-PO-7777", supplier_sku="A-UNKNOWN")
    problems = unmapped_open_orders(
        state(orders=[unmapped]), {"A-1": "SKU-1"}, store_id=STORE
    )
    assert len(problems) == 1
    assert "no configured store-SKU mapping" in problems[0]


def test_a_cancelled_unmapped_order_is_not_reported():
    unmapped = make_order(
        supplier_order_id="A-PO-7777",
        supplier_sku="A-UNKNOWN",
        status=OrderStatus.CANCELLED,
    )
    assert unmapped_open_orders(
        state(orders=[unmapped]), {"A-1": "SKU-1"}, store_id=STORE
    ) == []


def test_a_received_unmapped_order_is_not_reported():
    unmapped = make_order(supplier_order_id="A-PO-7777", supplier_sku="A-UNKNOWN")
    supplier_state = state(
        orders=[unmapped],
        receipts=[make_receipt(supplier_order_id="A-PO-7777", sku="SKU-WHATEVER")],
    )
    assert unmapped_open_orders(
        supplier_state, {"A-1": "SKU-1"}, store_id=STORE
    ) == []


def test_blocking_problems_propagate_into_the_outstanding_result():
    supplier_state = SupplierOrderState(
        supplier_id="SUPPLIER_A",
        usable=True,
        snapshot=OrderSnapshot("SUPPLIER_A", DESTINATION, CREATED, True, ()),
        blocking_problems=("SUPPLIER_A: open order A-PO-7777 has no mapping",),
    )
    result = outstanding(both(supplier_state))
    assert not result.usable
    assert "A-PO-7777" in result.problems[0]


def test_arriving_pairs_only_include_contributing_orders():
    orders = [
        make_order(supplier_order_id="A-PO-1", promised_delivery_date=date(2026, 9, 4)),
        make_order(
            supplier_order_id="A-PO-2",
            status=OrderStatus.CANCELLED,
            promised_delivery_date=date(2026, 9, 4),
        ),
    ]
    result = outstanding(both(state(orders=orders)))
    assert result.arriving() == ((date(2026, 9, 4), 10),)
