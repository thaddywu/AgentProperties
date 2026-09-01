"""Typed access to the application's SQLite database.

Every read and write of application state goes through this class.  It is the
only module that knows the row layout.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator, Optional, Sequence

from .enums import Channel, Outcome, Purpose, ReminderKind, RequestStatus
from .errors import NotFoundError
from .models import Letter, Reminder, Request, Submission

_ID_WIDTH = 6


class Repository:
    """Persistence for requests, letters, submissions, reminders, and event IDs."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    # -- transactions ------------------------------------------------------

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Run a block as one SQLite transaction, rolling back on any exception.

        Nested use joins the outer transaction, so a caller can compose
        operations without an inner commit making partial work durable.
        """
        if self._connection.in_transaction:
            yield self._connection
            return
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            yield self._connection
        except BaseException:
            self._connection.rollback()
            raise
        else:
            self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    # -- identifiers -------------------------------------------------------

    def _next_id(self, name: str, prefix: str) -> str:
        cursor = self._connection.execute(
            "INSERT INTO counters (name, value) VALUES (?, 1) "
            "ON CONFLICT (name) DO UPDATE SET value = value + 1 "
            "RETURNING value",
            (name,),
        )
        value = int(cursor.fetchone()[0])
        return f"{prefix}-{value:0{_ID_WIDTH}d}"

    # -- requests ----------------------------------------------------------

    def create_request(
        self,
        *,
        applicant_name: str,
        application_description: str,
        purpose: str,
        channel: str,
        destination: str,
        deadline: str,
        source_kind: str,
        source_reference: str,
        supersedes_request_id: Optional[str],
        now: str,
    ) -> str:
        request_id = self._next_id("request", "REQ")
        self._connection.execute(
            "INSERT INTO requests (request_id, applicant_name, application_description,"
            " purpose, channel, destination, deadline, status, source_kind,"
            " source_reference, supersedes_request_id, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?, ?, ?, ?)",
            (
                request_id,
                applicant_name,
                application_description,
                purpose,
                channel,
                destination,
                deadline,
                source_kind,
                source_reference,
                supersedes_request_id,
                now,
                now,
            ),
        )
        return request_id

    def set_request_status(self, request_id: str, status: RequestStatus, now: str) -> None:
        self._connection.execute(
            "UPDATE requests SET status = ?, updated_at = ? WHERE request_id = ?",
            (status.value, now, request_id),
        )

    def get_request(self, request_id: str) -> Optional[Request]:
        row = self._connection.execute(
            "SELECT * FROM requests WHERE request_id = ?", (request_id,)
        ).fetchone()
        return _request(row) if row else None

    def require_request(self, request_id: str) -> Request:
        request = self.get_request(request_id)
        if request is None:
            raise NotFoundError(f"unknown request {request_id!r}")
        return request

    def find_request_by_source(
        self, source_kind: str, source_reference: str
    ) -> Optional[Request]:
        row = self._connection.execute(
            "SELECT * FROM requests WHERE source_kind = ? AND source_reference = ?",
            (source_kind, source_reference),
        ).fetchone()
        return _request(row) if row else None

    def list_requests(self, status: Optional[RequestStatus] = None) -> list[Request]:
        if status is None:
            rows = self._connection.execute(
                "SELECT * FROM requests ORDER BY deadline, request_id"
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT * FROM requests WHERE status = ? ORDER BY deadline, request_id",
                (status.value,),
            ).fetchall()
        return [_request(row) for row in rows]

    def pending_requests(self) -> list[Request]:
        """Pending requests in ascending deadline order, request ID breaking ties."""
        rows = self._connection.execute(
            "SELECT * FROM requests WHERE status = 'PENDING'"
            " ORDER BY deadline, request_id"
        ).fetchall()
        return [_request(row) for row in rows]

    def superseded_by(self, request_id: str) -> Optional[str]:
        """The request created as a replacement for ``request_id``, if any."""
        row = self._connection.execute(
            "SELECT request_id FROM requests WHERE supersedes_request_id = ?"
            " ORDER BY request_id LIMIT 1",
            (request_id,),
        ).fetchone()
        return row[0] if row else None

    # -- letters -----------------------------------------------------------

    def create_letter(
        self, *, file_path: str, applicant_name: str, purpose: str, now: str
    ) -> str:
        letter_id = self._next_id("letter", "LET")
        self._connection.execute(
            "INSERT INTO letters (letter_id, file_path, applicant_name, purpose,"
            " registered_at) VALUES (?, ?, ?, ?, ?)",
            (letter_id, file_path, applicant_name, purpose, now),
        )
        return letter_id

    def get_letter(self, letter_id: str) -> Optional[Letter]:
        row = self._connection.execute(
            "SELECT * FROM letters WHERE letter_id = ?", (letter_id,)
        ).fetchone()
        return _letter(row) if row else None

    def list_letters(self) -> list[Letter]:
        rows = self._connection.execute(
            "SELECT * FROM letters ORDER BY registered_at, letter_id"
        ).fetchall()
        return [_letter(row) for row in rows]

    def find_best_letter(self, applicant_name: str, purpose: Purpose) -> Optional[Letter]:
        """The most recently registered compatible letter, letter ID breaking ties.

        Compatibility is exact, case-sensitive equality of the canonical
        applicant name and exact equality of the purpose — nothing else.
        """
        row = self._connection.execute(
            "SELECT * FROM letters WHERE applicant_name = ? AND purpose = ?"
            " ORDER BY registered_at DESC, letter_id DESC LIMIT 1",
            (applicant_name, purpose.value),
        ).fetchone()
        return _letter(row) if row else None

    # -- submissions -------------------------------------------------------

    def create_submission(
        self,
        *,
        request_id: str,
        letter_id: Optional[str],
        attempted_at: str,
        channel: str,
        outcome: str,
        receipt: Optional[str],
        error_code: Optional[str],
        error_message: Optional[str],
    ) -> str:
        submission_id = self._next_id("submission", "SUB")
        self._connection.execute(
            "INSERT INTO submissions (submission_id, request_id, letter_id,"
            " attempted_at, channel, outcome, receipt, error_code, error_message)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                submission_id,
                request_id,
                letter_id,
                attempted_at,
                channel,
                outcome,
                receipt,
                error_code,
                error_message,
            ),
        )
        return submission_id

    def list_submissions(self, request_id: Optional[str] = None) -> list[Submission]:
        if request_id is None:
            rows = self._connection.execute(
                "SELECT * FROM submissions ORDER BY attempted_at, submission_id"
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT * FROM submissions WHERE request_id = ?"
                " ORDER BY attempted_at, submission_id",
                (request_id,),
            ).fetchall()
        return [_submission(row) for row in rows]

    def has_successful_submission(self, request_id: str) -> bool:
        row = self._connection.execute(
            "SELECT 1 FROM submissions WHERE request_id = ? AND outcome = 'SUCCEEDED'"
            " LIMIT 1",
            (request_id,),
        ).fetchone()
        return row is not None

    # -- reminders ---------------------------------------------------------

    def create_reminder(
        self,
        *,
        request_id: str,
        reminder_kind: str,
        attempted_at: str,
        outcome: str,
        receipt: Optional[str],
        error_code: Optional[str],
        error_message: Optional[str],
    ) -> str:
        reminder_id = self._next_id("reminder", "REM")
        self._connection.execute(
            "INSERT INTO reminders (reminder_id, request_id, reminder_kind,"
            " attempted_at, outcome, receipt, error_code, error_message)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                reminder_id,
                request_id,
                reminder_kind,
                attempted_at,
                outcome,
                receipt,
                error_code,
                error_message,
            ),
        )
        return reminder_id

    def list_reminders(self, request_id: Optional[str] = None) -> list[Reminder]:
        if request_id is None:
            rows = self._connection.execute(
                "SELECT * FROM reminders ORDER BY attempted_at, reminder_id"
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT * FROM reminders WHERE request_id = ?"
                " ORDER BY attempted_at, reminder_id",
                (request_id,),
            ).fetchall()
        return [_reminder(row) for row in rows]

    def has_successful_reminder(self, request_id: str, kind: ReminderKind) -> bool:
        row = self._connection.execute(
            "SELECT 1 FROM reminders WHERE request_id = ? AND reminder_kind = ?"
            " AND outcome = 'SUCCEEDED' LIMIT 1",
            (request_id, kind.value),
        ).fetchone()
        return row is not None

    # -- applied event bookkeeping ----------------------------------------

    def event_applied(self, source_kind: str, event_id: str) -> bool:
        row = self._connection.execute(
            "SELECT 1 FROM applied_events WHERE source_kind = ? AND event_id = ?",
            (source_kind, event_id),
        ).fetchone()
        return row is not None

    def record_applied_event(
        self, source_kind: str, event_id: str, kind: str, now: str
    ) -> None:
        self._connection.execute(
            "INSERT INTO applied_events (source_kind, event_id, kind, applied_at)"
            " VALUES (?, ?, ?, ?)",
            (source_kind, event_id, kind, now),
        )

    def list_applied_events(self) -> list[sqlite3.Row]:
        return self._connection.execute(
            "SELECT * FROM applied_events ORDER BY applied_at, source_kind, event_id"
        ).fetchall()


# -- row conversion --------------------------------------------------------


def _request(row: sqlite3.Row) -> Request:
    return Request(
        request_id=row["request_id"],
        applicant_name=row["applicant_name"],
        application_description=row["application_description"],
        purpose=Purpose(row["purpose"]),
        channel=Channel(row["channel"]),
        destination=row["destination"],
        deadline=row["deadline"],
        status=RequestStatus(row["status"]),
        source_kind=row["source_kind"],
        source_reference=row["source_reference"],
        supersedes_request_id=row["supersedes_request_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _letter(row: sqlite3.Row) -> Letter:
    return Letter(
        letter_id=row["letter_id"],
        file_path=row["file_path"],
        applicant_name=row["applicant_name"],
        purpose=Purpose(row["purpose"]),
        registered_at=row["registered_at"],
    )


def _submission(row: sqlite3.Row) -> Submission:
    return Submission(
        submission_id=row["submission_id"],
        request_id=row["request_id"],
        letter_id=row["letter_id"],
        attempted_at=row["attempted_at"],
        channel=Channel(row["channel"]),
        outcome=Outcome(row["outcome"]),
        receipt=row["receipt"],
        error_code=row["error_code"],
        error_message=row["error_message"],
    )


def _reminder(row: sqlite3.Row) -> Reminder:
    return Reminder(
        reminder_id=row["reminder_id"],
        request_id=row["request_id"],
        reminder_kind=ReminderKind(row["reminder_kind"]),
        attempted_at=row["attempted_at"],
        outcome=Outcome(row["outcome"]),
        receipt=row["receipt"],
        error_code=row["error_code"],
        error_message=row["error_message"],
    )


__all__ = ["Repository"]
