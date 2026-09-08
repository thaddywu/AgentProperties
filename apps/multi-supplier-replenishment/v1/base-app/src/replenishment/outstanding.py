"""Authoritative outstanding-order quantity.

Outstanding quantity is derived from complete supplier order state and the
matching Inventory Ledger receipts.  Orders created manually or by another
system count.  Any inconsistency blocks the affected store SKU instead of being
guessed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Mapping, Sequence

from .config import SkuConfig
from .domain import OrderStatus, OrderSnapshot, PurchaseOrder, Receipt

OPEN_STATUSES: frozenset[OrderStatus] = frozenset(
    {OrderStatus.ACCEPTED, OrderStatus.SHIPPED, OrderStatus.DELIVERED}
)


@dataclass(frozen=True)
class SupplierOrderState:
    """One supplier's order snapshot plus the receipts posted against it."""

    supplier_id: str
    usable: bool
    error: str | None = None
    snapshot: OrderSnapshot | None = None
    receipts_by_order: Mapping[str, tuple[Receipt, ...]] = field(default_factory=dict)
    blocking_problems: tuple[str, ...] = ()

    @property
    def orders(self) -> tuple[PurchaseOrder, ...]:
        return self.snapshot.orders if self.snapshot else ()


@dataclass(frozen=True)
class Contribution:
    supplier_id: str
    supplier_order_id: str
    supplier_sku: str
    status: OrderStatus
    quantity: int
    contributes: int
    promised_delivery_date: date | None
    receipt_id: str | None
    note: str

    def as_dict(self) -> dict[str, object]:
        return {
            "supplier_id": self.supplier_id,
            "supplier_order_id": self.supplier_order_id,
            "supplier_sku": self.supplier_sku,
            "status": self.status.value,
            "order_quantity": self.quantity,
            "contributes": self.contributes,
            "promised_delivery_date": self.promised_delivery_date.isoformat()
            if self.promised_delivery_date
            else None,
            "receipt_id": self.receipt_id,
            "note": self.note,
        }


@dataclass(frozen=True)
class OutstandingResult:
    quantity: int
    contributions: tuple[Contribution, ...]
    problems: tuple[str, ...]

    @property
    def usable(self) -> bool:
        return not self.problems

    def arriving(self) -> tuple[tuple[date, int], ...]:
        """Promised delivery dates and quantities of still-expected orders."""
        return tuple(
            (item.promised_delivery_date, item.contributes)
            for item in self.contributions
            if item.contributes > 0 and item.promised_delivery_date is not None
        )


def validate_order(
    order: PurchaseOrder, *, supplier_id: str, destination_id: str
) -> list[str]:
    """Semantic checks on one authoritative supplier order."""
    problems: list[str] = []
    label = f"order {order.supplier_order_id or '<missing id>'} at {supplier_id}"
    if not order.supplier_order_id:
        problems.append(f"{supplier_id}: an order has no supplier order ID")
    if order.supplier_id != supplier_id:
        problems.append(
            f"{label}: reports supplier {order.supplier_id!r} in the "
            f"{supplier_id} snapshot"
        )
    if order.destination_id != destination_id:
        problems.append(
            f"{label}: destination {order.destination_id!r} is not the configured "
            f"destination {destination_id!r}"
        )
    if not isinstance(order.quantity, int) or order.quantity <= 0:
        problems.append(f"{label}: quantity {order.quantity!r} is not a positive integer")
    if not isinstance(order.unit_price, Decimal) or order.unit_price < 0:
        problems.append(f"{label}: unit price {order.unit_price!r} is not a USD amount")
    elif isinstance(order.quantity, int) and order.quantity > 0:
        expected_total = order.unit_price * order.quantity
        if order.total_cost != expected_total:
            problems.append(
                f"{label}: total {order.total_cost} does not equal quantity "
                f"{order.quantity} times unit price {order.unit_price}"
            )
    if order.currency != "USD":
        problems.append(f"{label}: currency {order.currency!r} is not USD")
    if order.status is not OrderStatus.CANCELLED and order.promised_delivery_date is None:
        problems.append(f"{label}: a non-cancelled order has no promised delivery date")
    return problems


