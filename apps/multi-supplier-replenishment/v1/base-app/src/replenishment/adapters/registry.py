"""Construction of external adapters from the owner configuration.

A configuration that names an adapter this build cannot construct is rejected
before the scheduler starts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..config import AdapterSpec, Config
from ..errors import ConfigError
from ..interfaces import (
    CalendarService,
    Clock,
    InventoryLedger,
    SalesHistory,
    SupplierService,
)
from ..timeutil import TimestampFormatError, from_rfc3339
from .calendar import LocalCalendarService
from .clock import FixedClock, SystemClock
from .inventory import LocalInventoryLedger
from .sales import LocalSalesHistory
from .supplier import LocalSupplierService
from .world import WorldStore

CLOCK_FACTORIES = ("system_clock", "fixed_clock")
WORLD_FACTORY = "local_world"


@dataclass(frozen=True)
class Services:
    """Every external system this application depends on."""

    clock: Clock
    inventory: InventoryLedger
    sales: SalesHistory
    calendar: CalendarService
    suppliers: Mapping[str, SupplierService]
    worlds: Mapping[str, WorldStore]

    def world_for(self, slot: str) -> WorldStore | None:
        return self.worlds.get(slot)


def _known_options(spec: AdapterSpec, allowed: set[str], where: str) -> None:
    unknown = sorted(set(spec.options) - allowed)
    if unknown:
        raise ConfigError(f"{where}: unknown adapter options {unknown}")


def _world(config: Config, spec: AdapterSpec, where: str) -> WorldStore:
    _known_options(spec, {"world_dir"}, where)
    raw = spec.options.get("world_dir")
    if not isinstance(raw, str) or not raw:
        raise ConfigError(f"{where}: 'world_dir' is required for the local world adapter")
    root = config.resolve_path(raw)
    if not root.is_dir():
        raise ConfigError(f"{where}: mock world directory does not exist: {root}")
    return WorldStore(root)


def build_clock(config: Config) -> Clock:
    spec = config.adapters["clock"]
    where = "config.adapters.clock"
    if spec.factory == "system_clock":
        _known_options(spec, set(), where)
        return SystemClock()
    if spec.factory == "fixed_clock":
        _known_options(spec, {"instant"}, where)
        raw = spec.options.get("instant")
        try:
            instant = from_rfc3339(raw, field=f"{where}.options.instant")
        except TimestampFormatError as exc:
            raise ConfigError(f"{where}: {exc}") from exc
        return FixedClock(instant)
    raise ConfigError(
        f"{where}: unknown clock factory {spec.factory!r}; expected one of "
        f"{list(CLOCK_FACTORIES)}"
    )


def build_services(config: Config) -> Services:
    """Construct every adapter or reject the configuration."""
    clock = build_clock(config)
    worlds: dict[str, WorldStore] = {}

    def world_for(slot: str) -> WorldStore:
        spec = config.adapters[slot]
        where = f"config.adapters.{slot}"
        if spec.factory != WORLD_FACTORY:
            raise ConfigError(
                f"{where}: unknown factory {spec.factory!r}; expected {WORLD_FACTORY!r}"
            )
        store = _world(config, spec, where)
        worlds[slot] = store
        return store

    inventory = LocalInventoryLedger(world_for("inventory_ledger"), clock)
    sales = LocalSalesHistory(world_for("sales_history"))
    calendar = LocalCalendarService(world_for("calendar"))

    suppliers: dict[str, SupplierService] = {}
    for supplier_id, spec in config.suppliers.items():
        where = f"config.suppliers[{supplier_id}]"
        if spec.factory != WORLD_FACTORY:
            raise ConfigError(
                f"{where}: unknown factory {spec.factory!r}; expected {WORLD_FACTORY!r}"
            )
        store = _world(config, AdapterSpec(spec.factory, spec.options), where)
        worlds[supplier_id] = store
        document = store.path(f"supplier_{supplier_id}.json")
        if not document.is_file():
            raise ConfigError(
                f"{where}: the mock world has no document for {supplier_id} at {document}"
            )
        suppliers[supplier_id] = LocalSupplierService(store, clock, supplier_id)

    return Services(
        clock=clock,
        inventory=inventory,
        sales=sales,
        calendar=calendar,
        suppliers=suppliers,
        worlds=worlds,
    )
