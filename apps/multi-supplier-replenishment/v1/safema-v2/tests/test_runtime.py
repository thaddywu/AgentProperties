from __future__ import annotations

import json
from decimal import Decimal

import pytest

from replenishment.adapters.supplier import LocalSupplierService
from replenishment.domain import OrderAccepted, OrderRejected, TriggerKind
from safema.errors import ModelError
from safema.loader import load_policies

from tests import support


def assert_denied(scenario, runtime, result, *, supplier="SUPPLIER_A"):
    assert isinstance(result, OrderRejected)
    assert result.code == "SAFEMA_POLICY_DENIED"
    assert scenario.world.raw_calls(supplier, "place_order") == []
    decision = runtime.registry.decisions()[-1]
    assert decision["decision"] == "DENY"
    assert decision["raw_invoked"] == 0
    assert not any(
        order.get("idempotency_key") in {"test/one", "unregistered/one"}
        for order in scenario.world.supplier_orders(supplier)
    )


def test_allowed_base_app_workflow_reaches_raw_supplier(safe_scenario):
    app, runtime = safe_scenario.open_safe()
    try:
        outcome = app.engine.execute(TriggerKind.MANUAL)
        assert outcome.results[0].outcome.value == "ORDER_ACCEPTED"
        assert len(safe_scenario.world.raw_calls("SUPPLIER_A", "place_order")) == 1
        assert len(safe_scenario.world.supplier_orders("SUPPLIER_A")) == 1
        decision = runtime.registry.decisions()[-1]
        assert decision["decision"] == "ALLOW"
        assert decision["raw_invoked"] == 1
        observed = json.loads(decision["observability_json"])
        state = observed["replenishment.authoritative_purchase_state.v2"]
        assert state["exposure_after_order"] <= state["hard_max"]
    finally:
        runtime.close()
        app.close()


def test_ceiling_violation_denied_before_raw_api(safe_scenario):
    safe_scenario.configure(hard_max=100, on_hand=70)
    app, runtime = safe_scenario.open_safe()
    try:
        result = safe_scenario.call(app, quantity=40)
        assert_denied(safe_scenario, runtime, result)
        observed = json.loads(runtime.registry.decisions()[-1]["observability_json"])
        state = observed["replenishment.authoritative_purchase_state.v2"]
        assert state["exposure_after_order"] == 110
        assert state["hard_max"] == 100
    finally:
        runtime.close()
        app.close()


def test_unregistered_supplier_instance_denied(safe_scenario):
    app, runtime = safe_scenario.open_safe()
    try:
        unregistered = LocalSupplierService(
            app.services.worlds["SUPPLIER_A"], app.services.clock, "SUPPLIER_A"
        )
        result = unregistered.place_order(
            "A-1", 10, Decimal("1.00"), support.DESTINATION, "unregistered/one"
        )
        assert_denied(safe_scenario, runtime, result)
    finally:
        runtime.close()
        app.close()


def test_wrong_destination_denied(safe_scenario):
    app, runtime = safe_scenario.open_safe()
    try:
        result = safe_scenario.call(app, destination="DEST-ATTACKER")
        assert_denied(safe_scenario, runtime, result)
    finally:
        runtime.close()
        app.close()


@pytest.mark.parametrize("field", ["base_unit", "on_hand"])
def test_missing_authoritative_inventory_state_denied(safe_scenario, field):
    safe_scenario.mutate_json(
        "inventory.json", lambda doc: doc["records"][0].pop(field)
    )
    app, runtime = safe_scenario.open_safe()
    try:
        result = safe_scenario.call(app)
        assert_denied(safe_scenario, runtime, result)
    finally:
        runtime.close()
        app.close()


def test_missing_snapshot_completeness_denied(safe_scenario):
    safe_scenario.mutate_json(
        "supplier_SUPPLIER_A.json", lambda doc: doc.pop("snapshot_complete")
    )
    app, runtime = safe_scenario.open_safe()
    try:
        result = safe_scenario.call(app)
        assert_denied(safe_scenario, runtime, result)
    finally:
        runtime.close()
        app.close()


def test_open_order_is_included_in_ceiling(safe_scenario):
    order = support.order(
        supplier_id="SUPPLIER_A",
        supplier_order_id="A-OPEN",
        supplier_sku="A-1",
        quantity=60,
        status="SHIPPED",
    )
    safe_scenario.configure(hard_max=100, on_hand=30, orders_a=[order])
    app, runtime = safe_scenario.open_safe()
    try:
        result = safe_scenario.call(app, quantity=20)
        assert_denied(safe_scenario, runtime, result)
        observed = json.loads(runtime.registry.decisions()[-1]["observability_json"])
        state = observed["replenishment.authoritative_purchase_state.v2"]
        assert state["outstanding"] == 60
        assert state["exposure_after_order"] == 110
    finally:
        runtime.close()
        app.close()


def test_cancelled_order_contributes_zero(safe_scenario):
    order = support.order(
        supplier_id="SUPPLIER_A",
        supplier_order_id="A-CANCELLED",
        supplier_sku="A-1",
        quantity=60,
        status="CANCELLED",
        promised_delivery_date=None,
    )
    safe_scenario.configure(hard_max=100, on_hand=30, orders_a=[order])
    app, runtime = safe_scenario.open_safe()
    try:
        result = safe_scenario.call(app, quantity=20)
        assert isinstance(result, OrderAccepted)
        decision = runtime.registry.decisions()[-1]
        assert decision["decision"] == "ALLOW"
        assert decision["raw_invoked"] == 1
    finally:
        runtime.close()
        app.close()


