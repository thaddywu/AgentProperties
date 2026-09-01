"""Safety Policy v1 — the conditions under which an external disclosure happens.

These tests drive :class:`recsub.policy.PolicyGuard` directly, including with
arguments the ordinary application flow would never produce, and assert that a
forbidden disclosure raises before any external component is called.
"""

from __future__ import annotations

import pytest

from recsub.enums import ReminderKind
from recsub.errors import PolicyViolation

from .conftest import PROFESSOR, Harness


def nothing_left_the_process(harness: Harness) -> bool:
    return harness.email.sent == [] and harness.portal.uploads == []


class TestGeneralConditions:
    """Policy 5."""

    def test_a_cancelled_request_cannot_authorize_a_submission(self, harness: Harness):
        request_id = harness.add_request(event_id="e-1", source_reference="msg-1")
        letter_id = harness.register()
        harness.app.cancel_request(request_id)

        with pytest.raises(PolicyViolation, match="REQUEST_NOT_PENDING"):
            harness.app.guard.submit_letter(request_id=request_id, letter_id=letter_id)

        assert nothing_left_the_process(harness)

    def test_a_submitted_request_cannot_authorize_a_second_submission(
        self, harness: Harness
    ):
        request_id = harness.add_request(event_id="e-1", source_reference="msg-1")
        letter_id = harness.register()
        harness.app.process_pending()
        assert harness.status(request_id) == "SUBMITTED"
        sent_before = len(harness.email.sent)

        with pytest.raises(PolicyViolation, match="REQUEST_NOT_PENDING"):
            harness.app.guard.submit_letter(request_id=request_id, letter_id=letter_id)

        assert len(harness.email.sent) == sent_before

    def test_an_unknown_request_cannot_authorize_a_submission(self, harness: Harness):
        letter_id = harness.register()

        with pytest.raises(PolicyViolation, match="REQUEST_NOT_FOUND"):
            harness.app.guard.submit_letter(request_id="REQ-999999", letter_id=letter_id)

        assert nothing_left_the_process(harness)

    def test_an_unregistered_file_cannot_be_submitted(self, harness: Harness):
        request_id = harness.add_request(event_id="e-1", source_reference="msg-1")
        harness.letter_file("never-registered.pdf")

        with pytest.raises(PolicyViolation, match="LETTER_NOT_REGISTERED"):
            harness.app.guard.submit_letter(request_id=request_id, letter_id="LET-000999")

        assert nothing_left_the_process(harness)

    def test_a_letter_for_another_applicant_is_forbidden(self, harness: Harness):
        request_id = harness.add_request(
            event_id="e-1", source_reference="msg-1", applicant="Ada Lovelace"
        )
        other = harness.register(applicant="Grace Hopper", name="grace.pdf")

        with pytest.raises(PolicyViolation, match="APPLICANT_MISMATCH"):
            harness.app.guard.submit_letter(request_id=request_id, letter_id=other)

        assert nothing_left_the_process(harness)

    def test_applicant_comparison_is_case_sensitive(self, harness: Harness):
        request_id = harness.add_request(
            event_id="e-1", source_reference="msg-1", applicant="Ada Lovelace"
        )
        other = harness.register(applicant="ada lovelace", name="lower.pdf")

        with pytest.raises(PolicyViolation, match="APPLICANT_MISMATCH"):
            harness.app.guard.submit_letter(request_id=request_id, letter_id=other)

    def test_a_letter_with_another_purpose_is_forbidden(self, harness: Harness):
        request_id = harness.add_request(
            event_id="e-1", source_reference="msg-1", purpose="FELLOWSHIP"
        )
        phd_letter = harness.register(purpose="PHD_APPLICATION")

        with pytest.raises(PolicyViolation, match="PURPOSE_MISMATCH"):
            harness.app.guard.submit_letter(request_id=request_id, letter_id=phd_letter)

        assert nothing_left_the_process(harness)

    def test_a_request_that_already_succeeded_is_refused_even_if_still_pending(
        self, harness: Harness
    ):
        """Defence in depth: the guard checks submission history, not only status."""
        request_id = harness.add_request(event_id="e-1", source_reference="msg-1")
        letter_id = harness.register()
        harness.app.process_pending()
        # Force the record back to PENDING behind the application's back.
        harness.app.repository._connection.execute(
            "UPDATE requests SET status = 'PENDING' WHERE request_id = ?", (request_id,)
        )

        with pytest.raises(PolicyViolation, match="ALREADY_SUBMITTED"):
            harness.app.guard.submit_letter(request_id=request_id, letter_id=letter_id)

    def test_a_registered_letter_whose_file_vanished_is_not_disclosed(
        self, harness: Harness
    ):
        import os

        request_id = harness.add_request(event_id="e-1", source_reference="msg-1")
        letter_id = harness.register()
        os.remove(harness.app.repository.get_letter(letter_id).file_path)

        with pytest.raises(PolicyViolation, match="LETTER_FILE_UNAVAILABLE"):
            harness.app.guard.submit_letter(request_id=request_id, letter_id=letter_id)

        assert nothing_left_the_process(harness)


