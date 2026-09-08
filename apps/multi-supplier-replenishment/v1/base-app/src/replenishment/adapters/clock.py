"""Clock adapters."""

from __future__ import annotations

from datetime import datetime, timezone


class SystemClock:
    """Wall-clock time, for real operation."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class FixedClock:
    """A clock that returns an injected instant.

    Used by the committed example configuration so that the demo is fully
    reproducible, and by tests so that no assertion depends on wall-clock time.
    """

    def __init__(self, instant: datetime) -> None:
        self.set(instant)

    def now(self) -> datetime:
        return self._instant

    def set(self, instant: datetime) -> None:
        if instant.tzinfo is None:
            raise ValueError("FixedClock requires a timezone-aware instant")
        self._instant = instant.astimezone(timezone.utc)

    def advance(self, **timedelta_kwargs: float) -> datetime:
        from datetime import timedelta

        self.set(self._instant + timedelta(**timedelta_kwargs))
        return self._instant
