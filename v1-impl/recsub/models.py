"""Value objects exchanged with external components and stored records.

Nothing in this module touches the database; the repository layer converts
between these objects and SQLite rows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence

from .enums import Channel, EventKind, Outcome, Purpose, ReminderKind, RequestStatus

# --------------------------------------------------------------------------
# Data returned by request-source agents (specification 3.1)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class NewRequest:
    """The complete set of request fields carried by an add or replacement event."""

    source_reference: str
    applicant_name: str
    application_description: str
    purpose: str
    channel: str
    destination: str
    deadline: str


@dataclass(frozen=True)
class RequestEvent:
    """One normalized request event.

    ``event_id`` is stable for the external change it describes, so the
    application can ignore an event it has already applied.
    """

    event_id: str
    source_kind: str
    kind: str
    #: Present for ``ADD_REQUEST`` and ``REPLACE_REQUEST``.
    new_request: Optional[NewRequest] = None
    #: Present for ``CANCEL_REQUEST`` and ``REPLACE_REQUEST``; identifies the
    #: existing request.  ``target_source_kind`` defaults to ``source_kind``.
    target_source_kind: Optional[str] = None
    target_source_reference: Optional[str] = None


# --------------------------------------------------------------------------
# Results returned by the email gateway and the portal automation agent
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ExternalResult:
    """A definitive external outcome (specification 3.2 and 3.3).

    Version 1 assumes external components always report one of exactly two
    outcomes; there is no ``UNKNOWN`` member.
    """

    outcome: Outcome
    receipt: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    @classmethod
    def succeeded(cls, receipt: str) -> "ExternalResult":
        return cls(outcome=Outcome.SUCCEEDED, receipt=receipt)

    @classmethod
    def failed(cls, error_code: str, error_message: str = "") -> "ExternalResult":
        return cls(
            outcome=Outcome.FAILED,
            error_code=error_code,
            error_message=error_message,
        )

    @property
    def ok(self) -> bool:
        return self.outcome is Outcome.SUCCEEDED


@dataclass(frozen=True)
class EmailMessage:
    """An ordinary email message handed to the gateway.

    The application always constructs this object inside the policy guard, so
    the recipients and attachments of every outbound message are decided in
    one place.
    """

    to: Sequence[str]
    cc: Sequence[str]
    subject: str
    body: str
    attachments: Sequence[str]
    correlation_id: str


# --------------------------------------------------------------------------
# Stored records (specification 5)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Request:
    request_id: str
    applicant_name: str
    application_description: str
    purpose: Purpose
    channel: Channel
    destination: str
    deadline: str  # canonical UTC storage string
    status: RequestStatus
    source_kind: str
    source_reference: str
    supersedes_request_id: Optional[str]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class Letter:
    letter_id: str
    file_path: str
    applicant_name: str
    purpose: Purpose
    registered_at: str


@dataclass(frozen=True)
class Submission:
    submission_id: str
    request_id: str
    letter_id: Optional[str]
    attempted_at: str
    channel: Channel
    outcome: Outcome
    receipt: Optional[str]
    error_code: Optional[str]
    error_message: Optional[str]


@dataclass(frozen=True)
class Reminder:
    reminder_id: str
    request_id: str
    reminder_kind: ReminderKind
    attempted_at: str
    outcome: Outcome
    receipt: Optional[str]
    error_code: Optional[str]
    error_message: Optional[str]


# --------------------------------------------------------------------------
# Operation reports returned to the CLI
# --------------------------------------------------------------------------


@dataclass
class SyncReport:
    """What one synchronization run did, including every problem it survived."""

    scanned_sources: int = 0
    events_seen: int = 0
    applied: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class ProcessReport:
    attempted: list[str] = field(default_factory=list)
    succeeded: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class ReminderReport:
    sent: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class DailyRunReport:
    sync: SyncReport
    process: ProcessReport
    reminders: ReminderReport
    errors: list[str] = field(default_factory=list)


EventLike = RequestEvent | Mapping[str, object]