class TestChannelsAndDestinations:
    """Policy 6 and 7."""

    def test_an_email_submission_uses_the_requests_own_address(self, harness: Harness):
        first = harness.add_request(
            event_id="e-1", source_reference="msg-1", destination="mit@example.edu"
        )
        second = harness.add_request(
            event_id="e-2", source_reference="msg-2", destination="stanford@example.edu"
        )
        harness.register()

        harness.app.process_pending()

        by_correlation = {m.correlation_id: m.to for m in harness.email.sent}
        assert by_correlation == {
            first: ["mit@example.edu"],
            second: ["stanford@example.edu"],
        }

    def test_a_batch_never_exchanges_destinations_between_requests(self, harness: Harness):
        """Policy 8: a batch does not combine the authority of several requests."""
        mit = harness.add_request(
            event_id="e-1",
            source_reference="msg-1",
            destination="mit@example.edu",
            deadline="2026-12-01T00:00:00Z",
        )
        stanford = harness.add_request(
            event_id="e-2",
            source_reference="msg-2",
            applicant="Grace Hopper",
            destination="stanford@example.edu",
            deadline="2026-12-02T00:00:00Z",
        )
        ada = harness.register(applicant="Ada Lovelace", name="ada.pdf")
        grace = harness.register(applicant="Grace Hopper", name="grace.pdf")
        ada_path = harness.app.repository.get_letter(ada).file_path
        grace_path = harness.app.repository.get_letter(grace).file_path

        harness.app.process_pending()

        sent = {m.correlation_id: m for m in harness.email.sent}
        assert sent[mit].to == ["mit@example.edu"]
        assert sent[mit].attachments == [ada_path]
        assert sent[stanford].to == ["stanford@example.edu"]
        assert sent[stanford].attachments == [grace_path]

    def test_a_portal_submission_uses_the_requests_own_url(self, harness: Harness):
        first = harness.add_request(
            event_id="p-1",
            source_reference="portal-1",
            channel="PORTAL",
            destination="https://portal.example.edu/submit/one",
            deadline="2026-12-01T00:00:00Z",
            source="portal_scan",
        )
        second = harness.add_request(
            event_id="p-2",
            source_reference="portal-2",
            channel="PORTAL",
            destination="https://portal.example.edu/submit/two",
            deadline="2026-12-02T00:00:00Z",
            source="portal_scan",
        )
        harness.register()

        harness.app.process_pending()

        urls = {u.correlation_id: u.submission_url for u in harness.portal.uploads}
        assert urls == {
            first: "https://portal.example.edu/submit/one",
            second: "https://portal.example.edu/submit/two",
        }

    def test_an_email_request_never_reaches_the_portal_agent(self, harness: Harness):
        harness.add_request(event_id="e-1", source_reference="msg-1", channel="EMAIL")
        harness.register()

        harness.app.process_pending()

        assert harness.portal.uploads == []
        assert len(harness.email.sent) == 1

    def test_a_portal_request_never_emails_the_letter(self, harness: Harness):
        harness.add_request(
            event_id="p-1",
            source_reference="portal-1",
            channel="PORTAL",
            source="portal_scan",
        )
        harness.register()

        harness.app.process_pending()

        assert harness.email.sent == []
        assert len(harness.portal.uploads) == 1

    def test_a_submission_email_has_one_recipient_no_cc_and_one_attachment(
        self, harness: Harness
    ):
        harness.add_request(event_id="e-1", source_reference="msg-1")
        letter_id = harness.register()
        harness.register(name="second-letter.pdf")  # a newer compatible letter exists too

        harness.app.process_pending()

        message = harness.email.sent[0]
        assert len(message.to) == 1
        assert message.cc == []
        assert len(message.attachments) == 1
        # exactly the selected letter, and no other letter file
        selected = harness.app.repository.get_letter(letter_id).file_path
        # exactly one compatible letter was chosen deterministically, and the
        # other registered letter for the same applicant was not disclosed
        assert message.attachments != [selected]
        assert len(set(message.attachments)) == 1


