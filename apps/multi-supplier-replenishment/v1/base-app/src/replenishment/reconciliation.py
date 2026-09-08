"""Resolution of unknown supplier outcomes by idempotency key.

This runs at the start of every run, before any planning input is read and
before any order is placed.  It never generates a replacement order.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .domain import (
    AttemptState,
    LookupFound,
    LookupNotFoundFinal,
    LookupUnknown,
    PurchaseOrder,
)
from .errors import ExternalServiceError
from .execution import validate_order_against_attempt
from .interfaces import Clock, SupplierService
from .journal import AttemptRecord, Journal


@dataclass(frozen=True)
class ReconciliationOutcome:
    attempt_id: int
    sku: str
    supplier_id: str
    idempotency_key: str
    lookup_outcome: str
    resulting_state: AttemptState
    detail: str

    def as_dict(self) -> dict[str, object]:
        return {
            "attempt_id": self.attempt_id,
            "sku": self.sku,
            "supplier_id": self.supplier_id,
            "idempotency_key": self.idempotency_key,
            "lookup_outcome": self.lookup_outcome,
            "resulting_state": self.resulting_state.value,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class ReconciliationReport:
    outcomes: tuple[ReconciliationOutcome, ...]
    blocked_skus: frozenset[str]

    def as_dict(self) -> dict[str, object]:
        return {
            "outcomes": [outcome.as_dict() for outcome in self.outcomes],
            "blocked_skus": sorted(self.blocked_skus),
        }


def _resolve_one(
    *,
    journal: Journal,
    clock: Clock,
    supplier: SupplierService | None,
    attempt: AttemptRecord,
    run_id: str | None,
) -> ReconciliationOutcome:
    if supplier is None:
        detail = (
            f"supplier {attempt.supplier_id!r} is not configured in this process; "
            "the outcome cannot be established"
        )
        return _record(
            journal, clock, attempt, run_id, "SUPPLIER_UNAVAILABLE",
            AttemptState.OUTCOME_UNKNOWN, detail,
        )

    try:
        result = supplier.lookup_by_idempotency_key(
            attempt.destination_id, attempt.idempotency_key
        )
    except ExternalServiceError as exc:
        detail = f"{type(exc).__name__} during lookup: {exc}"
        return _record(
            journal, clock, attempt, run_id, "SERVICE_FAILURE",
            AttemptState.OUTCOME_UNKNOWN, detail,
        )

    if isinstance(result, LookupFound):
        problems = validate_order_against_attempt(result.order, attempt)
        if problems:
            detail = (
                "supplier returned an order that contradicts the attempt: "
                + "; ".join(problems)
            )
            return _record(
                journal, clock, attempt, run_id, "FOUND",
                AttemptState.OUTCOME_UNKNOWN, detail,
            )
        order = result.order.with_store_sku(attempt.sku)
        detail = f"supplier order {order.supplier_order_id} was created by this key"
        return _record(
            journal, clock, attempt, run_id, "FOUND", AttemptState.ACCEPTED, detail,
            supplier_order_id=order.supplier_order_id,
            order=order,
        )

    if isinstance(result, LookupNotFoundFinal):
        detail = (
            "supplier guarantees the idempotency key created no order and can no "
            "longer do so (authoritative absence)"
        )
        if result.message:
            detail = f"{detail}: {result.message}"
        return _record(
            journal, clock, attempt, run_id, "NOT_FOUND_FINAL",
            AttemptState.REJECTED, detail,
        )

    if isinstance(result, LookupUnknown):
        detail = "supplier cannot establish whether the key created an order"
        if result.message:
            detail = f"{detail}: {result.message}"
        return _record(
            journal, clock, attempt, run_id, "UNKNOWN",
            AttemptState.OUTCOME_UNKNOWN, detail,
        )

    detail = f"malformed lookup response of type {type(result).__name__}"
    return _record(
        journal, clock, attempt, run_id, "MALFORMED",
        AttemptState.OUTCOME_UNKNOWN, detail,
    )


def _record(
    journal: Journal,
    clock: Clock,
    attempt: AttemptRecord,
    run_id: str | None,
    lookup_outcome: str,
    state: AttemptState,
    detail: str,
    supplier_order_id: str | None = None,
    order: PurchaseOrder | None = None,
) -> ReconciliationOutcome:
    now = clock.now()
    with journal.transaction():
        if order is not None:
            journal.record_supplier_order(
                order, observed_at=now, source="RECONCILIATION"
            )
        journal.update_attempt(
            attempt.attempt_id,
            state=state,
            updated_at=now,
            supplier_order_id=supplier_order_id or attempt.supplier_order_id,
            reason=detail,
        )
        journal.add_reconciliation_event(
            attempt_id=attempt.attempt_id,
            run_id=run_id,
            occurred_at=now,
            lookup_outcome=lookup_outcome,
            resulting_state=state,
            detail=detail,
        )
    return ReconciliationOutcome(
        attempt_id=attempt.attempt_id,
        sku=attempt.sku,
        supplier_id=attempt.supplier_id,
        idempotency_key=attempt.idempotency_key,
        lookup_outcome=lookup_outcome,
        resulting_state=state,
        detail=detail,
    )


def reconcile_unknown_attempts(
    *,
    journal: Journal,
    clock: Clock,
    suppliers: Mapping[str, SupplierService],
    run_id: str | None = None,
) -> ReconciliationReport:
    """Process every unresolved attempt in stable attempt-ID order."""
    outcomes: list[ReconciliationOutcome] = []
    blocked: set[str] = set()
    for attempt in journal.unresolved_attempts():
        outcome = _resolve_one(
            journal=journal,
            clock=clock,
            supplier=suppliers.get(attempt.supplier_id),
            attempt=attempt,
            run_id=run_id,
        )
        outcomes.append(outcome)
        if outcome.resulting_state is AttemptState.OUTCOME_UNKNOWN:
            blocked.add(attempt.sku)
    return ReconciliationReport(
        outcomes=tuple(outcomes), blocked_skus=frozenset(blocked)
    )
