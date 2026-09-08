"""Specification 6.3 and 6.5 — cancellation and batch submission."""

from __future__ import annotations

import os

import pytest

from recsub.errors import NotFoundError, StateError
from recsub.service import LETTER_FILE_MISSING

from .conftest import Harness


class TestCancellation:
    def test_cancelling_a_pending_request_changes_it_to_cancelled(self, harness: Harness):
        request_id = harness.add_request(event_id="e-1", source_reference="msg-1")

        request = harness.app.cancel_request(request_id)

        assert request.status.value == "CANCELLED"
        assert harness.status(request_id) == "CANCELLED"

    def test_cancelling_an_unknown_request_changes_nothing(self, harness: Harness):
        with pytest.raises(NotFoundError):
            harness.app.cancel_request("REQ-999999")
        assert harness.app.list_requests() == []

    def test_cancelling_an_already_cancelled_request_is_an_error(self, harness: Harness):
        request_id = harness.add_request(event_id="e-1", source_reference="msg-1")
        harness.app.cancel_request(request_id)

        with pytest.raises(StateError, match="CANCELLED"):
            harness.app.cancel_request(request_id)

    def test_cancelling_a_submitted_request_is_an_error(self, harness: Harness):
        request_id = harness.add_request(event_id="e-1", source_reference="msg-1")
        harness.register()
        harness.app.process_pending()

        with pytest.raises(StateError, match="SUBMITTED"):
            harness.app.cancel_request(request_id)
        assert harness.status(request_id) == "SUBMITTED"


class TestEmailSubmission:
    def test_a_successful_submission_records_it_and_marks_the_request_submitted(
        self, harness: Harness
    ):
        request_id = harness.add_request(event_id="e-1", source_reference="msg-1")
        letter_id = harness.register()

        report = harness.app.process_pending()

        assert report.succeeded and not report.failed
        assert harness.status(request_id) == "SUBMITTED"
        submissions = harness.app.list_submissions()
        assert len(submissions) == 1
        assert submissions[0].outcome.value == "SUCCEEDED"
        assert submissions[0].request_id == request_id
        assert submissions[0].letter_id == letter_id
        assert submissions[0].channel.value == "EMAIL"
        assert submissions[0].receipt
        assert submissions[0].error_code is None

    def test_the_email_goes_only_to_the_recorded_destination_with_one_attachment(
        self, harness: Harness
    ):
        harness.add_request(
            event_id="e-1", source_reference="msg-1", destination="dean@example.edu"
        )
        letter_id = harness.register()
        letter = harness.app.repository.get_letter(letter_id)

        harness.app.process_pending()

        assert len(harness.email.sent) == 1
        message = harness.email.sent[0]
        assert message.to == ["dean@example.edu"]
        assert message.cc == []
        assert message.attachments == [letter.file_path]
        assert "Ada Lovelace" in message.subject
        assert "MIT EECS PhD" in message.body

    def test_a_failed_submission_records_the_failure_and_leaves_it_pending(
        self, harness: Harness
    ):
        request_id = harness.add_request(event_id="e-1", source_reference="msg-1")
        harness.register()
        harness.email.fail_all = True

        report = harness.app.process_pending()

        assert report.failed and not report.succeeded
        assert harness.status(request_id) == "PENDING"
        submission = harness.app.list_submissions()[0]
        assert submission.outcome.value == "FAILED"
        assert submission.error_code == "SCRIPTED_FAILURE"
        assert submission.receipt is None

    def test_a_failed_attempt_can_be_retried_by_a_later_run(self, harness: Harness):
        request_id = harness.add_request(event_id="e-1", source_reference="msg-1")
        harness.register()
        harness.email.fail_all = True
        harness.app.process_pending()

        harness.email.fail_all = False
        harness.app.process_pending()

        assert harness.status(request_id) == "SUBMITTED"
        outcomes = [s.outcome.value for s in harness.app.list_submissions()]
        assert outcomes == ["FAILED", "SUCCEEDED"]

    def test_an_adapter_exception_becomes_a_failed_record(self, harness: Harness):
        request_id = harness.add_request(event_id="e-1", source_reference="msg-1")
        harness.register()
        harness.email.raise_correlation_ids = {request_id}

        harness.app.process_pending()

        submission = harness.app.list_submissions()[0]
        assert submission.outcome.value == "FAILED"
        assert submission.error_code == "ADAPTER_EXCEPTION"
        assert harness.status(request_id) == "PENDING"


