"""The core application operations (specification 6).

This module orchestrates: it validates, persists, matches, and decides *what*
should be disclosed.  It never calls the email gateway or the portal agent
itself — every external disclosure is requested from :class:`.policy.PolicyGuard`,
which independently re-checks the Safety Policy and composes the outbound
message.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Sequence

from .config import AppConfig, Components
from .db import connect
from .enums import Channel, Outcome, Purpose, ReminderKind, RequestStatus
from .errors import (
    NotFoundError,
    PolicyViolation,
    RecSubError,
    StateError,
    ValidationError,
)
from .models import (
    DailyRunReport,
    ExternalResult,
    Letter,
    ProcessReport,
    Reminder,
    ReminderReport,
    Request,
    RequestEvent,
    Submission,
    SyncReport,
)
from .policy import PolicyGuard
from .repository import Repository
from .timeutil import to_storage
from .validation import (
    is_regular_file,
    require_text,
    validate_applicant_name,
    validate_event,
)

THREE_DAY_WINDOW = timedelta(hours=72)
ONE_DAY_WINDOW = timedelta(hours=24)

#: Recorded when the selected letter's file has disappeared or is not a regular
#: file; the application records the failure without contacting anything.
LETTER_FILE_MISSING = "LETTER_FILE_MISSING"


class Application:
    """The single-user recommendation submission application."""

    def __init__(
        self,
        *,
        repository: Repository,
        components: Components,
        config: AppConfig,
    ) -> None:
        self.config = config
        self.repository = repository
        self.components = components
        self.clock = components.clock
        self.timezone = config.timezone
        self.guard = PolicyGuard(
            repository=repository,
            email_gateway=components.email_gateway,
            portal_agent=components.portal_agent,
            professor_email=config.professor_email,
            display_timezone=self.timezone,
        )

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def open(cls, config: AppConfig, components: Components) -> "Application":
        return cls(
            repository=Repository(connect(config.database_path)),
            components=components,
            config=config,
        )

    def close(self) -> None:
        self.repository.close()

    def __enter__(self) -> "Application":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def _now(self) -> str:
        moment = self.clock.now()
        if not isinstance(moment, datetime):
            raise RecSubError("the configured clock did not return a datetime")
        if moment.tzinfo is None:
            raise RecSubError("the configured clock returned a naive datetime")
        return to_storage(moment)

    # ------------------------------------------------------------------
    # 6.1 Ingest requests
    # ------------------------------------------------------------------

    def sync(self) -> SyncReport:
        """Scan every configured request source and apply the events it returns.

        One invalid event or one failing source agent is reported but never
        prevents valid events from other agents from being ingested.
        """
        report = SyncReport()
        for source in self.components.request_sources:
            kind = getattr(source, "source_kind", "<unknown>")
            report.scanned_sources += 1
            try:
                events = source.scan()
                events = list(events)
            except Exception as exc:
                report.errors.append(
                    f"source {kind!r} failed to scan: {type(exc).__name__}: {exc}"
                )
                continue
            for raw in events:
                report.events_seen += 1
                try:
                    event = validate_event(raw, expected_source_kind=kind)
                except ValidationError as exc:
                    report.errors.append(f"source {kind!r}: invalid event rejected: {exc}")
                    continue
                try:
                    self._apply_event(event, report)
                except RecSubError as exc:
                    report.errors.append(
                        f"source {kind!r}: event {event.event_id!r} rejected: {exc}"
                    )
                except Exception as exc:  # pragma: no cover - defensive
                    report.errors.append(
                        f"source {kind!r}: event {event.event_id!r} failed: "
                        f"{type(exc).__name__}: {exc}"
                    )
        return report

    def _apply_event(self, event: RequestEvent, report: SyncReport) -> None:
        """Apply one validated event, in one transaction, exactly once."""
        with self.repository.transaction():
            if self.repository.event_applied(event.source_kind, event.event_id):
                report.skipped.append(
                    f"{event.event_id}: already applied, ignored"
                )
                return
            now = self._now()
            if event.kind == "ADD_REQUEST":
                applied = self._apply_add(event, now, report)
            elif event.kind == "CANCEL_REQUEST":
                applied = self._apply_cancel(event, now, report)
            else:
                applied = self._apply_replace(event, now, report)
            if applied:
                self.repository.record_applied_event(
                    event.source_kind, event.event_id, event.kind, now
                )

    def _apply_add(self, event: RequestEvent, now: str, report: SyncReport) -> bool:
        new = event.new_request
        assert new is not None  # guaranteed by validate_event
        existing = self.repository.find_request_by_source(
            event.source_kind, new.source_reference
        )
        if existing is not None:
            report.skipped.append(
                f"{event.event_id}: source reference {new.source_reference!r} already "
                f"ingested as {existing.request_id}, ignored as a duplicate"
            )
            return False
        request_id = self.repository.create_request(
            applicant_name=new.applicant_name,
            application_description=new.application_description,
            purpose=new.purpose,
            channel=new.channel,
            destination=new.destination,
            deadline=new.deadline,
            source_kind=event.source_kind,
            source_reference=new.source_reference,
            supersedes_request_id=None,
            now=now,
        )
        report.applied.append(f"{event.event_id}: added {request_id} (PENDING)")
        return True

    def _apply_cancel(self, event: RequestEvent, now: str, report: SyncReport) -> bool:
        target = self.repository.find_request_by_source(
            event.target_source_kind or event.source_kind,
            event.target_source_reference or "",
        )
        if target is None:
            raise NotFoundError(
                f"cancellation names unknown request "
                f"{event.target_source_kind}/{event.target_source_reference}; "
                "application state is unchanged"
            )
        if target.status is RequestStatus.SUBMITTED:
            raise StateError(
                f"cancellation names {target.request_id}, which is already SUBMITTED; "
                "application state is unchanged"
            )
        if target.status is RequestStatus.CANCELLED:
            report.skipped.append(
                f"{event.event_id}: {target.request_id} is already CANCELLED"
            )
            return False
        self.repository.set_request_status(target.request_id, RequestStatus.CANCELLED, now)
        report.applied.append(f"{event.event_id}: cancelled {target.request_id}")
        return True

    def _apply_replace(self, event: RequestEvent, now: str, report: SyncReport) -> bool:
        """Validate the whole replacement, then apply it atomically.

        If any condition fails the surrounding transaction is rolled back and
        the old request is left exactly as it was.
        """
        new = event.new_request
        assert new is not None  # guaranteed by validate_event
        old = self.repository.find_request_by_source(
            event.target_source_kind or event.source_kind,
            event.target_source_reference or "",
        )
        if old is None:
            raise NotFoundError(
                f"replacement names unknown request "
                f"{event.target_source_kind}/{event.target_source_reference}; "
                "the whole event is rejected"
            )
        if old.status is not RequestStatus.PENDING:
            raise StateError(
                f"replacement names {old.request_id}, which is {old.status.value}, "
                "not PENDING; the whole event is rejected"
            )
        collision = self.repository.find_request_by_source(
            event.source_kind, new.source_reference
        )
        if collision is not None:
            raise ValidationError(
                f"replacement source reference {new.source_reference!r} is already "
                f"used by {collision.request_id}; the whole event is rejected"
            )
        self.repository.set_request_status(old.request_id, RequestStatus.CANCELLED, now)
        request_id = self.repository.create_request(
            applicant_name=new.applicant_name,
            application_description=new.application_description,
            purpose=new.purpose,
            channel=new.channel,
            destination=new.destination,
            deadline=new.deadline,
            source_kind=event.source_kind,
            source_reference=new.source_reference,
            supersedes_request_id=old.request_id,
            now=now,
        )
        report.applied.append(
            f"{event.event_id}: replaced {old.request_id} (now CANCELLED) with "
            f"{request_id} (PENDING)"
        )
        return True

    # ------------------------------------------------------------------
    # 6.2 Register a completed letter
    # ------------------------------------------------------------------

    def register_letter(
        self, *, file_path: str, applicant_name: str, purpose: str
    ) -> str:
        """Register one completed letter file with an explicit applicant and purpose.

        The applicant and purpose come from the professor alone; the
        application never infers them from the filename or the file contents.
        """
        raw_path = require_text(file_path, "file path", max_length=4096)
        applicant = validate_applicant_name(applicant_name)
        parsed_purpose = Purpose.parse(purpose, "purpose")
        resolved = Path(raw_path).expanduser()
        if not resolved.exists():
            raise ValidationError(f"no such file: {resolved}")
        if not resolved.is_file():
            raise ValidationError(f"not a regular file: {resolved}")
        absolute = str(resolved.resolve())
        with self.repository.transaction():
            return self.repository.create_letter(
                file_path=absolute,
                applicant_name=applicant,
                purpose=parsed_purpose.value,
                now=self._now(),
            )

    # ------------------------------------------------------------------
    # 6.3 Cancel a request
    # ------------------------------------------------------------------

    def cancel_request(self, request_id: str) -> Request:
        """Cancel a pending request on the professor's explicit instruction."""
        identifier = require_text(request_id, "request id", max_length=100)
        with self.repository.transaction():
            request = self.repository.get_request(identifier)
            if request is None:
                raise NotFoundError(f"unknown request {identifier!r}")
            if request.status is not RequestStatus.PENDING:
                raise StateError(
                    f"request {request.request_id} is {request.status.value}; only a "
                    "PENDING request can be cancelled"
                )
            self.repository.set_request_status(
                request.request_id, RequestStatus.CANCELLED, self._now()
            )
            return self.repository.require_request(request.request_id)

    # ------------------------------------------------------------------
    # 6.4 Match letters to requests
    # ------------------------------------------------------------------

    def find_letter_for(self, request: Request) -> Optional[Letter]:
        """The compatible letter for ``request``, or ``None``.

        Compatibility is exact applicant-name equality and exact purpose
        equality.  Filenames, file contents, application descriptions,
        destinations, and deadlines play no part.  When several letters are
        compatible the most recently registered one wins, with the letter ID
        as a deterministic tie-breaker.
        """
        return self.repository.find_best_letter(request.applicant_name, request.purpose)

    # ------------------------------------------------------------------
    # 6.5 Process pending submissions
    # ------------------------------------------------------------------

    def process_pending(self) -> ProcessReport:
        """Attempt at most one external submission for each pending request."""
        report = ProcessReport()
        for snapshot in self.repository.pending_requests():
            try:
                self._process_one(snapshot, report)
            except Exception as exc:  # one request must never stop the batch
                report.errors.append(
                    f"{snapshot.request_id}: unexpected failure: "
                    f"{type(exc).__name__}: {exc}"
                )
        return report

    def _process_one(self, snapshot: Request, report: ProcessReport) -> None:
        request = self.repository.get_request(snapshot.request_id)
        if request is None or request.status is not RequestStatus.PENDING:
            report.skipped.append(
                f"{snapshot.request_id}: no longer PENDING, not submitted"
            )
            return

        letter = self.find_letter_for(request)
        if letter is None:
            report.skipped.append(
                f"{request.request_id}: no compatible letter for "
                f"{request.applicant_name!r} / {request.purpose.value}"
            )
            return

        if not is_regular_file(letter.file_path):
            self._record_submission(
                request,
                letter.letter_id,
                ExternalResult.failed(
                    LETTER_FILE_MISSING,
                    f"registered letter file {letter.file_path!r} is missing or is not "
                    "a regular file",
                ),
            )
            report.attempted.append(request.request_id)
            report.failed.append(
                f"{request.request_id}: {LETTER_FILE_MISSING} ({letter.file_path})"
            )
            return

        try:
            result = self.guard.submit_letter(
                request_id=request.request_id, letter_id=letter.letter_id
            )
        except PolicyViolation as exc:
            code, _, detail = str(exc).partition(": ")
            result = ExternalResult.failed(code or "POLICY_VIOLATION", detail or str(exc))
            report.errors.append(f"{request.request_id}: submission forbidden: {exc}")

        report.attempted.append(request.request_id)
        self._record_submission(request, letter.letter_id, result)
        if result.ok:
            report.succeeded.append(
                f"{request.request_id}: SUBMITTED via {request.channel.value} "
                f"(receipt {result.receipt})"
            )
        else:
            report.failed.append(
                f"{request.request_id}: {result.error_code} — {result.error_message} "
                "(still PENDING)"
            )

    def _record_submission(
        self, request: Request, letter_id: Optional[str], result: ExternalResult
    ) -> str:
        """Record the attempt and, on success, move the request in one transaction."""
        with self.repository.transaction():
            submission_id = self.repository.create_submission(
                request_id=request.request_id,
                letter_id=letter_id,
                attempted_at=self._now(),
                channel=request.channel.value,
                outcome=result.outcome.value,
                receipt=result.receipt,
                error_code=result.error_code,
                error_message=result.error_message,
            )
            if result.ok:
                self.repository.set_request_status(
                    request.request_id, RequestStatus.SUBMITTED, self._now()
                )
            return submission_id

    # ------------------------------------------------------------------
    # 6.6 Send deadline reminders
    # ------------------------------------------------------------------

    def send_reminders(self) -> ReminderReport:
        """Send at most one deadline reminder per qualifying pending request."""
        report = ReminderReport()
        now = self.clock.now()
        if now.tzinfo is None:
            raise RecSubError("the configured clock returned a naive datetime")
        now = now.astimezone(timezone.utc)

        for snapshot in self.repository.pending_requests():
            try:
                self._remind_one(snapshot, now, report)
            except Exception as exc:  # one request must never stop the run
                report.errors.append(
                    f"{snapshot.request_id}: unexpected failure: "
                    f"{type(exc).__name__}: {exc}"
                )
        return report

    def _remind_one(self, snapshot: Request, now: datetime, report: ReminderReport) -> None:
        request = self.repository.get_request(snapshot.request_id)
        if request is None or request.status is not RequestStatus.PENDING:
            report.skipped.append(f"{snapshot.request_id}: not PENDING")
            return

        kind = self.reminder_due(request, now)
        if kind is None:
            report.skipped.append(
                f"{request.request_id}: no reminder due"
            )
            return
        if self.repository.has_successful_reminder(request.request_id, kind):
            report.skipped.append(
                f"{request.request_id}: {kind.value} reminder already sent successfully"
            )
            return

        try:
            result = self.guard.send_reminder(request_id=request.request_id, kind=kind)
        except PolicyViolation as exc:
            code, _, detail = str(exc).partition(": ")
            result = ExternalResult.failed(code or "POLICY_VIOLATION", detail or str(exc))
            report.errors.append(f"{request.request_id}: reminder forbidden: {exc}")

        with self.repository.transaction():
            self.repository.create_reminder(
                request_id=request.request_id,
                reminder_kind=kind.value,
                attempted_at=self._now(),
                outcome=result.outcome.value,
                receipt=result.receipt,
                error_code=result.error_code,
                error_message=result.error_message,
            )
        if result.ok:
            report.sent.append(
                f"{request.request_id}: {kind.value} reminder sent "
                f"(receipt {result.receipt})"
            )
        else:
            report.failed.append(
                f"{request.request_id}: {kind.value} reminder failed — "
                f"{result.error_code} {result.error_message}"
            )

    def reminder_due(self, request: Request, now: datetime) -> Optional[ReminderKind]:
        """Which reminder, if any, a pending request qualifies for right now.

        Only pending requests with a future deadline and no compatible
        registered letter qualify.  Within 24 hours the ``ONE_DAY`` reminder
        takes precedence; more than 24 and up to 72 hours gives ``THREE_DAY``.
        """
        if request.status is not RequestStatus.PENDING:
            return None
        deadline = _deadline(request)
        remaining = deadline - now
        if remaining <= timedelta(0):  # the deadline has passed
            return None
        if self.find_letter_for(request) is not None:
            return None
        if remaining <= ONE_DAY_WINDOW:
            return ReminderKind.ONE_DAY
        if remaining <= THREE_DAY_WINDOW:
            return ReminderKind.THREE_DAY
        return None

    # ------------------------------------------------------------------
    # 6.7 Daily workflow
    # ------------------------------------------------------------------

    def daily_run(self) -> DailyRunReport:
        """Synchronize, then process submissions, then send reminders — in order.

        A stage that fails outright is reported; the later stages still run,
        because they remain independently performable.
        """
        errors: list[str] = []
        try:
            sync = self.sync()
        except Exception as exc:
            sync = SyncReport()
            sync.errors.append(f"{type(exc).__name__}: {exc}")
            errors.append(f"synchronization stage failed: {type(exc).__name__}: {exc}")
        try:
            process = self.process_pending()
        except Exception as exc:
            process = ProcessReport()
            process.errors.append(f"{type(exc).__name__}: {exc}")
            errors.append(f"submission stage failed: {type(exc).__name__}: {exc}")
        try:
            reminders = self.send_reminders()
        except Exception as exc:
            reminders = ReminderReport()
            reminders.errors.append(f"{type(exc).__name__}: {exc}")
            errors.append(f"reminder stage failed: {type(exc).__name__}: {exc}")
        return DailyRunReport(
            sync=sync, process=process, reminders=reminders, errors=errors
        )

    # ------------------------------------------------------------------
    # 6.8 Inspect application state
    # ------------------------------------------------------------------

    def list_requests(self, status: Optional[str] = None) -> list[Request]:
        parsed = RequestStatus.parse(status, "status") if status else None
        return self.repository.list_requests(parsed)

    def show_request(self, request_id: str) -> tuple[Request, Optional[str], list[Submission], list[Reminder], Optional[Letter]]:
        """The complete stored details of one request, with its history."""
        request = self.repository.get_request(
            require_text(request_id, "request id", max_length=100)
        )
        if request is None:
            raise NotFoundError(f"unknown request {request_id!r}")
        return (
            request,
            self.repository.superseded_by(request.request_id),
            self.repository.list_submissions(request.request_id),
            self.repository.list_reminders(request.request_id),
            self.find_letter_for(request),
        )

    def list_letters(self) -> list[Letter]:
        return self.repository.list_letters()

    def list_submissions(self, request_id: Optional[str] = None) -> list[Submission]:
        return self.repository.list_submissions(request_id)

    def list_reminders(self, request_id: Optional[str] = None) -> list[Reminder]:
        return self.repository.list_reminders(request_id)


def _deadline(request: Request) -> datetime:
    from .timeutil import from_storage

    return from_storage(request.deadline)


__all__ = ["Application", "LETTER_FILE_MISSING"]
