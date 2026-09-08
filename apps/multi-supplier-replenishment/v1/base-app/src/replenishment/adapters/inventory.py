"""Local Inventory Ledger.

The ledger owns SKU identity, base unit, active status, on-hand quantity, and
receipts.  This application only ever reads from it; there is no mutation
operation on this adapter at all.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Sequence

from ..domain import BASE_UNIT, InventoryRecord, InventorySnapshot, MalformedRecord, Receipt
from ..errors import MalformedResponse, ServiceUnavailable
from ..interfaces import Clock
from ..timeutil import TimestampFormatError, from_rfc3339
from .world import INVENTORY_DOC, WorldStore


def _as_of(document: dict[str, Any], clock: Clock) -> datetime:
    explicit = document.get("as_of")
    if explicit:
        return from_rfc3339(explicit, field="inventory.as_of")
    offset = document.get("as_of_offset_seconds", 0)
    if not isinstance(offset, int):
        raise MalformedResponse("inventory: 'as_of_offset_seconds' must be an integer")
    return clock.now() + timedelta(seconds=offset)


class LocalInventoryLedger:
    """Reads the mock world's ledger document."""

    def __init__(self, world: WorldStore, clock: Clock) -> None:
        self._world = world
        self._clock = clock

    def _document(self) -> dict[str, Any]:
        try:
            document = self._world.read(INVENTORY_DOC)
        except FileNotFoundError as exc:
            raise ServiceUnavailable(str(exc)) from exc
        except ValueError as exc:
            raise MalformedResponse(f"inventory ledger: {exc}") from exc
        failure = document.get("failure")
        if failure == "unavailable":
            raise ServiceUnavailable("inventory ledger is unavailable")
        if failure == "malformed":
            raise MalformedResponse("inventory ledger returned an undecodable snapshot")
        if failure is not None:
            raise MalformedResponse(f"inventory ledger: unknown failure mode {failure!r}")
        return document

    def get_snapshot(self, store_id: str, skus: Sequence[str]) -> InventorySnapshot:
        document = self._document()
        revision_id = document.get("revision_id")
        if not isinstance(revision_id, str) or not revision_id:
            raise MalformedResponse("inventory ledger: snapshot has no revision ID")
        as_of = _as_of(document, self._clock)
        wanted = set(skus)
        records: list[InventoryRecord] = []
        malformed: list[MalformedRecord] = []
        for raw in document.get("records", []):
            if not isinstance(raw, dict):
                malformed.append(MalformedRecord(None, "record is not an object"))
                continue
            sku = raw.get("sku")
            if not isinstance(sku, str) or sku not in wanted:
                continue
            record_store = raw.get("store_id", document.get("store_id"))
            on_hand = raw.get("on_hand")
            active = raw.get("active")
            base_unit = raw.get("base_unit", BASE_UNIT)
            if isinstance(on_hand, bool) or not isinstance(on_hand, int):
                malformed.append(
                    MalformedRecord(sku, f"on_hand {on_hand!r} is not an integer")
                )
                continue
            if not isinstance(active, bool):
                malformed.append(
                    MalformedRecord(sku, f"active {active!r} is not a boolean")
                )
                continue
            if not isinstance(base_unit, str) or not isinstance(record_store, str):
                malformed.append(
                    MalformedRecord(sku, "store_id or base_unit is not a string")
                )
                continue
            records.append(
                InventoryRecord(
                    store_id=record_store,
                    sku=sku,
                    base_unit=base_unit,
                    active=active,
                    on_hand=on_hand,
                )
            )
        return InventorySnapshot(
            revision_id=revision_id,
            as_of=as_of,
            records=tuple(records),
            malformed=tuple(malformed),
        )

    def get_receipts(
        self, store_id: str, supplier_id: str, order_ids: Sequence[str]
    ) -> list[Receipt]:
        document = self._document()
        wanted = set(order_ids)
        receipts: list[Receipt] = []
        for raw in document.get("receipts", []):
            if not isinstance(raw, dict):
                raise MalformedResponse("inventory ledger: a receipt is not an object")
            order_id = raw.get("supplier_order_id")
            if raw.get("supplier_id") != supplier_id or order_id not in wanted:
                continue
            try:
                receipts.append(
                    Receipt(
                        receipt_id=str(raw["receipt_id"]),
                        store_id=str(raw.get("store_id", document.get("store_id"))),
                        supplier_id=str(raw["supplier_id"]),
                        supplier_order_id=str(order_id),
                        sku=str(raw["sku"]),
                        quantity=int(raw["quantity"]),
                        posted_at=from_rfc3339(raw["posted_at"], field="receipt.posted_at"),
                    )
                )
            except (KeyError, TypeError, ValueError, TimestampFormatError) as exc:
                raise MalformedResponse(
                    f"inventory ledger: receipt for order {order_id!r} is undecodable: {exc}"
                ) from exc
        receipts.sort(key=lambda item: (item.supplier_order_id, item.receipt_id))
        return receipts
