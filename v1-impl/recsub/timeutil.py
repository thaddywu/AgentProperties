"""Time parsing and formatting helpers.

The application stores every instant as a UTC RFC 3339 string in a single
fixed format (``YYYY-MM-DDTHH:MM:SSZ``, or with a fractional part) so that
lexicographic ordering in SQLite matches chronological ordering.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from .errors import ValidationError

#: RFC 3339 date-time with a mandatory explicit UTC offset.  A bare date, a
#: date-time without an offset, or a space-separated form is rejected.
_RFC3339 = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})"
    r"[Tt]"
    r"(?P<time>\d{2}:\d{2}:\d{2}(?:\.\d+)?)"
    r"(?P<offset>[Zz]|[+-]\d{2}:\d{2})$"
)


def parse_rfc3339(value: object, field: str = "timestamp") -> datetime:
    """Parse an RFC 3339 timestamp with an explicit offset into an aware UTC datetime.

    Specification 5.1 requires an explicit UTC offset; a date without a time
    zone is invalid.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValidationError(f"{field} must carry an explicit UTC offset")
        return value.astimezone(timezone.utc)
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be an RFC 3339 timestamp string")
    text = value.strip()
    if not _RFC3339.match(text):
        raise ValidationError(
            f"{field} must be an RFC 3339 timestamp with an explicit UTC offset "
            f"(for example 2026-12-01T23:59:00-05:00 or 2026-12-02T04:59:00Z), "
            f"got {value!r}"
        )
    normalized = text[:-1] + "+00:00" if text[-1] in "Zz" else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:  # calendar-invalid dates such as 2026-02-30
        raise ValidationError(f"{field} is not a valid date-time: {value!r}") from exc
    return parsed.astimezone(timezone.utc)


def to_storage(moment: datetime) -> str:
    """Render an aware datetime as the canonical UTC storage string."""
    if moment.tzinfo is None:
        raise ValidationError("cannot store a naive datetime")
    utc = moment.astimezone(timezone.utc)
    text = utc.isoformat(timespec="microseconds" if utc.microsecond else "seconds")
    return text.replace("+00:00", "Z")


def from_storage(text: str) -> datetime:
    """Read back a canonical UTC storage string."""
    return parse_rfc3339(text, "stored timestamp")


def for_display(text: str, tz) -> str:
    """Render a stored UTC timestamp in the configured display time zone."""
    return from_storage(text).astimezone(tz).isoformat(timespec="seconds")
