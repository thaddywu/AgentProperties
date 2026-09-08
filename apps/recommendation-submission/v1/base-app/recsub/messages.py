"""Plain-text bodies for the two kinds of message the application sends.

These helpers produce *text only*.  Recipients and attachments — the parts the
Safety Policy constrains — are decided exclusively by :mod:`recsub.policy`.

The application never generates, rewrites, summarizes, or inspects
recommendation-letter content; a submission email is a short conventional
covering note that names the applicant and the application.
"""

from __future__ import annotations

from .models import Request
from .timeutil import for_display


def submission_subject(request: Request) -> str:
    return f"Letter of recommendation for {request.applicant_name} — {request.application_description}"


def submission_body(request: Request, *, professor_email: str, display_tz) -> str:
    return (
        "Hello,\n\n"
        f"Please find attached my letter of recommendation for "
        f"{request.applicant_name}, submitted for {request.application_description} "
        f"({request.purpose.value}).\n\n"
        f"The requested deadline is {for_display(request.deadline, display_tz)}.\n\n"
        "Please contact me if anything further is required.\n\n"
        "Sincerely,\n"
        f"{professor_email}\n\n"
        f"(Reference: {request.request_id})\n"
    )


def reminder_subject(request: Request, reminder_kind: str) -> str:
    label = "3 days" if reminder_kind == "THREE_DAY" else "1 day"
    return (
        f"Recommendation deadline in {label}: {request.applicant_name} — "
        f"{request.application_description}"
    )


def reminder_body(request: Request, reminder_kind: str, *, display_tz) -> str:
    """A reminder names the request but never includes a letter (policy 10)."""
    return (
        "This is a reminder that a recommendation request is still pending and "
        "has no compatible registered letter.\n\n"
        f"  Request ID:  {request.request_id}\n"
        f"  Applicant:   {request.applicant_name}\n"
        f"  Application: {request.application_description}\n"
        f"  Purpose:     {request.purpose.value}\n"
        f"  Deadline:    {for_display(request.deadline, display_tz)}\n"
        f"  Reminder:    {reminder_kind}\n"
    )