class TestPortalSubmission:
    def test_a_portal_request_uploads_to_its_own_url(self, harness: Harness):
        request_id = harness.add_request(
            event_id="p-1",
            source_reference="portal-1",
            channel="PORTAL",
            destination="https://portal.example.edu/submit/abc",
            source="portal_scan",
        )
        letter_id = harness.register()
        letter = harness.app.repository.get_letter(letter_id)

        harness.app.process_pending()

        assert harness.email.sent == []  # a portal request never sends a letter email
        assert len(harness.portal.uploads) == 1
        upload = harness.portal.uploads[0]
        assert upload.submission_url == "https://portal.example.edu/submit/abc"
        assert upload.file_path == letter.file_path
        assert upload.correlation_id == request_id
        assert harness.status(request_id) == "SUBMITTED"

    def test_a_failed_portal_submission_leaves_the_request_pending(self, harness: Harness):
        request_id = harness.add_request(
            event_id="p-1",
            source_reference="portal-1",
            channel="PORTAL",
            source="portal_scan",
        )
        harness.register()
        harness.portal.fail_all = True

        harness.app.process_pending()

        assert harness.status(request_id) == "PENDING"
        assert harness.app.list_submissions()[0].channel.value == "PORTAL"


class TestSelectionAndSkipping:
    def test_a_request_without_a_compatible_letter_is_skipped_without_a_record(
        self, harness: Harness
    ):
        request_id = harness.add_request(event_id="e-1", source_reference="msg-1")

        report = harness.app.process_pending()

        assert report.attempted == []
        assert harness.app.list_submissions() == []
        assert harness.email.sent == []
        assert harness.status(request_id) == "PENDING"
        assert any("no compatible letter" in line for line in report.skipped)

    def test_submitted_and_cancelled_requests_are_never_processed(self, harness: Harness):
        submitted = harness.add_request(event_id="e-1", source_reference="msg-1")
        cancelled = harness.add_request(event_id="e-2", source_reference="msg-2")
        harness.register()
        harness.app.process_pending()  # submits both
        harness.app.cancel_request(cancelled) if harness.status(
            cancelled
        ) == "PENDING" else None

        before = len(harness.email.sent)
        report = harness.app.process_pending()

        assert report.attempted == []
        assert len(harness.email.sent) == before
        assert harness.status(submitted) == "SUBMITTED"

    def test_a_cancelled_request_is_not_submitted_even_with_a_letter(
        self, harness: Harness
    ):
        request_id = harness.add_request(event_id="e-1", source_reference="msg-1")
        harness.register()
        harness.app.cancel_request(request_id)

        report = harness.app.process_pending()

        assert report.attempted == []
        assert harness.email.sent == []
        assert harness.app.list_submissions() == []

    def test_a_missing_letter_file_fails_without_any_external_call(self, harness: Harness):
        request_id = harness.add_request(event_id="e-1", source_reference="msg-1")
        letter_id = harness.register()
        os.remove(harness.app.repository.get_letter(letter_id).file_path)

        report = harness.app.process_pending()

        assert harness.email.sent == []
        assert harness.portal.uploads == []
        submission = harness.app.list_submissions()[0]
        assert submission.outcome.value == "FAILED"
        assert submission.error_code == LETTER_FILE_MISSING
        assert submission.letter_id == letter_id
        assert harness.status(request_id) == "PENDING"
        assert report.failed


