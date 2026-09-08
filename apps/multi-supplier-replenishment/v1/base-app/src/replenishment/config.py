"""Owner configuration loading and strict validation.

The whole configuration is rejected when anything required is missing, an
unknown field is present, identifiers are duplicated, numeric ranges are
invalid, money carries more than two decimals, calendar labels are incomplete,
or a supplier mapping is ambiguous.  A running application never edits it.
"""

from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass
from datetime import time
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .decimals import DecimalFormatError, parse_decimal, parse_money
from .domain import ALL_CALENDAR_LABELS, CalendarLabel, SUPPLIER_IDS
from .errors import ConfigError

TOP_LEVEL_FIELDS = {
    "store_id",
    "destination_id",
    "timezone",
    "daily_run_time",
    "database_path",
    "scheduler_poll_seconds",
    "forecast",
    "calendar_multipliers",
    "adapters",
    "suppliers",
    "skus",
}
REQUIRED_TOP_LEVEL_FIELDS = TOP_LEVEL_FIELDS - {"scheduler_poll_seconds"}

ADAPTER_SLOTS = ("clock", "inventory_ledger", "sales_history", "calendar")
ADAPTER_FIELDS = {"factory", "options"}
SUPPLIER_FIELDS = {"supplier_id", "factory", "options"}
FORECAST_FIELDS = {"alpha"}
SKU_FIELDS = {
    "sku",
    "display_name",
    "hard_max",
    "safety_days",
    "max_lead_time_days",
    "max_unit_price_usd",
    "autonomous_order_limit_usd",
    "supplier_mappings",
}


@dataclass(frozen=True)
class AdapterSpec:
    factory: str
    options: Mapping[str, Any]


@dataclass(frozen=True)
class SupplierSpec:
    supplier_id: str
    factory: str
    options: Mapping[str, Any]


@dataclass(frozen=True)
class SkuConfig:
    sku: str
    display_name: str
    hard_max: int
    safety_days: int
    max_lead_time_days: int
    max_unit_price_usd: Decimal
    autonomous_order_limit_usd: Decimal
    supplier_mappings: Mapping[str, str]

    def supplier_sku(self, supplier_id: str) -> str | None:
        return self.supplier_mappings.get(supplier_id)

    @property
    def approved_suppliers(self) -> tuple[str, ...]:
        return tuple(s for s in SUPPLIER_IDS if s in self.supplier_mappings)


@dataclass(frozen=True)
class Config:
    store_id: str
    destination_id: str
    timezone_name: str
    daily_run_time: time
    database_path: Path
    scheduler_poll_seconds: int
    alpha: Decimal
    calendar_multipliers: Mapping[CalendarLabel, Decimal]
    adapters: Mapping[str, AdapterSpec]
    suppliers: Mapping[str, SupplierSpec]
    skus: tuple[SkuConfig, ...]
    source_path: Path
    base_dir: Path

    @property
    def tzinfo(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)

    @property
    def sku_ids(self) -> tuple[str, ...]:
        return tuple(sku.sku for sku in self.skus)

    def sku(self, sku_id: str) -> SkuConfig | None:
        for candidate in self.skus:
            if candidate.sku == sku_id:
                return candidate
        return None

    def multiplier(self, label: CalendarLabel) -> Decimal:
        return self.calendar_multipliers[label]

    def resolve_path(self, raw: str) -> Path:
        path = Path(raw).expanduser()
        return path if path.is_absolute() else (self.base_dir / path).resolve()

    def supplier_sku_index(self) -> dict[str, dict[str, str]]:
        """supplier_id -> supplier_sku -> store sku (unambiguous after validation)."""
        index: dict[str, dict[str, str]] = {sid: {} for sid in self.suppliers}
        for sku in self.skus:
            for supplier_id, supplier_sku in sku.supplier_mappings.items():
                index.setdefault(supplier_id, {})[supplier_sku] = sku.sku
        return index


