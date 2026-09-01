"""Deterministic local test doubles for the external interfaces.

These doubles exist so the application can be exercised end to end without any
real request source, email service, or portal.  They are deliberately not
simulators: they record what they were asked to do and return a scripted,
fully deterministic result.  None of them reads an attachment's contents and
none of them touches the application database.
"""

from .doubles import (
    FixedClock,
    JsonFileRequestSource,
    RecordingEmailGateway,
    RecordingPortalAgent,
    ScriptedRequestSource,
    fixed_clock,
    json_file_request_source,
    recording_email_gateway,
    recording_portal_agent,
)

__all__ = [
    "FixedClock",
    "JsonFileRequestSource",
    "RecordingEmailGateway",
    "RecordingPortalAgent",
    "ScriptedRequestSource",
    "fixed_clock",
    "json_file_request_source",
    "recording_email_gateway",
    "recording_portal_agent",
]
