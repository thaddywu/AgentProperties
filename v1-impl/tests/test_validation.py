"""Validation of normalized events and of the fixed enumerations."""

from __future__ import annotations

import pytest

from recsub.enums import Purpose
from recsub.errors import ValidationError
from recsub.models import NewRequest, RequestEvent
from recsub.timeutil import parse_rfc3339, to_storage
from recsub.validation import (
    validate_applicant_name,
    validate_destination,
    validate_event,
    validate_new_request,
)
from recsub.enums import Channel


def base_fields(**overrides):
    fields = {
        "source_reference": "msg-1",
        "applicant_name": "Ada Lovelace",
        "application_description": "MIT EECS PhD",
        "purpose": "PHD_APPLICATION",
        "channel": "EMAIL",
        "destination": "admissions@example.edu",
        "deadline": "2026-12-01T23:59:00-05:00",
    }
    fields.update(overrides)
    return fields


class TestDeadlines:
    def test_offset_is_normalized_to_utc(self):
        request = validate_new_request(base_fields())
        assert request.deadline == "2026-12-02T04:59:00Z"

    def test_zulu_form_is_accepted(self):
        request = validate_new_request(base_fields(deadline="2026-12-02T04:59:00Z"))
        assert request.deadline == "2026-12-02T04:59:00Z"

    @pytest.mark.parametrize(
        "deadline",
        [
            "2026-12-01",                 # a date with no time zone
            "2026-12-01T23:59:00",        # no offset
            "2026-12-01 23:59:00Z",       # not RFC 3339
            "2026-02-30T00:00:00Z",       # not a real date
            "December 1, 2026",
            "",
            None,
            12345,
        ],
    )
    def test_a_deadline_without_an_explicit_offset_is_invalid(self, deadline):
        with pytest.raises(ValidationError):
            validate_new_request(base_fields(deadline=deadline))


class TestApplicantNames:
    def test_surrounding_whitespace_is_removed(self):
        assert validate_applicant_name("  Ada Lovelace \n") == "Ada Lovelace"

    def test_a_blank_name_is_rejected(self):
        with pytest.raises(ValidationError):
            validate_applicant_name("   ")

    def test_names_are_not_case_folded(self):
        assert validate_applicant_name("ada lovelace") == "ada lovelace"


class TestDestinations:
    def test_an_email_request_requires_an_address(self):
        assert validate_destination(Channel.EMAIL, " dean@example.edu ") == "dean@example.edu"

    def test_a_url_is_not_an_email_destination(self):
        with pytest.raises(ValidationError):
            validate_destination(Channel.EMAIL, "https://portal.example.edu/submit/1")

    def test_a_portal_request_requires_an_absolute_http_url(self):
        url = "https://portal.example.edu/submit/1"
        assert validate_destination(Channel.PORTAL, url) == url

    @pytest.mark.parametrize(
        "destination",
        ["dean@example.edu", "/submit/1", "ftp://portal.example.edu/x", "portal.example.edu"],
    )
    def test_a_wrong_type_portal_destination_is_rejected(self, destination):
        with pytest.raises(ValidationError):
            validate_destination(Channel.PORTAL, destination)


class TestPurposes:
    @pytest.mark.parametrize("purpose", ["PHD_APPLICATION", "FELLOWSHIP"])
    def test_the_two_supported_purposes_parse(self, purpose):
        assert Purpose.parse(purpose, "purpose").value == purpose

    @pytest.mark.parametrize("purpose", ["OTHER", "phd_application", "*", "", None])
    def test_no_other_purpose_exists_in_version_1(self, purpose):
        with pytest.raises(ValidationError):
            Purpose.parse(purpose, "purpose")


class TestEvents:
    def test_a_valid_add_event_is_canonicalized(self):
        event = validate_event(
            {
                "event_id": " e-1 ",
                "source_kind": "email_inbox",
                "kind": "ADD_REQUEST",
                "new_request": base_fields(applicant_name="  Ada Lovelace  "),
            },
            expected_source_kind="email_inbox",
        )
        assert event.event_id == "e-1"
        assert event.new_request.applicant_name == "Ada Lovelace"

    def test_dataclass_events_are_accepted_too(self):
        event = validate_event(
            RequestEvent(
                event_id="e-1",
                source_kind="email_inbox",
                kind="ADD_REQUEST",
                new_request=NewRequest(**base_fields()),
            ),
            expected_source_kind="email_inbox",
        )
        assert event.kind == "ADD_REQUEST"

    def test_an_event_from_the_wrong_agent_is_rejected(self):
        with pytest.raises(ValidationError, match="source kind"):
            validate_event(
                {
                    "event_id": "e-1",
                    "source_kind": "portal_scan",
                    "kind": "ADD_REQUEST",
                    "new_request": base_fields(),
                },
                expected_source_kind="email_inbox",
            )

    def test_an_unknown_event_kind_is_rejected(self):
        with pytest.raises(ValidationError):
            validate_event(
                {"event_id": "e-1", "source_kind": "email_inbox", "kind": "UPDATE_REQUEST"},
                expected_source_kind="email_inbox",
            )

    def test_a_cancel_event_needs_a_target(self):
        with pytest.raises(ValidationError):
            validate_event(
                {"event_id": "e-1", "source_kind": "email_inbox", "kind": "CANCEL_REQUEST"},
                expected_source_kind="email_inbox",
            )

    def test_a_replace_event_needs_both_a_target_and_a_replacement(self):
        with pytest.raises(ValidationError):
            validate_event(
                {
                    "event_id": "e-1",
                    "source_kind": "email_inbox",
                    "kind": "REPLACE_REQUEST",
                    "target_source_reference": "msg-1",
                },
                expected_source_kind="email_inbox",
            )

    def test_a_non_event_object_is_rejected(self):
        with pytest.raises(ValidationError):
            validate_event("ADD_REQUEST", expected_source_kind="email_inbox")


def test_storage_round_trip():
    assert to_storage(parse_rfc3339("2026-12-01T23:59:00-05:00")) == "2026-12-02T04:59:00Z"