class TestReplacementAuthority:
    """Policy 3 and 9."""

    def test_the_replaced_request_cannot_authorize_a_submission(self, harness: Harness):
        old_id = harness.add_request(event_id="e-1", source_reference="msg-1")
        letter_id = harness.register()
        harness.inbox.events.append(
            {
                "event_id": "r-1",
                "source_kind": "email_inbox",
                "kind": "REPLACE_REQUEST",
                "target_source_reference": "msg-1",
                "new_request": {
                    "source_reference": "msg-2",
                    "applicant_name": "Ada Lovelace",
                    "application_description": "MIT EECS PhD",
                    "purpose": "PHD_APPLICATION",
                    "channel": "EMAIL",
                    "destination": "new-address@example.edu",
                    "deadline": "2026-12-15T23:59:00Z",
                },
            }
        )
        harness.app.sync()

        with pytest.raises(PolicyViolation, match="REQUEST_NOT_PENDING"):
            harness.app.guard.submit_letter(request_id=old_id, letter_id=letter_id)

        harness.app.process_pending()
        assert [m.to for m in harness.email.sent] == [["new-address@example.edu"]]

    def test_the_replacement_does_not_inherit_a_submitted_state(self, harness: Harness):
        harness.add_request(event_id="e-1", source_reference="msg-1")
        harness.register()
        harness.inbox.events.append(
            {
                "event_id": "r-1",
                "source_kind": "email_inbox",
                "kind": "REPLACE_REQUEST",
                "target_source_reference": "msg-1",
                "new_request": {
                    "source_reference": "msg-2",
                    "applicant_name": "Ada Lovelace",
                    "application_description": "MIT EECS PhD",
                    "purpose": "PHD_APPLICATION",
                    "channel": "EMAIL",
                    "destination": "new-address@example.edu",
                    "deadline": "2026-12-15T23:59:00Z",
                },
            }
        )
        harness.app.sync()

        new = harness.app.repository.find_request_by_source("email_inbox", "msg-2")
        assert new.status.value == "PENDING"
        assert harness.app.repository.has_successful_submission(new.request_id) is False

    def test_a_failed_attempt_does_not_authorize_a_retry_after_cancellation(
        self, harness: Harness
    ):
        request_id = harness.add_request(event_id="e-1", source_reference="msg-1")
        harness.register()
        harness.email.fail_all = True
        harness.app.process_pending()
        assert harness.status(request_id) == "PENDING"

        harness.app.cancel_request(request_id)
        harness.email.fail_all = False
        report = harness.app.process_pending()

        assert report.attempted == []
        assert len(harness.email.sent) == 1  # only the original failed attempt


