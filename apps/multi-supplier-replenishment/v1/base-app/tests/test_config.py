"""Section 13: the whole configuration is rejected when anything is wrong."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from replenishment.adapters.registry import build_services
from replenishment.config import load_config
from replenishment.errors import ConfigError

from . import support


def write(tmp_path: Path, mutate=None, **kwargs) -> Path:
    path = tmp_path / "config.json"
    support.write_config(
        path,
        world_dir=tmp_path / "world",
        database_path=tmp_path / "app.sqlite3",
        skus=[support.sku_config("SKU-1", mappings={"SUPPLIER_A": "A-1"})],
        **kwargs,
    )
    if mutate is not None:
        document = json.loads(path.read_text())
        mutate(document)
        path.write_text(json.dumps(document, indent=2))
    return path


def test_a_valid_configuration_loads(tmp_path):
    config = load_config(write(tmp_path))
    assert config.store_id == support.STORE
    assert config.destination_id == support.DESTINATION
    assert config.alpha == Decimal("0.30")
    assert config.daily_run_time.strftime("%H:%M") == "05:00"
    assert config.sku_ids == ("SKU-1",)
    assert config.skus[0].approved_suppliers == ("SUPPLIER_A",)
    assert len(config.calendar_multipliers) == 4


def test_toml_configuration_is_supported(tmp_path):
    json_path = write(tmp_path)
    document = json.loads(json_path.read_text())
    toml_path = tmp_path / "config.toml"
    sku = document["skus"][0]
    toml_path.write_text(
        "\n".join(
            [
                f'store_id = "{document["store_id"]}"',
                f'destination_id = "{document["destination_id"]}"',
                f'timezone = "{document["timezone"]}"',
                'daily_run_time = "05:00"',
                f'database_path = "{document["database_path"]}"',
                "",
                "[forecast]",
                'alpha = "0.30"',
                "",
                "[calendar_multipliers]",
                'NORMAL = "1.00"',
                'WEEKEND = "1.25"',
                'PRE_HOLIDAY = "1.40"',
                'HOLIDAY = "0.60"',
                "",
                "[adapters.clock]",
                'factory = "fixed_clock"',
                f'options = {{ instant = "{support.RUN_INSTANT}" }}',
                "[adapters.inventory_ledger]",
                'factory = "local_world"',
                f'options = {{ world_dir = "{tmp_path / "world"}" }}',
                "[adapters.sales_history]",
                'factory = "local_world"',
                f'options = {{ world_dir = "{tmp_path / "world"}" }}',
                "[adapters.calendar]",
                'factory = "local_world"',
                f'options = {{ world_dir = "{tmp_path / "world"}" }}',
                "",
                "[[suppliers]]",
                'supplier_id = "SUPPLIER_A"',
                'factory = "local_world"',
                f'options = {{ world_dir = "{tmp_path / "world"}" }}',
                "[[suppliers]]",
                'supplier_id = "SUPPLIER_B"',
                'factory = "local_world"',
                f'options = {{ world_dir = "{tmp_path / "world"}" }}',
                "",
                "[[skus]]",
                f'sku = "{sku["sku"]}"',
                f'display_name = "{sku["display_name"]}"',
                f'hard_max = {sku["hard_max"]}',
                f'safety_days = {sku["safety_days"]}',
                f'max_lead_time_days = {sku["max_lead_time_days"]}',
                f'max_unit_price_usd = "{sku["max_unit_price_usd"]}"',
                f'autonomous_order_limit_usd = "{sku["autonomous_order_limit_usd"]}"',
                'supplier_mappings = { SUPPLIER_A = "A-1" }',
                "",
            ]
        )
    )
    config = load_config(toml_path)
    assert config.sku_ids == ("SKU-1",)


def test_a_missing_file_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "absent.json")


def test_unknown_top_level_fields_are_rejected(tmp_path):
    path = write(tmp_path, mutate=lambda doc: doc.update({"surprise": 1}))
    with pytest.raises(ConfigError, match="unknown field 'surprise'"):
        load_config(path)


def test_a_missing_required_field_is_rejected(tmp_path):
    path = write(tmp_path, mutate=lambda doc: doc.pop("destination_id"))
    with pytest.raises(ConfigError, match="'destination_id' is required"):
        load_config(path)


def test_an_unknown_time_zone_is_rejected(tmp_path):
    path = write(tmp_path, timezone_name="Mars/Olympus")
    with pytest.raises(ConfigError, match="IANA time zone"):
        load_config(path)


def test_a_malformed_run_time_is_rejected(tmp_path):
    path = write(tmp_path, daily_run_time="0500")
    with pytest.raises(ConfigError, match="daily_run_time"):
        load_config(path)


@pytest.mark.parametrize("alpha", ["0", "-0.5", "1.5"])
def test_alpha_outside_its_range_is_rejected(tmp_path, alpha):
    path = write(tmp_path, alpha=alpha)
    with pytest.raises(ConfigError, match="alpha"):
        load_config(path)


def test_a_float_alpha_is_rejected(tmp_path):
    path = write(tmp_path, mutate=lambda doc: doc["forecast"].update({"alpha": 0.3}))
    with pytest.raises(ConfigError, match="floating point"):
        load_config(path)


def test_an_incomplete_calendar_multiplier_table_is_rejected(tmp_path):
    path = write(tmp_path, mutate=lambda doc: doc["calendar_multipliers"].pop("HOLIDAY"))
    with pytest.raises(ConfigError, match="'HOLIDAY' is required"):
        load_config(path)


def test_a_non_positive_multiplier_is_rejected(tmp_path):
    path = write(
        tmp_path, mutate=lambda doc: doc["calendar_multipliers"].update({"WEEKEND": "0"})
    )
    with pytest.raises(ConfigError, match="must be positive"):
        load_config(path)


def test_an_unknown_calendar_label_is_rejected(tmp_path):
    path = write(
        tmp_path,
        mutate=lambda doc: doc["calendar_multipliers"].update({"FESTIVAL": "2.00"}),
    )
    with pytest.raises(ConfigError, match="unknown field 'FESTIVAL'"):
        load_config(path)


def test_money_with_more_than_two_decimals_is_rejected(tmp_path):
    path = write(
        tmp_path,
        mutate=lambda doc: doc["skus"][0].update({"max_unit_price_usd": "1.234"}),
    )
    with pytest.raises(ConfigError, match="exactly two decimal places"):
        load_config(path)


def test_a_non_positive_price_limit_is_rejected(tmp_path):
    path = write(
        tmp_path,
        mutate=lambda doc: doc["skus"][0].update({"max_unit_price_usd": "0.00"}),
    )
    with pytest.raises(ConfigError, match="must be positive"):
        load_config(path)


@pytest.mark.parametrize(
    "field,value",
    [
        ("hard_max", -1),
        ("safety_days", -1),
        ("safety_days", 15),
        ("max_lead_time_days", 0),
        ("max_lead_time_days", 15),
    ],
)
def test_numeric_ranges_are_enforced(tmp_path, field, value):
    path = write(tmp_path, mutate=lambda doc: doc["skus"][0].update({field: value}))
    with pytest.raises(ConfigError, match=field):
        load_config(path)


def test_duplicate_sku_identifiers_are_rejected(tmp_path):
    path = write(
        tmp_path,
        mutate=lambda doc: doc["skus"].append(dict(doc["skus"][0])),
    )
    with pytest.raises(ConfigError, match="duplicate SKU identifier"):
        load_config(path)


def test_an_ambiguous_supplier_mapping_is_rejected(tmp_path):
    def mutate(doc):
        second = support.sku_config("SKU-2", mappings={"SUPPLIER_A": "A-1"})
        doc["skus"].append(second)

    path = write(tmp_path, mutate=mutate)
    with pytest.raises(ConfigError, match="ambiguous"):
        load_config(path)


def test_a_sku_without_any_supplier_mapping_is_rejected(tmp_path):
    path = write(
        tmp_path, mutate=lambda doc: doc["skus"][0].update({"supplier_mappings": {}})
    )
    with pytest.raises(ConfigError, match="supplier_mappings"):
        load_config(path)


def test_a_mapping_to_an_undeclared_supplier_is_rejected(tmp_path):
    path = write(
        tmp_path,
        mutate=lambda doc: doc["skus"][0]["supplier_mappings"].update(
            {"SUPPLIER_C": "C-1"}
        ),
    )
    with pytest.raises(ConfigError, match="not a declared supplier"):
        load_config(path)


def test_exactly_two_suppliers_are_required(tmp_path):
    path = write(tmp_path, mutate=lambda doc: doc["suppliers"].pop())
    with pytest.raises(ConfigError, match="exactly two supplier declarations"):
        load_config(path)


def test_duplicate_supplier_declarations_are_rejected(tmp_path):
    def mutate(doc):
        doc["suppliers"][1] = dict(doc["suppliers"][0])

    path = write(tmp_path, mutate=mutate)
    with pytest.raises(ConfigError, match="duplicate supplier declaration"):
        load_config(path)


def test_an_unexpected_supplier_id_is_rejected(tmp_path):
    path = write(
        tmp_path, mutate=lambda doc: doc["suppliers"][1].update({"supplier_id": "SUPPLIER_Z"})
    )
    with pytest.raises(ConfigError, match="supplier_id"):
        load_config(path)


def test_a_missing_adapter_slot_is_rejected(tmp_path):
    path = write(tmp_path, mutate=lambda doc: doc["adapters"].pop("calendar"))
    with pytest.raises(ConfigError, match="'calendar' is required"):
        load_config(path)


def test_all_problems_are_reported_together(tmp_path):
    def mutate(doc):
        doc.pop("store_id")
        doc["skus"][0]["hard_max"] = -5
        doc["calendar_multipliers"].pop("WEEKEND")

    path = write(tmp_path, mutate=mutate)
    with pytest.raises(ConfigError) as excinfo:
        load_config(path)
    message = str(excinfo.value)
    assert "store_id" in message and "hard_max" in message and "WEEKEND" in message


# -- adapter construction --------------------------------------------------


def test_an_adapter_that_cannot_be_constructed_rejects_the_configuration(tmp_path):
    config = load_config(write(tmp_path))
    # The mock world directory named by the configuration does not exist.
    with pytest.raises(ConfigError, match="mock world directory does not exist"):
        build_services(config)


def test_an_unknown_clock_factory_is_rejected(tmp_path):
    path = write(
        tmp_path,
        mutate=lambda doc: doc["adapters"]["clock"].update({"factory": "atomic"}),
    )
    with pytest.raises(ConfigError, match="unknown clock factory"):
        build_services(load_config(path))


def test_unknown_adapter_options_are_rejected(tmp_path):
    path = write(
        tmp_path,
        mutate=lambda doc: doc["adapters"]["calendar"]["options"].update({"retries": 3}),
    )
    world = support.World(tmp_path / "world")
    world.write_calendar()
    world.write_sales({})
    world.write_inventory({})
    world.write_supplier("SUPPLIER_A")
    world.write_supplier("SUPPLIER_B")
    with pytest.raises(ConfigError, match="unknown adapter options"):
        build_services(load_config(path))


def test_a_supplier_without_a_mock_world_document_is_rejected(tmp_path):
    path = write(tmp_path)
    world = support.World(tmp_path / "world")
    world.write_calendar()
    world.write_sales({})
    world.write_inventory({})
    world.write_supplier("SUPPLIER_A")
    with pytest.raises(ConfigError, match="no document for SUPPLIER_B"):
        build_services(load_config(path))