def _receipt_problems(
    order: PurchaseOrder,
    receipts: Sequence[Receipt],
    *,
    store_id: str,
    supplier_id: str,
    store_sku: str | None,
) -> tuple[list[str], Receipt | None]:
    label = f"order {order.supplier_order_id} at {supplier_id}"
    problems: list[str] = []
    if not receipts:
        return problems, None
    if len(receipts) > 1:
        problems.append(
            f"{label}: {len(receipts)} receipts are posted; version 1 allows at most one"
        )
        return problems, None
    receipt = receipts[0]
    if receipt.store_id != store_id:
        problems.append(
            f"{label}: receipt {receipt.receipt_id} belongs to store "
            f"{receipt.store_id!r}"
        )
    if receipt.supplier_id != supplier_id:
        problems.append(
            f"{label}: receipt {receipt.receipt_id} belongs to supplier "
            f"{receipt.supplier_id!r}"
        )
    if store_sku is not None and receipt.sku != store_sku:
        problems.append(
            f"{label}: receipt {receipt.receipt_id} posts SKU {receipt.sku!r}, "
            f"expected {store_sku!r}"
        )
    if receipt.quantity != order.quantity:
        problems.append(
            f"{label}: receipt {receipt.receipt_id} posts {receipt.quantity} of "
            f"{order.quantity}; partial receipt is not supported"
        )
    if order.status is OrderStatus.CANCELLED:
        problems.append(
            f"{label}: receipt {receipt.receipt_id} is posted against a cancelled order"
        )
    if problems:
        return problems, None
    return problems, receipt


def unmapped_open_orders(
    state: SupplierOrderState,
    supplier_sku_index: Mapping[str, str],
    *,
    store_id: str,
) -> list[str]:
    """Open orders whose supplier SKU is not mapped by the current configuration.

    Such an order cannot be attributed to a configured store SKU, so it is
    reported and blocks the suppliers's mapped SKUs rather than being omitted.
    """
    problems: list[str] = []
    for order in state.orders:
        if order.status is OrderStatus.CANCELLED:
            continue
        if order.supplier_sku in supplier_sku_index:
            continue
        receipts = state.receipts_by_order.get(order.supplier_order_id, ())
        if (
            len(receipts) == 1
            and receipts[0].quantity == order.quantity
            and receipts[0].store_id == store_id
            and receipts[0].supplier_id == state.supplier_id
        ):
            continue  # already received; contributes nothing anywhere
        problems.append(
            f"{state.supplier_id}: open order {order.supplier_order_id} for supplier "
            f"SKU {order.supplier_sku!r} has no configured store-SKU mapping"
        )
    return problems


def compute_outstanding(
    *,
    store_id: str,
    destination_id: str,
    sku_config: SkuConfig,
    supplier_states: Mapping[str, SupplierOrderState],
) -> OutstandingResult:
    """Sum outstanding quantity for one store SKU across its approved suppliers."""
    problems: list[str] = []
    contributions: list[Contribution] = []
    total = 0

    for supplier_id in sku_config.approved_suppliers:
        state = supplier_states.get(supplier_id)
        if state is None or not state.usable:
            reason = (
                state.error
                if state is not None and state.error
                else "no order snapshot was obtained"
            )
            problems.append(
                f"{supplier_id}: order state is unusable ({reason}); outstanding "
                f"quantity for {sku_config.sku} cannot be established"
            )
            continue
        problems.extend(state.blocking_problems)
        supplier_sku = sku_config.supplier_sku(supplier_id)
        if supplier_sku is None:
            continue
        for order in state.orders:
            if order.supplier_sku != supplier_sku:
                continue
            order_problems = validate_order(
                order, supplier_id=supplier_id, destination_id=destination_id
            )
            receipts = state.receipts_by_order.get(order.supplier_order_id, ())
            receipt_issues, matching_receipt = _receipt_problems(
                order,
                receipts,
                store_id=store_id,
                supplier_id=supplier_id,
                store_sku=sku_config.sku,
            )
            order_problems.extend(receipt_issues)
            if order_problems:
                problems.extend(order_problems)
                continue
            if order.status is OrderStatus.CANCELLED:
                contributes, note = 0, "cancelled order contributes zero"
            elif matching_receipt is not None:
                contributes = 0
                note = (
                    f"fully received by receipt {matching_receipt.receipt_id}; the "
                    "quantity is already in authoritative on-hand inventory"
                )
            else:
                contributes = order.quantity
                note = (
                    f"{order.status.value} and not yet receipted in the Inventory Ledger"
                )
            total += contributes
            contributions.append(
                Contribution(
                    supplier_id=supplier_id,
                    supplier_order_id=order.supplier_order_id,
                    supplier_sku=order.supplier_sku,
                    status=order.status,
                    quantity=order.quantity,
                    contributes=contributes,
                    promised_delivery_date=order.promised_delivery_date,
                    receipt_id=matching_receipt.receipt_id if matching_receipt else None,
                    note=note,
                )
            )

    contributions.sort(key=lambda item: (item.supplier_id, item.supplier_order_id))
    # De-duplicate blocking problems while keeping a stable order.
    seen: set[str] = set()
    ordered_problems: list[str] = []
    for problem in problems:
        if problem not in seen:
            seen.add(problem)
            ordered_problems.append(problem)
    return OutstandingResult(
        quantity=total,
        contributions=tuple(contributions),
        problems=tuple(ordered_problems),
    )
