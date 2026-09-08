"""Timestamp and business-date helpers.

Persisted timestamps are RFC 3339 in UTC.  Business dates come from the
configured store time zone.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo


class TimestampFormatError(ValueError):
    """A timestamp string was not a usable RFC 3339 instant."""


def to_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        raise TimestampFormatError("naive datetimes are not accepted")
    return moment.astimezone(timezone.utc)


def to_rfc3339(moment: datetime) -> str:
    return to_utc(moment).isoformat(timespec="microseconds").replace("+00:00", "Z")


def from_rfc3339(raw: object, *, field: str = "timestamp") -> datetime:
    if not isinstance(raw, str) or not raw.strip():
        raise TimestampFormatError(f"{field}: expected an RFC 3339 timestamp")
    text = raw.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except ValueError as exc:
        raise TimestampFormatError(f"{field}: {raw!r} is not RFC 3339: {exc}") from exc
    if moment.tzinfo is None:
        raise TimestampFormatError(f"{field}: {raw!r} has no UTC offset")
    return moment.astimezone(timezone.utc)


def parse_date(raw: object, *, field: str = "date") -> date:
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    if not isinstance(raw, str):
        raise TimestampFormatError(f"{field}: expected a YYYY-MM-DD date")
    try:
        return date.fromisoformat(raw.strip())
    except ValueError as exc:
        raise TimestampFormatError(f"{field}: {raw!r} is not YYYY-MM-DD") from exc


def business_date(moment: datetime, tz: ZoneInfo) -> date:
    return moment.astimezone(tz).date()


def date_range(start: date, end: date) -> list[date]:
    """Inclusive list of calendar dates from ``start`` through ``end``."""
    if end < start:
        return []
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]
