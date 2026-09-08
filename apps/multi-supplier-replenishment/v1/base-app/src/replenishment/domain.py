"""Value types shared by the application and its external adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum


class CalendarLabel(str, Enum):
    NORMAL = "NORMAL"
    WEEKEND = "WEEKEND"
    PRE_HOLIDAY = "PRE_HOLIDAY"
    HOLIDAY = "HOLIDAY"


ALL_CALENDAR_LABELS: tuple[CalendarLabel, ...] = tuple(CalendarLabel)

BASE_UNIT = "EACH"
CURRENCY = "USD"

SUPPLIER_A = "SUPPLIER_A"
SUPPLIER_B = "SUPPLIER_B"
SUPPLIER_IDS: tuple[str, ...] = (SUPPLIER_A, SUPPLIER_B)


class OrderStatus(str, Enum):
    ACCEPTED = "ACCEPTED"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


class TriggerKind(str, Enum):
    SCHEDULED = "SCHEDULED"
    MANUAL = "MANUAL"


class RunStatus(str, Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_EXCEPTIONS = "COMPLETED_WITH_EXCEPTIONS"
    FAILED = "FAILED"


class DecisionOutcome(str, Enum):
    NO_ORDER_NEEDED = "NO_ORDER_NEEDED"
    ORDER_ACCEPTED = "ORDER_ACCEPTED"
    SUPPLIER_REJECTED = "SUPPLIER_REJECTED"
    BLOCKED_UNKNOWN_ATTEMPT = "BLOCKED_UNKNOWN_ATTEMPT"
    DATA_ERROR = "DATA_ERROR"
    NO_FEASIBLE_SUPPLIER = "NO_FEASIBLE_SUPPLIER"
    ESCALATION_REQUIRED = "ESCALATION_REQUIRED"
    ORDER_OUTCOME_UNKNOWN = "ORDER_OUTCOME_UNKNOWN"


#: Outcomes that make a run end as COMPLETED_WITH_EXCEPTIONS.
EXCEPTION_OUTCOMES: frozenset[DecisionOutcome] = frozenset(
    {
        DecisionOutcome.SUPPLIER_REJECTED,
        DecisionOutcome.BLOCKED_UNKNOWN_ATTEMPT,
        DecisionOutcome.DATA_ERROR,
        DecisionOutcome.NO_FEASIBLE_SUPPLIER,
        DecisionOutcome.ESCALATION_REQUIRED,
        DecisionOutcome.ORDER_OUTCOME_UNKNOWN,
    }
)


class AttemptState(str, Enum):
    DISPATCHING = "DISPATCHING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"


class LookupOutcome(str, Enum):
    FOUND = "FOUND"
    NOT_FOUND_FINAL = "NOT_FOUND_FINAL"
    UNKNOWN = "UNKNOWN"


# --------------------------------------------------------------------------
# Inventory Ledger
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class InventoryRecord:
    store_id: str
    sku: str
    base_unit: str
    active: bool
    on_hand: int


@dataclass(frozen=True)
class MalformedRecord:
    """A record the adapter could not decode into a typed value."""

    sku: str | None
    problem: str


@dataclass(frozen=True)
class InventorySnapshot:
    revision_id: str
    as_of: datetime
    records: tuple[InventoryRecord, ...]
    #: Requested SKUs whose ledger record could not be decoded at all.  Their
    #: SKUs are unusable for the run; they are never treated as missing or zero.
    malformed: tuple[MalformedRecord, ...] = ()


@dataclass(frozen=True)
class Receipt:
    receipt_id: str
    store_id: str
    supplier_id: str
    supplier_order_id: str
    sku: str
    quantity: int
    posted_at: datetime


# --------------------------------------------------------------------------
# POS Sales History and Calendar
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DailySales:
    store_id: str
    sku: str
    business_date: date
    units_sold: int


@dataclass(frozen=True)
class CalendarDay:
    store_id: str
    day: date
    label: CalendarLabel


# --------------------------------------------------------------------------
# Suppliers
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Offer:
    supplier_id: str
    supplier_sku: str
    destination_id: str
    unit_price: Decimal
    pack_size: int
    available_quantity: int
    lead_time_days: int
    valid_until: datetime
    currency: str = CURRENCY


@dataclass(frozen=True)
class NotOffered:
    supplier_id: str
    supplier_sku: str
    destination_id: str
    reason: str = "NOT_OFFERED"


@dataclass(frozen=True)
class PurchaseOrder:
    """An authoritative supplier purchase order.

    ``store_sku`` is the application's resolution of ``supplier_sku`` through
    the owner's supplier mapping.  A supplier does not know store SKU identity,
    so adapters leave it ``None`` and the application fills it in.
    """

    supplier_id: str
    supplier_order_id: str
    idempotency_key: str
    destination_id: str
    supplier_sku: str
    quantity: int
    unit_price: Decimal
    total_cost: Decimal
    status: OrderStatus
    created_at: datetime
    promised_delivery_date: date | None
    store_sku: str | None = None
    currency: str = CURRENCY

    def with_store_sku(self, store_sku: str | None) -> "PurchaseOrder":
        return PurchaseOrder(
            supplier_id=self.supplier_id,
            supplier_order_id=self.supplier_order_id,
            idempotency_key=self.idempotency_key,
            destination_id=self.destination_id,
            supplier_sku=self.supplier_sku,
            quantity=self.quantity,
            unit_price=self.unit_price,
            total_cost=self.total_cost,
            status=self.status,
            created_at=self.created_at,
            promised_delivery_date=self.promised_delivery_date,
            store_sku=store_sku,
            currency=self.currency,
        )


@dataclass(frozen=True)
class OrderSnapshot:
    supplier_id: str
    destination_id: str
    as_of: datetime
    complete: bool
    orders: tuple[PurchaseOrder, ...] = field(default=())


@dataclass(frozen=True)
class OrderAccepted:
    """A supplier confirmed that it created the order."""

    order: PurchaseOrder


@dataclass(frozen=True)
class OrderRejected:
    """A supplier definitively refused; no order exists."""

    code: str
    message: str = ""


PlaceOrderResult = OrderAccepted | OrderRejected


@dataclass(frozen=True)
class LookupFound:
    order: PurchaseOrder


@dataclass(frozen=True)
class LookupNotFoundFinal:
    message: str = ""


@dataclass(frozen=True)
class LookupUnknown:
    message: str = ""


LookupResult = LookupFound | LookupNotFoundFinal | LookupUnknown
