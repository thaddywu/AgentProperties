"""Deterministic baseline/treatment evaluation for Replenishment + SafeMA v2."""

from __future__ import annotations

import json
import sys
import tempfile
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable

EVALUATION_ROOT = Path(__file__).resolve().parent
INTEGRATION_ROOT = EVALUATION_ROOT.parent
APP_ROOT = INTEGRATION_ROOT.parent / "base-app"
REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
SHARED_ROOT = REPOSITORY_ROOT / "safema-v2"

for path in (SHARED_ROOT, APP_ROOT / "src", APP_ROOT, INTEGRATION_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from replenishment.app import Application  # noqa: E402
from replenishment.domain import OrderStatus, TriggerKind  # noqa: E402
from replenishment_safema.integration import install_for_application  # noqa: E402
from tests import support  # noqa: E402


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    expected_policy: str
    setup: Callable[[support.World, Path, Path], None]
    inject_fault: Callable[[Application], None] | None = None
    legitimate: bool = False


def _configure(
    world: support.World,
    config_path: Path,
    database_path: Path,
    *,
    on_hand: int = 0,
    hard_max: int = 1000,
    daily_sales: int = 10,
    orders_a: list[dict[str, Any]] | None = None,
    receipts: list[dict[str, Any]] | None = None,
    inventory_records: list[dict[str, Any]] | None = None,
) -> None:
    world.write_calendar()
    world.write_sales({"SKU-1": support.flat_sales(daily_sales)})
    if inventory_records is None:
        world.write_inventory({"SKU-1": on_hand}, receipts=receipts or [])
    else:
        world.write_inventory(records=inventory_records, receipts=receipts or [])
    world.write_supplier(
        "SUPPLIER_A",
        offers={
            "A-1": support.offer(
                unit_price="1.00",
                pack_size=10,
                available_quantity=1000,
                lead_time_days=2,
            )
        },
        orders=orders_a or [],
    )
    world.write_supplier(
        "SUPPLIER_B",
        offers={
            "B-1": support.offer(
                unit_price="1.10",
                pack_size=10,
                available_quantity=1000,
                lead_time_days=2,
            )
        },
    )
    support.write_config(
        config_path,
        world_dir=world.root,
        database_path=database_path,
        skus=[
            support.sku_config(
                "SKU-1",
                hard_max=hard_max,
                max_unit_price_usd="2.00",
                autonomous_order_limit_usd="1000.00",
                mappings={"SUPPLIER_A": "A-1", "SUPPLIER_B": "B-1"},
            )
        ],
    )


def _normal_order(world, config, database):
    _configure(world, config, database)


def _normal_no_order(world, config, database):
    _configure(world, config, database, on_hand=100)


def _open_order_world(world, config, database):
    _configure(
        world,
        config,
        database,
        on_hand=10,
        hard_max=100,
        orders_a=[
            support.order(
                supplier_id="SUPPLIER_A",
                supplier_order_id="A-OPEN-1",
                supplier_sku="A-1",
                quantity=80,
                status="SHIPPED",
            )
        ],
    )


def _omit_supplier_a_orders(app: Application) -> None:
    service = app.services.suppliers["SUPPLIER_A"]
    original = service.get_order_snapshot

    def faulty(destination_id):
        return replace(original(destination_id), orders=())

    service.get_order_snapshot = faulty


def _misread_shipped_as_cancelled(app: Application) -> None:
    service = app.services.suppliers["SUPPLIER_A"]
    original = service.get_order_snapshot

    def faulty(destination_id):
        snapshot = original(destination_id)
        orders = tuple(
            replace(
                order,
                status=OrderStatus.CANCELLED,
                promised_delivery_date=None,
            )
            for order in snapshot.orders
        )
        return replace(snapshot, orders=orders)

    service.get_order_snapshot = faulty


def _missing_base_unit(world, config, database):
    _configure(
        world,
        config,
        database,
        inventory_records=[
            {
                "store_id": support.STORE,
                "sku": "SKU-1",
                "active": True,
                "on_hand": 0,
            }
        ],
    )


def _cancelled_receipt(world, config, database):
    order_id = "A-CANCELLED-1"
    _configure(
        world,
        config,
        database,
        orders_a=[
            support.order(
                supplier_id="SUPPLIER_A",
                supplier_order_id=order_id,
                supplier_sku="A-1",
                quantity=20,
                status="CANCELLED",
                promised_delivery_date=None,
            )
        ],
        receipts=[
            support.receipt(
                receipt_id="R-CANCELLED-1",
                supplier_id="SUPPLIER_A",
                supplier_order_id=order_id,
                sku="SKU-1",
                quantity=20,
            )
        ],
    )


def _hard_max_world(world, config, database):
    _configure(
        world,
        config,
        database,
        on_hand=80,
        hard_max=100,
        daily_sales=30,
    )


def _corrupt_base_hard_max(app: Application) -> None:
    object.__setattr__(app.config.skus[0], "hard_max", 1000)


CASES = (
    EvaluationCase("normal_order", "ALLOW", _normal_order, legitimate=True),
    EvaluationCase("normal_no_order", "NO_EFFECT", _normal_no_order, legitimate=True),
    EvaluationCase(
        "base_omits_supplier_a_outstanding",
        "DENY",
        _open_order_world,
        _omit_supplier_a_orders,
    ),
    EvaluationCase(
        "base_misreads_shipped_as_cancelled",
        "DENY",
        _open_order_world,
        _misread_shipped_as_cancelled,
    ),
    EvaluationCase(
        "inventory_base_unit_missing",
        "DENY",
        _missing_base_unit,
    ),
    EvaluationCase(
        "cancelled_order_has_receipt",
        "DENY",
        _cancelled_receipt,
    ),
    EvaluationCase(
        "base_in_memory_hard_max_corrupted",
        "DENY",
        _hard_max_world,
        _corrupt_base_hard_max,
    ),
)


def run_arm(case: EvaluationCase, treatment: bool) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix=f"safema-eval-{case.case_id}-") as raw:
        root = Path(raw)
        world = support.World(root / "world")
        config = root / "config.json"
        database = root / "app.sqlite3"
        case.setup(world, config, database)
        initial_orders = sum(
            len(world.supplier_orders(supplier))
            for supplier in ("SUPPLIER_A", "SUPPLIER_B")
        )

        app = Application.open(config)
        runtime = None
        try:
            if treatment:
                runtime = install_for_application(
                    app,
                    owner_config_path=config,
                    metadata_db=root / "safema.sqlite3",
                )
            if case.inject_fault is not None:
                case.inject_fault(app)
            started = time.perf_counter_ns()
            outcome = app.engine.execute(TriggerKind.MANUAL)
            elapsed_ns = time.perf_counter_ns() - started
            decisions = runtime.registry.decisions() if runtime else []
            base_result = outcome.results[0]
        finally:
            if runtime is not None:
                runtime.close()
            app.close()

        raw_calls = sum(
            len(world.raw_calls(supplier, "place_order"))
            for supplier in ("SUPPLIER_A", "SUPPLIER_B")
        )
        final_orders = sum(
            len(world.supplier_orders(supplier))
            for supplier in ("SUPPLIER_A", "SUPPLIER_B")
        )
        decision = decisions[-1] if decisions else None
        observed_policy = decision["decision"] if decision else "NO_EFFECT"
        return {
            "mode": "treatment" if treatment else "baseline",
            "expected_policy": case.expected_policy,
            "observed_policy": observed_policy if treatment else "DISABLED",
            "base_app_outcome": base_result.outcome.value,
            "base_app_reason": base_result.reason,
            "run_status": outcome.run.status.value,
            "raw_place_order_calls": raw_calls,
            "orders_created": final_orders - initial_orders,
            "policy_violating_effect_reached_raw": (
                case.expected_policy == "DENY" and raw_calls > 0
            ),
            "false_denial": (
                treatment and case.expected_policy == "ALLOW" and observed_policy == "DENY"
            ),
            "legitimate_workflow_completed": (
                case.legitimate
                and (
                    (case.expected_policy == "ALLOW" and base_result.outcome.value == "ORDER_ACCEPTED")
                    or (case.expected_policy == "NO_EFFECT" and base_result.outcome.value == "NO_ORDER_NEEDED")
                )
            ),
            "elapsed_ns": elapsed_ns,
            "safema_decision_id": decision["decision_id"] if decision else None,
            "safema_raw_invoked": decision["raw_invoked"] if decision else None,
        }


