"""Local Calendar/Holiday Service.

The service assigns exactly one demand-day label per local date.  It never
chooses a multiplier; the owner configuration does that.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from ..domain import CalendarDay, CalendarLabel
from ..errors import MalformedResponse, ServiceUnavailable
from ..timeutil import TimestampFormatError, parse_date
from .world import CALENDAR_DOC, WorldStore


class LocalCalendarService:
    def __init__(self, world: WorldStore) -> None:
        self._world = world

    def _document(self) -> dict[str, Any]:
        try:
            return self._world.read(CALENDAR_DOC)
        except FileNotFoundError as exc:
            raise ServiceUnavailable(str(exc)) from exc
        except ValueError as exc:
            raise MalformedResponse(f"calendar service: {exc}") from exc

    def get_days(
        self, store_id: str, start_date: date, end_date: date
    ) -> list[CalendarDay]:
        document = self._document()
        failure = document.get("failure")
        if failure == "unavailable":
            raise ServiceUnavailable("calendar service is unavailable")
        if failure == "malformed":
            raise MalformedResponse("calendar service returned undecodable data")
        if failure is not None:
            raise MalformedResponse(f"calendar service: unknown failure mode {failure!r}")

        days = document.get("days", {})
        if isinstance(days, dict):
            items: list[tuple[Any, Any]] = list(days.items())
        elif isinstance(days, list):
            items = []
            for entry in days:
                if not isinstance(entry, dict) or "date" not in entry:
                    raise MalformedResponse(
                        "calendar service: a day record is not an object with a date"
                    )
                items.append((entry["date"], entry.get("label")))
        else:
            raise MalformedResponse(
                "calendar service: 'days' must be an object or a list"
            )
        document_store = document.get("store_id", store_id)
        records: list[CalendarDay] = []
        for raw_day, raw_label in items:
            try:
                day = parse_date(raw_day, field="calendar.date")
            except TimestampFormatError as exc:
                raise MalformedResponse(f"calendar service: {exc}") from exc
            if not (start_date <= day <= end_date):
                continue
            if not isinstance(raw_label, str):
                raise MalformedResponse(
                    f"calendar service: label for {day} is not a string"
                )
            try:
                label = CalendarLabel(raw_label)
            except ValueError as exc:
                raise MalformedResponse(
                    f"calendar service: {raw_label!r} for {day} is not a recognized "
                    "demand-day label"
                ) from exc
            records.append(
                CalendarDay(store_id=str(document_store), day=day, label=label)
            )
        records.sort(key=lambda item: item.day)
        return records
