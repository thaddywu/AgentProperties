"""Local supplier service.

This is an authoritative external system in its own right: it owns its offers,
its order identifiers, its order lifecycle, and its idempotency keys.  Its
state lives in the mock-world directory, never in the application database.
Every call — including calls that time out — is appended to a raw call log so
that an operator or a test can see exactly what the application asked for.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from ..decimals import money_str
from ..domain import (
    LookupFound,
    LookupNotFoundFinal,
    LookupResult,
    LookupUnknown,
    NotOffered,
    Offer,
    OrderAccepted,
    OrderRejected,
    OrderSnapshot,
    OrderStatus,
    PlaceOrderResult,
    PurchaseOrder,
)
from ..errors import (
    MalformedResponse,
    ServiceUnavailable,
    SupplierTimeout,
    SupplierTransportError,
)
from ..interfaces import Clock
from ..timeutil import TimestampFormatError, from_rfc3339, parse_date, to_rfc3339
from .world import WorldStore, supplier_doc


class LocalSupplierService:
    def __init__(self, world: WorldStore, clock: Clock, supplier_id: str) -> None:
        self._world = world
        self._clock = clock
        self.supplier_id = supplier_id
        self._document_name = supplier_doc(supplier_id)

    # -- world state -----------------------------------------------------

    def _read(self) -> dict[str, Any]:
        try:
            return self._world.read(self._document_name)
        except FileNotFoundError as exc:
            raise ServiceUnavailable(str(exc)) from exc
        except ValueError as exc:
            raise MalformedResponse(f"{self.supplier_id}: {exc}") from exc

    def _write(self, document: dict[str, Any]) -> None:
        self._world.write(self._document_name, document)

    def _timezone(self, document: dict[str, Any]) -> timezone | ZoneInfo:
        name = document.get("timezone")
        if isinstance(name, str) and name:
            return ZoneInfo(name)
        return timezone.utc

    def _log(
        self, method: str, arguments: dict[str, Any], outcome: str, detail: str = ""
    ) -> None:
        self._world.append_raw_call(
            self.supplier_id,
            {
                "supplier_id": self.supplier_id,
                "at": to_rfc3339(self._clock.now()),
                "method": method,
                "arguments": arguments,
                "outcome": outcome,
                "detail": detail,
            },
        )

    @staticmethod
    def _next_behavior(document: dict[str, Any], bucket: str, key: str) -> str:
        queues = document.setdefault(bucket, {})
        if not isinstance(queues, dict):
            raise MalformedResponse(f"{bucket} must be an object")
        queue = queues.get(key)
        if isinstance(queue, str):
            queue = [queue]
            queues[key] = queue
        if isinstance(queue, list) and queue:
            return str(queue.pop(0))
        return "default"

    # -- offers ----------------------------------------------------------

    def _parse_offer(
        self, supplier_sku: str, destination_id: str, raw: dict[str, Any]
    ) -> Offer:
        try:
            return Offer(
                supplier_id=self.supplier_id,
                supplier_sku=str(raw.get("supplier_sku", supplier_sku)),
                destination_id=str(raw.get("destination_id", destination_id)),
                unit_price=Decimal(str(raw["unit_price"])),
                pack_size=int(raw["pack_size"]),
                available_quantity=int(raw["available_quantity"]),
                lead_time_days=int(raw["lead_time_days"]),
                valid_until=from_rfc3339(raw["valid_until"], field="offer.valid_until"),
                currency=str(raw.get("currency", "USD")),
            )
        except (KeyError, TypeError, ValueError, InvalidOperation, TimestampFormatError) as exc:
            raise MalformedResponse(
                f"{self.supplier_id}: offer for {supplier_sku!r} is undecodable: {exc}"
            ) from exc

    def get_offer(self, supplier_sku: str, destination_id: str) -> Offer | NotOffered:
        arguments = {
            "supplier_sku": supplier_sku,
            "destination_id": destination_id,
        }
        try:
            document = self._read()
        except Exception as exc:
            self._log("get_offer", arguments, "ERROR", str(exc))
            raise
        failures = document.get("offer_failures", {})
        failure = failures.get(supplier_sku) if isinstance(failures, dict) else None
        if failure == "unavailable":
            self._log("get_offer", arguments, "ERROR", "offer service unavailable")
            raise ServiceUnavailable(
                f"{self.supplier_id}: the offer service is unavailable"
            )
        if failure == "malformed":
            self._log("get_offer", arguments, "ERROR", "undecodable offer")
            raise MalformedResponse(
                f"{self.supplier_id}: offer for {supplier_sku!r} is undecodable"
            )

        offers = document.get("offers", {})
        raw = offers.get(supplier_sku) if isinstance(offers, dict) else None
        if raw is None:
            self._log("get_offer", arguments, "NOT_OFFERED")
            return NotOffered(
                supplier_id=self.supplier_id,
                supplier_sku=supplier_sku,
                destination_id=destination_id,
            )
        offer = self._parse_offer(supplier_sku, destination_id, raw)
        self._log(
            "get_offer",
            arguments,
            "OFFER",
            f"unit_price={offer.unit_price} pack_size={offer.pack_size} "
            f"available={offer.available_quantity} lead_time_days={offer.lead_time_days}",
        )
        return offer

    # -- order state -----------------------------------------------------

    def _parse_order(self, raw: dict[str, Any]) -> PurchaseOrder:
        try:
            promised = raw.get("promised_delivery_date")
            return PurchaseOrder(
                supplier_id=str(raw.get("supplier_id", self.supplier_id)),
                supplier_order_id=str(raw["supplier_order_id"]),
                idempotency_key=str(raw.get("idempotency_key") or ""),
                destination_id=str(raw["destination_id"]),
                supplier_sku=str(raw["supplier_sku"]),
                quantity=int(raw["quantity"]),
                unit_price=Decimal(str(raw["unit_price"])),
                total_cost=Decimal(str(raw["total_cost"])),
                status=OrderStatus(str(raw["status"])),
                created_at=from_rfc3339(raw["created_at"], field="order.created_at"),
                promised_delivery_date=parse_date(promised) if promised else None,
                currency=str(raw.get("currency", "USD")),
            )
        except (KeyError, TypeError, ValueError, InvalidOperation, TimestampFormatError) as exc:
            raise MalformedResponse(
                f"{self.supplier_id}: a purchase order is undecodable: {exc}"
            ) from exc

    def _orders(self, document: dict[str, Any]) -> list[PurchaseOrder]:
        raw_orders = document.get("orders", [])
        if not isinstance(raw_orders, list):
            raise MalformedResponse(f"{self.supplier_id}: 'orders' must be a list")
        return [self._parse_order(raw) for raw in raw_orders]

    def get_order_snapshot(self, destination_id: str) -> OrderSnapshot:
        arguments = {"destination_id": destination_id}
        try:
            document = self._read()
        except Exception as exc:
            self._log("get_order_snapshot", arguments, "ERROR", str(exc))
            raise
        failure = document.get("snapshot_failure")
        if failure == "unavailable":
            self._log("get_order_snapshot", arguments, "ERROR", "snapshot unavailable")
            raise ServiceUnavailable(
                f"{self.supplier_id}: the order snapshot service is unavailable"
            )
        if failure == "malformed":
            self._log("get_order_snapshot", arguments, "ERROR", "undecodable snapshot")
            raise MalformedResponse(
                f"{self.supplier_id}: the order snapshot is undecodable"
            )

        offset = document.get("as_of_offset_seconds", 0)
        if not isinstance(offset, int):
            raise MalformedResponse(
                f"{self.supplier_id}: 'as_of_offset_seconds' must be an integer"
            )
        explicit = document.get("as_of")
        as_of = (
            from_rfc3339(explicit, field="order_snapshot.as_of")
            if explicit
            else self._clock.now() + timedelta(seconds=offset)
        )
        orders = tuple(
            order for order in self._orders(document)
            if order.destination_id == destination_id
        )
        complete = document.get("snapshot_complete", True)
        if not isinstance(complete, bool):
            raise MalformedResponse(
                f"{self.supplier_id}: 'snapshot_complete' must be a boolean"
            )
        self._log(
            "get_order_snapshot",
            arguments,
            "SNAPSHOT",
            f"orders={len(orders)} complete={complete}",
        )
        return OrderSnapshot(
            supplier_id=self.supplier_id,
            destination_id=destination_id,
            as_of=as_of,
            complete=complete,
            orders=orders,
        )

    # -- idempotency lookup ----------------------------------------------

    def lookup_by_idempotency_key(
        self, destination_id: str, key: str
    ) -> LookupResult:
        arguments = {"destination_id": destination_id, "idempotency_key": key}
        try:
            document = self._read()
        except Exception as exc:
            self._log("lookup_by_idempotency_key", arguments, "ERROR", str(exc))
            raise
        behavior = self._next_behavior(document, "lookup_behaviors", key)
        if behavior == "default":
            behavior = self._next_behavior(document, "lookup_behaviors", "*")
        self._write(document)

        if behavior == "unavailable":
            self._log("lookup_by_idempotency_key", arguments, "ERROR", "lookup unavailable")
            raise ServiceUnavailable(f"{self.supplier_id}: lookup is unavailable")
        if behavior == "unknown":
            self._log("lookup_by_idempotency_key", arguments, "UNKNOWN")
            return LookupUnknown("the supplier cannot decide")

        match = next(
            (
                order
                for order in self._orders(document)
                if order.idempotency_key == key
                and order.destination_id == destination_id
            ),
            None,
        )
        if behavior == "not_found_final":
            self._log("lookup_by_idempotency_key", arguments, "NOT_FOUND_FINAL")
            return LookupNotFoundFinal("the key created no order")
        if match is not None:
            self._log(
                "lookup_by_idempotency_key",
                arguments,
                "FOUND",
                f"supplier_order_id={match.supplier_order_id}",
            )
            return LookupFound(match)
        self._log("lookup_by_idempotency_key", arguments, "NOT_FOUND_FINAL")
        return LookupNotFoundFinal("the key created no order and can no longer do so")

    # -- placement -------------------------------------------------------

    def _create_order(
        self,
        document: dict[str, Any],
        *,
        supplier_sku: str,
        quantity: int,
        unit_price: Decimal,
        destination_id: str,
        idempotency_key: str,
        lead_time_days: int,
    ) -> PurchaseOrder:
        sequence = int(document.get("order_seq", 0)) + 1
        document["order_seq"] = sequence
        prefix = str(document.get("order_id_prefix", self.supplier_id))
        created_at = self._clock.now()
        local_today = created_at.astimezone(self._timezone(document)).date()
        promised = local_today + timedelta(days=lead_time_days)
        total = unit_price * quantity
        record = {
            "supplier_id": self.supplier_id,
            "supplier_order_id": f"{prefix}-PO-{sequence:04d}",
            "idempotency_key": idempotency_key,
            "destination_id": destination_id,
            "supplier_sku": supplier_sku,
            "quantity": quantity,
            "unit_price": money_str(unit_price),
            "total_cost": money_str(total),
            "status": OrderStatus.ACCEPTED.value,
            "created_at": to_rfc3339(created_at),
            "promised_delivery_date": promised.isoformat(),
            "currency": "USD",
        }
        document.setdefault("orders", []).append(record)
        offers = document.get("offers", {})
        if isinstance(offers, dict) and supplier_sku in offers:
            available = int(offers[supplier_sku].get("available_quantity", 0))
            offers[supplier_sku]["available_quantity"] = max(0, available - quantity)
        return self._parse_order(record)

    def place_order(
        self,
        supplier_sku: str,
        quantity: int,
        expected_unit_price: Decimal,
        destination_id: str,
        idempotency_key: str,
    ) -> PlaceOrderResult:
        """Consequential effect: create one purchase order at this supplier."""
        arguments = {
            "supplier_sku": supplier_sku,
            "quantity": quantity,
            "expected_unit_price": str(expected_unit_price),
            "destination_id": destination_id,
            "idempotency_key": idempotency_key,
        }
        try:
            document = self._read()
        except Exception as exc:
            self._log("place_order", arguments, "ERROR", str(exc))
            raise

        existing = next(
            (
                order
                for order in self._orders(document)
                if order.idempotency_key == idempotency_key
                and order.destination_id == destination_id
            ),
            None,
        )
        if existing is not None:
            self._log(
                "place_order",
                arguments,
                "ACCEPTED_IDEMPOTENT_REPLAY",
                f"supplier_order_id={existing.supplier_order_id}",
            )
            return OrderAccepted(existing)

        behavior = self._next_behavior(document, "place_order_behaviors", supplier_sku)
        if behavior == "default":
            behavior = self._next_behavior(document, "place_order_behaviors", "*")

        offers = document.get("offers", {})
        raw_offer = offers.get(supplier_sku) if isinstance(offers, dict) else None

        if behavior == "timeout":
            self._write(document)
            self._log("place_order", arguments, "TIMEOUT", "no order was created")
            raise SupplierTimeout(
                f"{self.supplier_id}: placement timed out for {supplier_sku!r}"
            )

        if raw_offer is None:
            self._write(document)
            self._log("place_order", arguments, "REJECTED", "NOT_OFFERED")
            return OrderRejected("NOT_OFFERED", f"{supplier_sku!r} is not offered")
        offer = self._parse_offer(supplier_sku, destination_id, raw_offer)

        if behavior.startswith("reject"):
            parts = behavior.split(":", 2)
            code = parts[1] if len(parts) > 1 else "REJECTED"
            message = parts[2] if len(parts) > 2 else "the supplier refused the order"
            self._write(document)
            self._log("place_order", arguments, "REJECTED", code)
            return OrderRejected(code, message)
        if offer.destination_id != destination_id:
            self._write(document)
            self._log("place_order", arguments, "REJECTED", "WRONG_DESTINATION")
            return OrderRejected("WRONG_DESTINATION", "the offer is for another destination")
        if expected_unit_price != offer.unit_price:
            self._write(document)
            self._log("place_order", arguments, "REJECTED", "PRICE_CHANGED")
            return OrderRejected(
                "PRICE_CHANGED",
                f"the current unit price is {offer.unit_price}, not {expected_unit_price}",
            )
        if quantity <= 0 or quantity % offer.pack_size != 0:
            self._write(document)
            self._log("place_order", arguments, "REJECTED", "INVALID_QUANTITY")
            return OrderRejected(
                "INVALID_QUANTITY",
                f"{quantity} is not a positive multiple of pack size {offer.pack_size}",
            )
        if quantity > offer.available_quantity:
            self._write(document)
            self._log("place_order", arguments, "REJECTED", "INSUFFICIENT_AVAILABILITY")
            return OrderRejected(
                "INSUFFICIENT_AVAILABILITY",
                f"only {offer.available_quantity} available",
            )

        order = self._create_order(
            document,
            supplier_sku=supplier_sku,
            quantity=quantity,
            unit_price=offer.unit_price,
            destination_id=destination_id,
            idempotency_key=idempotency_key,
            lead_time_days=offer.lead_time_days,
        )
        self._write(document)

        if behavior == "lost_response":
            self._log(
                "place_order",
                arguments,
                "LOST_RESPONSE",
                f"the order {order.supplier_order_id} was created but the response was lost",
            )
            raise SupplierTransportError(
                f"{self.supplier_id}: the connection was lost after dispatch"
            )
        if behavior == "contradictory":
            contradicted = PurchaseOrder(
                supplier_id=order.supplier_id,
                supplier_order_id=order.supplier_order_id,
                idempotency_key=order.idempotency_key,
                destination_id=order.destination_id,
                supplier_sku=order.supplier_sku,
                quantity=order.quantity + 1,
                unit_price=order.unit_price,
                total_cost=order.total_cost,
                status=order.status,
                created_at=order.created_at,
                promised_delivery_date=order.promised_delivery_date,
            )
            self._log(
                "place_order",
                arguments,
                "ACCEPTED_CONTRADICTORY",
                f"supplier_order_id={order.supplier_order_id}",
            )
            return OrderAccepted(contradicted)

        self._log(
            "place_order",
            arguments,
            "ACCEPTED",
            f"supplier_order_id={order.supplier_order_id}",
        )
        return OrderAccepted(order)
