"""The command-line interface (specification 6.8).

Every operation is available as a subcommand.  Add ``--json`` to any command
for machine-readable output; the default output is a human-readable rendering
with timestamps shown in the configured display time zone.

Exit codes: ``0`` success, ``1`` an application error, ``2`` a usage or
configuration error.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
from typing import Any, Optional, Sequence

from . import __version__
from .config import AppConfig, build_components, load_config
from .db import connect
from .errors import ConfigError, RecSubError
from .models import Letter, Reminder, Request, Submission
from .service import Application
from .timeutil import for_display

CONFIG_ENV = "RECSUB_CONFIG"
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="recsub",
        description="Recommendation Submission System (version 1)",
    )
    parser.add_argument("--version", action="version", version=f"recsub {__version__}")
    parser.add_argument(
        "--config",
        help=f"path to the configuration file (default: ${CONFIG_ENV})",
    )
    parser.add_argument(
        "--json", action="store_true", help="print machine-readable JSON output"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("check-config", help="validate configuration and exit")
    subparsers.add_parser(
        "init-db", help="create the SQLite database and its schema if absent"
    )
    subparsers.add_parser(
        "sync", help="scan every configured request source and apply its events"
    )

    register = subparsers.add_parser(
        "register-letter", help="register a completed recommendation-letter file"
    )
    register.add_argument("--path", required=True, help="path to the completed letter file")
    register.add_argument(
        "--applicant", required=True, help="the applicant's canonical name"
    )
    register.add_argument(
        "--purpose",
        required=True,
        choices=["PHD_APPLICATION", "FELLOWSHIP"],
        help="the recommendation purpose",
    )

    cancel = subparsers.add_parser("cancel-request", help="cancel one PENDING request")
    cancel.add_argument("request_id")

    subparsers.add_parser("process", help="submit every pending request that has a letter")
    subparsers.add_parser("remind", help="send due deadline reminders")
    subparsers.add_parser(
        "daily-run", help="sync, then process submissions, then send reminders"
    )

    listing = subparsers.add_parser("list-requests", help="list recommendation requests")
    listing.add_argument(
        "--status", choices=["PENDING", "SUBMITTED", "CANCELLED"], help="filter by status"
    )

    show = subparsers.add_parser("show-request", help="show one request in full")
    show.add_argument("request_id")

    subparsers.add_parser("list-letters", help="list registered letters")
    subparsers.add_parser("list-submissions", help="list submission history")
    subparsers.add_parser("list-reminders", help="list reminder history")
    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None, *, stream=None) -> int:
    out = stream if stream is not None else sys.stdout
    parser = build_parser()
    args = parser.parse_args(argv)

    config_path = args.config or os.environ.get(CONFIG_ENV)
    if not config_path:
        print(
            f"error: no configuration file; pass --config PATH or set ${CONFIG_ENV}",
            file=sys.stderr,
        )
        return EXIT_USAGE

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    if args.command == "check-config":
        try:
            build_components(config)
        except ConfigError as exc:
            print(f"configuration error: {exc}", file=sys.stderr)
            return EXIT_USAGE
        _emit(out, args.json, _config_payload(config), _render_config)
        return EXIT_OK

    if args.command == "init-db":
        connect(config.database_path).close()
        _emit(
            out,
            args.json,
            {"database_path": config.database_path, "initialized": True},
            lambda payload: f"database ready at {payload['database_path']}",
        )
        return EXIT_OK

    try:
        components = build_components(config)
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    try:
        with Application.open(config, components) as app:
            return _dispatch(app, args, out)
    except RecSubError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR


def _dispatch(app: Application, args: argparse.Namespace, out) -> int:
    tz = app.timezone
    command = args.command

    if command == "sync":
        report = app.sync()
        _emit(out, args.json, dataclasses.asdict(report), _render_sync)
        return EXIT_OK

    if command == "register-letter":
        letter_id = app.register_letter(
            file_path=args.path, applicant_name=args.applicant, purpose=args.purpose
        )
        letter = app.repository.get_letter(letter_id)
        _emit(
            out,
            args.json,
            _letter_payload(letter, tz),
            lambda payload: f"registered {payload['letter_id']} for "
            f"{payload['applicant_name']} ({payload['purpose']}): {payload['file_path']}",
        )
        return EXIT_OK

    if command == "cancel-request":
        request = app.cancel_request(args.request_id)
        _emit(
            out,
            args.json,
            _request_payload(request, tz),
            lambda payload: f"{payload['request_id']} is now {payload['status']}",
        )
        return EXIT_OK

    if command == "process":
        report = app.process_pending()
        _emit(out, args.json, dataclasses.asdict(report), _render_process)
        return EXIT_OK

    if command == "remind":
        report = app.send_reminders()
        _emit(out, args.json, dataclasses.asdict(report), _render_reminders)
        return EXIT_OK

    if command == "daily-run":
        report = app.daily_run()
        _emit(out, args.json, dataclasses.asdict(report), _render_daily)
        return EXIT_OK

    if command == "list-requests":
        requests = app.list_requests(args.status)
        payload = {"requests": [_request_payload(item, tz) for item in requests]}
        _emit(out, args.json, payload, _render_requests)
        return EXIT_OK

    if command == "show-request":
        request, superseded_by, submissions, reminders, letter = app.show_request(
            args.request_id
        )
        payload = _request_payload(request, tz)
        payload["superseded_by_request_id"] = superseded_by
        payload["compatible_letter_id"] = letter.letter_id if letter else None
        payload["submissions"] = [_submission_payload(item, tz) for item in submissions]
        payload["reminders"] = [_reminder_payload(item, tz) for item in reminders]
        _emit(out, args.json, payload, _render_request_detail)
        return EXIT_OK

    if command == "list-letters":
        payload = {"letters": [_letter_payload(item, tz) for item in app.list_letters()]}
        _emit(out, args.json, payload, _render_letters)
        return EXIT_OK

    if command == "list-submissions":
        payload = {
            "submissions": [
                _submission_payload(item, tz) for item in app.list_submissions()
            ]
        }
        _emit(out, args.json, payload, _render_submissions)
        return EXIT_OK

    if command == "list-reminders":
        payload = {
            "reminders": [_reminder_payload(item, tz) for item in app.list_reminders()]
        }
        _emit(out, args.json, payload, _render_reminders_list)
        return EXIT_OK

    raise AssertionError(f"unhandled command {command!r}")  # pragma: no cover


# ---------------------------------------------------------------------------
# Payloads
# ---------------------------------------------------------------------------


def _config_payload(config: AppConfig) -> dict[str, Any]:
    return {
        "source_path": config.source_path,
        "database_path": config.database_path,
        "professor_email": config.professor_email,
        "display_time_zone": config.display_time_zone,
        "request_sources": [spec.factory for spec in config.request_sources],
        "email_gateway": config.email_gateway.factory,
        "portal_agent": config.portal_agent.factory,
        "clock": config.clock.factory,
    }


def _request_payload(request: Request, tz) -> dict[str, Any]:
    return {
        "request_id": request.request_id,
        "applicant_name": request.applicant_name,
        "application_description": request.application_description,
        "purpose": request.purpose.value,
        "channel": request.channel.value,
        "destination": request.destination,
        "deadline_utc": request.deadline,
        "deadline_local": for_display(request.deadline, tz),
        "status": request.status.value,
        "source_kind": request.source_kind,
        "source_reference": request.source_reference,
        "supersedes_request_id": request.supersedes_request_id,
        "created_at": request.created_at,
        "updated_at": request.updated_at,
    }


def _letter_payload(letter: Letter, tz) -> dict[str, Any]:
    return {
        "letter_id": letter.letter_id,
        "file_path": letter.file_path,
        "applicant_name": letter.applicant_name,
        "purpose": letter.purpose.value,
        "registered_at_utc": letter.registered_at,
        "registered_at_local": for_display(letter.registered_at, tz),
    }


def _submission_payload(submission: Submission, tz) -> dict[str, Any]:
    return {
        "submission_id": submission.submission_id,
        "request_id": submission.request_id,
        "letter_id": submission.letter_id,
        "attempted_at_utc": submission.attempted_at,
        "attempted_at_local": for_display(submission.attempted_at, tz),
        "channel": submission.channel.value,
        "outcome": submission.outcome.value,
        "receipt": submission.receipt,
        "error_code": submission.error_code,
        "error_message": submission.error_message,
    }


def _reminder_payload(reminder: Reminder, tz) -> dict[str, Any]:
    return {
        "reminder_id": reminder.reminder_id,
        "request_id": reminder.request_id,
        "reminder_kind": reminder.reminder_kind.value,
        "attempted_at_utc": reminder.attempted_at,
        "attempted_at_local": for_display(reminder.attempted_at, tz),
        "outcome": reminder.outcome.value,
        "receipt": reminder.receipt,
        "error_code": reminder.error_code,
        "error_message": reminder.error_message,
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _emit(out, as_json: bool, payload: Any, render) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True), file=out)
    else:
        print(render(payload), file=out)


def _bullets(title: str, items: Sequence[str]) -> list[str]:
    if not items:
        return []
    return [f"{title}:"] + [f"  - {item}" for item in items]


def _render_config(payload: dict[str, Any]) -> str:
    lines = [f"configuration {payload['source_path']} is valid", ""]
    for key in (
        "database_path",
        "professor_email",
        "display_time_zone",
        "email_gateway",
        "portal_agent",
        "clock",
    ):
        lines.append(f"  {key:<20} {payload[key]}")
    lines.append(f"  {'request_sources':<20} {', '.join(payload['request_sources']) or '(none)'}")
    return "\n".join(lines)


def _render_sync(payload: dict[str, Any]) -> str:
    lines = [
        f"scanned {payload['scanned_sources']} source(s), saw {payload['events_seen']} event(s)"
    ]
    lines += _bullets("applied", payload["applied"])
    lines += _bullets("skipped", payload["skipped"])
    lines += _bullets("problems", payload["errors"])
    return "\n".join(lines)


def _render_process(payload: dict[str, Any]) -> str:
    lines = [f"attempted {len(payload['attempted'])} submission(s)"]
    lines += _bullets("succeeded", payload["succeeded"])
    lines += _bullets("failed", payload["failed"])
    lines += _bullets("skipped", payload["skipped"])
    lines += _bullets("problems", payload["errors"])
    return "\n".join(lines)


def _render_reminders(payload: dict[str, Any]) -> str:
    lines = [f"sent {len(payload['sent'])} reminder(s)"]
    lines += _bullets("sent", payload["sent"])
    lines += _bullets("failed", payload["failed"])
    lines += _bullets("skipped", payload["skipped"])
    lines += _bullets("problems", payload["errors"])
    return "\n".join(lines)


def _render_daily(payload: dict[str, Any]) -> str:
    lines = ["daily run", "", "1. synchronization", _indent(_render_sync(payload["sync"]))]
    lines += ["", "2. submissions", _indent(_render_process(payload["process"]))]
    lines += ["", "3. reminders", _indent(_render_reminders(payload["reminders"]))]
    if payload["errors"]:
        lines += [""] + _bullets("stage failures", payload["errors"])
    return "\n".join(lines)


def _indent(text: str) -> str:
    return "\n".join("   " + line for line in text.splitlines())


def _render_requests(payload: dict[str, Any]) -> str:
    rows = payload["requests"]
    if not rows:
        return "no requests"
    lines = [
        f"{'REQUEST':<12} {'STATUS':<10} {'CHANNEL':<8} {'PURPOSE':<16} "
        f"{'DEADLINE (local)':<26} APPLICANT"
    ]
    for row in rows:
        lines.append(
            f"{row['request_id']:<12} {row['status']:<10} {row['channel']:<8} "
            f"{row['purpose']:<16} {row['deadline_local']:<26} {row['applicant_name']}"
        )
    return "\n".join(lines)


def _render_request_detail(payload: dict[str, Any]) -> str:
    lines = []
    for key in (
        "request_id",
        "applicant_name",
        "application_description",
        "purpose",
        "channel",
        "destination",
        "deadline_utc",
        "deadline_local",
        "status",
        "source_kind",
        "source_reference",
        "supersedes_request_id",
        "superseded_by_request_id",
        "compatible_letter_id",
        "created_at",
        "updated_at",
    ):
        lines.append(f"  {key:<26} {payload[key]}")
    lines.append("")
    lines.append("  submissions:")
    for item in payload["submissions"] or []:
        lines.append(
            f"    {item['submission_id']} {item['attempted_at_local']} "
            f"{item['channel']} {item['outcome']} letter={item['letter_id']} "
            f"receipt={item['receipt']} error={item['error_code']} "
            f"{item['error_message'] or ''}".rstrip()
        )
    if not payload["submissions"]:
        lines.append("    (none)")
    lines.append("  reminders:")
    for item in payload["reminders"] or []:
        lines.append(
            f"    {item['reminder_id']} {item['attempted_at_local']} "
            f"{item['reminder_kind']} {item['outcome']} receipt={item['receipt']} "
            f"error={item['error_code']}"
        )
    if not payload["reminders"]:
        lines.append("    (none)")
    return "\n".join(lines)


def _render_letters(payload: dict[str, Any]) -> str:
    rows = payload["letters"]
    if not rows:
        return "no registered letters"
    lines = [f"{'LETTER':<12} {'PURPOSE':<16} {'REGISTERED (local)':<26} APPLICANT / PATH"]
    for row in rows:
        lines.append(
            f"{row['letter_id']:<12} {row['purpose']:<16} "
            f"{row['registered_at_local']:<26} {row['applicant_name']} — {row['file_path']}"
        )
    return "\n".join(lines)


def _render_submissions(payload: dict[str, Any]) -> str:
    rows = payload["submissions"]
    if not rows:
        return "no submission attempts"
    lines = [
        f"{'SUBMISSION':<12} {'REQUEST':<12} {'LETTER':<12} {'CHANNEL':<8} "
        f"{'OUTCOME':<10} {'WHEN (local)':<26} RECEIPT / ERROR"
    ]
    for row in rows:
        detail = row["receipt"] or f"{row['error_code']}: {row['error_message']}"
        lines.append(
            f"{row['submission_id']:<12} {row['request_id']:<12} "
            f"{str(row['letter_id']):<12} {row['channel']:<8} {row['outcome']:<10} "
            f"{row['attempted_at_local']:<26} {detail}"
        )
    return "\n".join(lines)


def _render_reminders_list(payload: dict[str, Any]) -> str:
    rows = payload["reminders"]
    if not rows:
        return "no reminder attempts"
    lines = [
        f"{'REMINDER':<12} {'REQUEST':<12} {'KIND':<12} {'OUTCOME':<10} "
        f"{'WHEN (local)':<26} RECEIPT / ERROR"
    ]
    for row in rows:
        detail = row["receipt"] or f"{row['error_code']}: {row['error_message']}"
        lines.append(
            f"{row['reminder_id']:<12} {row['request_id']:<12} "
            f"{row['reminder_kind']:<12} {row['outcome']:<10} "
            f"{row['attempted_at_local']:<26} {detail}"
        )
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
