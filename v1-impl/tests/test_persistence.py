"""Specification 7 — persistence, ownership, and transactional consistency."""

from __future__ import annotations

from pathlib import Path

import pytest

from recsub.config import Components
from recsub.db import connect
from recsub.enums import RequestStatus
from recsub.repository import Repository
from recsub.service import Application

from .conftest import Harness, make_config


def reopen(harness: Harness) -> Application:
    """Open a second application over the same database file."""
    return Application.open(
        make_config(harness.tmp_path),
        Components(
            request_sources=(),
            email_gateway=harness.email,
            portal_agent=harness.portal,
            clock=harness.clock,
        ),
    )


class TestDurability:
    def test_state_survives_reopening_the_database(self, harness: Harness):
        request_id = harness.add_request(event_id="e-1", source_reference="msg-1")
        letter_id = harness.register()
        harness.app.process_pending()
        harness.app.close()

        with reopen(harness) as app:
            request = app.repository.require_request(request_id)
            assert request.status is RequestStatus.SUBMITTED
            assert app.repository.get_letter(letter_id) is not None
            assert len(app.list_submissions()) == 1
            assert app.repository.event_applied("email_inbox", "e-1")

    def test_letter_files_stay_outside_the_database(self, harness: Harness):
        path = Path(harness.letter_file("secret.pdf"))
        path.write_text("CONFIDENTIAL LETTER TEXT\n", encoding="utf-8")
        harness.app.register_letter(
            file_path=str(path), applicant_name="Ada Lovelace", purpose="PHD_APPLICATION"
        )
        harness.add_request(event_id="e-1", source_reference="msg-1")
        harness.app.process_pending()
        harness.app.close()

        database = (harness.tmp_path / "recsub.sqlite3").read_bytes()
        assert b"CONFIDENTIAL LETTER TEXT" not in database
        assert path.read_text(encoding="utf-8") == "CONFIDENTIAL LETTER TEXT\n"


class TestTransactions:
    def test_a_successful_submission_and_its_status_change_commit_together(
        self, harness: Harness
    ):
        request_id = harness.add_request(event_id="e-1", source_reference="msg-1")
        harness.register()

        original = harness.app.repository.set_request_status

        def explode(*args, **kwargs):
            raise RuntimeError("the status update failed")

        harness.app.repository.set_request_status = explode
        report = harness.app.process_pending()
        harness.app.repository.set_request_status = original

        # The external send happened, but nothing was half-recorded: there is no
        # successful submission sitting against a PENDING request.
        assert len(harness.email.sent) == 1
        assert harness.app.list_submissions() == []
        assert harness.status(request_id) == "PENDING"
        assert report.errors

    def test_a_failed_replacement_rolls_back_completely(self, harness: Harness):
        old_id = harness.add_request(event_id="e-1", source_reference="msg-1")
        original = harness.app.repository.create_request

        def explode(*args, **kwargs):
            raise RuntimeError("insert failed")

        harness.app.repository.create_request = explode
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
                    "destination": "admissions@example.edu",
                    "deadline": "2026-12-15T23:59:00Z",
                },
            }
        )
        report = harness.app.sync()
        harness.app.repository.create_request = original

        assert harness.status(old_id) == "PENDING"  # the cancellation rolled back
        assert not harness.app.repository.event_applied("email_inbox", "r-1")
        assert report.errors

    def test_an_applied_event_id_and_its_state_change_commit_together(
        self, harness: Harness
    ):
        harness.add_request(event_id="e-1", source_reference="msg-1")
        applied = harness.app.repository.list_applied_events()

        assert [(row["source_kind"], row["event_id"]) for row in applied] == [
            ("email_inbox", "e-1")
        ]


class TestSchema:
    def test_initialization_is_idempotent(self, tmp_path: Path):
        path = tmp_path / "db.sqlite3"
        connect(path).close()
        connect(path).close()
        connection = connect(path)
        version = connection.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        ).fetchone()[0]
        assert version == "1"
        connection.close()

    def test_the_schema_rejects_a_value_outside_an_enumeration(self, tmp_path: Path):
        import sqlite3

        repository = Repository(connect(tmp_path / "db.sqlite3"))
        with pytest.raises(sqlite3.IntegrityError):
            with repository.transaction():
                repository.create_request(
                    applicant_name="Ada",
                    application_description="d",
                    purpose="TENURE",
                    channel="EMAIL",
                    destination="a@b.co",
                    deadline="2026-01-01T00:00:00Z",
                    source_kind="s",
                    source_reference="r",
                    supersedes_request_id=None,
                    now="2026-01-01T00:00:00Z",
                )
        repository.close()

    def test_the_same_source_reference_cannot_be_ingested_twice(self, tmp_path: Path):
        import sqlite3

        repository = Repository(connect(tmp_path / "db.sqlite3"))
        fields = dict(
            applicant_name="Ada",
            application_description="d",
            purpose="FELLOWSHIP",
            channel="EMAIL",
            destination="a@b.co",
            deadline="2026-01-01T00:00:00Z",
            source_kind="inbox",
            source_reference="msg-1",
            supersedes_request_id=None,
            now="2026-01-01T00:00:00Z",
        )
        with repository.transaction():
            repository.create_request(**fields)
        with pytest.raises(sqlite3.IntegrityError):
            with repository.transaction():
                repository.create_request(**fields)
        repository.close()
