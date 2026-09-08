"""The fixed enumerations of Application Specification section 4.

Version 1 deliberately has no wildcard, hierarchy, or ``OTHER`` member in any
of these enumerations.
"""

from __future__ import annotations

from enum import Enum

from .errors import ValidationError


class _StrEnum(str, Enum):
    """An enumeration whose members compare and serialize as their name."""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value

    @classmethod
    def parse(cls, value: object, field: str) -> "_StrEnum":
        """Return the member equal to ``value`` or raise :class:`ValidationError`."""
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise ValidationError(
                f"{field} must be one of {cls.choices()}, got {value!r}"
            )
        try:
            return cls(value)
        except ValueError:
            raise ValidationError(
                f"{field} must be one of {cls.choices()}, got {value!r}"
            ) from None

    @classmethod
    def choices(cls) -> str:
        return ", ".join(member.value for member in cls)


class Purpose(_StrEnum):
    """Specification 4.1. Compatibility is exact equality, nothing else."""

    PHD_APPLICATION = "PHD_APPLICATION"
    FELLOWSHIP = "FELLOWSHIP"


class Channel(_StrEnum):
    """Specification 4.2."""

    EMAIL = "EMAIL"
    PORTAL = "PORTAL"


class RequestStatus(_StrEnum):
    """Specification 4.3. ``SUBMITTED`` and ``CANCELLED`` are terminal."""

    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    CANCELLED = "CANCELLED"


class Outcome(_StrEnum):
    """The definitive outcome of an external attempt (specification 3.2/3.3)."""

    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class EventKind(_StrEnum):
    """The request-event kinds a request source may return (specification 3.1)."""

    ADD_REQUEST = "ADD_REQUEST"
    CANCEL_REQUEST = "CANCEL_REQUEST"
    REPLACE_REQUEST = "REPLACE_REQUEST"


class ReminderKind(_StrEnum):
    """Specification 5.4."""

    THREE_DAY = "THREE_DAY"
    ONE_DAY = "ONE_DAY"
