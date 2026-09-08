"""Specification 6.8 — the command-line interface, end to end.

Each invocation goes through :func:`recsub.cli.main` exactly as the shell
would, against a configuration file that names the local test doubles.  State
survives between invocations in the SQLite database and in the doubles' log
file, so these tests exercise the real persistence path.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from recsub.cli import main

CLOCK = "2026-11-01T12:00:00Z"
PROFESSOR = "professor@example.edu"


class Cli:
    """A configured workspace plus a helper for running commands."""

    def __init__(self, tmp_path: Path) -> None:
        self.root = tmp_path
        self.events_path = tmp_path / "events.json"
        self.log_path = tmp_path / "outbound.jsonl"
        self.config_path = tmp_path / "config.json"
        self.events_path.write_text("[]", encoding="utf-8")
        self.config_path.write_text(
            json.dumps(
                {
                    "database_path": "recsub.sqlite3",
                    "professor_email": PROFESSOR,
                    "display_time_zone": "America/New_York",
                    "request_sources": [
                        {
                            "factory": "recsub.testing.doubles:json_file_request_source",
                            "options": {
                                "source_kind": "email_inbox",
                                "events_path": "events.json",
                            },
                        }
                    ],
                    "email_gateway": {
                        "factory": "recsub.testing.doubles:recording_email_gateway",
                        "options": {"log_path": "outbound.jsonl"},
                    },
                    "portal_agent": {
                        "factory": "recsub.testing.doubles:recording_portal_agent",
                        "options": {"log_path": "outbound.jsonl"},
                    },
                    "clock": {
                        "factory": "recsub.testing.doubles:fixed_clock",
                        "options": {"instant": CLOCK},
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def run(self, *args: str, expect: int = 0) -> str:
        stream = io.StringIO()
        code = main(["--config", str(self.config_path), *args], stream=stream)
        assert code == expect, f"{args} exited {code}\n{stream.getvalue()}"
        return stream.getvalue()

    def json_run(self, *args: str) -> dict:
        return json.loads(self.run("--json", *args))

    def set_events(self, events: list[dict]) -> None:
        self.events_path.write_text(json.dumps(events), encoding="utf-8")

    def letter(self, name: str = "ada.pdf") -> str:
        path = self.root / "letters" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("completed letter\n", encoding="utf-8")
        return str(path)

    @property
    def outbound(self) -> list[dict]:
        if not self.log_path.is_file():
            return []
        return [
            json.loads(line)
            for line in self.log_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]


@pytest.fixture
def cli(tmp_path: Path) -> Cli:
    return Cli(tmp_path)


def event(reference: str, *, deadline: str, destination: str, channel: str = "EMAIL",
          applicant: str = "Ada Lovelace", purpose: str = "PHD_APPLICATION") -> dict:
    return {
        "event_id": f"evt-{reference}",
        "source_kind": "email_inbox",
        "kind": "ADD_REQUEST",
        "new_request": {
            "source_reference": reference,
            "applicant_name": applicant,
            "application_description": f"{applicant} — {reference}",
            "purpose": purpose,
            "channel": channel,
            "destination": destination,
            "deadline": deadline,
        },
    }


class TestSetup:
    def test_check_config_reports_a_valid_configuration(self, cli: Cli):
        output = cli.run("check-config")
        assert "is valid" in output
        assert PROFESSOR in output

    def test_init_db_creates_the_database(self, cli: Cli):
        cli.run("init-db")
        assert (cli.root / "recsub.sqlite3").is_file()

    def test_a_missing_configuration_file_is_a_usage_error(self, tmp_path: Path):
        stream = io.StringIO()
        code = main(["--config", str(tmp_path / "nope.json"), "list-requests"], stream=stream)
        assert code == 2

    def test_a_command_without_any_configuration_is_a_usage_error(self, monkeypatch):
        monkeypatch.delenv("RECSUB_CONFIG", raising=False)
        assert main(["list-requests"], stream=io.StringIO()) == 2

    def test_the_configuration_may_come_from_the_environment(self, cli: Cli, monkeypatch):
        monkeypatch.setenv("RECSUB_CONFIG", str(cli.config_path))
        stream = io.StringIO()
        assert main(["list-requests"], stream=stream) == 0


class TestFullWorkflow:
    def test_the_professor_can_run_the_whole_workflow(self, cli: Cli):
        cli.run("init-db")
        cli.set_events(
            [
                event("msg-1", deadline="2026-12-01T23:59:00-05:00", destination="mit@example.edu"),
                event(
                    "portal-1",
                    deadline="2026-12-05T00:00:00Z",
                    destination="https://portal.example.edu/submit/1",
                    channel="PORTAL",
                ),
                event(
                    "msg-2",
                    deadline="2026-11-03T12:00:00Z",
                    destination="nsf@example.edu",
                    applicant="Grace Hopper",
                    purpose="FELLOWSHIP",
                ),
            ]
        )

        sync = cli.json_run("sync")
        assert len(sync["applied"]) == 3
        assert sync["errors"] == []

        requests = cli.json_run("list-requests")["requests"]
        assert [r["status"] for r in requests] == ["PENDING"] * 3
        by_reference = {r["source_reference"]: r for r in requests}
        assert by_reference["msg-1"]["deadline_utc"] == "2026-12-02T04:59:00Z"
        assert by_reference["msg-1"]["deadline_local"].startswith("2026-12-01T23:59:00")

        registered = cli.json_run(
            "register-letter",
            "--path",
            cli.letter(),
            "--applicant",
            "Ada Lovelace",
            "--purpose",
            "PHD_APPLICATION",
        )
        assert registered["letter_id"] == "LET-000001"

        process = cli.json_run("process")
        assert len(process["succeeded"]) == 2  # both of Ada's requests
        assert len(process["skipped"]) == 1    # Grace has no letter

        statuses = {
            r["source_reference"]: r["status"]
            for r in cli.json_run("list-requests")["requests"]
        }
        assert statuses == {"msg-1": "SUBMITTED", "portal-1": "SUBMITTED", "msg-2": "PENDING"}

        reminders = cli.json_run("remind")
        assert len(reminders["sent"]) == 1

        history = cli.json_run("list-submissions")["submissions"]
        assert [s["outcome"] for s in history] == ["SUCCEEDED", "SUCCEEDED"]
        assert all(s["receipt"] for s in history)

        reminder_history = cli.json_run("list-reminders")["reminders"]
        assert [r["reminder_kind"] for r in reminder_history] == ["THREE_DAY"]

        # What actually left the process, as recorded by the doubles.
        outbound = cli.outbound
        assert [entry["kind"] for entry in outbound] == ["email", "portal", "email"]
        assert outbound[0]["call"]["to"] == ["mit@example.edu"]
        assert outbound[0]["call"]["cc"] == []
        assert len(outbound[0]["call"]["attachments"]) == 1
        assert outbound[1]["call"]["submission_url"] == "https://portal.example.edu/submit/1"
        assert outbound[2]["call"]["to"] == [PROFESSOR]
        assert outbound[2]["call"]["attachments"] == []

    def test_show_request_displays_everything_stored(self, cli: Cli):
        cli.set_events(
            [event("msg-1", deadline="2026-12-01T00:00:00Z", destination="mit@example.edu")]
        )
        cli.run("sync")
        cli.run(
            "register-letter", "--path", cli.letter(), "--applicant", "Ada Lovelace",
            "--purpose", "PHD_APPLICATION",
        )
        cli.run("process")

        detail = cli.json_run("show-request", "REQ-000001")

        assert detail["status"] == "SUBMITTED"
        assert detail["destination"] == "mit@example.edu"
        assert detail["source_kind"] == "email_inbox"
        assert detail["compatible_letter_id"] == "LET-000001"
        assert len(detail["submissions"]) == 1
        assert detail["submissions"][0]["outcome"] == "SUCCEEDED"

        human = cli.run("show-request", "REQ-000001")
        assert "SUBMITTED" in human and "mit@example.edu" in human

    def test_repeated_sync_does_not_duplicate_requests(self, cli: Cli):
        cli.set_events(
            [event("msg-1", deadline="2026-12-01T00:00:00Z", destination="mit@example.edu")]
        )
        cli.run("sync")
        cli.run("sync")
        cli.run("sync")

        assert len(cli.json_run("list-requests")["requests"]) == 1

    def test_daily_run_performs_all_three_stages(self, cli: Cli):
        cli.run(
            "register-letter", "--path", cli.letter(), "--applicant", "Ada Lovelace",
            "--purpose", "PHD_APPLICATION",
        )
        cli.set_events(
            [
                event("msg-1", deadline="2026-12-01T00:00:00Z", destination="mit@example.edu"),
                event(
                    "msg-2",
                    deadline="2026-11-03T12:00:00Z",
                    destination="nsf@example.edu",
                    applicant="Grace Hopper",
                ),
            ]
        )

        report = cli.json_run("daily-run")

        assert len(report["sync"]["applied"]) == 2
        assert len(report["process"]["succeeded"]) == 1
        assert len(report["reminders"]["sent"]) == 1
        assert report["errors"] == []

        human = cli.run("daily-run")
        assert "1. synchronization" in human
        assert human.index("1. synchronization") < human.index("2. submissions")
        assert human.index("2. submissions") < human.index("3. reminders")


class TestErrorReporting:
    def test_cancelling_an_unknown_request_reports_an_error(self, cli: Cli):
        cli.run("init-db")
        cli.run("cancel-request", "REQ-999999", expect=1)

    def test_cancelling_a_pending_request_succeeds(self, cli: Cli):
        cli.set_events(
            [event("msg-1", deadline="2026-12-01T00:00:00Z", destination="mit@example.edu")]
        )
        cli.run("sync")

        output = cli.run("cancel-request", "REQ-000001")

        assert "CANCELLED" in output
        assert cli.json_run("list-requests", "--status", "CANCELLED")["requests"]
        assert cli.json_run("list-requests", "--status", "PENDING")["requests"] == []

    def test_registering_a_missing_file_reports_an_error(self, cli: Cli):
        cli.run("init-db")
        cli.run(
            "register-letter", "--path", str(cli.root / "absent.pdf"),
            "--applicant", "Ada Lovelace", "--purpose", "PHD_APPLICATION",
            expect=1,
        )
        assert cli.json_run("list-letters")["letters"] == []

    def test_an_unsupported_purpose_is_refused_by_the_parser(self, cli: Cli):
        with pytest.raises(SystemExit):
            main(
                ["--config", str(cli.config_path), "register-letter", "--path",
                 cli.letter(), "--applicant", "Ada", "--purpose", "OTHER"],
                stream=io.StringIO(),
            )

    def test_an_invalid_event_is_reported_but_others_are_ingested(self, cli: Cli):
        cli.set_events(
            [
                {"event_id": "bad", "source_kind": "email_inbox", "kind": "ADD_REQUEST",
                 "new_request": {"source_reference": "x", "applicant_name": "Ada",
                                 "application_description": "d", "purpose": "OTHER",
                                 "channel": "EMAIL", "destination": "a@b.co",
                                 "deadline": "2026-12-01T00:00:00Z"}},
                event("msg-1", deadline="2026-12-01T00:00:00Z", destination="mit@example.edu"),
            ]
        )

        report = cli.json_run("sync")

        assert len(report["errors"]) == 1
        assert len(report["applied"]) == 1
        assert len(cli.json_run("list-requests")["requests"]) == 1

    def test_empty_listings_are_readable(self, cli: Cli):
        cli.run("init-db")
        assert "no requests" in cli.run("list-requests")
        assert "no registered letters" in cli.run("list-letters")
        assert "no submission attempts" in cli.run("list-submissions")
        assert "no reminder attempts" in cli.run("list-reminders")
