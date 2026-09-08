"""Specification 6.7 — the daily run."""

from __future__ import annotations

from .conftest import PROFESSOR, Harness

CLOCK_NOW = "2026-11-01T12:00:00Z"
SOON = "2026-11-03T12:00:00Z"   # 48 hours away: inside the THREE_DAY window
LATER = "2026-12-01T00:00:00Z"  # far away: no reminder


def add_event(event_id, reference, applicant, deadline, destination):
    return {
        "event_id": event_id,
        "source_kind": "email_inbox",
        "kind": "ADD_REQUEST",
        "new_request": {
            "source_reference": reference,
            "applicant_name": applicant,
            "application_description": f"{applicant} application",
            "purpose": "PHD_APPLICATION",
            "channel": "EMAIL",
            "destination": destination,
            "deadline": deadline,
        },
    }


class TestOrder:
    def test_the_three_stages_run_in_order(self, harness: Harness):
        order: list[str] = []
        for stage in ("sync", "process_pending", "send_reminders"):
            original = getattr(harness.app, stage)

            def wrapper(_original=original, _stage=stage):
                order.append(_stage)
                return _original()

            setattr(harness.app, stage, wrapper)

        harness.app.daily_run()

        assert order == ["sync", "process_pending", "send_reminders"]

    def test_an_event_scanned_this_run_is_submitted_in_the_same_run(
        self, harness: Harness
    ):
        harness.register(applicant="Ada Lovelace")
        harness.inbox.events.append(
            add_event("e-1", "msg-1", "Ada Lovelace", LATER, "mit@example.edu")
        )

        report = harness.app.daily_run()

        assert len(report.sync.applied) == 1
        assert len(report.process.succeeded) == 1
        request = harness.app.repository.find_request_by_source("email_inbox", "msg-1")
        assert request.status.value == "SUBMITTED"
        assert harness.email.sent[0].to == ["mit@example.edu"]

    def test_a_request_submitted_in_stage_two_gets_no_reminder_in_stage_three(
        self, harness: Harness
    ):
        harness.register(applicant="Ada Lovelace")
        harness.inbox.events.append(
            add_event("e-1", "msg-1", "Ada Lovelace", SOON, "mit@example.edu")
        )

        report = harness.app.daily_run()

        assert report.process.succeeded
        assert report.reminders.sent == []
        assert harness.app.list_reminders() == []

    def test_a_request_still_lacking_a_letter_is_reminded_in_the_same_run(
        self, harness: Harness
    ):
        harness.inbox.events.append(
            add_event("e-1", "msg-1", "Grace Hopper", SOON, "nsf@example.edu")
        )

        report = harness.app.daily_run()

        assert report.sync.applied
        assert report.process.attempted == []
        assert len(report.reminders.sent) == 1
        assert harness.email.sent[0].to == [PROFESSOR]
        assert harness.app.list_reminders()[0].reminder_kind.value == "THREE_DAY"


class TestResilience:
    def test_a_failing_source_does_not_prevent_submissions_or_reminders(
        self, harness: Harness
    ):
        harness.inbox.raises = RuntimeError("inbox unavailable")
        with_letter = harness.add_request(
            event_id="p-1",
            source_reference="portal-1",
            applicant="Ada Lovelace",
            channel="PORTAL",
            deadline=LATER,
            source="portal_scan",
        )
        without_letter = harness.add_request(
            event_id="p-2",
            source_reference="portal-2",
            applicant="Grace Hopper",
            channel="PORTAL",
            deadline=SOON,
            source="portal_scan",
        )
        harness.register(applicant="Ada Lovelace")

        report = harness.app.daily_run()

        assert report.sync.errors
        assert harness.status(with_letter) == "SUBMITTED"
        assert len(report.reminders.sent) == 1
        assert harness.app.list_reminders()[0].request_id == without_letter

    def test_a_failing_stage_is_reported_and_the_later_stages_still_run(
        self, harness: Harness
    ):
        harness.add_request(
            event_id="e-1", source_reference="msg-1", deadline=SOON, applicant="Ada Lovelace"
        )

        def explode():
            raise RuntimeError("the submission stage is broken")

        harness.app.process_pending = explode

        report = harness.app.daily_run()

        assert any("submission stage failed" in line for line in report.errors)
        assert len(report.reminders.sent) == 1

    def test_the_daily_run_is_safe_to_repeat(self, harness: Harness):
        harness.register(applicant="Ada Lovelace")
        harness.inbox.events.append(
            add_event("e-1", "msg-1", "Ada Lovelace", SOON, "mit@example.edu")
        )

        harness.app.daily_run()
        harness.clock.advance(hours=1)
        second = harness.app.daily_run()

        assert len(harness.app.list_requests()) == 1
        assert len(harness.app.list_submissions()) == 1
        assert second.process.attempted == []
        assert len(harness.email.sent) == 1
