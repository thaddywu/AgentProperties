"""Run orchestration: reconciliation, authoritative reads, per-SKU decisions,
and at most one purchase order per store SKU per run."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Mapping, Sequence

from .adapters.registry import Services
from .config import Config, SkuConfig
from .decimals import money_str
from .domain import (
    AttemptState,
    BASE_UNIT,
    CalendarLabel,
    DecisionOutcome,
    EXCEPTION_OUTCOMES,
    InventoryRecord,
    InventorySnapshot,
    NotOffered,
    Offer,
    OrderStatus,
    RunStatus,
    TriggerKind,
)
from .errors import ExternalServiceError, FatalRunError, RunLockError
from .execution import idempotency_key, place_purchase_order
from .forecast import BaseForecast, ForecastInputError, compute_base, history_window
from .journal import Journal, RunRecord
from .locking import RunLock
from .outstanding import (
    OutstandingResult,
    SupplierOrderState,
    compute_outstanding,
    unmapped_open_orders,
)
from .planning import build_plan, project_stockout
from .reconciliation import ReconciliationReport, reconcile_unknown_attempts
from .selection import (
    Candidate,
    OfferExclusion,
    check_offer_usable,
    owner_limit_failures,
    rank_candidates,
)
from .timeutil import business_date, date_range, to_rfc3339

#: Section 4.2 and 4.5 freshness bound for authoritative snapshots.
MAX_SNAPSHOT_AGE = timedelta(minutes=15)


@dataclass
class SkuResult:
    sku: str
    outcome: DecisionOutcome
    reason: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunOutcome:
    run: RunRecord
    reconciliation: ReconciliationReport | None
    results: tuple[SkuResult, ...]
    fatal_reason: str | None = None


def _snapshot_freshness_problem(
    as_of: datetime, run_started_at: datetime, label: str
) -> str | None:
    if as_of > run_started_at:
        return (
            f"{label} snapshot is timestamped {to_rfc3339(as_of)}, which is after the "
            f"run start {to_rfc3339(run_started_at)}"
        )
    if run_started_at - as_of > MAX_SNAPSHOT_AGE:
        age = run_started_at - as_of
        return (
            f"{label} snapshot is {int(age.total_seconds())}s old, older than the "
            f"{int(MAX_SNAPSHOT_AGE.total_seconds())}s freshness bound"
        )
    return None


class ReplenishmentEngine:
    """Executes one replenishment run at a time."""

    def __init__(
        self,
        config: Config,
        services: Services,
        journal: Journal,
        lock: RunLock | None = None,
    ) -> None:
        self.config = config
        self.services = services
        self.journal = journal
        self.lock = lock or RunLock(str(config.database_path) + ".lock")

    # -- entry point ------------------------------------------------------

    def execute(self, trigger_kind: TriggerKind) -> RunOutcome:
        if self.lock.held:
            raise RunLockError("this worker is already executing a run")
        active = self.journal.active_run()
        if active is not None:
            raise RunLockError(
                f"run {active.run_id} is still RUNNING; runs must not overlap"
            )
        self.lock.acquire()
        try:
            active = self.journal.active_run()
            if active is not None:
                raise RunLockError(
                    f"run {active.run_id} is still RUNNING; runs must not overlap"
                )
            return self._execute_locked(trigger_kind)
        finally:
            self.lock.release()

    def _execute_locked(self, trigger_kind: TriggerKind) -> RunOutcome:
        clock = self.services.clock
        run_started_at = clock.now()
        run_date = business_date(run_started_at, self.config.tzinfo)
        run = self.journal.create_run(trigger_kind, run_date, run_started_at)

        reconciliation = reconcile_unknown_attempts(
            journal=self.journal,
            clock=clock,
            suppliers=self.services.suppliers,
            run_id=run.run_id,
        )
        for outcome in reconciliation.outcomes:
            self.journal.add_run_event(
                run.run_id,
                clock.now(),
                "RECONCILIATION",
                f"attempt {outcome.attempt_id} for {outcome.sku} at "
                f"{outcome.supplier_id}: {outcome.lookup_outcome} -> "
                f"{outcome.resulting_state.value}",
                outcome.as_dict(),
            )

        try:
            snapshot = self._inventory_snapshot(run, run_started_at)
        except FatalRunError as exc:
            self.journal.add_run_event(
                run.run_id, clock.now(), "FATAL", str(exc)
            )
            self.journal.finish_run(
                run.run_id, RunStatus.FAILED, clock.now(), note=str(exc)
            )
            return RunOutcome(
                run=self.journal.get_run(run.run_id),  # type: ignore[arg-type]
                reconciliation=reconciliation,
                results=(),
                fatal_reason=str(exc),
            )

        supplier_states = self._supplier_order_states(run, run_started_at)

        source_snapshots: dict[str, Any] = {
            "inventory": {
                "revision_id": snapshot.revision_id,
                "as_of": to_rfc3339(snapshot.as_of),
            },
            "suppliers": {
                supplier_id: {
                    "usable": state.usable,
                    "as_of": to_rfc3339(state.snapshot.as_of)
                    if state.snapshot
                    else None,
                    "complete": state.snapshot.complete if state.snapshot else None,
                    "error": state.error,
                }
                for supplier_id, state in sorted(supplier_states.items())
            },
        }
        self.journal.set_source_snapshots(run.run_id, source_snapshots)

        records_by_sku = self._index_records(snapshot)
        results: list[SkuResult] = []
        for sku_config in self.config.skus:
            result = self._process_sku(
                run=run,
                run_started_at=run_started_at,
                run_date=run_date,
                sku_config=sku_config,
                snapshot=snapshot,
                records_by_sku=records_by_sku,
                supplier_states=supplier_states,
                blocked_skus=reconciliation.blocked_skus,
            )
            self.journal.record_decision(
                run.run_id,
                result.sku,
                result.outcome,
                result.reason,
                result.detail,
                clock.now(),
            )
            results.append(result)

        status = (
            RunStatus.COMPLETED_WITH_EXCEPTIONS
            if any(item.outcome in EXCEPTION_OUTCOMES for item in results)
            else RunStatus.COMPLETED
        )
        self.journal.finish_run(run.run_id, status, clock.now())
        return RunOutcome(
            run=self.journal.get_run(run.run_id),  # type: ignore[arg-type]
            reconciliation=reconciliation,
            results=tuple(results),
        )

    # -- authoritative reads ---------------------------------------------

    def _inventory_snapshot(
        self, run: RunRecord, run_started_at: datetime
    ) -> InventorySnapshot:
        requested = list(self.config.sku_ids)
        try:
            snapshot = self.services.inventory.get_snapshot(
                self.config.store_id, requested
            )
        except ExternalServiceError as exc:
            raise FatalRunError(
                f"the Inventory Ledger snapshot could not be obtained: {exc}; "
                "no purchase call may be made in this run"
            ) from exc
        if not snapshot.revision_id:
            raise FatalRunError("the Inventory Ledger snapshot has no revision ID")
        problem = _snapshot_freshness_problem(
            snapshot.as_of, run_started_at, "the Inventory Ledger"
        )
        if problem:
            raise FatalRunError(problem)
        wanted = set(requested)
        for record in snapshot.records:
            if record.store_id != self.config.store_id:
                raise FatalRunError(
                    f"the Inventory Ledger snapshot contains a record for store "
                    f"{record.store_id!r}, not {self.config.store_id!r}"
                )
            if record.sku not in wanted:
                raise FatalRunError(
                    f"the Inventory Ledger snapshot contains unrequested SKU "
                    f"{record.sku!r}"
                )
        return snapshot

    @staticmethod
    def _index_records(
        snapshot: InventorySnapshot,
    ) -> dict[str, list[InventoryRecord]]:
        index: dict[str, list[InventoryRecord]] = {}
        for record in snapshot.records:
            index.setdefault(record.sku, []).append(record)
        return index

    def _supplier_order_states(
        self, run: RunRecord, run_started_at: datetime
    ) -> dict[str, SupplierOrderState]:
        clock = self.services.clock
        index = self.config.supplier_sku_index()
        states: dict[str, SupplierOrderState] = {}
        for supplier_id, service in sorted(self.services.suppliers.items()):
            error: str | None = None
            snapshot = None
            receipts_by_order: dict[str, tuple[Any, ...]] = {}
            blocking: tuple[str, ...] = ()
            try:
                snapshot = service.get_order_snapshot(self.config.destination_id)
            except ExternalServiceError as exc:
                error = f"{type(exc).__name__}: {exc}"
            if snapshot is not None and error is None:
                if snapshot.supplier_id != supplier_id:
                    error = (
                        f"the snapshot reports supplier {snapshot.supplier_id!r}, "
                        f"expected {supplier_id!r}"
                    )
                elif snapshot.destination_id != self.config.destination_id:
                    error = (
                        f"the snapshot is for destination "
                        f"{snapshot.destination_id!r}, expected "
                        f"{self.config.destination_id!r}"
                    )
                elif not snapshot.complete:
                    error = "the supplier reported an incomplete order snapshot"
                else:
                    error = _snapshot_freshness_problem(
                        snapshot.as_of, run_started_at, f"the {supplier_id} order"
                    )
            if error is None and snapshot is not None:
                open_ids = [
                    order.supplier_order_id
                    for order in snapshot.orders
                    if order.status is not OrderStatus.CANCELLED
                ]
                try:
                    receipts = self.services.inventory.get_receipts(
                        self.config.store_id, supplier_id, open_ids
                    )
                except ExternalServiceError as exc:
                    error = (
                        f"receipts for {supplier_id} orders could not be obtained: {exc}"
                    )
                else:
                    grouped: dict[str, list[Any]] = {}
                    for receipt in receipts:
                        grouped.setdefault(receipt.supplier_order_id, []).append(receipt)
                    receipts_by_order = {
                        order_id: tuple(items) for order_id, items in grouped.items()
                    }
            state = SupplierOrderState(
                supplier_id=supplier_id,
                usable=error is None and snapshot is not None,
                error=error,
                snapshot=snapshot if error is None else None,
                receipts_by_order=receipts_by_order,
            )
            if state.usable:
                blocking = tuple(
                    unmapped_open_orders(
                        state, index.get(supplier_id, {}), store_id=self.config.store_id
                    )
                )
                state = SupplierOrderState(
                    supplier_id=state.supplier_id,
                    usable=True,
                    error=None,
                    snapshot=state.snapshot,
                    receipts_by_order=state.receipts_by_order,
                    blocking_problems=blocking,
                )
                for order in state.orders:
                    self.journal.record_supplier_order(
                        order.with_store_sku(
                            index.get(supplier_id, {}).get(order.supplier_sku)
                        ),
                        observed_at=clock.now(),
                        source="ORDER_SNAPSHOT",
                    )
            else:
                self.journal.add_run_event(
                    run.run_id,
                    clock.now(),
                    "SUPPLIER_ORDER_STATE",
                    f"{supplier_id}: order state is unusable ({error})",
                    {"supplier_id": supplier_id, "error": error},
                )
            for problem in blocking:
                self.journal.add_run_event(
                    run.run_id,
                    clock.now(),
                    "UNMAPPED_ORDER",
                    problem,
                    {"supplier_id": supplier_id},
                )
            states[supplier_id] = state
        return states

    # -- per-SKU processing ----------------------------------------------

    def _process_sku(
        self,
        *,
        run: RunRecord,
        run_started_at: datetime,
        run_date: date,
        sku_config: SkuConfig,
        snapshot: InventorySnapshot,
        records_by_sku: Mapping[str, Sequence[InventoryRecord]],
        supplier_states: Mapping[str, SupplierOrderState],
        blocked_skus: frozenset[str],
    ) -> SkuResult:
        sku = sku_config.sku
        detail: dict[str, Any] = {
            "sku": sku,
            "display_name": sku_config.display_name,
            "run_business_date": run_date.isoformat(),
            "limits": {
                "hard_max": sku_config.hard_max,
                "safety_days": sku_config.safety_days,
                "max_lead_time_days": sku_config.max_lead_time_days,
                "max_unit_price_usd": str(sku_config.max_unit_price_usd),
                "autonomous_order_limit_usd": str(
                    sku_config.autonomous_order_limit_usd
                ),
            },
            "approved_suppliers": {
                supplier_id: sku_config.supplier_mappings[supplier_id]
                for supplier_id in sku_config.approved_suppliers
            },
            "inventory_revision_id": snapshot.revision_id,
        }

        if sku in blocked_skus:
            attempts = [
                attempt
                for attempt in self.journal.unresolved_attempts()
                if attempt.sku == sku
            ]
            detail["blocking_attempts"] = [
                {
                    "attempt_id": attempt.attempt_id,
                    "supplier_id": attempt.supplier_id,
                    "idempotency_key": attempt.idempotency_key,
                    "state": attempt.state.value,
                    "reason": attempt.reason,
                }
                for attempt in attempts
            ]
            return SkuResult(
                sku,
                DecisionOutcome.BLOCKED_UNKNOWN_ATTEMPT,
                "an earlier purchase attempt for this SKU has an unresolved outcome; "
                "no new order may be placed until it is reconciled",
                detail,
            )

        record, problem = self._inventory_record(sku_config, snapshot, records_by_sku)
        if problem is not None:
            return SkuResult(sku, DecisionOutcome.DATA_ERROR, problem, detail)
        assert record is not None
        detail["on_hand"] = record.on_hand

        outstanding = compute_outstanding(
            store_id=self.config.store_id,
            destination_id=self.config.destination_id,
            sku_config=sku_config,
            supplier_states=supplier_states,
        )
        detail["outstanding_quantity"] = outstanding.quantity
        detail["outstanding_contributions"] = [
            item.as_dict() for item in outstanding.contributions
        ]
        if not outstanding.usable:
            detail["outstanding_problems"] = list(outstanding.problems)
            return SkuResult(
                sku,
                DecisionOutcome.DATA_ERROR,
                "outstanding quantity cannot be established: "
                + "; ".join(outstanding.problems),
                detail,
            )

        position = record.on_hand + outstanding.quantity
        detail["inventory_position"] = position
        if position > sku_config.hard_max:
            return SkuResult(
                sku,
                DecisionOutcome.ESCALATION_REQUIRED,
                f"on-hand {record.on_hand} plus outstanding {outstanding.quantity} "
                f"already exceeds hard_max {sku_config.hard_max}; no offer was "
                "requested and no order may be placed",
                detail,
            )

        window = history_window(run_date)
        sales_by_date, sales_problem = self._sales(sku_config, window)
        if sales_problem is not None:
            return SkuResult(sku, DecisionOutcome.DATA_ERROR, sales_problem, detail)

        horizon_end = run_date + timedelta(
            days=sku_config.max_lead_time_days + sku_config.safety_days
        )
        labels, calendar_problem = self._calendar(window[0], horizon_end)
        if calendar_problem is not None:
            return SkuResult(sku, DecisionOutcome.DATA_ERROR, calendar_problem, detail)

        try:
            forecast = compute_base(
                window,
                sales_by_date,
                labels,
                self.config.calendar_multipliers,
                self.config.alpha,
            )
        except ForecastInputError as exc:
            return SkuResult(
                sku, DecisionOutcome.DATA_ERROR, f"forecast inputs are unusable: {exc}", detail
            )

        detail["forecast"] = self._forecast_detail(forecast, run_date, horizon_end, labels)

        return self._decide(
            run=run,
            run_started_at=run_started_at,
            run_date=run_date,
            sku_config=sku_config,
            on_hand=record.on_hand,
            outstanding=outstanding,
            forecast=forecast,
            labels=labels,
            detail=detail,
        )

    def _inventory_record(
        self,
        sku_config: SkuConfig,
        snapshot: InventorySnapshot,
        records_by_sku: Mapping[str, Sequence[InventoryRecord]],
    ) -> tuple[InventoryRecord | None, str | None]:
        sku = sku_config.sku
        malformed = [item for item in snapshot.malformed if item.sku == sku]
        if malformed:
            return None, (
                "the Inventory Ledger record is malformed: "
                + "; ".join(item.problem for item in malformed)
            )
        records = list(records_by_sku.get(sku, ()))
        if not records:
            return None, (
                "the Inventory Ledger returned no record for this SKU; a missing "
                "record is not a zero quantity"
            )
        if len(records) > 1:
            return None, (
                f"the Inventory Ledger returned {len(records)} records for this SKU"
            )
        record = records[0]
        if not record.active:
            return None, "the SKU is not active in the Inventory Ledger"
        if record.base_unit != BASE_UNIT:
            return None, (
                f"the Inventory Ledger reports base unit {record.base_unit!r}, "
                f"expected {BASE_UNIT!r}"
            )
        if record.on_hand < 0:
            return None, f"on-hand quantity {record.on_hand} is negative"
        return record, None

    def _sales(
        self, sku_config: SkuConfig, window: Sequence[date]
    ) -> tuple[dict[date, int], str | None]:
        start, end = window[0], window[-1]
        try:
            records = self.services.sales.get_daily_sales(
                self.config.store_id, sku_config.sku, start, end
            )
        except ExternalServiceError as exc:
            return {}, f"POS sales history is unusable: {exc}"
        by_date: dict[date, int] = {}
        problems: list[str] = []
        for item in records:
            if item.store_id != self.config.store_id:
                problems.append(
                    f"a sales record belongs to store {item.store_id!r}"
                )
                continue
            if item.sku != sku_config.sku:
                problems.append(f"a sales record is for SKU {item.sku!r}")
                continue
            if not (start <= item.business_date <= end):
                problems.append(
                    f"a sales record for {item.business_date} is outside the "
                    f"requested window {start}..{end}"
                )
                continue
            if item.business_date in by_date:
                problems.append(f"duplicate sales records for {item.business_date}")
                continue
            if item.units_sold < 0:
                problems.append(
                    f"units_sold {item.units_sold} for {item.business_date} is negative"
                )
                continue
            by_date[item.business_date] = item.units_sold
        missing = [day for day in window if day not in by_date]
        if missing:
            shown = ", ".join(day.isoformat() for day in missing[:5])
            more = "" if len(missing) <= 5 else f" (+{len(missing) - 5} more)"
            problems.append(
                f"{len(missing)} of the 28 required sales observations are missing: "
                f"{shown}{more}; a missing date is unknown, not zero"
            )
        if problems:
            return {}, "POS sales history is unusable: " + "; ".join(problems)
        return by_date, None

    def _calendar(
        self, start: date, end: date
    ) -> tuple[dict[date, CalendarLabel], str | None]:
        try:
            records = self.services.calendar.get_days(
                self.config.store_id, start, end
            )
        except ExternalServiceError as exc:
            return {}, f"calendar data is unusable: {exc}"
        labels: dict[date, CalendarLabel] = {}
        problems: list[str] = []
        for item in records:
            if item.store_id != self.config.store_id:
                problems.append(
                    f"a calendar record belongs to store {item.store_id!r}"
                )
                continue
            if not (start <= item.day <= end):
                continue
            if item.day in labels:
                problems.append(f"duplicate calendar records for {item.day}")
                continue
            labels[item.day] = item.label
        missing = [day for day in date_range(start, end) if day not in labels]
        if missing:
            shown = ", ".join(day.isoformat() for day in missing[:5])
            more = "" if len(missing) <= 5 else f" (+{len(missing) - 5} more)"
            problems.append(f"calendar labels are missing for {shown}{more}")
        if problems:
            return {}, "calendar data is unusable: " + "; ".join(problems)
        return labels, None

    def _forecast_detail(
        self,
        forecast: BaseForecast,
        run_date: date,
        horizon_end: date,
        labels: Mapping[date, CalendarLabel],
    ) -> dict[str, Any]:
        return {
            "alpha": str(self.config.alpha),
            "window_start": forecast.window_start.isoformat(),
            "window_end": forecast.window_end.isoformat(),
            "base_daily_demand": str(forecast.base),
            "history": [
                {
                    "date": point.day.isoformat(),
                    "units_sold": point.units_sold,
                    "label": point.label.value,
                    "multiplier": str(point.multiplier),
                    "normalized": str(point.normalized),
                }
                for point in forecast.points
            ],
            "future_multipliers": [
                {
                    "date": day.isoformat(),
                    "label": labels[day].value,
                    "multiplier": str(self.config.multiplier(labels[day])),
                }
                for day in date_range(run_date, horizon_end)
                if day in labels
            ],
        }

    # -- candidates, ranking, execution ----------------------------------

    def _decide(
        self,
        *,
        run: RunRecord,
        run_started_at: datetime,
        run_date: date,
        sku_config: SkuConfig,
        on_hand: int,
        outstanding: OutstandingResult,
        forecast: BaseForecast,
        labels: Mapping[date, CalendarLabel],
        detail: dict[str, Any],
    ) -> SkuResult:
        sku = sku_config.sku
        exclusions: list[OfferExclusion] = []
        candidates: list[Candidate] = []
        zero_requirement: list[str] = []
        lead_time_escalations: list[dict[str, Any]] = []
        arriving = outstanding.arriving()

        for supplier_id in sku_config.approved_suppliers:
            supplier_sku = sku_config.supplier_mappings[supplier_id]
            service = self.services.suppliers.get(supplier_id)
            if service is None:
                exclusions.append(
                    OfferExclusion(
                        supplier_id, supplier_sku, "NOT_CONFIGURED",
                        "the supplier is not constructed in this process",
                    )
                )
                continue
            try:
                offer = service.get_offer(supplier_sku, self.config.destination_id)
            except ExternalServiceError as exc:
                exclusions.append(
                    OfferExclusion(
                        supplier_id, supplier_sku, "OFFER_UNAVAILABLE",
                        f"{type(exc).__name__}: {exc}",
                    )
                )
                continue
            if isinstance(offer, NotOffered):
                exclusions.append(
                    OfferExclusion(
                        supplier_id, supplier_sku, "NOT_OFFERED",
                        "the supplier does not offer this supplier SKU for the "
                        "configured destination",
                    )
                )
                continue
            if not isinstance(offer, Offer):
                exclusions.append(
                    OfferExclusion(
                        supplier_id, supplier_sku, "MALFORMED_OFFER",
                        f"the supplier returned {type(offer).__name__}",
                    )
                )
                continue
            problems = check_offer_usable(
                offer,
                supplier_id=supplier_id,
                supplier_sku=supplier_sku,
                destination_id=self.config.destination_id,
                run_started_at=run_started_at,
            )
            if problems:
                exclusions.append(
                    OfferExclusion(
                        supplier_id, supplier_sku, "OFFER_UNUSABLE", "; ".join(problems)
                    )
                )
                continue
            if offer.lead_time_days > sku_config.max_lead_time_days:
                lead_time_escalations.append(
                    {
                        "supplier_id": supplier_id,
                        "supplier_sku": supplier_sku,
                        "lead_time_days": offer.lead_time_days,
                        "max_lead_time_days": sku_config.max_lead_time_days,
                        "reason": (
                            f"lead time {offer.lead_time_days} days exceeds the "
                            f"configured maximum {sku_config.max_lead_time_days}"
                        ),
                    }
                )
                continue

            plan = build_plan(
                run_date=run_date,
                base=forecast.base,
                labels_by_date=labels,
                multipliers=self.config.calendar_multipliers,
                lead_time_days=offer.lead_time_days,
                safety_days=sku_config.safety_days,
                on_hand=on_hand,
                outstanding_quantity=outstanding.quantity,
                pack_size=offer.pack_size,
            )
            if plan.raw_requirement == 0:
                zero_requirement.append(supplier_id)
                exclusions.append(
                    OfferExclusion(
                        supplier_id, supplier_sku, "NO_REQUIREMENT",
                        f"inventory position {plan.inventory_position} already meets "
                        f"the {plan.coverage_days}-day target {plan.target_inventory}",
                    )
                )
                continue
            if plan.order_quantity > offer.available_quantity:
                exclusions.append(
                    OfferExclusion(
                        supplier_id, supplier_sku, "INSUFFICIENT_AVAILABILITY",
                        f"the rounded quantity {plan.order_quantity} exceeds the "
                        f"available {offer.available_quantity}; version 1 does not "
                        "split or reduce an order",
                    )
                )
                continue
            total_cost = offer.unit_price * plan.order_quantity
            projection = project_stockout(
                run_date=run_date,
                lead_time_days=offer.lead_time_days,
                base=forecast.base,
                labels_by_date=labels,
                multipliers=self.config.calendar_multipliers,
                on_hand=on_hand,
                arriving_before=arriving,
            )
            candidates.append(
                Candidate(
                    supplier_id=supplier_id,
                    supplier_sku=supplier_sku,
                    offer=offer,
                    plan=plan,
                    total_cost=total_cost,
                    limit_failures=tuple(
                        owner_limit_failures(
                            sku_config=sku_config,
                            offer=offer,
                            plan=plan,
                            total_cost=total_cost,
                        )
                    ),
                    projection=projection,
                )
            )

        ranked = rank_candidates(candidates)
        detail["offer_exclusions"] = [item.as_dict() for item in exclusions]
        detail["lead_time_escalations"] = lead_time_escalations
        detail["candidates"] = [item.as_dict() for item in candidates]
        detail["ranking"] = [
            {"position": position, "supplier_id": item.supplier_id}
            for position, item in enumerate(ranked, start=1)
        ]

        if ranked:
            return self._execute(
                run=run,
                sku_config=sku_config,
                selected=ranked[0],
                detail=detail,
            )
        limit_failing = [item for item in candidates if item.limit_failures]
        if limit_failing:
            reasons = "; ".join(
                f"{item.supplier_id}: " + "; ".join(item.limit_failures)
                for item in limit_failing
            )
            return SkuResult(
                sku,
                DecisionOutcome.ESCALATION_REQUIRED,
                f"an otherwise usable candidate exceeds an owner purchasing limit; "
                f"human review is required ({reasons})",
                detail,
            )
        if zero_requirement:
            return SkuResult(
                sku,
                DecisionOutcome.NO_ORDER_NEEDED,
                "the approved replenishment calculation produced no requirement for "
                "any usable offer",
                detail,
            )
        if lead_time_escalations:
            reasons = "; ".join(
                f"{item['supplier_id']}: {item['reason']}"
                for item in lead_time_escalations
            )
            return SkuResult(
                sku,
                DecisionOutcome.ESCALATION_REQUIRED,
                f"every usable offer exceeds the configured maximum lead time "
                f"({reasons})",
                detail,
            )
        return SkuResult(
            sku,
            DecisionOutcome.NO_FEASIBLE_SUPPLIER,
            "no approved supplier produced a fully available, usable candidate: "
            + ("; ".join(f"{item.supplier_id}: {item.reason}" for item in exclusions)
               or "no approved supplier was evaluated"),
            detail,
        )

    def _execute(
        self,
        *,
        run: RunRecord,
        sku_config: SkuConfig,
        selected: Candidate,
        detail: dict[str, Any],
    ) -> SkuResult:
        clock = self.services.clock
        sku = sku_config.sku
        key = idempotency_key(run.run_id, sku, selected.supplier_id)
        detail["selected"] = {
            "supplier_id": selected.supplier_id,
            "supplier_sku": selected.supplier_sku,
            "quantity": selected.plan.order_quantity,
            "expected_unit_price_usd": money_str(selected.offer.unit_price),
            "total_cost_usd": money_str(selected.total_cost),
            "destination_id": self.config.destination_id,
            "idempotency_key": key,
        }
        try:
            attempt = self.journal.commit_attempt(
                run_id=run.run_id,
                sku=sku,
                supplier_id=selected.supplier_id,
                supplier_sku=selected.supplier_sku,
                destination_id=self.config.destination_id,
                quantity=selected.plan.order_quantity,
                expected_unit_price=selected.offer.unit_price,
                total_cost=selected.total_cost,
                idempotency_key=key,
                created_at=clock.now(),
            )
        except Exception as exc:  # the intention is not durable; do not call out
            detail["attempt_commit_error"] = str(exc)
            return SkuResult(
                sku,
                DecisionOutcome.DATA_ERROR,
                "the purchase intention could not be committed durably, so the "
                f"supplier was not called: {exc}",
                detail,
            )

        detail["attempt_id"] = attempt.attempt_id
        result = place_purchase_order(
            journal=self.journal,
            clock=clock,
            supplier=self.services.suppliers[selected.supplier_id],
            attempt=attempt,
        )
        detail["attempt_state"] = result.state.value
        detail["attempt_reason"] = result.reason
        if result.order is not None:
            detail["supplier_order"] = {
                "supplier_order_id": result.order.supplier_order_id,
                "status": result.order.status.value,
                "promised_delivery_date": (
                    result.order.promised_delivery_date.isoformat()
                    if result.order.promised_delivery_date
                    else None
                ),
            }
        if result.state is AttemptState.ACCEPTED:
            return SkuResult(sku, DecisionOutcome.ORDER_ACCEPTED, result.reason, detail)
        if result.state is AttemptState.REJECTED:
            detail["rejection_code"] = result.rejection_code
            return SkuResult(
                sku, DecisionOutcome.SUPPLIER_REJECTED, result.reason, detail
            )
        return SkuResult(
            sku, DecisionOutcome.ORDER_OUTCOME_UNKNOWN, result.reason, detail
        )