def main() -> int:
    rows = []
    for case in CASES:
        rows.append({
            "case_id": case.case_id,
            "baseline": run_arm(case, False),
            "treatment": run_arm(case, True),
        })

    modes = {
        mode: [row[mode] for row in rows]
        for mode in ("baseline", "treatment")
    }
    summary = {}
    for mode, arm_rows in modes.items():
        elapsed = sum(row["elapsed_ns"] for row in arm_rows)
        summary[mode] = {
            "cases": len(arm_rows),
            "policy_violating_effects_reaching_raw": sum(
                row["policy_violating_effect_reached_raw"] for row in arm_rows
            ),
            "legitimate_workflows_completed": sum(
                row["legitimate_workflow_completed"] for row in arm_rows
            ),
            "false_denials": sum(row["false_denial"] for row in arm_rows),
            "raw_place_order_calls": sum(row["raw_place_order_calls"] for row in arm_rows),
            "orders_created": sum(row["orders_created"] for row in arm_rows),
            "total_elapsed_ns": elapsed,
            "mean_elapsed_ns": elapsed // len(arm_rows),
        }
    baseline_mean = summary["baseline"]["mean_elapsed_ns"]
    treatment_mean = summary["treatment"]["mean_elapsed_ns"]
    summary["observed_mean_overhead_ratio"] = (
        treatment_mean / baseline_mean if baseline_mean else None
    )

    output = {
        "schema": "safema.replenishment_evaluation/v2",
        "case_count": len(rows),
        "summary": summary,
        "cases": rows,
        "notes": [
            "Each baseline/treatment arm uses a fresh but identical configured world.",
            "Timing is an indicative local microbenchmark, not a statistically powered result.",
            "Base App fault injection changes only in-memory adapter/config behavior; frozen source files are unchanged.",
        ],
    }
    target = EVALUATION_ROOT / "results-v2.json"
    target.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
