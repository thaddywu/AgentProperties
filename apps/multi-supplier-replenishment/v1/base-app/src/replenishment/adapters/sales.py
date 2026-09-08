"""Local POS Sales History.

A zero is observed zero demand.  A date that is simply absent is unknown and is
never replaced with a zero by this adapter or by the application.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from ..domain import DailySales
from ..errors import MalformedResponse, ServiceUnavailable
from ..timeutil import TimestampFormatError, parse_date
from .world import SALES_DOC, WorldStore


class LocalSalesHistory:
    def __init__(self, world: WorldStore) -> None:
        self._world = world

    def _document(self) -> dict[str, Any]:
        try:
            return self._world.read(SALES_DOC)
        except FileNotFoundError as exc:
            raise ServiceUnavailable(str(exc)) from exc
        except ValueError as exc:
            raise MalformedResponse(f"sales history: {exc}") from exc

    def get_daily_sales(
        self, store_id: str, sku: str, start_date: date, end_date: date
    ) -> list[DailySales]:
        document = self._document()
        failures = document.get("failures", {})
        failure = failures.get(sku) if isinstance(failures, dict) else None
        if failure == "unavailable":
            raise ServiceUnavailable(f"sales history is unavailable for {sku}")
        if failure == "malformed":
            raise MalformedResponse(f"sales history returned undecodable data for {sku}")
        if failure is not None:
            raise MalformedResponse(f"sales history: unknown failure mode {failure!r}")

        entries = document.get("sales", {}).get(sku)
        if entries is None:
            return []
        records: list[DailySales] = []
        document_store = document.get("store_id", store_id)
        if isinstance(entries, dict):
            items = [
                {"date": day, "units_sold": units} for day, units in entries.items()
            ]
        elif isinstance(entries, list):
            items = entries
        else:
            raise MalformedResponse(
                f"sales history: entries for {sku} must be an object or a list"
            )
        for raw in items:
            if not isinstance(raw, dict):
                raise MalformedResponse(
                    f"sales history: a record for {sku} is not an object"
                )
            try:
                day = parse_date(raw["date"], field="sales.date")
                units = raw["units_sold"]
            except (KeyError, TimestampFormatError) as exc:
                raise MalformedResponse(
                    f"sales history: a record for {sku} is undecodable: {exc}"
                ) from exc
            if isinstance(units, bool) or not isinstance(units, int):
                raise MalformedResponse(
                    f"sales history: units_sold {units!r} for {sku} on {day} is not an integer"
                )
            if not (start_date <= day <= end_date):
                continue
            records.append(
                DailySales(
                    store_id=str(raw.get("store_id", document_store)),
                    sku=str(raw.get("sku", sku)),
                    business_date=day,
                    units_sold=units,
                )
            )
        records.sort(key=lambda item: item.business_date)
        return records
