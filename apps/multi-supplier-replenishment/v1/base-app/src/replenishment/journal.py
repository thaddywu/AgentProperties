"""Durable journal of what the application observed and attempted.

Journal rows never override authoritative external state; they describe this
application's own view and actions.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterator, Mapping, Sequence

from .decimals import money_str
from .domain import (
    AttemptState,
    DecisionOutcome,
    LookupOutcome,
    OrderStatus,
    PurchaseOrder,
    RunStatus,
    TriggerKind,
)
from .timeutil import from_rfc3339, parse_date, to_rfc3339


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    run_seq: int
    trigger_kind: TriggerKind
    business_date: date
    started_at: datetime
    ended_at: datetime | None
    status: RunStatus
    source_snapshots: Mapping[str, Any] = field(default_factory=dict)
    note: str = ""


@dataclass(frozen=True)
class DecisionRecord:
    decision_id: int
    run_id: str
    sku: str
    outcome: DecisionOutcome
    reason: str
    detail: Mapping[str, Any]
    recorded_at: datetime


@dataclass(frozen=True)
class AttemptRecord:
    attempt_id: int
    run_id: str
    sku: str
    supplier_id: str
    supplier_sku: str
    destination_id: str
    quantity: int
    expected_unit_price: Decimal
    total_cost: Decimal
    idempotency_key: str
    state: AttemptState
    supplier_order_id: str | None
    reason: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ReconciliationEvent:
    event_id: int
    attempt_id: int
    run_id: str | None
    occurred_at: datetime
    lookup_outcome: str
    resulting_state: AttemptState
    detail: str


@dataclass(frozen=True)
class RecordedOrder:
    supplier_id: str
    supplier_order_id: str
    idempotency_key: str | None
    destination_id: str
    supplier_sku: str
    store_sku: str | None
    quantity: int
    unit_price: Decimal
    total_cost: Decimal
    observed_status: OrderStatus
    created_at: datetime
    promised_delivery_date: date | None
    observed_at: datetime
    source: str


class DuplicateScheduledRun(Exception):
    """A scheduled run already exists for the requested local business date."""


def _row_to_run(row: sqlite3.Row) -> RunRecord:
    return RunRecord(
        run_id=row["run_id"],
        run_seq=row["run_seq"],
        trigger_kind=TriggerKind(row["trigger_kind"]),
        business_date=parse_date(row["business_date"]),
        started_at=from_rfc3339(row["started_at"]),
        ended_at=from_rfc3339(row["ended_at"]) if row["ended_at"] else None,
        status=RunStatus(row["status"]),
        source_snapshots=json.loads(row["source_snapshots"] or "{}"),
        note=row["note"] or "",
    )


def _row_to_decision(row: sqlite3.Row) -> DecisionRecord:
    return DecisionRecord(
        decision_id=row["decision_id"],
        run_id=row["run_id"],
        sku=row["sku"],
        outcome=DecisionOutcome(row["outcome"]),
        reason=row["reason"] or "",
        detail=json.loads(row["detail"] or "{}"),
        recorded_at=from_rfc3339(row["recorded_at"]),
    )


def _row_to_attempt(row: sqlite3.Row) -> AttemptRecord:
    return AttemptRecord(
        attempt_id=row["attempt_id"],
        run_id=row["run_id"],
        sku=row["sku"],
        supplier_id=row["supplier_id"],
        supplier_sku=row["supplier_sku"],
        destination_id=row["destination_id"],
        quantity=row["quantity"],
        expected_unit_price=Decimal(row["expected_unit_price"]),
        total_cost=Decimal(row["total_cost"]),
        idempotency_key=row["idempotency_key"],
        state=AttemptState(row["state"]),
        supplier_order_id=row["supplier_order_id"],
        reason=row["reason"] or "",
        created_at=from_rfc3339(row["created_at"]),
        updated_at=from_rfc3339(row["updated_at"]),
    )


def _row_to_recorded_order(row: sqlite3.Row) -> RecordedOrder:
    promised = row["promised_delivery_date"]
    return RecordedOrder(
        supplier_id=row["supplier_id"],
        supplier_order_id=row["supplier_order_id"],
        idempotency_key=row["idempotency_key"],
        destination_id=row["destination_id"],
        supplier_sku=row["supplier_sku"],
        store_sku=row["store_sku"],
        quantity=row["quantity"],
        unit_price=Decimal(row["unit_price"]),
        total_cost=Decimal(row["total_cost"]),
        observed_status=OrderStatus(row["observed_status"]),
        created_at=from_rfc3339(row["created_at"]),
        promised_delivery_date=parse_date(promised) if promised else None,
        observed_at=from_rfc3339(row["observed_at"]),
        source=row["source"],
    )


class Journal:
    """Every read and write of application-owned SQLite state."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._db = connection

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Group writes that describe one external response into one commit."""
        self._db.execute("BEGIN IMMEDIATE")
        try:
            yield
        except Exception:
            self._db.execute("ROLLBACK")
            raise
        self._db.execute("COMMIT")

    # -- runs -------------------------------------------------------------

    def create_run(
        self, trigger_kind: TriggerKind, business_date_value: date, started_at: datetime
    ) -> RunRecord:
        self._db.execute("BEGIN IMMEDIATE")
        try:
            if trigger_kind is TriggerKind.SCHEDULED:
                existing = self._db.execute(
                    "SELECT run_id FROM runs WHERE trigger_kind = 'SCHEDULED' "
                    "AND business_date = ?",
                    (business_date_value.isoformat(),),
                ).fetchone()
                if existing is not None:
                    raise DuplicateScheduledRun(
                        f"scheduled run {existing['run_id']} already exists for "
                        f"{business_date_value.isoformat()}"
                    )
            row = self._db.execute(
                "SELECT COALESCE(MAX(run_seq), 0) + 1 AS next_seq FROM runs"
            ).fetchone()
            run_seq = int(row["next_seq"])
            run_id = f"RUN-{run_seq:06d}"
            self._db.execute(
                "INSERT INTO runs (run_id, run_seq, trigger_kind, business_date, "
                "started_at, ended_at, status, source_snapshots, note) "
                "VALUES (?, ?, ?, ?, ?, NULL, ?, '{}', '')",
                (
                    run_id,
                    run_seq,
                    trigger_kind.value,
                    business_date_value.isoformat(),
                    to_rfc3339(started_at),
                    RunStatus.RUNNING.value,
                ),
            )
            self._db.execute("COMMIT")
        except Exception:
            self._db.execute("ROLLBACK")
            raise
        return self.get_run(run_id)  # type: ignore[return-value]

    def set_source_snapshots(self, run_id: str, snapshots: Mapping[str, Any]) -> None:
        self._db.execute(
            "UPDATE runs SET source_snapshots = ? WHERE run_id = ?",
            (json.dumps(snapshots, sort_keys=True), run_id),
        )

    def finish_run(
        self, run_id: str, status: RunStatus, ended_at: datetime, note: str = ""
    ) -> None:
        self._db.execute(
            "UPDATE runs SET status = ?, ended_at = ?, note = ? WHERE run_id = ?",
            (status.value, to_rfc3339(ended_at), note, run_id),
        )

    def get_run(self, run_id: str) -> RunRecord | None:
        row = self._db.execute(
            "SELECT * FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        return _row_to_run(row) if row else None

    def list_runs(self, limit: int | None = None) -> list[RunRecord]:
        sql = "SELECT * FROM runs ORDER BY run_seq DESC"
        params: tuple[Any, ...] = ()
        if limit is not None:
            sql += " LIMIT ?"
            params = (limit,)
        return [_row_to_run(row) for row in self._db.execute(sql, params)]

    def active_run(self) -> RunRecord | None:
        row = self._db.execute(
            "SELECT * FROM runs WHERE status = 'RUNNING' ORDER BY run_seq LIMIT 1"
        ).fetchone()
        return _row_to_run(row) if row else None

    def scheduled_run_for(self, business_date_value: date) -> RunRecord | None:
        row = self._db.execute(
            "SELECT * FROM runs WHERE trigger_kind = 'SCHEDULED' AND business_date = ?",
            (business_date_value.isoformat(),),
        ).fetchone()
        return _row_to_run(row) if row else None

    def last_completed_run(self) -> RunRecord | None:
        row = self._db.execute(
            "SELECT * FROM runs WHERE status IN ('COMPLETED', "
            "'COMPLETED_WITH_EXCEPTIONS') ORDER BY run_seq DESC LIMIT 1"
        ).fetchone()
        return _row_to_run(row) if row else None

    def add_run_event(
        self,
        run_id: str,
        occurred_at: datetime,
        category: str,
        message: str,
        detail: Mapping[str, Any] | None = None,
    ) -> None:
        self._db.execute(
            "INSERT INTO run_events (run_id, occurred_at, category, message, detail) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                run_id,
                to_rfc3339(occurred_at),
                category,
                message,
                json.dumps(detail or {}, sort_keys=True, default=str),
            ),
        )

    def run_events(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM run_events WHERE run_id = ? ORDER BY event_id", (run_id,)
        )
        return [
            {
                "event_id": row["event_id"],
                "occurred_at": row["occurred_at"],
                "category": row["category"],
                "message": row["message"],
                "detail": json.loads(row["detail"] or "{}"),
            }
            for row in rows
        ]

    # -- decisions --------------------------------------------------------

    def record_decision(
        self,
        run_id: str,
        sku: str,
        outcome: DecisionOutcome,
        reason: str,
        detail: Mapping[str, Any],
        recorded_at: datetime,
    ) -> None:
        self._db.execute(
            "INSERT INTO sku_decisions (run_id, sku, outcome, reason, detail, "
            "recorded_at) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (run_id, sku) DO UPDATE SET outcome = excluded.outcome, "
            "reason = excluded.reason, detail = excluded.detail, "
            "recorded_at = excluded.recorded_at",
            (
                run_id,
                sku,
                outcome.value,
                reason,
                json.dumps(detail, sort_keys=True, default=str),
                to_rfc3339(recorded_at),
            ),
        )

    def decisions_for_run(self, run_id: str) -> list[DecisionRecord]:
        rows = self._db.execute(
            "SELECT * FROM sku_decisions WHERE run_id = ? ORDER BY sku", (run_id,)
        )
        return [_row_to_decision(row) for row in rows]

    def decision(self, run_id: str, sku: str) -> DecisionRecord | None:
        row = self._db.execute(
            "SELECT * FROM sku_decisions WHERE run_id = ? AND sku = ?", (run_id, sku)
        ).fetchone()
        return _row_to_decision(row) if row else None

    # -- purchase attempts ------------------------------------------------

    def commit_attempt(
        self,
        *,
        run_id: str,
        sku: str,
        supplier_id: str,
        supplier_sku: str,
        destination_id: str,
        quantity: int,
        expected_unit_price: Decimal,
        total_cost: Decimal,
        idempotency_key: str,
        created_at: datetime,
    ) -> AttemptRecord:
        """Durably record the purchase intention before any supplier call."""
        stamp = to_rfc3339(created_at)
        self._db.execute("BEGIN IMMEDIATE")
        try:
            cursor = self._db.execute(
                "INSERT INTO purchase_attempts (run_id, sku, supplier_id, "
                "supplier_sku, destination_id, quantity, expected_unit_price, "
                "total_cost, idempotency_key, state, supplier_order_id, reason, "
                "created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, '', ?, ?)",
                (
                    run_id,
                    sku,
                    supplier_id,
                    supplier_sku,
                    destination_id,
                    quantity,
                    money_str(expected_unit_price),
                    money_str(total_cost),
                    idempotency_key,
                    AttemptState.DISPATCHING.value,
                    stamp,
                    stamp,
                ),
            )
            attempt_id = int(cursor.lastrowid or 0)
            self._db.execute("COMMIT")
        except Exception:
            self._db.execute("ROLLBACK")
            raise
        return self.get_attempt(attempt_id)  # type: ignore[return-value]

    def update_attempt(
        self,
        attempt_id: int,
        *,
        state: AttemptState,
        updated_at: datetime,
        supplier_order_id: str | None = None,
        reason: str = "",
    ) -> None:
        self._db.execute(
            "UPDATE purchase_attempts SET state = ?, supplier_order_id = ?, "
            "reason = ?, updated_at = ? WHERE attempt_id = ?",
            (
                state.value,
                supplier_order_id,
                reason,
                to_rfc3339(updated_at),
                attempt_id,
            ),
        )

    def get_attempt(self, attempt_id: int) -> AttemptRecord | None:
        row = self._db.execute(
            "SELECT * FROM purchase_attempts WHERE attempt_id = ?", (attempt_id,)
        ).fetchone()
        return _row_to_attempt(row) if row else None

    def attempt_for(self, run_id: str, sku: str) -> AttemptRecord | None:
        row = self._db.execute(
            "SELECT * FROM purchase_attempts WHERE run_id = ? AND sku = ?",
            (run_id, sku),
        ).fetchone()
        return _row_to_attempt(row) if row else None

    def unresolved_attempts(self) -> list[AttemptRecord]:
        """Attempts whose external outcome is not yet established, in stable order."""
        rows = self._db.execute(
            "SELECT * FROM purchase_attempts WHERE state IN (?, ?) ORDER BY attempt_id",
            (AttemptState.DISPATCHING.value, AttemptState.OUTCOME_UNKNOWN.value),
        )
        return [_row_to_attempt(row) for row in rows]

    def list_attempts(
        self, states: Sequence[AttemptState] | None = None, run_id: str | None = None
    ) -> list[AttemptRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if states:
            clauses.append(
                "state IN (" + ",".join("?" for _ in states) + ")"
            )
            params.extend(state.value for state in states)
        if run_id:
            clauses.append("run_id = ?")
            params.append(run_id)
        sql = "SELECT * FROM purchase_attempts"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY attempt_id"
        return [_row_to_attempt(row) for row in self._db.execute(sql, params)]

    # -- reconciliation ---------------------------------------------------

    def add_reconciliation_event(
        self,
        *,
        attempt_id: int,
        run_id: str | None,
        occurred_at: datetime,
        lookup_outcome: str,
        resulting_state: AttemptState,
        detail: str = "",
    ) -> None:
        self._db.execute(
            "INSERT INTO reconciliation_events (attempt_id, run_id, occurred_at, "
            "lookup_outcome, resulting_state, detail) VALUES (?, ?, ?, ?, ?, ?)",
            (
                attempt_id,
                run_id,
                to_rfc3339(occurred_at),
                lookup_outcome,
                resulting_state.value,
                detail,
            ),
        )

    def reconciliation_events(
        self, attempt_id: int | None = None
    ) -> list[ReconciliationEvent]:
        sql = "SELECT * FROM reconciliation_events"
        params: tuple[Any, ...] = ()
        if attempt_id is not None:
            sql += " WHERE attempt_id = ?"
            params = (attempt_id,)
        sql += " ORDER BY event_id"
        return [
            ReconciliationEvent(
                event_id=row["event_id"],
                attempt_id=row["attempt_id"],
                run_id=row["run_id"],
                occurred_at=from_rfc3339(row["occurred_at"]),
                lookup_outcome=row["lookup_outcome"],
                resulting_state=AttemptState(row["resulting_state"]),
                detail=row["detail"] or "",
            )
            for row in self._db.execute(sql, params)
        ]

    # -- observed supplier orders ----------------------------------------

    def record_supplier_order(
        self, order: PurchaseOrder, observed_at: datetime, source: str
    ) -> None:
        self._db.execute(
            "INSERT INTO recorded_supplier_orders (supplier_id, supplier_order_id, "
            "idempotency_key, destination_id, supplier_sku, store_sku, quantity, "
            "unit_price, total_cost, observed_status, created_at, "
            "promised_delivery_date, observed_at, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (supplier_id, supplier_order_id) DO UPDATE SET "
            "observed_status = excluded.observed_status, "
            "store_sku = excluded.store_sku, "
            "promised_delivery_date = excluded.promised_delivery_date, "
            "observed_at = excluded.observed_at, source = excluded.source",
            (
                order.supplier_id,
                order.supplier_order_id,
                order.idempotency_key,
                order.destination_id,
                order.supplier_sku,
                order.store_sku,
                order.quantity,
                money_str(order.unit_price),
                money_str(order.total_cost),
                order.status.value,
                to_rfc3339(order.created_at),
                order.promised_delivery_date.isoformat()
                if order.promised_delivery_date
                else None,
                to_rfc3339(observed_at),
                source,
            ),
        )

    def recorded_orders(self, sku: str | None = None) -> list[RecordedOrder]:
        sql = "SELECT * FROM recorded_supplier_orders"
        params: tuple[Any, ...] = ()
        if sku is not None:
            sql += " WHERE store_sku = ?"
            params = (sku,)
        sql += " ORDER BY supplier_id, supplier_order_id"
        return [_row_to_recorded_order(row) for row in self._db.execute(sql, params)]

    # -- restart recovery -------------------------------------------------

    def recover_interrupted(self, now: datetime) -> dict[str, list[str]]:
        """Mark interrupted runs failed and dispatching attempts unknown."""
        stamp = to_rfc3339(now)
        recovered_runs: list[str] = []
        recovered_attempts: list[str] = []
        self._db.execute("BEGIN IMMEDIATE")
        try:
            for row in self._db.execute(
                "SELECT attempt_id FROM purchase_attempts WHERE state = ?",
                (AttemptState.DISPATCHING.value,),
            ).fetchall():
                attempt_id = row["attempt_id"]
                self._db.execute(
                    "UPDATE purchase_attempts SET state = ?, reason = ?, "
                    "updated_at = ? WHERE attempt_id = ?",
                    (
                        AttemptState.OUTCOME_UNKNOWN.value,
                        "process interrupted after the dispatching commit; "
                        "supplier outcome not established",
                        stamp,
                        attempt_id,
                    ),
                )
                self._db.execute(
                    "INSERT INTO reconciliation_events (attempt_id, run_id, "
                    "occurred_at, lookup_outcome, resulting_state, detail) "
                    "VALUES (?, NULL, ?, 'RECOVERED_FROM_DISPATCHING', ?, ?)",
                    (
                        attempt_id,
                        stamp,
                        AttemptState.OUTCOME_UNKNOWN.value,
                        "startup recovery of an interrupted dispatch",
                    ),
                )
                recovered_attempts.append(str(attempt_id))
            for row in self._db.execute(
                "SELECT run_id FROM runs WHERE status = ?", (RunStatus.RUNNING.value,)
            ).fetchall():
                run_id = row["run_id"]
                self._db.execute(
                    "UPDATE runs SET status = ?, ended_at = ?, note = ? "
                    "WHERE run_id = ?",
                    (
                        RunStatus.FAILED.value,
                        stamp,
                        "interrupted: process restarted while the run was RUNNING",
                        run_id,
                    ),
                )
                recovered_runs.append(run_id)
            self._db.execute("COMMIT")
        except Exception:
            self._db.execute("ROLLBACK")
            raise
        return {"runs": recovered_runs, "attempts": recovered_attempts}
