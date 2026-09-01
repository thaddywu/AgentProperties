"""Specification 6.1 — ingesting request events."""

from __future__ import annotations

from recsub.enums import RequestStatus

from .conftest import Harness


def add_event(event_id="e-1", reference="msg-1", **overrides):
    fields = {
        "source_reference": reference,
        "applicant_name": "Ada Lovelace",
        "application_description": "MIT EECS PhD",
        "purpose": "PHD_APPLICATION",
        "channel": "EMAIL",
        "destination": "admissions@example.edu",
        "deadline": "2026-12-01T23:59:00Z",
    }
    fields.update(overrides)
    return {
        "event_id": event_id,
        "source_kind": "email_inbox",
        "kind": "ADD_REQUEST",
        "new_request": fields,
    }


def cancel_event(event_id="c-1", reference="msg-1"):
    return {
        "event_id": event_id,
        "source_kind": "email_inbox",
        "kind": "CANCEL_REQUEST",
        "target_source_reference": reference,
    }


def replace_event(event_id="r-1", old="msg-1", new_reference="msg-2", **overrides):
    fields = {
        "source_reference": new_reference,
        "applicant_name": "Ada Lovelace",
        "application_description": "MIT EECS PhD",
        "purpose": "PHD_APPLICATION",
        "channel": "EMAIL",
        "destination": "admissions@example.edu",
        "deadline": "2026-12-15T23:59:00Z",
    }
    fields.update(overrides)
    return {
        "event_id": event_id,
        "source_kind": "email_inbox",
        "kind": "REPLACE_REQUEST",
        "target_source_reference": old,
        "new_request": fields,
    }


class TestAdd:
    def test_a_valid_add_event_creates_a_pending_request(self, harness: Harness):
        harness.inbox.events.append(add_event())
        report = harness.app.sync()

        assert len(report.applied) == 1
        requests = harness.app.list_requests()
        assert len(requests) == 1
        request = requests[0]
        assert request.status is RequestStatus.PENDING
        assert request.applicant_name == "Ada Lovelace"
        assert request.destination == "admissions@example.edu"
        assert request.deadline == "2026-12-01T23:59:00Z"
        assert request.source_kind == "email_inbox"
        assert request.source_reference == "msg-1"
        assert request.supersedes_request_id is None

    def test_the_application_does_not_alter_the_supplied_fields(self, harness: Harness):
        harness.inbox.events.append(
            add_event(
                purpose="FELLOWSHIP",
                channel="PORTAL",
                destination="https://portal.example.edu/submit/9",
                deadline="2026-12-01T23:59:00-05:00",
                applicant_name="  Grace Hopper  ",
            )
        )
        harness.app.sync()

        request = harness.app.list_requests()[0]
        assert request.applicant_name == "Grace Hopper"  # trimmed only
        assert request.purpose.value == "FELLOWSHIP"
        assert request.channel.value == "PORTAL"
        assert request.destination == "https://portal.example.edu/submit/9"
        assert request.deadline == "2026-12-02T04:59:00Z"  # normalized to UTC only


