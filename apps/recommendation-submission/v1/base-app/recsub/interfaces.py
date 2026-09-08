"""The external interfaces the application depends on (specification 3).

Every one of these is a :class:`typing.Protocol`: an integration only has to
provide the listed operations, and any implementation can be replaced with a
local test double through configuration.  None of these components may touch
the application's SQLite database — they exchange data with the core through
call arguments and return values only.

One concrete integration may implement more than one protocol (for example a
portal integration that both scans requests and performs portal submissions);
from the application's perspective those remain separate responsibilities.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, Sequence, runtime_checkable

from .models import EmailMessage, ExternalResult, RequestEvent


@runtime_checkable
class RequestSource(Protocol):
    """A request-source agent that scans one external system."""

    @property
    def source_kind(self) -> str:
        """A short stable identifier for this source, such as ``"email_inbox"``."""

    def scan(self) -> Sequence[RequestEvent]:
        """Return the normalized request events currently visible to this agent.

        The agent may return events it has returned before; the application
        deduplicates by event ID.  The agent returns data only and never
        changes application state.
        """


@runtime_checkable
class EmailGateway(Protocol):
    """A gateway that sends one ordinary email message."""

    def send(self, message: EmailMessage) -> ExternalResult:
        """Send ``message`` and report a definitive ``SUCCEEDED``/``FAILED`` result.

        A successful result carries an external receipt such as a message
        identifier.  A failed result carries an error code or message and means
        the gateway did not complete the send.
        """


@runtime_checkable
class PortalAgent(Protocol):
    """A portal automation agent that performs one portal submission."""

    def submit(
        self,
        *,
        correlation_id: str,
        submission_url: str,
        file_path: str,
    ) -> ExternalResult:
        """Upload ``file_path`` to ``submission_url`` for one request.

        ``correlation_id`` is the application request ID, used for logging.  A
        successful result means the agent observed an explicit portal
        confirmation.
        """


@runtime_checkable
class Clock(Protocol):
    """A replaceable source of the current time."""

    def now(self) -> datetime:
        """Return the current time as a timezone-aware datetime."""


class SystemClock:
    """The default clock, reading real UTC time."""

    def now(self) -> datetime:
        from datetime import timezone

        return datetime.now(timezone.utc)


def system_clock() -> SystemClock:
    """Configuration factory for :class:`SystemClock`."""
    return SystemClock()
