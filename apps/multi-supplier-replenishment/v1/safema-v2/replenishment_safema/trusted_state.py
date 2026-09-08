"""Independent authoritative state resolution for PURCHASE authorization."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable

from safema.errors import ModelError
from safema.types import Context, Effect, ResolvedMetadata, Resource

MAX_AGE = timedelta(minutes=15)
ORDER_STATUSES = {"ACCEPTED", "SHIPPED", "DELIVERED", "CANCELLED"}
OUTSTANDING_STATUSES = {"ACCEPTED", "SHIPPED", "DELIVERED"}


def _mapping(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ModelError(f"{where} must be an object")
    return value


def _list(value: Any, where: str) -> list[Any]:
    if not isinstance(value, list):
        raise ModelError(f"{where} must be a list")
    return value


def _text(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value:
        raise ModelError(f"{where} must be a non-empty string")
    return value


def _integer(value: Any, where: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ModelError(f"{where} must be an integer >= {minimum}")
    return value


def _decimal(value: Any, where: str, *, positive: bool = False) -> Decimal:
    if isinstance(value, bool):
        raise ModelError(f"{where} must be an exact decimal")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ModelError(f"{where} must be an exact decimal") from exc
    if not result.is_finite() or (positive and result <= 0):
        raise ModelError(f"{where} must be a finite{' positive' if positive else ''} decimal")
    return result


def _instant(value: Any, where: str) -> datetime:
    text = _text(value, where)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        result = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ModelError(f"{where} must be an RFC 3339 timestamp") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ModelError(f"{where} must include a time-zone offset")
    return result.astimezone(timezone.utc)


def _read_json(path: Path, where: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ModelError(f"cannot read trusted {where} at {path}: {exc}") from exc
    return _mapping(value, where), raw


@dataclass(frozen=True)
class SkuAuthority:
    store_sku: str
    hard_max: int
    max_unit_price: Decimal
    max_order_spend: Decimal
    max_lead_time_days: int
    mappings: dict[str, str]


@dataclass(frozen=True)
class OwnerAuthority:
    store_id: str
    destination_id: str
    supplier_ids: tuple[str, ...]
    skus: tuple[SkuAuthority, ...]
    world_dir: Path
    fixed_now: datetime | None


class ReplenishmentTrustedStateResolver:
    """Resolve one effect from owner config and raw authoritative world state.

    It deliberately does not call the Base App's adapters or consume its
    inventory/outstanding calculations.
    """

    resolver_id = "replenishment.authoritative_purchase_state.v2"

    def __init__(
        self,
        owner_config_path: str | Path,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.config_path = Path(owner_config_path).expanduser().resolve()
        document, raw = _read_json(self.config_path, "owner configuration")
        self.config_digest = hashlib.sha256(raw).hexdigest()
        self.authority = self._parse_owner(document)
        self._now = now or self._configured_clock(document)

    @property
    def supplier_ids(self) -> tuple[str, ...]:
        return self.authority.supplier_ids

    def _configured_clock(
        self, document: dict[str, Any]
    ) -> Callable[[], datetime]:
        adapters = _mapping(document.get("adapters"), "config.adapters")
        clock = _mapping(adapters.get("clock"), "config.adapters.clock")
        factory = _text(clock.get("factory"), "config.adapters.clock.factory")
        if factory == "fixed_clock":
            options = _mapping(clock.get("options"), "config.adapters.clock.options")
            fixed = _instant(options.get("instant"), "config clock instant")
            return lambda: fixed
        if factory == "system_clock":
            return lambda: datetime.now(timezone.utc)
        raise ModelError(f"unsupported trusted clock factory {factory!r}")

    def _parse_owner(self, document: dict[str, Any]) -> OwnerAuthority:
        store_id = _text(document.get("store_id"), "config.store_id")
        destination_id = _text(
            document.get("destination_id"), "config.destination_id"
        )
        suppliers = _list(document.get("suppliers"), "config.suppliers")
        supplier_ids = tuple(
            _text(_mapping(item, "supplier").get("supplier_id"), "supplier_id")
            for item in suppliers
        )
        if len(supplier_ids) != len(set(supplier_ids)) or not supplier_ids:
            raise ModelError("owner supplier IDs must be non-empty and unique")

        adapters = _mapping(document.get("adapters"), "config.adapters")
        inventory = _mapping(
            adapters.get("inventory_ledger"), "config.adapters.inventory_ledger"
        )
        options = _mapping(inventory.get("options"), "inventory adapter options")
        raw_world = _text(options.get("world_dir"), "inventory world_dir")
        world = Path(raw_world).expanduser()
        if not world.is_absolute():
            world = (self.config_path.parent / world).resolve()

        skus = []
        seen_skus: set[str] = set()
        seen_pairs: set[tuple[str, str]] = set()
        for index, item in enumerate(_list(document.get("skus"), "config.skus")):
            raw = _mapping(item, f"config.skus[{index}]")
            sku = _text(raw.get("sku"), f"config.skus[{index}].sku")
            if sku in seen_skus:
                raise ModelError(f"duplicate owner SKU {sku!r}")
            seen_skus.add(sku)
            mappings = _mapping(
                raw.get("supplier_mappings"), f"config.skus[{index}].supplier_mappings"
            )
            checked: dict[str, str] = {}
            for supplier_id, supplier_sku_value in mappings.items():
                if supplier_id not in supplier_ids:
                    raise ModelError(f"SKU {sku!r} maps unknown supplier {supplier_id!r}")
                supplier_sku = _text(supplier_sku_value, "supplier SKU")
                pair = (supplier_id, supplier_sku)
                if pair in seen_pairs:
                    raise ModelError(f"ambiguous owner mapping {pair!r}")
                seen_pairs.add(pair)
                checked[supplier_id] = supplier_sku
            if not checked:
                raise ModelError(f"SKU {sku!r} has no approved supplier mapping")
            skus.append(
                SkuAuthority(
                    store_sku=sku,
                    hard_max=_integer(raw.get("hard_max"), f"{sku}.hard_max"),
                    max_unit_price=_decimal(
                        raw.get("max_unit_price_usd"),
                        f"{sku}.max_unit_price_usd",
                        positive=True,
                    ),
                    max_order_spend=_decimal(
                        raw.get("autonomous_order_limit_usd"),
                        f"{sku}.autonomous_order_limit_usd",
                        positive=True,
                    ),
                    max_lead_time_days=_integer(
                        raw.get("max_lead_time_days"),
                        f"{sku}.max_lead_time_days",
                        minimum=1,
                    ),
                    mappings=checked,
                )
            )
        return OwnerAuthority(
            store_id=store_id,
            destination_id=destination_id,
            supplier_ids=supplier_ids,
            skus=tuple(skus),
            world_dir=world,
            fixed_now=None,
        )

    def _assert_config_unchanged(self) -> None:
        try:
            digest = hashlib.sha256(self.config_path.read_bytes()).hexdigest()
        except OSError as exc:
            raise ModelError(f"owner configuration is unavailable: {exc}") from exc
        if digest != self.config_digest:
            raise ModelError("owner configuration changed after SafeMA startup")

    def _snapshot_time(
        self, document: dict[str, Any], now: datetime, where: str
    ) -> datetime:
        if "as_of" in document:
            instant = _instant(document["as_of"], f"{where}.as_of")
        elif "as_of_offset_seconds" in document:
            offset = document["as_of_offset_seconds"]
            if isinstance(offset, bool) or not isinstance(offset, int):
                raise ModelError(f"{where}.as_of_offset_seconds must be an integer")
            instant = now + timedelta(seconds=offset)
        else:
            raise ModelError(f"{where} has no snapshot timestamp evidence")
        if instant > now:
            raise ModelError(f"{where} snapshot is from the future")
        if now - instant > MAX_AGE:
            raise ModelError(f"{where} snapshot is stale")
        return instant

    def _sku_authority(self, supplier_id: str, supplier_sku: str) -> SkuAuthority:
        matches = [
            sku
            for sku in self.authority.skus
            if sku.mappings.get(supplier_id) == supplier_sku
        ]
        if len(matches) != 1:
            raise ModelError(
                f"actual ({supplier_id!r}, {supplier_sku!r}) resolves to "
                f"{len(matches)} approved store SKUs"
            )
        return matches[0]

    def _inventory(
        self, store_sku: str, now: datetime
    ) -> tuple[int, list[dict[str, Any]], dict[str, Any]]:
        document, _ = _read_json(
            self.authority.world_dir / "inventory.json", "Inventory Ledger"
        )
        if _text(document.get("store_id"), "inventory.store_id") != self.authority.store_id:
            raise ModelError("Inventory Ledger store identity disagrees with owner config")
        revision = _text(document.get("revision_id"), "inventory.revision_id")
        as_of = self._snapshot_time(document, now, "Inventory Ledger")
        matches = []
        for raw_item in _list(document.get("records"), "inventory.records"):
            raw = _mapping(raw_item, "inventory record")
            if raw.get("sku") == store_sku:
                matches.append(raw)
        if len(matches) != 1:
            raise ModelError(
                f"Inventory Ledger has {len(matches)} records for {store_sku!r}"
            )
        record = matches[0]
        required = {"store_id", "sku", "base_unit", "active", "on_hand"}
        if not required.issubset(record):
            raise ModelError(
                f"Inventory Ledger record for {store_sku!r} is missing "
                f"{sorted(required - set(record))}"
            )
        if record["store_id"] != self.authority.store_id or record["sku"] != store_sku:
            raise ModelError("Inventory Ledger record identity disagrees")
        if record["base_unit"] != "EACH":
            raise ModelError("Inventory Ledger base unit is not EACH")
        if record["active"] is not True:
            raise ModelError("Inventory Ledger SKU is not active")
        on_hand = _integer(record["on_hand"], "inventory.on_hand")
        receipts = _list(document.get("receipts"), "inventory.receipts")
        return on_hand, receipts, {
            "revision_id": revision,
            "as_of": as_of.isoformat(),
        }

    def _supplier_documents(
        self, now: datetime
    ) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        documents: dict[str, dict[str, Any]] = {}
        observed: dict[str, Any] = {}
        for supplier_id in self.authority.supplier_ids:
            path = self.authority.world_dir / f"supplier_{supplier_id}.json"
            document, _ = _read_json(path, f"{supplier_id} order service")
            if document.get("supplier_id") != supplier_id:
                raise ModelError(f"{supplier_id} document reports a different supplier")
            if document.get("destination_id") != self.authority.destination_id:
                raise ModelError(f"{supplier_id} document reports a different destination")
            if "snapshot_complete" not in document:
                raise ModelError(f"{supplier_id} snapshot has no completeness flag")
            if document["snapshot_complete"] is not True:
                raise ModelError(f"{supplier_id} snapshot is incomplete")
            as_of = self._snapshot_time(document, now, f"{supplier_id} order")
            _list(document.get("orders"), f"{supplier_id}.orders")
            documents[supplier_id] = document
            observed[supplier_id] = {
                "as_of": as_of.isoformat(),
                "complete": True,
            }
        return documents, observed

    def _outstanding(
        self,
        store_sku: str,
        receipts: list[dict[str, Any]],
        supplier_documents: dict[str, dict[str, Any]],
    ) -> tuple[int, list[dict[str, Any]]]:
        reverse = {
            (supplier_id, supplier_sku): sku.store_sku
            for sku in self.authority.skus
            for supplier_id, supplier_sku in sku.mappings.items()
        }
        orders: dict[tuple[str, str], dict[str, Any]] = {}
        target_keys: list[tuple[str, str]] = []
        for supplier_id, document in supplier_documents.items():
            for raw_item in document["orders"]:
                raw = _mapping(raw_item, f"{supplier_id} order")
                order_supplier = _text(raw.get("supplier_id"), "order.supplier_id")
                order_id = _text(raw.get("supplier_order_id"), "order.supplier_order_id")
                supplier_sku = _text(raw.get("supplier_sku"), "order.supplier_sku")
                destination = _text(raw.get("destination_id"), "order.destination_id")
                status = _text(raw.get("status"), "order.status")
                quantity = _integer(raw.get("quantity"), "order.quantity", minimum=1)
                if order_supplier != supplier_id or destination != self.authority.destination_id:
                    raise ModelError("supplier order identity disagrees with its snapshot")
                if status not in ORDER_STATUSES:
                    raise ModelError(f"supplier order has unknown status {status!r}")
                mapped = reverse.get((supplier_id, supplier_sku))
                if mapped is None:
                    raise ModelError(
                        f"supplier order {order_id!r} has no trusted SKU mapping"
                    )
                key = (supplier_id, order_id)
                if key in orders:
                    raise ModelError(f"duplicate supplier order identity {key!r}")
                orders[key] = {
                    "supplier_id": supplier_id,
                    "supplier_order_id": order_id,
                    "supplier_sku": supplier_sku,
                    "store_sku": mapped,
                    "status": status,
                    "quantity": quantity,
                }
                if mapped == store_sku:
                    target_keys.append(key)

        by_order: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for raw_item in receipts:
            raw = _mapping(raw_item, "receipt")
            receipt_sku = raw.get("sku")
            order_id = raw.get("supplier_order_id")
            supplier_id = raw.get("supplier_id")
            if not isinstance(receipt_sku, str) or not isinstance(order_id, str) or not isinstance(supplier_id, str):
                raise ModelError("receipt identity fields must be strings")
            key = (supplier_id, order_id)
            if key in orders:
                by_order.setdefault(key, []).append(raw)
                continue
            same_id = [
                order for candidate, order in orders.items()
                if candidate[1] == order_id and order["store_sku"] == receipt_sku
            ]
            if same_id:
                raise ModelError("receipt supplier identity disagrees with its order")

        total = 0
        contributing = []
        for key in target_keys:
            order = orders[key]
            matches = by_order.get(key, [])
            if len(matches) > 1:
                raise ModelError(f"order {key!r} has duplicate receipts")
            if matches:
                receipt = matches[0]
                required = {
                    "receipt_id", "store_id", "supplier_id", "supplier_order_id",
                    "sku", "quantity", "posted_at",
                }
                if not required.issubset(receipt):
                    raise ModelError("receipt is missing required identity or quantity fields")
                if receipt["store_id"] != self.authority.store_id:
                    raise ModelError("receipt store identity disagrees")
                if receipt["supplier_id"] != order["supplier_id"]:
                    raise ModelError("receipt supplier identity disagrees")
                if receipt["sku"] != order["store_sku"]:
                    raise ModelError("receipt SKU identity disagrees")
                quantity = _integer(receipt["quantity"], "receipt.quantity", minimum=1)
                if quantity != order["quantity"]:
                    raise ModelError("receipt quantity disagrees with order")
                _instant(receipt["posted_at"], "receipt.posted_at")
                if order["status"] == "CANCELLED":
                    raise ModelError("cancelled supplier order has a posted receipt")
                continue
            if order["status"] in OUTSTANDING_STATUSES:
                total += order["quantity"]
                contributing.append(order)
        return total, contributing

    def _offer(
        self,
        supplier_id: str,
        supplier_sku: str,
        document: dict[str, Any],
        now: datetime,
        sku: SkuAuthority,
    ) -> dict[str, Any]:
        offers = _mapping(document.get("offers"), f"{supplier_id}.offers")
        raw = _mapping(offers.get(supplier_sku), f"offer {supplier_id}/{supplier_sku}")
        price = _decimal(raw.get("unit_price"), "offer.unit_price", positive=True)
        pack = _integer(raw.get("pack_size"), "offer.pack_size", minimum=1)
        available = _integer(raw.get("available_quantity"), "offer.available_quantity")
        if available % pack:
            raise ModelError("offer availability is not a pack multiple")
        lead = _integer(raw.get("lead_time_days"), "offer.lead_time_days", minimum=1)
        valid_until = _instant(raw.get("valid_until"), "offer.valid_until")
        if valid_until <= now:
            raise ModelError("offer is expired")
        currency = raw.get("currency", "USD")
        if currency != "USD":
            raise ModelError("offer currency is not USD")
        return {
            "supplier_id": supplier_id,
            "destination_id": self.authority.destination_id,
            "store_sku": sku.store_sku,
            "unit_price": price,
            "pack_size": pack,
            "available_quantity": available,
            "lead_time_days": lead,
            "valid_until": valid_until.isoformat(),
            "currency": currency,
            "max_unit_price": sku.max_unit_price,
            "max_order_spend": sku.max_order_spend,
            "max_lead_time_days": sku.max_lead_time_days,
        }

    def resolve(self, effect: Effect) -> ResolvedMetadata:
        self._assert_config_unchanged()
        if effect.kind != "PURCHASE" or len(effect.resources) != 1 or len(effect.contexts) != 1:
            raise ModelError("resolver expected one-resource, one-context PURCHASE")
        supplier_id = _text(effect.attributes.get("supplier_id"), "effect.supplier_id")
        if supplier_id not in self.authority.supplier_ids:
            raise ModelError("effect supplier is not owner-approved")
        supplier_sku = _text(effect.resources[0].identity, "effect supplier SKU")
        if effect.resources[0].object_class != "supplier_sku":
            raise ModelError("effect resource is not a supplier SKU")
        destination = _text(effect.contexts[0].identity, "effect destination")
        if effect.contexts[0].object_class != "delivery_destination":
            raise ModelError("effect context is not a delivery destination")
        quantity = effect.attributes.get("proposed_quantity")
        if isinstance(quantity, bool) or not isinstance(quantity, int):
            raise ModelError("effect proposed quantity must be an integer")
        price = effect.attributes.get("expected_unit_price")
        if not isinstance(price, Decimal) or not price.is_finite():
            raise ModelError("effect expected price must be an exact Decimal")
        _text(effect.attributes.get("idempotency_key"), "effect idempotency key")

        sku = self._sku_authority(supplier_id, supplier_sku)
        now = self._now().astimezone(timezone.utc)
        on_hand, receipts, inventory_observed = self._inventory(sku.store_sku, now)
        supplier_documents, supplier_observed = self._supplier_documents(now)
        outstanding, contributing = self._outstanding(
            sku.store_sku, receipts, supplier_documents
        )
        offer = self._offer(
            supplier_id, supplier_sku, supplier_documents[supplier_id], now, sku
        )

        resources = (
            Resource(
                identity=supplier_sku,
                object_class="supplier_sku_mapping",
                attributes={"supplier_id": supplier_id, "store_sku": sku.store_sku},
            ),
            Resource(
                identity=sku.store_sku,
                object_class="inventory_exposure",
                attributes={
                    "store_id": self.authority.store_id,
                    "active": True,
                    "base_unit": "EACH",
                    "on_hand": on_hand,
                    "outstanding": outstanding,
                    "hard_max": sku.hard_max,
                },
            ),
            Resource(
                identity=supplier_sku,
                object_class="supplier_offer",
                attributes=offer,
            ),
        )
        contexts = (
            Context(
                identity=self.authority.destination_id,
                object_class="replenishment_destination_authority",
                attributes={"store_id": self.authority.store_id},
            ),
        )
        return ResolvedMetadata(
            resources=resources,
            contexts=contexts,
            observability={
                "owner_config_sha256": self.config_digest,
                "resolved_at": now.isoformat(),
                "actual_destination": destination,
                "store_sku": sku.store_sku,
                "inventory": inventory_observed,
                "suppliers": supplier_observed,
                "on_hand": on_hand,
                "outstanding": outstanding,
                "proposed_quantity": quantity,
                "hard_max": sku.hard_max,
                "exposure_after_order": on_hand + outstanding + quantity,
                "contributing_orders": contributing,
                "offer": offer,
            },
        )