class TestRepeatedScans:
    def test_the_same_event_id_is_applied_only_once(self, harness: Harness):
        harness.inbox.events.append(add_event())

        first = harness.app.sync()
        second = harness.app.sync()
        third = harness.app.sync()

        assert len(harness.app.list_requests()) == 1
        assert first.applied and not first.skipped
        assert not second.applied and second.skipped
        assert not third.applied and third.skipped
        assert harness.inbox.scan_count == 3

    def test_a_new_event_id_for_an_ingested_source_reference_is_a_duplicate(
        self, harness: Harness
    ):
        harness.inbox.events.append(add_event(event_id="e-1", reference="msg-1"))
        harness.app.sync()
        harness.inbox.events.append(add_event(event_id="e-2", reference="msg-1"))

        report = harness.app.sync()

        assert len(harness.app.list_requests()) == 1
        assert any("duplicate" in line for line in report.skipped)

    def test_a_repeated_cancellation_does_not_repeat_the_state_change(
        self, harness: Harness
    ):
        request_id = harness.add_request(event_id="e-1", source_reference="msg-1")
        harness.inbox.events.append(cancel_event())

        harness.app.sync()
        updated_at = harness.app.repository.require_request(request_id).updated_at
        harness.clock.advance(hours=1)
        second = harness.app.sync()

        request = harness.app.repository.require_request(request_id)
        assert request.status is RequestStatus.CANCELLED
        assert request.updated_at == updated_at  # untouched by the repeat
        assert not second.applied

    def test_a_second_cancellation_event_for_a_cancelled_request_is_idempotent(
        self, harness: Harness
    ):
        request_id = harness.add_request(event_id="e-1", source_reference="msg-1")
        harness.inbox.events.append(cancel_event(event_id="c-1"))
        harness.app.sync()
        harness.inbox.events.append(cancel_event(event_id="c-2"))

        report = harness.app.sync()

        assert harness.status(request_id) == "CANCELLED"
        assert not report.errors
        assert any("already CANCELLED" in line for line in report.skipped)


class TestInvalidEvents:
    def test_an_invalid_event_does_not_block_other_valid_events(self, harness: Harness):
        harness.inbox.events.extend(
            [
                add_event(event_id="bad-1", reference="msg-bad", deadline="2026-12-01"),
                add_event(event_id="ok-1", reference="msg-1"),
                {"event_id": "bad-2", "source_kind": "email_inbox", "kind": "NONSENSE"},
                add_event(event_id="ok-2", reference="msg-2", applicant_name="Grace Hopper"),
            ]
        )

        report = harness.app.sync()

        references = {r.source_reference for r in harness.app.list_requests()}
        assert references == {"msg-1", "msg-2"}
        assert len(report.errors) == 2
        assert len(report.applied) == 2

    def test_one_failing_agent_does_not_stop_the_others(self, harness: Harness):
        harness.inbox.raises = RuntimeError("the inbox is unreachable")
        harness.portal_source.events.append(
            {
                "event_id": "p-1",
                "source_kind": "portal_scan",
                "kind": "ADD_REQUEST",
                "new_request": {
                    "source_reference": "portal-1",
                    "applicant_name": "Grace Hopper",
                    "application_description": "NSF Fellowship",
                    "purpose": "FELLOWSHIP",
                    "channel": "PORTAL",
                    "destination": "https://portal.example.edu/submit/1",
                    "deadline": "2026-12-20T23:59:00Z",
                },
            }
        )

        report = harness.app.sync()

        assert len(harness.app.list_requests()) == 1
        assert report.scanned_sources == 2
        assert any("unreachable" in line for line in report.errors)

    def test_an_invalid_event_is_not_recorded_as_applied(self, harness: Harness):
        harness.inbox.events.append(add_event(event_id="bad-1", deadline="tomorrow"))
        harness.app.sync()
        assert harness.app.repository.list_applied_events() == []


class TestCancellationEvents:
    def test_a_cancellation_moves_a_pending_request_to_cancelled(self, harness: Harness):
        request_id = harness.add_request(event_id="e-1", source_reference="msg-1")
        harness.inbox.events.append(cancel_event())

        harness.app.sync()

        assert harness.status(request_id) == "CANCELLED"

    def test_a_cancellation_for_an_unknown_request_changes_nothing(self, harness: Harness):
        harness.inbox.events.append(cancel_event(reference="never-seen"))

        report = harness.app.sync()

        assert harness.app.list_requests() == []
        assert harness.app.repository.list_applied_events() == []
        assert any("unknown request" in line for line in report.errors)

    def test_a_cancellation_for_a_submitted_request_changes_nothing(self, harness: Harness):
        request_id = harness.add_request(event_id="e-1", source_reference="msg-1")
        harness.register()
        harness.app.process_pending()
        assert harness.status(request_id) == "SUBMITTED"

        harness.inbox.events.append(cancel_event())
        report = harness.app.sync()

        assert harness.status(request_id) == "SUBMITTED"
        assert any("already SUBMITTED" in line for line in report.errors)


