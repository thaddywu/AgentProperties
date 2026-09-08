"""Validation of everything that enters the application from outside.

The core application validates normalized data from request sources and from
the professor's own commands.  It never parses email prose or portal pages,
and it never infers a field it was not given.
"""

from __future__ import annotations

import os
import re
from typing import Mapping, Optional
from urllib.parse import urlparse

from .enums import Channel, EventKind, Purpose
from .errors import ValidationError
from .models import EventLike, NewRequest, RequestEvent
from .timeutil import parse_rfc3339, to_storage

#: A deliberately conservative single-address pattern.  The application is not
#: an email client; it only checks that a destination is plausibly one address.
_EMAIL = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[A-Za-z]{2,}$")

MAX_TEXT = 2000


def is_regular_file(path: str) -> bool:
    """Whether ``path`` currently identifies an existing regular file."""
    try:
        return os.path.isfile(path)
    except (OSError, ValueError):  # pragma: no cover - defensive
        return False


def require_text(value: object, field: str, *, max_length: int = MAX_TEXT) -> str:
    """Return ``value`` trimmed, or raise if it is not a non-blank string.

    Leading and trailing whitespace is removed once, here, at the boundary;
    afterwards values are compared by exact, case-sensitive equality.
    """
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be a string, got {type(value).__name__}")
    trimmed = value.strip()
    if not trimmed:
        raise ValidationError(f"{field} must not be blank")
    if len(trimmed) > max_length:
        raise ValidationError(f"{field} must be at most {max_length} characters")
    return trimmed


def validate_applicant_name(value: object, field: str = "applicant name") -> str:
    """Trim an applicant's canonical name (specification 5.1)."""
    return require_text(value, field, max_length=300)


def validate_email_address(value: object, field: str = "email destination") -> str:
    address = require_text(value, field, max_length=320)
    if not _EMAIL.match(address):
        raise ValidationError(f"{field} must be one email address, got {address!r}")
    return address


def validate_portal_url(value: object, field: str = "portal destination") -> str:
    url = require_text(value, field, max_length=2000)
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
        raise ValidationError(
            f"{field} must be an absolute http or https URL, got {url!r}"
        )
    return url


def validate_destination(channel: Channel, value: object) -> str:
    """Validate a destination against its channel (specification 5.1).

    A destination of the wrong type is rejected during ingestion.
    """
    if channel is Channel.EMAIL:
        return validate_email_address(value)
    return validate_portal_url(value)


def validate_new_request(payload: object, *, where: str = "request") -> NewRequest:
    """Validate the complete field set carried by an add or replacement event."""
    if isinstance(payload, Mapping):
        try:
            payload = NewRequest(
                source_reference=payload["source_reference"],  # type: ignore[index]
                applicant_name=payload["applicant_name"],  # type: ignore[index]
                application_description=payload["application_description"],  # type: ignore[index]
                purpose=payload["purpose"],  # type: ignore[index]
                channel=payload["channel"],  # type: ignore[index]
                destination=payload["destination"],  # type: ignore[index]
                deadline=payload["deadline"],  # type: ignore[index]
            )
        except (KeyError, TypeError) as exc:
            raise ValidationError(f"{where} is missing field {exc}") from None
    if not isinstance(payload, NewRequest):
        raise ValidationError(f"{where} must carry the complete new-request fields")

    purpose = Purpose.parse(payload.purpose, f"{where} purpose")
    channel = Channel.parse(payload.channel, f"{where} channel")
    return NewRequest(
        source_reference=require_text(payload.source_reference, f"{where} source_reference", max_length=300),
        applicant_name=validate_applicant_name(payload.applicant_name, f"{where} applicant name"),
        application_description=require_text(
            payload.application_description, f"{where} application description"
        ),
        purpose=purpose.value,
        channel=channel.value,
        destination=validate_destination(channel, payload.destination),
        deadline=to_storage(parse_rfc3339(payload.deadline, f"{where} deadline")),
    )


def _coerce_event(event: EventLike) -> RequestEvent:
    if isinstance(event, RequestEvent):
        return event
    if isinstance(event, Mapping):
        unknown = set(event) - {
            "event_id",
            "source_kind",
            "kind",
            "new_request",
            "target_source_kind",
            "target_source_reference",
        }
        if unknown:
            raise ValidationError(f"event has unknown field(s): {sorted(unknown)}")
        try:
            return RequestEvent(
                event_id=event["event_id"],  # type: ignore[index]
                source_kind=event["source_kind"],  # type: ignore[index]
                kind=event["kind"],  # type: ignore[index]
                new_request=event.get("new_request"),  # type: ignore[arg-type]
                target_source_kind=event.get("target_source_kind"),  # type: ignore[arg-type]
                target_source_reference=event.get("target_source_reference"),  # type: ignore[arg-type]
            )
        except KeyError as exc:
            raise ValidationError(f"event is missing field {exc}") from None
    raise ValidationError(
        f"a request source must return RequestEvent objects, got {type(event).__name__}"
    )


def validate_event(event: EventLike, *, expected_source_kind: str) -> RequestEvent:
    """Validate one normalized request event completely, before any state change.

    Returns a canonical event whose text fields are trimmed and whose
    new-request payload is fully validated.  Raises :class:`ValidationError`
    describing the first problem found.
    """
    raw = _coerce_event(event)
    event_id = require_text(raw.event_id, "event_id", max_length=300)
    source_kind = require_text(raw.source_kind, "source_kind", max_length=100)
    if source_kind != expected_source_kind:
        raise ValidationError(
            f"event {event_id!r} declares source kind {source_kind!r} but was "
            f"returned by the {expected_source_kind!r} agent"
        )
    kind = EventKind.parse(raw.kind, "event kind")

    new_request: Optional[NewRequest] = None
    target_kind: Optional[str] = None
    target_reference: Optional[str] = None

    if kind is EventKind.ADD_REQUEST:
        if raw.target_source_reference is not None:
            raise ValidationError("an ADD_REQUEST event must not identify an old request")
        new_request = validate_new_request(raw.new_request, where="ADD_REQUEST")
    elif kind is EventKind.CANCEL_REQUEST:
        if raw.new_request is not None:
            raise ValidationError("a CANCEL_REQUEST event must not carry request fields")
        target_kind = require_text(
            raw.target_source_kind if raw.target_source_kind is not None else source_kind,
            "target_source_kind",
            max_length=100,
        )
        target_reference = require_text(
            raw.target_source_reference, "target_source_reference", max_length=300
        )
    else:  # REPLACE_REQUEST
        target_kind = require_text(
            raw.target_source_kind if raw.target_source_kind is not None else source_kind,
            "target_source_kind",
            max_length=100,
        )
        target_reference = require_text(
            raw.target_source_reference, "target_source_reference", max_length=300
        )
        new_request = validate_new_request(raw.new_request, where="REPLACE_REQUEST replacement")

    return RequestEvent(
        event_id=event_id,
        source_kind=source_kind,
        kind=kind.value,
        new_request=new_request,
        target_source_kind=target_kind,
        target_source_reference=target_reference,
    )