class _Validator:
    def __init__(self) -> None:
        self.problems: list[str] = []

    def fail(self, message: str) -> None:
        self.problems.append(message)

    def require_mapping(self, value: Any, where: str) -> dict[str, Any]:
        if not isinstance(value, dict):
            self.fail(f"{where}: expected a table/object")
            return {}
        return value

    def check_keys(self, data: Mapping[str, Any], allowed: set[str], where: str) -> None:
        for key in data:
            if key not in allowed:
                self.fail(f"{where}: unknown field {key!r}")

    def require_str(self, data: Mapping[str, Any], key: str, where: str) -> str | None:
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            self.fail(f"{where}: {key!r} must be a non-empty string")
            return None
        return value

    def require_int(
        self,
        data: Mapping[str, Any],
        key: str,
        where: str,
        *,
        minimum: int | None = None,
        maximum: int | None = None,
    ) -> int | None:
        value = data.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            self.fail(f"{where}: {key!r} must be an integer")
            return None
        if minimum is not None and value < minimum:
            self.fail(f"{where}: {key!r} must be >= {minimum}, got {value}")
            return None
        if maximum is not None and value > maximum:
            self.fail(f"{where}: {key!r} must be <= {maximum}, got {value}")
            return None
        return value

    def require_money(
        self, data: Mapping[str, Any], key: str, where: str, *, positive: bool
    ) -> Decimal | None:
        if key not in data:
            self.fail(f"{where}: {key!r} is required")
            return None
        try:
            value = parse_money(data[key], field=f"{where}.{key}")
        except DecimalFormatError as exc:
            self.fail(str(exc))
            return None
        if positive and value <= 0:
            self.fail(f"{where}: {key!r} must be positive, got {value}")
            return None
        return value


