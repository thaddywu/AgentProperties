"""Operator reports in machine-readable JSON and readable text.

Reports distinguish zero, missing, rejected, unavailable, malformed, and
unknown values, and never present a proposed order as an accepted one.
"""

from __future__ import annotations

import json
from typing import Any, Sequence

from .app import Application
from .domain import AttemptState, DecisionOutcome
from .journal import AttemptRecord, DecisionRecord, RecordedOrder, RunRecord
from .scheduler import Scheduler
from .timeutil import to_rfc3339

MISSING = "—"


def _run_dict(run: RunRecord) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "trigger_kind": run.trigger_kind.value,
        "business_date": run.business_date.isoformat(),
        "started_at": to_rfc3339(run.started_at),
        "ended_at": to_rfc3339(run.ended_at) if run.ended_at else None,
        "status": run.status.value,
        "source_snapshots": dict(run.source_snapshots),
        "note": run.note,
    }


def _decision_dict(decision: DecisionRecord) -> dict[str, Any]:
    return {
        "run_id": decision.run_id,
        "sku": decision.sku,
        "outcome": decision.outcome.value,
        "reason": decision.reason,
        "recorded_at": to_rfc3339(decision.recorded_at),
        "detail": dict(decision.detail),
    }


def _attempt_dict(attempt: AttemptRecord) -> dict[str, Any]:
    return {
        "attempt_id": attempt.attempt_id,
        "run_id": attempt.run_id,
        "sku": attempt.sku,
        "supplier_id": attempt.supplier_id,
        "supplier_sku": attempt.supplier_sku,
        "destination_id": attempt.destination_id,
        "quantity": attempt.quantity,
        "expected_unit_price_usd": str(attempt.expected_unit_price),
        "total_cost_usd": str(attempt.total_cost),
        "idempotency_key": attempt.idempotency_key,
        "state": attempt.state.value,
        "supplier_order_id": attempt.supplier_order_id,
        "reason": attempt.reason,
        "created_at": to_rfc3339(attempt.created_at),
        "updated_at": to_rfc3339(attempt.updated_at),
    }


def _order_dict(order: RecordedOrder) -> dict[str, Any]:
    return {
        "supplier_id": order.supplier_id,
        "supplier_order_id": order.supplier_order_id,
        "idempotency_key": order.idempotency_key,
        "destination_id": order.destination_id,
        "supplier_sku": order.supplier_sku,
        "store_sku": order.store_sku,
        "quantity": order.quantity,
        "unit_price_usd": str(order.unit_price),
        "total_cost_usd": str(order.total_cost),
        "observed_status": order.observed_status.value,
        "created_at": to_rfc3339(order.created_at),
        "promised_delivery_date": (
            order.promised_delivery_date.isoformat()
            if order.promised_delivery_date
            else None
        ),
        "observed_at": to_rfc3339(order.observed_at),
        "source": order.source,
    }


# -- report builders -------------------------------------------------------


def status_report(app: Application) -> dict[str, Any]:
    scheduler = Scheduler(app)
    last = app.journal.last_completed_run()
    active = app.journal.active_run()
    unresolved = app.journal.unresolved_attempts()
    return {
        "store_id": app.config.store_id,
        "destination_id": app.config.destination_id,
        "timezone": app.config.timezone_name,
        "database_path": str(app.config.database_path),
        "enabled_skus": list(app.config.sku_ids),
        "scheduler": scheduler.status().as_dict(),
        "active_run": _run_dict(active) if active else None,
        "last_completed_run": _run_dict(last) if last else None,
        "unresolved_attempts": [_attempt_dict(item) for item in unresolved],
        "recovered_on_startup": app.recovered,
    }


def runs_report(app: Application, limit: int | None = None) -> dict[str, Any]:
    return {"runs": [_run_dict(run) for run in app.journal.list_runs(limit)]}


