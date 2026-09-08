"""Candidate feasibility and the deterministic supplier ranking of Section 8."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Sequence

from .config import SkuConfig
from .domain import CURRENCY, Offer
from .planning import SupplierPlan, StockoutProjection


@dataclass(frozen=True)
class OfferExclusion:
    """A supplier that cannot be considered, and exactly why."""

    supplier_id: str
    supplier_sku: str | None
    kind: str
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {
            "supplier_id": self.supplier_id,
            "supplier_sku": self.supplier_sku,
            "kind": self.kind,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class Candidate:
    supplier_id: str
    supplier_sku: str
    offer: Offer
    plan: SupplierPlan
    total_cost: Decimal
    limit_failures: tuple[str, ...]
    projection: StockoutProjection | None = None

    @property
    def executable(self) -> bool:
        return not self.limit_failures

    @property
    def avoids_stockout(self) -> bool:
        return self.projection is not None and self.projection.avoids_stockout

    def as_dict(self) -> dict[str, object]:
        return {
            "supplier_id": self.supplier_id,
            "supplier_sku": self.supplier_sku,
            "unit_price_usd": str(self.offer.unit_price),
            "pack_size": self.offer.pack_size,
            "available_quantity": self.offer.available_quantity,
            "lead_time_days": self.offer.lead_time_days,
            "offer_valid_until": self.offer.valid_until.isoformat(),
            "coverage_days": self.plan.coverage_days,
            "coverage_forecast": str(self.plan.coverage_forecast),
            "target_inventory": self.plan.target_inventory,
            "on_hand": self.plan.on_hand,
            "outstanding_quantity": self.plan.outstanding_quantity,
            "inventory_position": self.plan.inventory_position,
            "raw_requirement": self.plan.raw_requirement,
            "order_quantity": self.plan.order_quantity,
            "exposure_after_order": self.plan.exposure_after_order,
            "total_cost_usd": str(self.total_cost),
            "executable": self.executable,
            "limit_failures": list(self.limit_failures),
            "avoids_projected_stockout": self.avoids_stockout,
            "projection": (
                {
                    "arrival_date": self.projection.arrival_date.isoformat(),
                    "expected_demand_before_arrival": (
                        self.projection.expected_demand_before_arrival
                    ),
                    "expected_supply_before_arrival": (
                        self.projection.expected_supply_before_arrival
                    ),
                }
                if self.projection is not None
                else None
            ),
        }


def check_offer_usable(
    offer: Offer,
    *,
    supplier_id: str,
    supplier_sku: str,
    destination_id: str,
    run_started_at: datetime,
) -> list[str]:
    """Identity, validity, and type conditions that make an offer usable at all."""
    problems: list[str] = []
    if offer.supplier_id != supplier_id:
        problems.append(
            f"offer reports supplier {offer.supplier_id!r}, expected {supplier_id!r}"
        )
    if offer.supplier_sku != supplier_sku:
        problems.append(
            f"offer is for supplier SKU {offer.supplier_sku!r}, expected "
            f"{supplier_sku!r}"
        )
    if offer.destination_id != destination_id:
        problems.append(
            f"offer is for destination {offer.destination_id!r}, expected "
            f"{destination_id!r}"
        )
    if offer.currency != CURRENCY:
        problems.append(f"offer currency {offer.currency!r} is not {CURRENCY}")
    if not isinstance(offer.unit_price, Decimal) or offer.unit_price <= 0:
        problems.append(f"offer unit price {offer.unit_price!r} is not a positive USD amount")
    elif offer.unit_price.as_tuple().exponent != -2:
        problems.append(
            f"offer unit price {offer.unit_price} does not have exactly two decimals"
        )
    if not isinstance(offer.pack_size, int) or offer.pack_size <= 0:
        problems.append(f"offer pack size {offer.pack_size!r} is not a positive integer")
    if (
        not isinstance(offer.available_quantity, int)
        or offer.available_quantity < 0
    ):
        problems.append(
            f"offer available quantity {offer.available_quantity!r} is not a "
            "non-negative integer"
        )
    if not isinstance(offer.lead_time_days, int) or offer.lead_time_days <= 0:
        problems.append(
            f"offer lead time {offer.lead_time_days!r} is not a positive number of days"
        )
    if offer.valid_until <= run_started_at:
        problems.append(
            f"offer expired at {offer.valid_until.isoformat()} before the run started"
        )
    return problems


def owner_limit_failures(
    *,
    sku_config: SkuConfig,
    offer: Offer,
    plan: SupplierPlan,
    total_cost: Decimal,
) -> list[str]:
    """Owner purchasing limits.  Failing one of these is an escalation, not an error."""
    failures: list[str] = []
    if offer.unit_price > sku_config.max_unit_price_usd:
        failures.append(
            f"unit price {offer.unit_price} exceeds the configured maximum "
            f"{sku_config.max_unit_price_usd}"
        )
    if total_cost > sku_config.autonomous_order_limit_usd:
        failures.append(
            f"order total {total_cost} exceeds the autonomous per-order spend limit "
            f"{sku_config.autonomous_order_limit_usd}"
        )
    if plan.exposure_after_order > sku_config.hard_max:
        failures.append(
            f"inventory exposure after the order ({plan.exposure_after_order}) exceeds "
            f"hard_max {sku_config.hard_max}"
        )
    return failures


def rank_candidates(candidates: Sequence[Candidate]) -> list[Candidate]:
    """Return executable candidates in the exact order of Section 8.

    Candidates that avoid projected stockout displace those that do not; the
    surviving set is ranked by the path that applies to it.
    """
    executable = [candidate for candidate in candidates if candidate.executable]
    if not executable:
        return []
    avoiding = [candidate for candidate in executable if candidate.avoids_stockout]
    if avoiding:
        return sorted(
            avoiding,
            key=lambda item: (
                item.total_cost,
                item.offer.lead_time_days,
                item.offer.unit_price,
                item.supplier_id,
            ),
        )
    return sorted(
        executable,
        key=lambda item: (
            item.offer.lead_time_days,
            item.total_cost,
            item.offer.unit_price,
            item.supplier_id,
        ),
    )
