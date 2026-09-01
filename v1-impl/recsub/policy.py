"""Enforcement of the Safety Policy at the moment of external disclosure.

Design rule of this implementation: **the guard in this module is the only
code that calls the email gateway or the portal automation agent.**  Nothing
else in the package imports those components for use.

The guard does not trust its caller.  For every disclosure it re-reads the
authoritative request and letter records from the database and re-checks all
of the conditions in policy section 5 against that freshly read state.  It
then *constructs* the outbound message itself, taking the recipient from the
request's own recorded destination and the attachment from the letter's own
registered path, so a caller cannot supply a recipient, a channel, or a file
of its own.  If any condition fails, it raises
:class:`~recsub.errors.PolicyViolation` and makes no external call at all.

Policy clause → check:

* 5 (request exists and is ``PENDING``)          -> ``REQUEST_NOT_FOUND`` / ``REQUEST_NOT_PENDING``
* 4 (file is a registered letter)                -> ``LETTER_NOT_REGISTERED`` / ``LETTER_FILE_UNAVAILABLE``
* 5 (applicant names exactly equal)              -> ``APPLICANT_MISMATCH``
* 5 (purposes exactly equal)                     -> ``PURPOSE_MISMATCH``
* 5, 7 (recorded channel is used)                -> ``CHANNEL_MISMATCH``
* 5, 6, 7 (recorded destination is used)         -> ``DESTINATION_MISMATCH``
* 5, 9 (no earlier successful submission)        -> ``ALREADY_SUBMITTED``
* 6 (one primary recipient, no CC, one attachment) -> ``MESSAGE_SHAPE``
* 10 (reminders go only to the professor, carry no letter) -> ``MESSAGE_SHAPE``
"""

from __future__ import annotations

from typing import Optional

from .enums import Channel, Outcome, ReminderKind, RequestStatus
from .errors import PolicyViolation
from .interfaces import EmailGateway, PortalAgent
from .messages import (
    reminder_body,
    reminder_subject,
    submission_body,
    submission_subject,
)
from .models import EmailMessage, ExternalResult, Letter, Request
from .repository import Repository
from .validation import is_regular_file, validate_email_address, validate_portal_url

#: Error code recorded when an adapter raises instead of returning a result.
ADAPTER_EXCEPTION = "ADAPTER_EXCEPTION"
#: Error code recorded when an adapter returns something that is not a
#: definitive :class:`~recsub.models.ExternalResult`.
INVALID_ADAPTER_RESULT = "INVALID_ADAPTER_RESULT"