def run_detail_report(app: Application, run_id: str) -> dict[str, Any]:
    run = app.journal.get_run(run_id)
    if run is None:
        raise KeyError(run_id)
    decisions = app.journal.decisions_for_run(run_id)
    attempts = app.journal.list_attempts(run_id=run_id)
    return {
        "run": _run_dict(run),
        "events": app.journal.run_events(run_id),
        "decisions": [_decision_dict(item) for item in decisions],
        "attempts": [_attempt_dict(item) for item in attempts],
    }


def decisions_report(
    app: Application, run_id: str, sku: str | None = None
) -> dict[str, Any]:
    decisions = app.journal.decisions_for_run(run_id)
    if sku is not None:
        decisions = [item for item in decisions if item.sku == sku]
    return {"run_id": run_id, "decisions": [_decision_dict(item) for item in decisions]}


def attempts_report(
    app: Application,
    states: Sequence[AttemptState] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    attempts = app.journal.list_attempts(states=states, run_id=run_id)
    payload: list[dict[str, Any]] = []
    for attempt in attempts:
        item = _attempt_dict(attempt)
        item["reconciliation_history"] = [
            {
                "event_id": event.event_id,
                "run_id": event.run_id,
                "occurred_at": to_rfc3339(event.occurred_at),
                "lookup_outcome": event.lookup_outcome,
                "resulting_state": event.resulting_state.value,
                "detail": event.detail,
            }
            for event in app.journal.reconciliation_events(attempt.attempt_id)
        ]
        payload.append(item)
    return {"attempts": payload}


def orders_report(app: Application, sku: str | None = None) -> dict[str, Any]:
    return {
        "recorded_supplier_orders": [
            _order_dict(order) for order in app.journal.recorded_orders(sku)
        ]
    }


def supplier_calls_report(
    app: Application, supplier_id: str | None = None, limit: int | None = None
) -> dict[str, Any]:
    """Raw supplier calls recorded by the local mock world.

    This reads external mock-world files, not the application database.  A
    production supplier adapter has no such log.
    """
    supplier_ids = (
        [supplier_id] if supplier_id else sorted(app.config.suppliers)
    )
    calls: list[dict[str, Any]] = []
    for identifier in supplier_ids:
        world = app.services.world_for(identifier)
        if world is None:
            continue
        entries = world.raw_calls(identifier)
        if limit is not None:
            entries = entries[-limit:]
        calls.extend(entries)
    calls.sort(key=lambda entry: (entry.get("at", ""), entry.get("supplier_id", "")))
    return {"raw_supplier_calls": calls}


# -- text rendering --------------------------------------------------------


def _row(label: str, value: Any) -> str:
    return f"  {label:<28} {MISSING if value is None else value}"


def render_status(report: dict[str, Any]) -> str:
    scheduler = report["scheduler"]
    lines = ["Replenishment status", ""]
    lines.append(_row("store", report["store_id"]))
    lines.append(_row("destination", report["destination_id"]))
    lines.append(_row("time zone", report["timezone"]))
    lines.append(_row("application database", report["database_path"]))
    lines.append(_row("enabled SKUs", ", ".join(report["enabled_skus"])))
    lines.append("")
    lines.append("Scheduler")
    lines.append(_row("local now", scheduler["local_now"]))
    lines.append(_row("daily run time", scheduler["daily_run_time"]))
    lines.append(_row("next due at", scheduler["next_due_at"]))
    lines.append(_row("due now", scheduler["due_now"]))
    lines.append(_row("today's scheduled run", scheduler["todays_scheduled_run_id"]))
    lines.append(_row("its status", scheduler["todays_scheduled_run_status"]))
    lines.append("")
    active = report["active_run"]
    lines.append(_row("active run", active["run_id"] if active else None))
    last = report["last_completed_run"]
    if last:
        lines.append(
            _row(
                "last completed run",
                f"{last['run_id']} {last['status']} for {last['business_date']}",
            )
        )
    else:
        lines.append(_row("last completed run", None))
    unresolved = report["unresolved_attempts"]
    lines.append(_row("unresolved attempts", len(unresolved)))
    for attempt in unresolved:
        lines.append(
            f"    attempt {attempt['attempt_id']} {attempt['sku']} "
            f"{attempt['supplier_id']} {attempt['state']}: {attempt['reason']}"
        )
    recovered = report["recovered_on_startup"]
    if recovered["runs"] or recovered["attempts"]:
        lines.append("")
        lines.append("Startup recovery")
        lines.append(_row("runs marked failed", ", ".join(recovered["runs"]) or None))
        lines.append(
            _row("attempts made unknown", ", ".join(recovered["attempts"]) or None)
        )
    return "\n".join(lines)


def render_runs(report: dict[str, Any]) -> str:
    lines = [f"{'RUN':<12} {'TRIGGER':<10} {'DATE':<12} {'STATUS':<28} STARTED"]
    for run in report["runs"]:
        lines.append(
            f"{run['run_id']:<12} {run['trigger_kind']:<10} "
            f"{run['business_date']:<12} {run['status']:<28} {run['started_at']}"
        )
    if len(lines) == 1:
        lines.append("  (no runs recorded)")
    return "\n".join(lines)


def render_run_detail(report: dict[str, Any]) -> str:
    run = report["run"]
    lines = [f"Run {run['run_id']} ({run['trigger_kind']})", ""]
    lines.append(_row("business date", run["business_date"]))
    lines.append(_row("status", run["status"]))
    lines.append(_row("started at", run["started_at"]))
    lines.append(_row("ended at", run["ended_at"]))
    if run["note"]:
        lines.append(_row("note", run["note"]))
    snapshots = run["source_snapshots"]
    if snapshots:
        lines.append("")
        lines.append("Source snapshots")
        inventory = snapshots.get("inventory")
        if inventory:
            lines.append(
                _row(
                    "inventory",
                    f"revision {inventory['revision_id']} as of {inventory['as_of']}",
                )
            )
        for supplier_id, state in sorted(snapshots.get("suppliers", {}).items()):
            summary = (
                f"as of {state['as_of']} complete={state['complete']}"
                if state["usable"]
                else f"UNUSABLE: {state['error']}"
            )
            lines.append(_row(supplier_id, summary))
    if report["events"]:
        lines.append("")
        lines.append("Run events")
        for event in report["events"]:
            lines.append(f"  [{event['category']}] {event['message']}")
    lines.append("")
    lines.append("Decisions")
    for decision in report["decisions"]:
        lines.append(f"  {decision['sku']:<18} {decision['outcome']}")
        lines.append(f"      {decision['reason']}")
    if not report["decisions"]:
        lines.append("  (no SKU was processed)")
    if report["attempts"]:
        lines.append("")
        lines.append("Purchase attempts")
        for attempt in report["attempts"]:
            lines.append(
                f"  attempt {attempt['attempt_id']} {attempt['sku']} "
                f"{attempt['supplier_id']} qty {attempt['quantity']} @ "
                f"{attempt['expected_unit_price_usd']} -> {attempt['state']}"
            )
            lines.append(f"      key {attempt['idempotency_key']}")
            lines.append(
                f"      supplier order "
                f"{attempt['supplier_order_id'] or MISSING}: {attempt['reason']}"
            )
    return "\n".join(lines)


def render_decisions(report: dict[str, Any]) -> str:
    lines = [f"Decisions for {report['run_id']}", ""]
    for decision in report["decisions"]:
        detail = decision["detail"]
        lines.append(f"{decision['sku']}  {decision['outcome']}")
        lines.append(f"  reason: {decision['reason']}")
        lines.append(_row("on hand", detail.get("on_hand")))
        lines.append(_row("outstanding", detail.get("outstanding_quantity")))
        forecast = detail.get("forecast")
        if forecast:
            lines.append(_row("base daily demand", forecast["base_daily_demand"]))
            lines.append(
                _row(
                    "history window",
                    f"{forecast['window_start']} .. {forecast['window_end']}",
                )
            )
        for contribution in detail.get("outstanding_contributions", []):
            lines.append(
                f"    outstanding {contribution['supplier_order_id']} "
                f"({contribution['status']}) contributes "
                f"{contribution['contributes']} of {contribution['order_quantity']}"
                f" — {contribution['note']}"
            )
        for exclusion in detail.get("offer_exclusions", []):
            lines.append(
                f"    excluded {exclusion['supplier_id']} [{exclusion['kind']}]: "
                f"{exclusion['reason']}"
            )
        for escalation in detail.get("lead_time_escalations", []):
            lines.append(
                f"    escalation {escalation['supplier_id']}: {escalation['reason']}"
            )
        for candidate in detail.get("candidates", []):
            lines.append(
                f"    candidate {candidate['supplier_id']} qty "
                f"{candidate['order_quantity']} @ {candidate['unit_price_usd']} "
                f"total {candidate['total_cost_usd']} lead "
                f"{candidate['lead_time_days']}d "
                f"avoids_stockout={candidate['avoids_projected_stockout']} "
                f"executable={candidate['executable']}"
            )
            for failure in candidate["limit_failures"]:
                lines.append(f"        owner limit: {failure}")
        selected = detail.get("selected")
        if selected:
            lines.append(
                f"    selected {selected['supplier_id']} "
                f"{selected['supplier_sku']} qty {selected['quantity']} @ "
                f"{selected['expected_unit_price_usd']} "
                f"total {selected['total_cost_usd']}"
            )
            lines.append(f"    idempotency key {selected['idempotency_key']}")
        order = detail.get("supplier_order")
        if order:
            lines.append(
                f"    supplier order {order['supplier_order_id']} "
                f"{order['status']} promised {order['promised_delivery_date']}"
            )
        lines.append("")
    if not report["decisions"]:
        lines.append("(no decisions)")
    return "\n".join(lines)


def render_attempts(report: dict[str, Any]) -> str:
    lines = []
    for attempt in report["attempts"]:
        lines.append(
            f"attempt {attempt['attempt_id']}  {attempt['run_id']}  "
            f"{attempt['sku']}  {attempt['supplier_id']}  {attempt['state']}"
        )
        lines.append(
            f"  {attempt['quantity']} x {attempt['supplier_sku']} @ "
            f"{attempt['expected_unit_price_usd']} = "
            f"{attempt['total_cost_usd']} to {attempt['destination_id']}"
        )
        lines.append(f"  key {attempt['idempotency_key']}")
        lines.append(f"  supplier order {attempt['supplier_order_id'] or MISSING}")
        lines.append(f"  reason {attempt['reason'] or MISSING}")
        for event in attempt["reconciliation_history"]:
            lines.append(
                f"    reconciled {event['occurred_at']}: {event['lookup_outcome']} "
                f"-> {event['resulting_state']} ({event['detail']})"
            )
        lines.append("")
    if not lines:
        lines.append("(no purchase attempts)")
    return "\n".join(lines)


def render_orders(report: dict[str, Any]) -> str:
    lines = [
        f"{'SUPPLIER':<12} {'ORDER':<12} {'STORE SKU':<18} {'QTY':>6} "
        f"{'STATUS':<10} {'PROMISED':<12} SOURCE"
    ]
    for order in report["recorded_supplier_orders"]:
        lines.append(
            f"{order['supplier_id']:<12} {order['supplier_order_id']:<12} "
            f"{(order['store_sku'] or MISSING):<18} {order['quantity']:>6} "
            f"{order['observed_status']:<10} "
            f"{(order['promised_delivery_date'] or MISSING):<12} {order['source']}"
        )
    if len(lines) == 1:
        lines.append("  (no supplier orders recorded)")
    return "\n".join(lines)


def render_supplier_calls(report: dict[str, Any]) -> str:
    lines = []
    for call in report["raw_supplier_calls"]:
        lines.append(
            f"{call['at']}  {call['supplier_id']}  {call['method']}  -> "
            f"{call['outcome']}"
        )
        lines.append(f"    arguments {json.dumps(call['arguments'], sort_keys=True)}")
        if call.get("detail"):
            lines.append(f"    {call['detail']}")
    if not lines:
        lines.append("(no raw supplier calls recorded)")
    return "\n".join(lines)


def render_run_outcome(report: dict[str, Any]) -> str:
    """Human-readable summary printed right after a run."""
    return render_run_detail(report)


OUTCOME_ORDER = tuple(item.value for item in DecisionOutcome)