class TestBatchBehavior:
    def test_pending_requests_are_processed_in_deadline_order(self, harness: Harness):
        late = harness.add_request(
            event_id="e-1", source_reference="msg-1", deadline="2026-12-20T00:00:00Z"
        )
        early = harness.add_request(
            event_id="e-2", source_reference="msg-2", deadline="2026-12-01T00:00:00Z"
        )
        middle = harness.add_request(
            event_id="e-3", source_reference="msg-3", deadline="2026-12-10T00:00:00Z"
        )
        harness.register()

        report = harness.app.process_pending()

        assert report.attempted == [early, middle, late]
        assert [m.correlation_id for m in harness.email.sent] == [early, middle, late]

    def test_equal_deadlines_are_broken_by_request_id(self, harness: Harness):
        first = harness.add_request(event_id="e-1", source_reference="msg-1")
        second = harness.add_request(event_id="e-2", source_reference="msg-2")
        harness.register()

        report = harness.app.process_pending()

        assert report.attempted == sorted([first, second])

    def test_the_batch_continues_after_one_request_fails(self, harness: Harness):
        first = harness.add_request(
            event_id="e-1", source_reference="msg-1", deadline="2026-12-01T00:00:00Z"
        )
        second = harness.add_request(
            event_id="e-2",
            source_reference="msg-2",
            applicant="Grace Hopper",
            deadline="2026-12-02T00:00:00Z",
        )
        third = harness.add_request(
            event_id="e-3",
            source_reference="msg-3",
            applicant="Alan Turing",
            deadline="2026-12-03T00:00:00Z",
        )
        harness.register(applicant="Ada Lovelace", name="ada.pdf")
        harness.register(applicant="Grace Hopper", name="grace.pdf")
        harness.register(applicant="Alan Turing", name="alan.pdf")
        harness.email.fail_correlation_ids = {second}

        report = harness.app.process_pending()

        assert harness.status(first) == "SUBMITTED"
        assert harness.status(second) == "PENDING"
        assert harness.status(third) == "SUBMITTED"
        assert len(report.attempted) == 3

    def test_the_batch_continues_after_one_adapter_raises(self, harness: Harness):
        first = harness.add_request(
            event_id="e-1", source_reference="msg-1", deadline="2026-12-01T00:00:00Z"
        )
        second = harness.add_request(
            event_id="e-2",
            source_reference="msg-2",
            applicant="Grace Hopper",
            deadline="2026-12-02T00:00:00Z",
        )
        harness.register(applicant="Ada Lovelace", name="ada.pdf")
        harness.register(applicant="Grace Hopper", name="grace.pdf")
        harness.email.raise_correlation_ids = {first}

        harness.app.process_pending()

        assert harness.status(first) == "PENDING"
        assert harness.status(second) == "SUBMITTED"

    def test_one_batch_run_makes_at_most_one_attempt_per_request(self, harness: Harness):
        request_id = harness.add_request(event_id="e-1", source_reference="msg-1")
        harness.register()
        harness.email.fail_all = True

        harness.app.process_pending()

        assert len(harness.email.sent) == 1
        assert len(harness.app.list_submissions(request_id)) == 1


class TestLetterReuse:
    def test_one_phd_letter_serves_several_phd_requests_for_the_same_applicant(
        self, harness: Harness
    ):
        first = harness.add_request(
            event_id="e-1", source_reference="msg-1", destination="mit@example.edu"
        )
        second = harness.add_request(
            event_id="e-2", source_reference="msg-2", destination="stanford@example.edu"
        )
        third = harness.add_request(
            event_id="e-3",
            source_reference="portal-1",
            channel="PORTAL",
            destination="https://portal.example.edu/submit/3",
            source="portal_scan",
        )
        letter_id = harness.register()
        letter = harness.app.repository.get_letter(letter_id)

        harness.app.process_pending()

        assert [harness.status(r) for r in (first, second, third)] == ["SUBMITTED"] * 3
        assert {m.to[0] for m in harness.email.sent} == {
            "mit@example.edu",
            "stanford@example.edu",
        }
        assert all(m.attachments == [letter.file_path] for m in harness.email.sent)
        assert harness.portal.uploads[0].file_path == letter.file_path
        # the letter is not consumed by a successful submission
        assert harness.app.repository.get_letter(letter_id) == letter

    def test_a_letter_is_not_reused_for_a_different_purpose(self, harness: Harness):
        phd = harness.add_request(event_id="e-1", source_reference="msg-1")
        fellowship = harness.add_request(
            event_id="e-2", source_reference="msg-2", purpose="FELLOWSHIP"
        )
        harness.register(purpose="PHD_APPLICATION")

        harness.app.process_pending()

        assert harness.status(phd) == "SUBMITTED"
        assert harness.status(fellowship) == "PENDING"
        assert len(harness.email.sent) == 1
