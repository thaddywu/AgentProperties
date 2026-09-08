"""Section 16.14: the committed example world, in which normal orders,
no-order decisions, escalation, a supplier failure, a rejection, and an unknown
outcome all occur in one run."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from replenishment import reporting
from replenishment.app import Application
from replenishment.cli import main
from replenishment.domain import AttemptState, DecisionOutcome, RunStatus, TriggerKind

from . import support

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture
def example(tmp_path: Path) -> Path:
    """The committed example configuration, pointed at a temporary copy."""
    world = tmp_path / "world"
    shutil.copytree(FIXTURES / "world", world)
    document = json.loads((FIXTURES / "config.example.json").read_text())
    document["database_path"] = str(tmp_path / "state" / "app.sqlite3")
    for slot in ("inventory_ledger", "sales_history", "calendar"):
        document["adapters"][slot]["options"]["world_dir"] = str(world)
    for supplier in document["suppliers"]:
        supplier["options"]["world_dir"] = str(world)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(document, indent=2))
    return path


def outcomes(results):
    return {item.sku: item.outcome for item in results}


def world_of(config_path: Path) -> support.World:
    document = json.loads(config_path.read_text())
    return support.World(
        Path(document["adapters"]["inventory_ledger"]["options"]["world_dir"])
    )


def test_the_example_world_exercises_every_documented_outcome(example: Path):
    world = world_of(example)
    inventory_before = hashlib.sha256(
        (world.root / "inventory.json").read_bytes()
    ).hexdigest()

    with Application.open(example) as app:
        outcome = app.engine.execute(TriggerKind.MANUAL)

    assert outcome.run.status is RunStatus.COMPLETED_WITH_EXCEPTIONS
    assert outcomes(outcome.results) == {
        "SKU-CANDY-BAR-45G": DecisionOutcome.NO_ORDER_NEEDED,
        "SKU-CHIPS-BBQ-150G": DecisionOutcome.ORDER_ACCEPTED,
        "SKU-COFFEE-CUP-12OZ": DecisionOutcome.ORDER_ACCEPTED,
        "SKU-ENERGY-16OZ": DecisionOutcome.ESCALATION_REQUIRED,
        "SKU-GUM-PACK-10": DecisionOutcome.SUPPLIER_REJECTED,
        "SKU-JUICE-1L": DecisionOutcome.ESCALATION_REQUIRED,
        "SKU-NUTS-MIX-90G": DecisionOutcome.ORDER_OUTCOME_UNKNOWN,
        "SKU-SODA-CAN-330": DecisionOutcome.NO_ORDER_NEEDED,
        "SKU-WATER-500ML": DecisionOutcome.NO_ORDER_NEEDED,
    }

    by_sku = {item.sku: item for item in outcome.results}

    # An external, manually created order counts toward inventory on the way.
    soda = by_sku["SKU-SODA-CAN-330"].detail
    assert soda["outstanding_quantity"] == 240
    assert soda["outstanding_contributions"][0]["supplier_order_id"] == "A-PO-0003"

    # A DELIVERED order still counts until the ledger receipt is posted.
    candy = by_sku["SKU-CANDY-BAR-45G"].detail
    assert candy["outstanding_contributions"][0]["status"] == "DELIVERED"
    assert candy["outstanding_contributions"][0]["contributes"] == 108

    # A DELIVERED order with a matching receipt counts as zero.
    water = by_sku["SKU-WATER-500ML"].detail
    assert water["outstanding_contributions"][0]["contributes"] == 0
    assert water["outstanding_contributions"][0]["receipt_id"] == "RCPT-000001"

    # Supplier A is unavailable for coffee; supplier B is still usable.
    coffee = by_sku["SKU-COFFEE-CUP-12OZ"].detail
    assert coffee["offer_exclusions"][0]["supplier_id"] == "SUPPLIER_A"
    assert coffee["offer_exclusions"][0]["kind"] == "OFFER_UNAVAILABLE"
    assert coffee["selected"]["supplier_id"] == "SUPPLIER_B"

    # Escalations carry the failing owner limit and placed no order.
    assert "spend limit" in by_sku["SKU-ENERGY-16OZ"].reason
    assert "hard_max" in by_sku["SKU-JUICE-1L"].reason

    # Exactly one raw placement call per attempted purchase, and none for the
    # escalated or no-order SKUs.
    placed_a = [
        call["arguments"]["supplier_sku"]
        for call in world.raw_calls("SUPPLIER_A", method="place_order")
    ]
    placed_b = [
        call["arguments"]["supplier_sku"]
        for call in world.raw_calls("SUPPLIER_B", method="place_order")
    ]
    assert placed_a == ["A-GUM-PACK-10", "A-NUTS-MIX-90G"]
    assert placed_b == ["B-CHIPS-BBQ-150", "B-COFFEE-12OZ-CUP"]

    # Authoritative supplier world state.
    a_orders = {item["supplier_order_id"] for item in world.supplier_orders("SUPPLIER_A")}
    assert a_orders == {"A-PO-0003", "A-PO-0004"}  # the pre-existing one and the lost one
    b_orders = {item["supplier_order_id"] for item in world.supplier_orders("SUPPLIER_B")}
    assert b_orders == {"B-PO-0007", "B-PO-0008", "B-PO-0009", "B-PO-0010"}

    # The Inventory Ledger was never written to.
    assert (
        hashlib.sha256((world.root / "inventory.json").read_bytes()).hexdigest()
        == inventory_before
    )

    with Application.open(example, recover=False) as app:
        attempts = {item.sku: item for item in app.journal.list_attempts()}
        assert attempts["SKU-GUM-PACK-10"].state is AttemptState.REJECTED
        assert attempts["SKU-NUTS-MIX-90G"].state is AttemptState.OUTCOME_UNKNOWN
        assert attempts["SKU-CHIPS-BBQ-150G"].state is AttemptState.ACCEPTED
        assert set(attempts) == {
            "SKU-CHIPS-BBQ-150G",
            "SKU-COFFEE-CUP-12OZ",
            "SKU-GUM-PACK-10",
            "SKU-NUTS-MIX-90G",
        }
        # Every enabled SKU has an operator-visible outcome.
        decisions = app.journal.decisions_for_run(outcome.run.run_id)
        assert len(decisions) == len(app.config.skus)


def test_the_second_run_reconciles_the_unknown_outcome(example: Path):
    with Application.open(example) as app:
        app.engine.execute(TriggerKind.MANUAL)
    with Application.open(example) as app:
        second = app.engine.execute(TriggerKind.MANUAL)
        attempt = next(
            item
            for item in app.journal.list_attempts()
            if item.sku == "SKU-NUTS-MIX-90G"
        )
        assert attempt.state is AttemptState.ACCEPTED
        assert attempt.supplier_order_id == "A-PO-0004"
        events = app.journal.reconciliation_events(attempt.attempt_id)
        assert [item.lookup_outcome for item in events] == ["FOUND"]

    by_sku = {item.sku: item for item in second.results}
    # The recovered order covers the requirement, so no replacement is created.
    assert by_sku["SKU-NUTS-MIX-90G"].outcome is DecisionOutcome.NO_ORDER_NEEDED
    # The earlier rejection did not stop a later run from ordering the SKU.
    assert by_sku["SKU-GUM-PACK-10"].outcome is DecisionOutcome.ORDER_ACCEPTED

    world = world_of(example)
    nuts_orders = [
        item
        for item in world.supplier_orders("SUPPLIER_A")
        if item["supplier_sku"] == "A-NUTS-MIX-90G"
    ]
    assert len(nuts_orders) == 1  # never duplicated


def test_reports_render_in_text_and_json(example: Path):
    with Application.open(example) as app:
        run_id = app.engine.execute(TriggerKind.MANUAL).run.run_id
    with Application.open(example, recover=False) as app:
        status = reporting.status_report(app)
        assert reporting.render_status(status)
        assert status["last_completed_run"]["run_id"] == run_id

        detail = reporting.run_detail_report(app, run_id)
        assert reporting.render_run_detail(detail)
        assert json.dumps(detail)  # JSON-serializable

        decisions = reporting.decisions_report(app, run_id)
        text = reporting.render_decisions(decisions)
        assert "SKU-JUICE-1L" in text and "ESCALATION_REQUIRED" in text
        # An escalation is never presented as an executed purchase.
        juice = next(
            item for item in decisions["decisions"] if item["sku"] == "SKU-JUICE-1L"
        )
        assert "selected" not in juice["detail"]
        assert "supplier_order" not in juice["detail"]

        attempts = reporting.attempts_report(app)
        assert any(
            item["state"] == "OUTCOME_UNKNOWN" for item in attempts["attempts"]
        )
        assert reporting.render_attempts(attempts)

        orders = reporting.orders_report(app)
        assert reporting.render_orders(orders)
        calls = reporting.supplier_calls_report(app)
        assert reporting.render_supplier_calls(calls)
        assert any(
            call["method"] == "place_order" for call in calls["raw_supplier_calls"]
        )


def test_the_cli_runs_and_inspects(example: Path, capsys):
    assert main(["--config", str(example), "init-db"]) == 0
    capsys.readouterr()
    assert main(["--config", str(example), "run", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["run"]["status"] == "COMPLETED_WITH_EXCEPTIONS"

    assert main(["--config", str(example), "status"]) == 0
    assert "Replenishment status" in capsys.readouterr().out

    assert main(["--config", str(example), "runs", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["runs"][0]["run_id"] == "RUN-000001"

    assert main(["--config", str(example), "decisions", "--sku", "SKU-GUM-PACK-10"]) == 0
    assert "SUPPLIER_REJECTED" in capsys.readouterr().out

    assert main(["--config", str(example), "attempts", "--state", "OUTCOME_UNKNOWN"]) == 0
    assert "SKU-NUTS-MIX-90G" in capsys.readouterr().out

    assert main(["--config", str(example), "orders", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["recorded_supplier_orders"]

    assert main(["--config", str(example), "supplier-calls", "--supplier", "SUPPLIER_A"]) == 0
    assert "place_order" in capsys.readouterr().out

    assert main(["--config", str(example), "scheduler", "--max-cycles", "1"]) == 0
    assert "scheduler started" in capsys.readouterr().out


def test_the_cli_rejects_an_invalid_configuration(tmp_path: Path, capsys):
    broken = tmp_path / "broken.json"
    broken.write_text("{}")
    assert main(["--config", str(broken), "status"]) == 2
    assert "invalid configuration" in capsys.readouterr().err
