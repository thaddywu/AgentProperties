"""The doubles themselves.

Each double is configurable from a configuration file through the factory
functions at the bottom of the module, so the command-line application can be
run end to end against them.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from ..errors import ConfigError
from ..models import EmailMessage, ExternalResult, RequestEvent
from ..timeutil import parse_rfc3339


# ---------------------------------------------------------------------------
# Clock
# ---------------------------------------------------------------------------


class FixedClock:
    """A clock that returns a fixed instant until it is explicitly moved."""

    def __init__(self, instant: str | datetime) -> None:
        self._instant = parse_rfc3339(instant, "clock instant")

    def now(self) -> datetime:
        return self._instant

    def set(self, instant: str | datetime) -> None:
        self._instant = parse_rfc3339(instant, "clock instant")

    def advance(self, **delta: float) -> datetime:
        """Move the clock forward, for example ``advance(hours=25)``."""
        self._instant = self._instant + timedelta(**delta)
        return self._instant


# ---------------------------------------------------------------------------
# Request sources
# ---------------------------------------------------------------------------


class ScriptedRequestSource:
    """An in-memory request source returning a fixed list of events.

    ``scan`` returns the same events every time it is called, which is exactly
    the repeated-scan behaviour the application must tolerate.
    """

    def __init__(self, source_kind: str, events: Iterable[Any] = ()) -> None:
        self._source_kind = source_kind
        self.events: list[Any] = list(events)
        self.scan_count = 0
        self.raises: Optional[Exception] = None

    @property
    def source_kind(self) -> str:
        return self._source_kind

    def scan(self) -> Sequence[Any]:
        self.scan_count += 1
        if self.raises is not None:
            raise self.raises
        return list(self.events)


class JsonFileRequestSource:
    """A request source that reads normalized events from a local JSON file.

    The file holds a JSON list of event objects using exactly the field names
    of :class:`~recsub.models.RequestEvent`.  A missing file yields no events.
    Nothing here parses email prose or portal pages: the events are already
    normalized.
    """

    def __init__(self, source_kind: str, events_path: str) -> None:
        self._source_kind = source_kind
        self._events_path = Path(events_path)
        self.scan_count = 0

    @property
    def source_kind(self) -> str:
        return self._source_kind

    def scan(self) -> Sequence[Any]:
        self.scan_count += 1
        if not self._events_path.is_file():
            return []
        data = json.loads(self._events_path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError(f"{self._events_path} must contain a JSON list of events")
        return data


# ---------------------------------------------------------------------------
# Email gateway and portal agent
# ---------------------------------------------------------------------------


@dataclass
class SentEmail:
    """One recorded call to the email gateway double."""

    to: list[str]
    cc: list[str]
    subject: str
    body: str
    attachments: list[str]
    correlation_id: str


@dataclass
class PortalUpload:
    """One recorded call to the portal agent double."""

    correlation_id: str
    submission_url: str
    file_path: str


class _Scripted:
    """Shared deterministic outcome scripting."""

    def __init__(
        self,
        *,
        fail_correlation_ids: Sequence[str] = (),
        fail_all: bool = False,
        raise_correlation_ids: Sequence[str] = (),
        error_code: str = "SCRIPTED_FAILURE",
        log_path: Optional[str] = None,
    ) -> None:
        self.fail_correlation_ids = set(fail_correlation_ids)
        self.fail_all = fail_all
        self.raise_correlation_ids = set(raise_correlation_ids)
        self.error_code = error_code
        self._log_path = Path(log_path) if log_path else None
        self.calls: list[Any] = []

    def _log(self, kind: str, payload: dict[str, Any], result: ExternalResult) -> None:
        if self._log_path is None:
            return
        record = {"kind": kind, "call": payload, "outcome": result.outcome.value,
                  "receipt": result.receipt, "error_code": result.error_code}
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    def _outcome(self, correlation_id: str, prefix: str) -> ExternalResult:
        if correlation_id in self.raise_correlation_ids:
            raise RuntimeError(f"scripted adapter exception for {correlation_id}")
        if self.fail_all or correlation_id in self.fail_correlation_ids:
            return ExternalResult.failed(
                self.error_code, f"scripted failure for {correlation_id}"
            )
        return ExternalResult.succeeded(f"{prefix}-{len(self.calls):04d}")


class RecordingEmailGateway(_Scripted):
    """An email gateway that records messages and returns a scripted result.

    It never opens an attachment and never contacts anything.
    """

    def send(self, message: EmailMessage) -> ExternalResult:
        record = SentEmail(
            to=list(message.to),
            cc=list(message.cc),
            subject=message.subject,
            body=message.body,
            attachments=list(message.attachments),
            correlation_id=message.correlation_id,
        )
        result = self._outcome(message.correlation_id, "email")
        self.calls.append(record)
        self._log("email", asdict(record), result)
        return result

    @property
    def sent(self) -> list[SentEmail]:
        return list(self.calls)

    def sent_to(self, address: str) -> list[SentEmail]:
        return [message for message in self.calls if address in message.to]


class RecordingPortalAgent(_Scripted):
    """A portal agent that records uploads and returns a scripted result."""

    def submit(
        self, *, correlation_id: str, submission_url: str, file_path: str
    ) -> ExternalResult:
        record = PortalUpload(
            correlation_id=correlation_id,
            submission_url=submission_url,
            file_path=file_path,
        )
        result = self._outcome(correlation_id, "portal")
        self.calls.append(record)
        self._log("portal", asdict(record), result)
        return result

    @property
    def uploads(self) -> list[PortalUpload]:
        return list(self.calls)


# ---------------------------------------------------------------------------
# Configuration factories
# ---------------------------------------------------------------------------


def fixed_clock(*, instant: str) -> FixedClock:
    return FixedClock(instant)


def json_file_request_source(*, source_kind: str, events_path: str) -> JsonFileRequestSource:
    if not source_kind or not source_kind.strip():
        raise ConfigError("json_file_request_source requires a non-empty source_kind")
    return JsonFileRequestSource(source_kind.strip(), events_path)


def recording_email_gateway(
    *,
    log_path: Optional[str] = None,
    fail_correlation_ids: Sequence[str] = (),
    fail_all: bool = False,
    raise_correlation_ids: Sequence[str] = (),
    error_code: str = "SCRIPTED_FAILURE",
) -> RecordingEmailGateway:
    return RecordingEmailGateway(
        log_path=log_path,
        fail_correlation_ids=fail_correlation_ids,
        fail_all=fail_all,
        raise_correlation_ids=raise_correlation_ids,
        error_code=error_code,
    )


def recording_portal_agent(
    *,
    log_path: Optional[str] = None,
    fail_correlation_ids: Sequence[str] = (),
    fail_all: bool = False,
    raise_correlation_ids: Sequence[str] = (),
    error_code: str = "SCRIPTED_FAILURE",
) -> RecordingPortalAgent:
    return RecordingPortalAgent(
        log_path=log_path,
        fail_correlation_ids=fail_correlation_ids,
        fail_all=fail_all,
        raise_correlation_ids=raise_correlation_ids,
        error_code=error_code,
    )