class PolicyGuard:
    """The single enforcement point for every external disclosure."""

    def __init__(
        self,
        *,
        repository: Repository,
        email_gateway: EmailGateway,
        portal_agent: PortalAgent,
        professor_email: str,
        display_timezone,
    ) -> None:
        self._repository = repository
        self._email_gateway = email_gateway
        self._portal_agent = portal_agent
        self._professor_email = professor_email
        self._display_timezone = display_timezone

    # ------------------------------------------------------------------
    # Recommendation submissions
    # ------------------------------------------------------------------

    def submit_letter(self, *, request_id: str, letter_id: str) -> ExternalResult:
        """Disclose one registered letter for one pending request.

        Raises :class:`PolicyViolation` — before contacting anything external —
        when the disclosure is not permitted.
        """
        request, letter = self._authorize_submission(request_id, letter_id)

        if request.channel is Channel.EMAIL:
            message = self._build_submission_email(request, letter)
            self._check_submission_email(message, request, letter)
            return self._call(lambda: self._email_gateway.send(message))

        if request.channel is Channel.PORTAL:
            url = self._portal_target(request)
            return self._call(
                lambda: self._portal_agent.submit(
                    correlation_id=request.request_id,
                    submission_url=url,
                    file_path=letter.file_path,
                )
            )

        raise PolicyViolation(  # pragma: no cover - the enumeration has two members
            f"CHANNEL_MISMATCH: request {request.request_id} has no supported "
            "submission channel"
        )

    def _portal_target(self, request: Request) -> str:
        """The request's own recorded portal URL, re-validated (policy 7)."""
        try:
            return validate_portal_url(request.destination)
        except Exception:
            raise PolicyViolation(
                f"DESTINATION_MISMATCH: request {request.request_id} does not record a "
                "usable portal submission URL"
            ) from None

    def _authorize_submission(
        self, request_id: str, letter_id: str
    ) -> tuple[Request, Letter]:
        """Re-read authoritative state and apply policy section 5."""
        request = self._repository.get_request(request_id)
        if request is None:
            raise PolicyViolation(
                f"REQUEST_NOT_FOUND: no request {request_id!r} may authorize a submission"
            )
        if request.status is not RequestStatus.PENDING:
            raise PolicyViolation(
                f"REQUEST_NOT_PENDING: request {request.request_id} is "
                f"{request.status.value} and must not authorize a submission"
            )

        # Policy 4: only a file the professor explicitly registered may be sent.
        letter = self._repository.get_letter(letter_id) if letter_id else None
        if letter is None:
            raise PolicyViolation(
                f"LETTER_NOT_REGISTERED: {letter_id!r} is not a registered letter"
            )
        if not is_regular_file(letter.file_path):
            raise PolicyViolation(
                f"LETTER_FILE_UNAVAILABLE: {letter.file_path!r} is not a regular file"
            )

        if letter.applicant_name != request.applicant_name:
            raise PolicyViolation(
                "APPLICANT_MISMATCH: letter "
                f"{letter.letter_id} belongs to {letter.applicant_name!r} but request "
                f"{request.request_id} names {request.applicant_name!r}"
            )
        if letter.purpose is not request.purpose:
            raise PolicyViolation(
                "PURPOSE_MISMATCH: letter "
                f"{letter.letter_id} is {letter.purpose.value} but request "
                f"{request.request_id} is {request.purpose.value}"
            )
        if self._repository.has_successful_submission(request.request_id):
            raise PolicyViolation(
                f"ALREADY_SUBMITTED: request {request.request_id} already completed a "
                "successful recommendation submission"
            )
        return request, letter

    def _build_submission_email(self, request: Request, letter: Letter) -> EmailMessage:
        """Compose the submission email from recorded state only."""
        return EmailMessage(
            to=[request.destination],  # policy 6: the recorded destination, only
            cc=[],
            subject=submission_subject(request),
            body=submission_body(
                request,
                professor_email=self._professor_email,
                display_tz=self._display_timezone,
            ),
            attachments=[letter.file_path],  # policy 6: exactly this one file
            correlation_id=request.request_id,
        )

    def _check_submission_email(
        self, message: EmailMessage, request: Request, letter: Letter
    ) -> None:
        """Post-condition check on the composed message (policy 6)."""
        if request.channel is not Channel.EMAIL:
            raise PolicyViolation(
                f"CHANNEL_MISMATCH: request {request.request_id} is "
                f"{request.channel.value} and must not authorize an email submission"
            )
        if list(message.to) != [request.destination]:
            raise PolicyViolation(
                "DESTINATION_MISMATCH: a submission email must have the request's "
                "recorded email destination as its only primary recipient"
            )
        try:
            validate_email_address(request.destination)
        except Exception:
            raise PolicyViolation(
                f"DESTINATION_MISMATCH: request {request.request_id} does not record a "
                "usable email destination"
            ) from None
        if list(message.cc):
            raise PolicyViolation("MESSAGE_SHAPE: a submission email must have no CC recipients")
        if list(message.attachments) != [letter.file_path]:
            raise PolicyViolation(
                "MESSAGE_SHAPE: a submission email must attach exactly the one "
                "selected registered letter"
            )

    # ------------------------------------------------------------------
    # Deadline reminders
    # ------------------------------------------------------------------

    def send_reminder(self, *, request_id: str, kind: ReminderKind) -> ExternalResult:
        """Send one deadline reminder to the professor's configured address."""
        request = self._repository.get_request(request_id)
        if request is None:
            raise PolicyViolation(
                f"REQUEST_NOT_FOUND: no request {request_id!r} may justify a reminder"
            )
        if request.status is not RequestStatus.PENDING:
            raise PolicyViolation(
                f"REQUEST_NOT_PENDING: a reminder about {request.status.value} request "
                f"{request.request_id} is forbidden"
            )

        message = EmailMessage(
            to=[self._professor_email],  # policy 10: the professor, and no one else
            cc=[],
            subject=reminder_subject(request, kind.value),
            body=reminder_body(request, kind.value, display_tz=self._display_timezone),
            attachments=[],  # policy 10: a reminder never carries a letter
            correlation_id=request.request_id,
        )
        if list(message.to) != [self._professor_email] or list(message.cc):
            raise PolicyViolation(
                "MESSAGE_SHAPE: a reminder may go only to the professor's configured "
                "address, with no CC recipients"
            )
        if list(message.attachments):
            raise PolicyViolation("MESSAGE_SHAPE: a reminder must not attach any file")
        return self._call(lambda: self._email_gateway.send(message))

    # ------------------------------------------------------------------
    # External call handling
    # ------------------------------------------------------------------

    @staticmethod
    def _call(operation) -> ExternalResult:
        """Invoke an external component and normalize whatever comes back.

        An adapter that raises, or that returns anything other than a
        definitive result, is reported as a ``FAILED`` attempt: version 1
        treats "the component did not report success" as "not submitted".
        """
        try:
            result = operation()
        except Exception as exc:  # an adapter that failed to translate its own error
            return ExternalResult.failed(ADAPTER_EXCEPTION, f"{type(exc).__name__}: {exc}")
        return _normalize(result)


def _normalize(result: object) -> ExternalResult:
    if not isinstance(result, ExternalResult):
        return ExternalResult.failed(
            INVALID_ADAPTER_RESULT,
            f"external component returned {type(result).__name__}, expected ExternalResult",
        )
    try:
        outcome = Outcome(result.outcome)
    except ValueError:
        return ExternalResult.failed(
            INVALID_ADAPTER_RESULT, f"unsupported outcome {result.outcome!r}"
        )
    if outcome is Outcome.SUCCEEDED:
        return ExternalResult(
            outcome=Outcome.SUCCEEDED,
            receipt=result.receipt if result.receipt else None,
        )
    return ExternalResult(
        outcome=Outcome.FAILED,
        error_code=result.error_code or "UNSPECIFIED_ERROR",
        error_message=result.error_message or "",
    )


__all__ = ["PolicyGuard", "ADAPTER_EXCEPTION", "INVALID_ADAPTER_RESULT"]
