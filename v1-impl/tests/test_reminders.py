"""Specification 6.6 — deadline reminders."""

from __future__ import annotations

import pytest

from .conftest import PROFESSOR, Harness

# The harness clock starts at 2026-11-01T12:00:00Z.
IN_2_HOURS = "2026-11-01T14:00:00Z"
IN_20_HOURS = "2026-11-02T08:00:00Z"
IN_24_HOURS = "2026-11-02T12:00:00Z"
IN_48_HOURS = "2026-11-03T12:00:00Z"
IN_72_HOURS = "2026-11-04T12:00:00Z"
IN_73_HOURS = "2026-11-04T13:00:00Z"
IN_10_DAYS = "2026-11-11T12:00:00Z"
PASSED = "2026-10-30T12:00:00Z"


def pending(harness: Harness, deadline: str, *, reference="msg-1", event="e-1", **kw) -> str:
    return harness.add_request(
        event_id=event, source_reference=reference, deadline=deadline, **kw
    )


class TestWindows:
    @pytest.mark.parametrize("deadline", [IN_48_HOURS, IN_72_HOURS])
    def test_between_24_and_72_hours_sends_a_three_day_reminder(
        self, harness: Harness, deadline
    ):
        request_id = pending(harness, deadline)

        report = harness.app.send_reminders()

        assert report.sent
        reminders = harness.app.list_reminders()
        assert [r.reminder_kind.value for r in reminders] == ["THREE_DAY"]
        assert reminders[0].request_id == request_id
        assert reminders[0].outcome.value == "SUCCEEDED"

    @pytest.mark.parametrize("deadline", [IN_2_HOURS, IN_20_HOURS, IN_24_HOURS])
    def test_within_24_hours_sends_a_one_day_reminder(self, harness: Harness, deadline):
        pending(harness, deadline)

        harness.app.send_reminders()

        assert [r.reminder_kind.value for r in harness.app.list_reminders()] == ["ONE_DAY"]

    @pytest.mark.parametrize("deadline", [IN_73_HOURS, IN_10_DAYS])
    def test_beyond_72_hours_sends_nothing(self, harness: Harness, deadline):
        pending(harness, deadline)

        report = harness.app.send_reminders()

        assert harness.app.list_reminders() == []
        assert harness.email.sent == []
        assert report.skipped

    def test_a_past_deadline_sends_nothing(self, harness: Harness):
        pending(harness, PASSED)

        harness.app.send_reminders()

        assert harness.app.list_reminders() == []
        assert harness.email.sent == []

    def test_one_invocation_sends_at_most_one_reminder_per_request(self, harness: Harness):
        pending(harness, IN_2_HOURS)

        harness.app.send_reminders()

        assert len(harness.app.list_reminders()) == 1


class TestQualification:
    def test_a_request_with_a_compatible_letter_is_not_reminded(self, harness: Harness):
        pending(harness, IN_48_HOURS)
        harness.register()

        report = harness.app.send_reminders()

        assert harness.app.list_reminders() == []
        assert harness.email.sent == []
        assert report.skipped

    def test_an_incompatible_letter_does_not_suppress_the_reminder(self, harness: Harness):
        pending(harness, IN_48_HOURS, purpose="FELLOWSHIP")
        harness.register(purpose="PHD_APPLICATION")

        harness.app.send_reminders()

        assert len(harness.app.list_reminders()) == 1

    def test_cancelled_and_submitted_requests_are_not_reminded(self, harness: Harness):
        cancelled = pending(harness, IN_48_HOURS, reference="msg-1", event="e-1")
        submitted = pending(
            harness, IN_48_HOURS, reference="msg-2", event="e-2", applicant="Grace Hopper"
        )
        harness.app.cancel_request(cancelled)
        harness.register(applicant="Grace Hopper", name="grace.pdf")
        harness.app.process_pending()
        assert harness.status(submitted) == "SUBMITTED"

        harness.app.send_reminders()

        assert harness.app.list_reminders() == []


class TestReminderContent:
    def test_a_reminder_goes_only_to_the_professor_and_carries_no_letter(
        self, harness: Harness
    ):
        request_id = pending(harness, IN_48_HOURS, destination="dean@example.edu")

        harness.app.send_reminders()

        assert len(harness.email.sent) == 1
        message = harness.email.sent[0]
        assert message.to == [PROFESSOR]
        assert message.cc == []
        assert message.attachments == []
        assert request_id in message.body
        assert "Ada Lovelace" in message.body
        assert "MIT EECS PhD" in message.body
        assert "PHD_APPLICATION" in message.body
        assert "2026-11-03" in message.body  # the deadline, in the display time zone


class TestAtMostOnceSuccessfully:
    def test_a_successful_three_day_reminder_is_not_repeated(self, harness: Harness):
        pending(harness, IN_48_HOURS)

        harness.app.send_reminders()
        harness.clock.advance(hours=1)
        report = harness.app.send_reminders()

        assert len(harness.app.list_reminders()) == 1
        assert any("already sent" in line for line in report.skipped)

    def test_a_successful_one_day_reminder_is_not_repeated(self, harness: Harness):
        pending(harness, IN_48_HOURS)
        harness.app.send_reminders()  # THREE_DAY

        harness.clock.advance(hours=30)  # deadline is now 18 hours away
        harness.app.send_reminders()  # ONE_DAY
        harness.clock.advance(hours=1)
        harness.app.send_reminders()  # nothing more

        kinds = [r.reminder_kind.value for r in harness.app.list_reminders()]
        assert kinds == ["THREE_DAY", "ONE_DAY"]

    def test_the_one_day_reminder_takes_precedence_inside_24_hours(self, harness: Harness):
        pending(harness, IN_20_HOURS)

        harness.app.send_reminders()
        harness.clock.advance(hours=1)
        harness.app.send_reminders()

        kinds = [r.reminder_kind.value for r in harness.app.list_reminders()]
        assert kinds == ["ONE_DAY"]

    def test_a_failed_reminder_is_recorded_and_retried_in_the_window(
        self, harness: Harness
    ):
        request_id = pending(harness, IN_48_HOURS)
        harness.email.fail_all = True

        harness.app.send_reminders()
        first = harness.app.list_reminders()
        assert len(first) == 1 and first[0].outcome.value == "FAILED"
        assert first[0].error_code == "SCRIPTED_FAILURE"
        assert harness.status(request_id) == "PENDING"

        harness.email.fail_all = False
        harness.clock.advance(hours=1)
        harness.app.send_reminders()

        outcomes = [r.outcome.value for r in harness.app.list_reminders()]
        assert outcomes == ["FAILED", "SUCCEEDED"]

    def test_a_failing_reminder_does_not_stop_the_others(self, harness: Harness):
        first = pending(harness, IN_48_HOURS, reference="msg-1", event="e-1")
        second = pending(
            harness,
            IN_48_HOURS,
            reference="msg-2",
            event="e-2",
            applicant="Grace Hopper",
        )
        harness.email.fail_correlation_ids = {first}

        report = harness.app.send_reminders()

        by_request = {r.request_id: r.outcome.value for r in harness.app.list_reminders()}
        assert by_request == {first: "FAILED", second: "SUCCEEDED"}
        assert report.sent and report.failed

    def test_a_raising_gateway_is_recorded_as_a_failed_reminder(self, harness: Harness):
        request_id = pending(harness, IN_48_HOURS)
        harness.email.raise_correlation_ids = {request_id}

        harness.app.send_reminders()

        reminder = harness.app.list_reminders()[0]
        assert reminder.outcome.value == "FAILED"
        assert reminder.error_code == "ADAPTER_EXCEPTION"
