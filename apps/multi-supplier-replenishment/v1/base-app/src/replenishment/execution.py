"""Purchase execution: the durable attempt, the single ``place_order`` call, and
strict validation of whatever came back."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from .domain import (
    AttemptState,
    OrderAccepted,
    OrderRejected,
    OrderStatus,
    PurchaseOrder,
)
from .errors import ExternalServiceError
from .interfaces import Clock, SupplierService
from .journal import AttemptRecord, Journal

IDEMPOTENCY_KEY_TEMPLATE = "replenishment/{run_id}/{store_sku}/{supplier_id}"


def idempotency_key(run_id: str, store_sku: str, supplier_id: str) -> str:
    """The stable key of Section 9; unique per run, store SKU, and supplier."""
    return IDEMPOTENCY_KEY_TEMPLATE.format(
        run_id=run_id, store_sku=store_sku, supplier_id=supplier_id
    )


def validate_order_against_attempt(
    order: PurchaseOrder, attempt: AttemptRecord
) -> list[str]:
    """Every field a supplier claims must agree with the attempted order."""
    problems: list[str] = []
    if not isinstance(order, PurchaseOrder):
        return [f"supplier returned {type(order).__name__}, not a purchase order"]
    if order.supplier_id != attempt.supplier_id:
        problems.append(
            f"supplier {order.supplier_id!r} does not match the attempted "
            f"{attempt.supplier_id!r}"
        )
    if order.supplier_sku != attempt.supplier_sku:
        problems.append(
            f"supplier SKU {order.supplier_sku!r} does not match the attempted "
            f"{attempt.supplier_sku!r}"
        )
    if order.destination_id != attempt.destination_id:
        problems.append(
            f"destination {order.destination_id!r} does not match the attempted "
            f"{attempt.destination_id!r}"
        )
    if order.idempotency_key != attempt.idempotency_key:
        problems.append(
            f"idempotency key {order.idempotency_key!r} does not match the attempted "
            f"{attempt.idempotency_key!r}"
        )
    if order.quantity != attempt.quantity:
        problems.append(
            f"quantity {order.quantity!r} does not match the attempted {attempt.quantity}"
        )
    if not isinstance(order.unit_price, Decimal) or order.unit_price != attempt.expected_unit_price:
        problems.append(
            f"unit price {order.unit_price!r} does not match the attempted "
            f"{attempt.expected_unit_price}"
        )
    if not isinstance(order.total_cost, Decimal) or order.total_cost != attempt.total_cost:
        problems.append(
            f"total {order.total_cost!r} does not match the attempted {attempt.total_cost}"
        )
    if order.status is not OrderStatus.ACCEPTED:
        problems.append(
            f"initial status {order.status.value if isinstance(order.status, OrderStatus) else order.status!r} "
            "is not ACCEPTED"
        )
    if not order.supplier_order_id:
        problems.append("the response carries no supplier order ID")
    if order.promised_delivery_date is None:
        problems.append("the response carries no promised delivery date")
    if order.currency != "USD":
        problems.append(f"currency {order.currency!r} is not USD")
    return problems


@dataclass(frozen=True)
class ExecutionResult:
    state: AttemptState
    reason: str
    order: PurchaseOrder | None = None
    rejection_code: str | None = None


def place_purchase_order(
    *,
    journal: Journal,
    clock: Clock,
    supplier: SupplierService,
    attempt: AttemptRecord,
) -> ExecutionResult:
    """Call the supplier exactly once and record the outcome we can prove.

    The attempt row is already durable before this function runs.  A lost,
    timed-out, undecodable, or self-contradictory response leaves the attempt
    ``OUTCOME_UNKNOWN``; it is never downgraded to a rejection.
    """
    try:
        result = supplier.place_order(
            attempt.supplier_sku,
            attempt.quantity,
            attempt.expected_unit_price,
            attempt.destination_id,
            attempt.idempotency_key,
        )
    except ExternalServiceError as exc:
        reason = (
            f"{type(exc).__name__} during placement: {exc}; the supplier may or may "
            "not have created the order"
        )
        journal.update_attempt(
            attempt.attempt_id,
            state=AttemptState.OUTCOME_UNKNOWN,
            updated_at=clock.now(),
            reason=reason,
        )
        return ExecutionResult(state=AttemptState.OUTCOME_UNKNOWN, reason=reason)

    if isinstance(result, OrderRejected):
        reason = f"supplier rejected the order ({result.code}): {result.message}".strip()
        journal.update_attempt(
            attempt.attempt_id,
            state=AttemptState.REJECTED,
            updated_at=clock.now(),
            reason=reason,
        )
        return ExecutionResult(
            state=AttemptState.REJECTED, reason=reason, rejection_code=result.code
        )

    if not isinstance(result, OrderAccepted):
        reason = (
            f"undecodable placement response of type {type(result).__name__}; the "
            "external outcome is unknown"
        )
        journal.update_attempt(
            attempt.attempt_id,
            state=AttemptState.OUTCOME_UNKNOWN,
            updated_at=clock.now(),
            reason=reason,
        )
        return ExecutionResult(state=AttemptState.OUTCOME_UNKNOWN, reason=reason)

    problems = validate_order_against_attempt(result.order, attempt)
    if problems:
        reason = (
            "accepted response contradicts the attempted order: "
            + "; ".join(problems)
        )
        journal.update_attempt(
            attempt.attempt_id,
            state=AttemptState.OUTCOME_UNKNOWN,
            updated_at=clock.now(),
            reason=reason,
        )
        return ExecutionResult(state=AttemptState.OUTCOME_UNKNOWN, reason=reason)

    order = result.order.with_store_sku(attempt.sku)
    now = clock.now()
    # The attempt state and the confirmed order describe one response, so they
    # are committed together.
    with journal.transaction():
        journal.update_attempt(
            attempt.attempt_id,
            state=AttemptState.ACCEPTED,
            updated_at=now,
            supplier_order_id=order.supplier_order_id,
            reason="supplier accepted the order",
        )
        journal.record_supplier_order(order, observed_at=now, source="PLACEMENT")
    return ExecutionResult(
        state=AttemptState.ACCEPTED,
        reason="supplier accepted the order",
        order=order,
    )
