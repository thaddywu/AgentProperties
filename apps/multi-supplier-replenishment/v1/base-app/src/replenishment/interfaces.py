"""Explicit boundaries to every external system this application reads or calls.

Adapters raise :mod:`replenishment.errors` exceptions for transport and
availability problems.  They return domain values for anything the external
system answered, including refusals such as ``NotOffered`` and ``OrderRejected``.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Protocol, Sequence, runtime_checkable

from .domain import (
    CalendarDay,
    DailySales,
    InventorySnapshot,
    LookupResult,
    Offer,
    NotOffered,
    OrderSnapshot,
    PlaceOrderResult,
    Receipt,
)


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime:
        """Return one timezone-aware instant."""


@runtime_checkable
class InventoryLedger(Protocol):
    def get_snapshot(self, store_id: str, skus: Sequence[str]) -> InventorySnapshot:
        """Return one atomic ledger snapshot for the requested SKUs."""

    def get_receipts(
        self, store_id: str, supplier_id: str, order_ids: Sequence[str]
    ) -> list[Receipt]:
        """Return every posted receipt for the requested supplier order IDs."""


@runtime_checkable
class SalesHistory(Protocol):
    def get_daily_sales(
        self, store_id: str, sku: str, start_date: date, end_date: date
    ) -> list[DailySales]:
        """Return completed POS sales for an inclusive local business-date range."""


@runtime_checkable
class CalendarService(Protocol):
    def get_days(
        self, store_id: str, start_date: date, end_date: date
    ) -> list[CalendarDay]:
        """Return one demand-day label for each date in an inclusive range."""


@runtime_checkable
class SupplierService(Protocol):
    supplier_id: str

    def get_offer(self, supplier_sku: str, destination_id: str) -> Offer | NotOffered:
        """Return the supplier's current offer for one supplier SKU."""

    def get_order_snapshot(self, destination_id: str) -> OrderSnapshot:
        """Return a complete view of orders affecting the destination's exposure."""

    def lookup_by_idempotency_key(
        self, destination_id: str, key: str
    ) -> LookupResult:
        """Resolve whether an idempotency key created an order."""

    def place_order(
        self,
        supplier_sku: str,
        quantity: int,
        expected_unit_price: Decimal,
        destination_id: str,
        idempotency_key: str,
    ) -> PlaceOrderResult:
        """Consequential effect: submit one new purchase order to the supplier."""