def load_config(path: str | Path) -> Config:
    """Load and fully validate a JSON or TOML configuration file."""
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise ConfigError(f"configuration file not found: {source}")
    raw_text = source.read_bytes()
    if source.suffix.lower() == ".toml":
        try:
            data = tomllib.loads(raw_text.decode("utf-8"))
        except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
            raise ConfigError(f"{source}: invalid TOML: {exc}") from exc
    else:
        try:
            data = json.loads(raw_text.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ConfigError(f"{source}: invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{source}: configuration root must be an object")
    return _build(data, source)


def _build(data: Mapping[str, Any], source: Path) -> Config:
    v = _Validator()
    v.check_keys(data, TOP_LEVEL_FIELDS, "config")
    for key in sorted(REQUIRED_TOP_LEVEL_FIELDS):
        if key not in data:
            v.fail(f"config: {key!r} is required")

    store_id = v.require_str(data, "store_id", "config")
    destination_id = v.require_str(data, "destination_id", "config")

    timezone_name = v.require_str(data, "timezone", "config")
    if timezone_name is not None:
        try:
            ZoneInfo(timezone_name)
        except (ZoneInfoNotFoundError, ValueError, OSError):
            v.fail(f"config: {timezone_name!r} is not a known IANA time zone")
            timezone_name = None

    run_time = None
    raw_run_time = data.get("daily_run_time")
    if isinstance(raw_run_time, str):
        try:
            hour_text, minute_text = raw_run_time.split(":")
            run_time = time(int(hour_text), int(minute_text))
        except (ValueError, TypeError):
            v.fail("config: 'daily_run_time' must be 'HH:MM'")
    elif "daily_run_time" in data:
        v.fail("config: 'daily_run_time' must be a 'HH:MM' string")

    database_path_raw = v.require_str(data, "database_path", "config")
    poll_seconds = 30
    if "scheduler_poll_seconds" in data:
        checked = v.require_int(
            data, "scheduler_poll_seconds", "config", minimum=1, maximum=3600
        )
        poll_seconds = checked if checked is not None else 30

    alpha = _build_forecast(data, v)
    multipliers = _build_multipliers(data, v)
    adapters = _build_adapters(data, v)
    suppliers = _build_suppliers(data, v)
    skus = _build_skus(data, v, suppliers)

    if v.problems:
        raise ConfigError(
            f"{source}: invalid configuration:\n  - "
            + "\n  - ".join(v.problems)
        )

    assert store_id and destination_id and timezone_name and database_path_raw
    assert run_time is not None and alpha is not None
    base_dir = source.parent
    db_path = Path(database_path_raw).expanduser()
    if not db_path.is_absolute():
        db_path = base_dir / db_path
    db_path = Path(os.path.normpath(db_path))
    return Config(
        store_id=store_id,
        destination_id=destination_id,
        timezone_name=timezone_name,
        daily_run_time=run_time,
        database_path=db_path,
        scheduler_poll_seconds=poll_seconds,
        alpha=alpha,
        calendar_multipliers=multipliers,
        adapters=adapters,
        suppliers=suppliers,
        skus=skus,
        source_path=source,
        base_dir=base_dir,
    )


def _build_forecast(data: Mapping[str, Any], v: _Validator) -> Decimal | None:
    section = v.require_mapping(data.get("forecast", {}), "config.forecast")
    v.check_keys(section, FORECAST_FIELDS, "config.forecast")
    if "alpha" not in section:
        v.fail("config.forecast: 'alpha' is required")
        return None
    try:
        alpha = parse_decimal(section["alpha"], field="config.forecast.alpha")
    except DecimalFormatError as exc:
        v.fail(str(exc))
        return None
    if not (Decimal(0) < alpha <= Decimal(1)):
        v.fail(f"config.forecast: 'alpha' must satisfy 0 < alpha <= 1, got {alpha}")
        return None
    return alpha


def _build_multipliers(
    data: Mapping[str, Any], v: _Validator
) -> dict[CalendarLabel, Decimal]:
    section = v.require_mapping(
        data.get("calendar_multipliers", {}), "config.calendar_multipliers"
    )
    known = {label.value for label in ALL_CALENDAR_LABELS}
    v.check_keys(section, known, "config.calendar_multipliers")
    multipliers: dict[CalendarLabel, Decimal] = {}
    for label in ALL_CALENDAR_LABELS:
        if label.value not in section:
            v.fail(f"config.calendar_multipliers: {label.value!r} is required")
            continue
        try:
            value = parse_decimal(
                section[label.value], field=f"config.calendar_multipliers.{label.value}"
            )
        except DecimalFormatError as exc:
            v.fail(str(exc))
            continue
        if value <= 0:
            v.fail(
                f"config.calendar_multipliers: {label.value!r} must be positive, got {value}"
            )
            continue
        multipliers[label] = value
    return multipliers


def _build_adapters(data: Mapping[str, Any], v: _Validator) -> dict[str, AdapterSpec]:
    section = v.require_mapping(data.get("adapters", {}), "config.adapters")
    v.check_keys(section, set(ADAPTER_SLOTS), "config.adapters")
    specs: dict[str, AdapterSpec] = {}
    for slot in ADAPTER_SLOTS:
        where = f"config.adapters.{slot}"
        if slot not in section:
            v.fail(f"config.adapters: {slot!r} is required")
            continue
        entry = v.require_mapping(section[slot], where)
        v.check_keys(entry, ADAPTER_FIELDS, where)
        factory = v.require_str(entry, "factory", where)
        options = entry.get("options", {})
        if not isinstance(options, dict):
            v.fail(f"{where}: 'options' must be a table/object")
            options = {}
        if factory is not None:
            specs[slot] = AdapterSpec(factory=factory, options=options)
    return specs


def _build_suppliers(data: Mapping[str, Any], v: _Validator) -> dict[str, SupplierSpec]:
    entries = data.get("suppliers", [])
    if not isinstance(entries, list):
        v.fail("config.suppliers: expected a list of exactly two supplier declarations")
        return {}
    if len(entries) != 2:
        v.fail(
            "config.suppliers: exactly two supplier declarations are required, "
            f"got {len(entries)}"
        )
    specs: dict[str, SupplierSpec] = {}
    for position, entry in enumerate(entries):
        where = f"config.suppliers[{position}]"
        table = v.require_mapping(entry, where)
        v.check_keys(table, SUPPLIER_FIELDS, where)
        supplier_id = v.require_str(table, "supplier_id", where)
        factory = v.require_str(table, "factory", where)
        options = table.get("options", {})
        if not isinstance(options, dict):
            v.fail(f"{where}: 'options' must be a table/object")
            options = {}
        if supplier_id is None or factory is None:
            continue
        if supplier_id not in SUPPLIER_IDS:
            v.fail(
                f"{where}: 'supplier_id' must be one of {list(SUPPLIER_IDS)}, "
                f"got {supplier_id!r}"
            )
            continue
        if supplier_id in specs:
            v.fail(f"{where}: duplicate supplier declaration {supplier_id!r}")
            continue
        specs[supplier_id] = SupplierSpec(
            supplier_id=supplier_id, factory=factory, options=options
        )
    if specs and set(specs) != set(SUPPLIER_IDS):
        v.fail(
            "config.suppliers: both "
            f"{SUPPLIER_IDS[0]!r} and {SUPPLIER_IDS[1]!r} must be declared"
        )
    return specs


def _build_skus(
    data: Mapping[str, Any], v: _Validator, suppliers: Mapping[str, SupplierSpec]
) -> tuple[SkuConfig, ...]:
    entries = data.get("skus", [])
    if not isinstance(entries, list):
        v.fail("config.skus: expected a list of SKU records")
        return ()
    if not entries:
        v.fail("config.skus: at least one enabled SKU is required")
    seen: set[str] = set()
    supplier_sku_owner: dict[tuple[str, str], str] = {}
    result: list[SkuConfig] = []
    for position, entry in enumerate(entries):
        where = f"config.skus[{position}]"
        table = v.require_mapping(entry, where)
        v.check_keys(table, SKU_FIELDS, where)
        sku_id = v.require_str(table, "sku", where)
        display_name = v.require_str(table, "display_name", where)
        hard_max = v.require_int(table, "hard_max", where, minimum=0)
        safety_days = v.require_int(table, "safety_days", where, minimum=0, maximum=14)
        max_lead = v.require_int(
            table, "max_lead_time_days", where, minimum=1, maximum=14
        )
        max_price = v.require_money(table, "max_unit_price_usd", where, positive=True)
        spend_limit = v.require_money(
            table, "autonomous_order_limit_usd", where, positive=True
        )

        mappings_raw = table.get("supplier_mappings")
        mappings: dict[str, str] = {}
        if not isinstance(mappings_raw, dict) or not mappings_raw:
            v.fail(
                f"{where}: 'supplier_mappings' must map at least one approved supplier "
                "to its supplier SKU"
            )
        else:
            for supplier_id, supplier_sku in mappings_raw.items():
                if supplier_id not in suppliers:
                    v.fail(
                        f"{where}.supplier_mappings: {supplier_id!r} is not a declared supplier"
                    )
                    continue
                if not isinstance(supplier_sku, str) or not supplier_sku.strip():
                    v.fail(
                        f"{where}.supplier_mappings.{supplier_id}: supplier SKU must be "
                        "a non-empty string"
                    )
                    continue
                mappings[supplier_id] = supplier_sku

        if sku_id is not None:
            if sku_id in seen:
                v.fail(f"{where}: duplicate SKU identifier {sku_id!r}")
            seen.add(sku_id)
            for supplier_id, supplier_sku in mappings.items():
                key = (supplier_id, supplier_sku)
                previous = supplier_sku_owner.get(key)
                if previous is not None and previous != sku_id:
                    v.fail(
                        f"{where}.supplier_mappings.{supplier_id}: supplier SKU "
                        f"{supplier_sku!r} is ambiguous; it is already mapped to "
                        f"store SKU {previous!r}"
                    )
                supplier_sku_owner[key] = sku_id

        if None in (sku_id, display_name, hard_max, safety_days, max_lead):
            continue
        if max_price is None or spend_limit is None or not mappings:
            continue
        assert sku_id and display_name is not None
        result.append(
            SkuConfig(
                sku=sku_id,
                display_name=display_name,
                hard_max=hard_max,
                safety_days=safety_days,
                max_lead_time_days=max_lead,
                max_unit_price_usd=max_price,
                autonomous_order_limit_usd=spend_limit,
                supplier_mappings=dict(sorted(mappings.items())),
            )
        )
    return tuple(sorted(result, key=lambda item: item.sku))
