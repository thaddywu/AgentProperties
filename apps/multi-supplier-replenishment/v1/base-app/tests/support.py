"""Builders for a complete deterministic local world and configuration.

Nothing here touches a network, wall-clock time, or a random identifier.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

STORE = "STORE-T"
DESTINATION = "DEST-T"
TIMEZONE = "America/New_York"
#: 05:05 local on the run's business date, five minutes after the daily 05:00.
RUN_INSTANT = "2026-09-03T09:05:00Z"
RUN_DATE = date(2026, 9, 3)
FAR_FUTURE = "2026-12-31T00:00:00Z"

CALENDAR_START = date(2026, 7, 1)
CALENDAR_END = date(2026, 10, 31)

MULTIPLIERS = {
    "NORMAL": "1.00",
    "WEEKEND": "1.25",
    "PRE_HOLIDAY": "1.40",
    "HOLIDAY": "0.60",
}


def history_dates(run_date: date = RUN_DATE) -> list[date]:
    """The 28 business dates immediately preceding ``run_date``."""
    return [run_date - timedelta(days=offset) for offset in range(28, 0, -1)]


def date_span(start: date, end: date) -> list[date]:
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def flat_sales(units: int, run_date: date = RUN_DATE) -> dict[str, int]:
    """The same number of units on each of the 28 historical dates."""
    return {day.isoformat(): units for day in history_dates(run_date)}


def offer(
    *,
    unit_price: str = "1.00",
    pack_size: int = 10,
    available_quantity: int = 10_000,
    lead_time_days: int = 2,
    valid_until: str = FAR_FUTURE,
    **extra: Any,
) -> dict[str, Any]:
    payload = {
        "unit_price": unit_price,
        "pack_size": pack_size,
        "available_quantity": available_quantity,
        "lead_time_days": lead_time_days,
        "valid_until": valid_until,
    }
    payload.update(extra)
    return payload


def order(
    *,
    supplier_id: str,
    supplier_order_id: str,
    supplier_sku: str,
    quantity: int,
    unit_price: str = "1.00",
    status: str = "ACCEPTED",
    idempotency_key: str = "",
    created_at: str = "2026-09-01T12:00:00Z",
    promised_delivery_date: str | None = "2026-09-05",
    destination_id: str = DESTINATION,
    total_cost: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    from decimal import Decimal

    computed = str((Decimal(unit_price) * quantity).quantize(Decimal("0.01")))
    payload = {
        "supplier_id": supplier_id,
        "supplier_order_id": supplier_order_id,
        "idempotency_key": idempotency_key,
        "destination_id": destination_id,
        "supplier_sku": supplier_sku,
        "quantity": quantity,
        "unit_price": unit_price,
        "total_cost": total_cost if total_cost is not None else computed,
        "status": status,
        "created_at": created_at,
        "promised_delivery_date": promised_delivery_date,
        "currency": "USD",
    }
    payload.update(extra)
    return payload


def receipt(
    *,
    receipt_id: str,
    supplier_id: str,
    supplier_order_id: str,
    sku: str,
    quantity: int,
    store_id: str = STORE,
    posted_at: str = "2026-09-02T12:00:00Z",
) -> dict[str, Any]:
    return {
        "receipt_id": receipt_id,
        "store_id": store_id,
        "supplier_id": supplier_id,
        "supplier_order_id": supplier_order_id,
        "sku": sku,
        "quantity": quantity,
        "posted_at": posted_at,
    }


def sku_config(
    sku: str,
    *,
    display_name: str | None = None,
    hard_max: int = 10_000,
    safety_days: int = 2,
    max_lead_time_days: int = 5,
    max_unit_price_usd: str = "9.00",
    autonomous_order_limit_usd: str = "9000.00",
    mappings: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "sku": sku,
        "display_name": display_name or sku,
        "hard_max": hard_max,
        "safety_days": safety_days,
        "max_lead_time_days": max_lead_time_days,
        "max_unit_price_usd": max_unit_price_usd,
        "autonomous_order_limit_usd": autonomous_order_limit_usd,
        "supplier_mappings": dict(
            mappings if mappings is not None else {"SUPPLIER_A": f"A::{sku}"}
        ),
    }


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


class World:
    """A writable mock external world on disk."""

    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    # -- documents -------------------------------------------------------

    def write_inventory(
        self,
        on_hand: Mapping[str, int] | None = None,
        *,
        records: Sequence[Mapping[str, Any]] | None = None,
        receipts: Sequence[Mapping[str, Any]] = (),
        revision_id: str = "INV-REV-1",
        as_of_offset_seconds: int = 0,
        as_of: str | None = None,
        failure: str | None = None,
        store_id: str = STORE,
    ) -> None:
        if records is None:
            records = [
                {
                    "store_id": store_id,
                    "sku": sku,
                    "base_unit": "EACH",
                    "active": True,
                    "on_hand": quantity,
                }
                for sku, quantity in sorted((on_hand or {}).items())
            ]
        document: dict[str, Any] = {
            "store_id": store_id,
            "revision_id": revision_id,
            "as_of_offset_seconds": as_of_offset_seconds,
            "failure": failure,
            "records": list(records),
            "receipts": list(receipts),
        }
        if as_of is not None:
            document["as_of"] = as_of
        _write(self.root / "inventory.json", document)

    def write_sales(
        self,
        sales: Mapping[str, Any],
        *,
        failures: Mapping[str, str] | None = None,
        store_id: str = STORE,
    ) -> None:
        _write(
            self.root / "sales.json",
            {
                "store_id": store_id,
                "failures": dict(failures or {}),
                "sales": dict(sales),
            },
        )

    def write_calendar(
        self,
        *,
        labels: Mapping[str, str] | None = None,
        default_label: str = "NORMAL",
        weekend_labels: bool = False,
        overrides: Mapping[str, str] | None = None,
        days: Any = None,
        failure: str | None = None,
        store_id: str = STORE,
    ) -> None:
        if days is None:
            if labels is not None:
                days = dict(labels)
            else:
                days = {}
                for day in date_span(CALENDAR_START, CALENDAR_END):
                    label = default_label
                    if weekend_labels and day.weekday() >= 5:
                        label = "WEEKEND"
                    days[day.isoformat()] = label
                days.update(overrides or {})
        _write(
            self.root / "calendar.json",
            {"store_id": store_id, "failure": failure, "days": days},
        )

    def write_supplier(
        self,
        supplier_id: str,
        *,
        offers: Mapping[str, Any] | None = None,
        orders: Sequence[Mapping[str, Any]] = (),
        offer_failures: Mapping[str, str] | None = None,
        place_order_behaviors: Mapping[str, Any] | None = None,
        lookup_behaviors: Mapping[str, Any] | None = None,
        snapshot_complete: bool = True,
        snapshot_failure: str | None = None,
        as_of_offset_seconds: int = 0,
        as_of: str | None = None,
        order_seq: int = 0,
        destination_id: str = DESTINATION,
    ) -> None:
        document: dict[str, Any] = {
            "supplier_id": supplier_id,
            "destination_id": destination_id,
            "timezone": TIMEZONE,
            "order_id_prefix": supplier_id[-1],
            "order_seq": order_seq,
            "as_of_offset_seconds": as_of_offset_seconds,
            "snapshot_complete": snapshot_complete,
            "snapshot_failure": snapshot_failure,
            "offers": dict(offers or {}),
            "offer_failures": dict(offer_failures or {}),
            "place_order_behaviors": {
                key: list(value) if isinstance(value, (list, tuple)) else [value]
                for key, value in (place_order_behaviors or {}).items()
            },
            "lookup_behaviors": {
                key: list(value) if isinstance(value, (list, tuple)) else [value]
                for key, value in (lookup_behaviors or {}).items()
            },
            "orders": [dict(item) for item in orders],
        }
        if as_of is not None:
            document["as_of"] = as_of
        _write(self.root / f"supplier_{supplier_id}.json", document)

    # -- inspection ------------------------------------------------------

    def document(self, name: str) -> dict[str, Any]:
        return read_json(self.root / name)

    def supplier_document(self, supplier_id: str) -> dict[str, Any]:
        return self.document(f"supplier_{supplier_id}.json")

    def supplier_orders(self, supplier_id: str) -> list[dict[str, Any]]:
        return self.supplier_document(supplier_id)["orders"]

    def inventory_document(self) -> dict[str, Any]:
        return self.document("inventory.json")

    def raw_calls(
        self, supplier_id: str, method: str | None = None
    ) -> list[dict[str, Any]]:
        path = self.root / "raw_calls" / f"{supplier_id}.jsonl"
        if not path.is_file():
            return []
        entries = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if method is not None:
            entries = [entry for entry in entries if entry["method"] == method]
        return entries


def write_config(
    path: Path,
    *,
    world_dir: Path,
    database_path: Path,
    skus: Iterable[Mapping[str, Any]],
    instant: str = RUN_INSTANT,
    alpha: str = "0.30",
    multipliers: Mapping[str, str] | None = None,
    daily_run_time: str = "05:00",
    timezone_name: str = TIMEZONE,
    store_id: str = STORE,
    destination_id: str = DESTINATION,
    scheduler_poll_seconds: int | None = None,
    **overrides: Any,
) -> Path:
    world_option = {"world_dir": str(world_dir)}
    document: dict[str, Any] = {
        "store_id": store_id,
        "destination_id": destination_id,
        "timezone": timezone_name,
        "daily_run_time": daily_run_time,
        "database_path": str(database_path),
        "forecast": {"alpha": alpha},
        "calendar_multipliers": dict(multipliers or MULTIPLIERS),
        "adapters": {
            "clock": {"factory": "fixed_clock", "options": {"instant": instant}},
            "inventory_ledger": {"factory": "local_world", "options": world_option},
            "sales_history": {"factory": "local_world", "options": world_option},
            "calendar": {"factory": "local_world", "options": world_option},
        },
        "suppliers": [
            {
                "supplier_id": "SUPPLIER_A",
                "factory": "local_world",
                "options": world_option,
            },
            {
                "supplier_id": "SUPPLIER_B",
                "factory": "local_world",
                "options": world_option,
            },
        ],
        "skus": [dict(item) for item in skus],
    }
    if scheduler_poll_seconds is not None:
        document["scheduler_poll_seconds"] = scheduler_poll_seconds
    document.update(overrides)
    _write(path, document)
    return path
