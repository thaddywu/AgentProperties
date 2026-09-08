"""Skeletons for real external adapters.

Copy this file outside the repository, fill in the bodies against whatever
real service you use, and point your configuration at the factories at the
bottom.  Nothing here contacts a real service: every body raises
``NotImplementedError``.

Three rules apply to every adapter:

1. **Return data, never touch the database.**  An adapter receives call
   arguments and returns values.  The application owns its SQLite file.
2. **Translate your own failures.**  Turn a timeout, an authentication error,
   or an HTTP 500 into ``ExternalResult.failed(code, message)``.  Only report
   ``ExternalResult.succeeded(receipt)`` when the external system explicitly
   confirmed the action.
3. **Normalize before you return.**  A request source parses the email or
   portal page; the core application never sees prose or HTML.
"""

from __future__ import annotations

from typing import Sequence

from recsub.models import EmailMessage, ExternalResult, NewRequest, RequestEvent


class InboxRequestSource:
    """Scans a mailbox and returns normalized request events.

    ``event_id`` must be stable for the same external change — a message
    identifier works well — because the application uses it to ignore events it
    has already applied.
    """

    def __init__(self, mailbox: str) -> None:
        self._mailbox = mailbox

    @property
    def source_kind(self) -> str:
        return "email_inbox"

    def scan(self) -> Sequence[RequestEvent]:
        raise NotImplementedError(
            "read the mailbox and build RequestEvent objects, for example:\n"
            "    RequestEvent(event_id=message.id, source_kind=self.source_kind,\n"
            "                 kind='ADD_REQUEST',\n"
            "                 new_request=NewRequest(...))"
        )


class SmtpEmailGateway:
    """Sends one ordinary email message.

    ``message.attachments`` holds absolute paths to files that already exist on
    disk; attach each one and use its base name as the attachment filename.
    """

    def __init__(self, host: str, port: int, sender: str) -> None:
        self._host = host
        self._port = port
        self._sender = sender

    def send(self, message: EmailMessage) -> ExternalResult:
        raise NotImplementedError(
            "send the message and return ExternalResult.succeeded(<message id>) "
            "or ExternalResult.failed(<code>, <message>)"
        )


class BrowserPortalAgent:
    """Uploads one file to one portal submission URL.

    Report ``SUCCEEDED`` only after observing an explicit portal confirmation,
    and put the confirmation identifier in the receipt.
    """

    def __init__(self, profile_directory: str) -> None:
        self._profile_directory = profile_directory

    def submit(
        self, *, correlation_id: str, submission_url: str, file_path: str
    ) -> ExternalResult:
        raise NotImplementedError(
            "drive the browser to submission_url, upload file_path, and return "
            "ExternalResult.succeeded(<confirmation id>) or "
            "ExternalResult.failed(<code>, <message>)"
        )


# --- configuration factories -----------------------------------------------
#
#   "email_gateway": {
#     "factory": "adapters_template:smtp_email_gateway",
#     "options": {"host": "smtp.example.edu", "port": 587,
#                 "sender": "professor@example.edu"}
#   }


def inbox_request_source(*, mailbox: str) -> InboxRequestSource:
    return InboxRequestSource(mailbox)


def smtp_email_gateway(*, host: str, port: int, sender: str) -> SmtpEmailGateway:
    return SmtpEmailGateway(host, port, sender)


def browser_portal_agent(*, profile_directory: str) -> BrowserPortalAgent:
    return BrowserPortalAgent(profile_directory)