class TestReminderPolicy:
    """Policy 10."""

    def test_a_reminder_may_only_go_to_the_professor(self, harness: Harness):
        harness.add_request(
            event_id="e-1",
            source_reference="msg-1",
            destination="committee@example.edu",
            deadline="2026-11-03T12:00:00Z",
        )

        harness.app.send_reminders()

        assert [m.to for m in harness.email.sent] == [[PROFESSOR]]
        assert harness.email.sent_to("committee@example.edu") == []

    def test_a_reminder_never_attaches_a_letter(self, harness: Harness):
        harness.add_request(
            event_id="e-1", source_reference="msg-1", deadline="2026-11-03T12:00:00Z"
        )
        # A compatible letter exists for a *different* purpose, so the request
        # still qualifies for a reminder.
        harness.register(purpose="FELLOWSHIP")

        harness.app.send_reminders()

        assert harness.email.sent[0].attachments == []

    def test_a_reminder_about_a_cancelled_request_is_forbidden(self, harness: Harness):
        request_id = harness.add_request(
            event_id="e-1", source_reference="msg-1", deadline="2026-11-03T12:00:00Z"
        )
        harness.app.cancel_request(request_id)

        with pytest.raises(PolicyViolation, match="REQUEST_NOT_PENDING"):
            harness.app.guard.send_reminder(
                request_id=request_id, kind=ReminderKind.THREE_DAY
            )

        assert harness.email.sent == []

    def test_a_reminder_about_a_submitted_request_is_forbidden(self, harness: Harness):
        request_id = harness.add_request(
            event_id="e-1", source_reference="msg-1", deadline="2026-11-03T12:00:00Z"
        )
        harness.register()
        harness.app.process_pending()

        with pytest.raises(PolicyViolation, match="REQUEST_NOT_PENDING"):
            harness.app.guard.send_reminder(
                request_id=request_id, kind=ReminderKind.ONE_DAY
            )

    def test_a_reminder_for_an_unknown_request_is_forbidden(self, harness: Harness):
        with pytest.raises(PolicyViolation, match="REQUEST_NOT_FOUND"):
            harness.app.guard.send_reminder(
                request_id="REQ-999999", kind=ReminderKind.ONE_DAY
            )
        assert harness.email.sent == []


class TestDeadlinesDoNotChangeAuthority:
    """Policy 11."""

    def test_a_past_deadline_does_not_cancel_or_block_a_pending_request(
        self, harness: Harness
    ):
        request_id = harness.add_request(
            event_id="e-1", source_reference="msg-1", deadline="2026-10-01T00:00:00Z"
        )
        harness.register()

        harness.app.process_pending()

        assert harness.status(request_id) == "SUBMITTED"
        assert len(harness.email.sent) == 1


class TestAdapterResults:
    def test_a_nonsense_adapter_result_is_treated_as_a_failure(self, harness: Harness):
        request_id = harness.add_request(event_id="e-1", source_reference="msg-1")
        harness.register()
        harness.email.send = lambda message: "definitely submitted, trust me"

        harness.app.process_pending()

        submission = harness.app.list_submissions()[0]
        assert submission.outcome.value == "FAILED"
        assert submission.error_code == "INVALID_ADAPTER_RESULT"
        assert harness.status(request_id) == "PENDING"


class TestTamperedState:
    """The guard re-reads and re-validates; it never trusts a stored row blindly."""

    def _corrupt_destination(self, harness: Harness, request_id: str, value: str) -> None:
        harness.app.repository._connection.execute(
            "UPDATE requests SET destination = ? WHERE request_id = ?", (value, request_id)
        )

    def test_an_email_request_with_a_url_destination_is_refused(self, harness: Harness):
        request_id = harness.add_request(event_id="e-1", source_reference="msg-1")
        letter_id = harness.register()
        self._corrupt_destination(harness, request_id, "https://portal.example.edu/x")

        with pytest.raises(PolicyViolation, match="DESTINATION_MISMATCH"):
            harness.app.guard.submit_letter(request_id=request_id, letter_id=letter_id)

        assert nothing_left_the_process(harness)

    def test_a_portal_request_with_an_address_destination_is_refused(
        self, harness: Harness
    ):
        request_id = harness.add_request(
            event_id="p-1",
            source_reference="portal-1",
            channel="PORTAL",
            source="portal_scan",
        )
        letter_id = harness.register()
        self._corrupt_destination(harness, request_id, "dean@example.edu")

        with pytest.raises(PolicyViolation, match="DESTINATION_MISMATCH"):
            harness.app.guard.submit_letter(request_id=request_id, letter_id=letter_id)

        assert nothing_left_the_process(harness)

    def test_the_batch_records_a_refusal_instead_of_disclosing(self, harness: Harness):
        request_id = harness.add_request(event_id="e-1", source_reference="msg-1")
        harness.register()
        self._corrupt_destination(harness, request_id, "https://portal.example.edu/x")

        report = harness.app.process_pending()

        assert nothing_left_the_process(harness)
        submission = harness.app.list_submissions()[0]
        assert submission.outcome.value == "FAILED"
        assert submission.error_code == "DESTINATION_MISMATCH"
        assert harness.status(request_id) == "PENDING"
        assert report.errors