class TestReplacementEvents:
    def test_a_valid_replacement_cancels_creates_and_records_supersession(
        self, harness: Harness
    ):
        old_id = harness.add_request(event_id="e-1", source_reference="msg-1")
        harness.inbox.events.append(
            replace_event(old="msg-1", new_reference="msg-2", deadline="2026-12-15T23:59:00Z")
        )

        harness.app.sync()

        old = harness.app.repository.require_request(old_id)
        new = harness.app.repository.find_request_by_source("email_inbox", "msg-2")
        assert old.status is RequestStatus.CANCELLED
        assert new is not None
        assert new.status is RequestStatus.PENDING
        assert new.supersedes_request_id == old_id
        assert new.deadline == "2026-12-15T23:59:00Z"
        assert harness.app.repository.superseded_by(old_id) == new.request_id

    def test_the_replacement_is_a_distinct_request_with_its_own_context(
        self, harness: Harness
    ):
        old_id = harness.add_request(event_id="e-1", source_reference="msg-1")
        harness.inbox.events.append(
            replace_event(
                old="msg-1",
                new_reference="msg-2",
                channel="PORTAL",
                destination="https://portal.example.edu/submit/7",
            )
        )

        harness.app.sync()

        new = harness.app.repository.find_request_by_source("email_inbox", "msg-2")
        assert new.request_id != old_id
        assert new.channel.value == "PORTAL"
        assert new.destination == "https://portal.example.edu/submit/7"

    def test_a_replacement_with_an_invalid_replacement_leaves_the_old_request_alone(
        self, harness: Harness
    ):
        old_id = harness.add_request(event_id="e-1", source_reference="msg-1")
        before = harness.app.repository.require_request(old_id)

        harness.inbox.events.append(
            replace_event(old="msg-1", new_reference="msg-2", destination="not-an-address")
        )
        report = harness.app.sync()

        assert harness.app.repository.require_request(old_id) == before
        assert harness.app.repository.find_request_by_source("email_inbox", "msg-2") is None
        assert len(harness.app.list_requests()) == 1
        assert report.errors

    def test_a_replacement_of_an_unknown_request_creates_nothing(self, harness: Harness):
        harness.inbox.events.append(replace_event(old="never-seen", new_reference="msg-2"))

        report = harness.app.sync()

        assert harness.app.list_requests() == []
        assert any("unknown request" in line for line in report.errors)

    def test_a_replacement_of_a_cancelled_request_is_rejected_whole(self, harness: Harness):
        old_id = harness.add_request(event_id="e-1", source_reference="msg-1")
        harness.app.cancel_request(old_id)

        harness.inbox.events.append(replace_event(old="msg-1", new_reference="msg-2"))
        report = harness.app.sync()

        assert harness.status(old_id) == "CANCELLED"
        assert harness.app.repository.find_request_by_source("email_inbox", "msg-2") is None
        assert any("not PENDING" in line for line in report.errors)

    def test_a_replacement_reusing_an_existing_source_reference_is_rejected(
        self, harness: Harness
    ):
        old_id = harness.add_request(event_id="e-1", source_reference="msg-1")
        harness.add_request(event_id="e-2", source_reference="msg-2", applicant="Grace Hopper")

        harness.inbox.events.append(replace_event(old="msg-1", new_reference="msg-2"))
        report = harness.app.sync()

        assert harness.status(old_id) == "PENDING"
        assert len(harness.app.list_requests()) == 2
        assert any("already used" in line for line in report.errors)

    def test_a_repeated_replacement_event_is_applied_once(self, harness: Harness):
        harness.add_request(event_id="e-1", source_reference="msg-1")
        harness.inbox.events.append(replace_event(event_id="r-1", old="msg-1", new_reference="msg-2"))

        harness.app.sync()
        harness.app.sync()

        assert len(harness.app.list_requests()) == 2