def test_cancelled_order_with_receipt_is_denied(safe_scenario):
    order = support.order(
        supplier_id="SUPPLIER_A",
        supplier_order_id="A-CANCELLED",
        supplier_sku="A-1",
        quantity=20,
        status="CANCELLED",
        promised_delivery_date=None,
    )
    receipt = support.receipt(
        receipt_id="R-CANCELLED",
        supplier_id="SUPPLIER_A",
        supplier_order_id="A-CANCELLED",
        sku="SKU-1",
        quantity=20,
    )
    safe_scenario.configure(orders_a=[order], receipts=[receipt])
    app, runtime = safe_scenario.open_safe()
    try:
        result = safe_scenario.call(app)
        assert_denied(safe_scenario, runtime, result)
    finally:
        runtime.close()
        app.close()


@pytest.mark.parametrize("status", ["ACCEPTED", "SHIPPED", "DELIVERED"])
def test_each_open_lifecycle_state_contributes_until_receipt(safe_scenario, status):
    order = support.order(
        supplier_id="SUPPLIER_A",
        supplier_order_id=f"A-{status}",
        supplier_sku="A-1",
        quantity=60,
        status=status,
    )
    safe_scenario.configure(hard_max=100, on_hand=30, orders_a=[order])
    app, runtime = safe_scenario.open_safe()
    try:
        result = safe_scenario.call(app, quantity=20)
        assert_denied(safe_scenario, runtime, result)
    finally:
        runtime.close()
        app.close()


def test_full_receipt_removes_delivered_order_from_outstanding(safe_scenario):
    order = support.order(
        supplier_id="SUPPLIER_A",
        supplier_order_id="A-DELIVERED",
        supplier_sku="A-1",
        quantity=60,
        status="DELIVERED",
    )
    receipt = support.receipt(
        receipt_id="R-DELIVERED",
        supplier_id="SUPPLIER_A",
        supplier_order_id="A-DELIVERED",
        sku="SKU-1",
        quantity=60,
    )
    safe_scenario.configure(
        hard_max=100, on_hand=30, orders_a=[order], receipts=[receipt]
    )
    app, runtime = safe_scenario.open_safe()
    try:
        result = safe_scenario.call(app, quantity=20)
        assert isinstance(result, OrderAccepted)
        observed = json.loads(runtime.registry.decisions()[-1]["observability_json"])
        assert observed["replenishment.authoritative_purchase_state.v2"]["outstanding"] == 0
    finally:
        runtime.close()
        app.close()


@pytest.mark.parametrize(
    "quantity,price",
    [("10", Decimal("1.00")), (True, Decimal("1.00")), (10, "1.00")],
)
def test_malformed_effect_operands_fail_closed(safe_scenario, quantity, price):
    app, runtime = safe_scenario.open_safe()
    try:
        result = safe_scenario.call(app, quantity=quantity, price=price)
        assert_denied(safe_scenario, runtime, result)
    finally:
        runtime.close()
        app.close()


def test_supplier_sku_operand_mismatch_denied(safe_scenario):
    app, runtime = safe_scenario.open_safe()
    try:
        result = safe_scenario.call(app, supplier_sku="B-1")
        assert_denied(safe_scenario, runtime, result)
    finally:
        runtime.close()
        app.close()


@pytest.mark.parametrize(
    "quantity,price",
    [(15, Decimal("1.00")), (10, Decimal("1.01")), (1010, Decimal("1.00"))],
)
def test_offer_operand_mismatch_denied(safe_scenario, quantity, price):
    app, runtime = safe_scenario.open_safe()
    try:
        result = safe_scenario.call(app, quantity=quantity, price=price)
        assert_denied(safe_scenario, runtime, result)
    finally:
        runtime.close()
        app.close()


def test_forged_base_app_hard_max_claim_is_not_used(safe_scenario):
    safe_scenario.configure(hard_max=100, on_hand=80)
    app, runtime = safe_scenario.open_safe()
    try:
        # Corrupt the Base App's in-memory owner limit after startup. SafeMA
        # independently uses the pinned owner file, not this object.
        object.__setattr__(app.config.skus[0], "hard_max", 10_000)
        result = safe_scenario.call(app, quantity=30)
        assert_denied(safe_scenario, runtime, result)
    finally:
        runtime.close()
        app.close()


def test_owner_configuration_change_after_startup_fails_closed(safe_scenario):
    app, runtime = safe_scenario.open_safe()
    try:
        document = json.loads(safe_scenario.config_path.read_text(encoding="utf-8"))
        document["skus"][0]["hard_max"] = 100_000
        safe_scenario.config_path.write_text(json.dumps(document), encoding="utf-8")
        result = safe_scenario.call(app, quantity=10)
        assert_denied(safe_scenario, runtime, result)
    finally:
        runtime.close()
        app.close()


def test_policy_yaml_unknown_operator_fails_at_load(tmp_path):
    source = (
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "policies/replenishment-purchase-v2.yaml"
    )
    mutated = tmp_path / "policy.yaml"
    mutated.write_text(
        source.read_text(encoding="utf-8").replace("        - gt:\n", "        - mystery:\n", 1),
        encoding="utf-8",
    )
    with pytest.raises(ModelError, match="unsupported policy operator"):
        load_policies(mutated)
