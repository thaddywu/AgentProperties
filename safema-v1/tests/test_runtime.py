from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from recsub.config import AppConfig, ComponentSpec, Components
from recsub.models import EmailMessage, NewRequest, RequestEvent
from recsub.service import Application
from recsub.testing.doubles import (
    FixedClock,
    RecordingEmailGateway,
    RecordingPortalAgent,
    ScriptedRequestSource,
)
from safema.errors import SafeMADenied
from safema.runtime import install


ROOT = Path(__file__).resolve().parents[2]


def runtime(tmp_path: Path):
    return install(
        effect_models_path=ROOT / "safema-v1/models/api-effects-v1.yaml",
        origins_path=ROOT / "safema-v1/models/trusted-origins-v1.yaml",
        policy_path=ROOT / "safema-v1/policies/same-principal-active-destination-v1.yaml",
        metadata_db=tmp_path / "safema.db",
    )


def event(*, channel="EMAIL", destination="alice-submit@example.edu"):
    return RequestEvent(
        event_id="EVENT-001",
        source_kind="trusted-world",
        kind="ADD_REQUEST",
        new_request=NewRequest(
            source_reference="WORLD-REQ-001",
            applicant_name="Alice",
            application_description="Example University CS",
            purpose="PHD_APPLICATION",
            channel=channel,
            destination=destination,
            deadline="2027-01-01T00:00:00Z",
        ),
    )


def application(tmp_path: Path, request_event: RequestEvent):
    source = ScriptedRequestSource("trusted-world", [request_event])
    email = RecordingEmailGateway()
    portal = RecordingPortalAgent()
    clock = FixedClock("2026-09-01T12:00:00Z")
    placeholder = ComponentSpec("unused:factory")
    config = AppConfig(
        database_path=str(tmp_path / "app.db"),
        professor_email="professor@example.edu",
        display_time_zone="UTC",
        request_sources=(),
        email_gateway=placeholder,
        portal_agent=placeholder,
        clock=placeholder,
    )
    components = Components((source,), email, portal, clock)
    return Application.open(config, components), email, portal


def prepare(app: Application, tmp_path: Path) -> Path:
    letter = tmp_path / "alice-letter.pdf"
    letter.write_bytes(b"deterministic Alice recommendation v1\n")
    assert app.sync().applied
    assert app.register_letter(
        file_path=str(letter), applicant_name="Alice", purpose="PHD_APPLICATION"
    ) == "LET-000001"
    return letter


def tamper_destination(app: Application, value: str) -> None:
    with app.repository.transaction() as connection:
        connection.execute(
            "UPDATE requests SET destination = ? WHERE request_id = 'REQ-000001'",
            (value,),
        )


@pytest.mark.parametrize(
    "channel,destination,raw_attribute",
    [
        ("EMAIL", "alice-submit@example.edu", "sent"),
        ("PORTAL", "https://portal.example.edu/alice", "uploads"),
    ],
)
def test_legal_submission_reaches_raw_adapter(
    tmp_path, channel, destination, raw_attribute
):
    guard = runtime(tmp_path)
    app, email, portal = application(
        tmp_path, event(channel=channel, destination=destination)
    )
    try:
        prepare(app, tmp_path)
        report = app.process_pending()
        adapter = email if channel == "EMAIL" else portal
        assert len(getattr(adapter, raw_attribute)) == 1
        assert report.succeeded and not report.failed
        decision = guard.registry.decisions()[-1]
        assert decision["decision"] == "ALLOW"
        assert decision["raw_invoked"] == 1
    finally:
        app.close()
        guard.close()


@pytest.mark.parametrize(
    "channel,good,bad",
    [
        ("EMAIL", "alice-submit@example.edu", "mallory-submit@example.edu"),
        ("PORTAL", "https://portal.example.edu/alice", "https://portal.example.edu/mallory"),
    ],
)
def test_tampered_app_destination_is_denied_before_raw_adapter(
    tmp_path, channel, good, bad
):
    guard = runtime(tmp_path)
    app, email, portal = application(tmp_path, event(channel=channel, destination=good))
    try:
        prepare(app, tmp_path)
        tamper_destination(app, bad)
        report = app.process_pending()
        assert len(email.sent) + len(portal.uploads) == 0
        assert report.failed and not report.succeeded
        decision = guard.registry.decisions()[-1]
        assert decision["decision"] == "DENY"
        assert decision["raw_invoked"] == 0
        assert bad in decision["reason"]
        assert app.repository.require_request("REQ-000001").status.value == "PENDING"
    finally:
        app.close()
        guard.close()


def test_baseline_same_fault_reaches_wrong_recipient(tmp_path):
    app, email, _ = application(tmp_path, event())
    try:
        prepare(app, tmp_path)
        tamper_destination(app, "mallory-submit@example.edu")
        report = app.process_pending()
        assert report.succeeded
        assert email.sent[0].to == ["mallory-submit@example.edu"]
    finally:
        app.close()


def test_same_path_content_replacement_invalidates_resource_version(tmp_path):
    guard = runtime(tmp_path)
    app, email, _ = application(tmp_path, event())
    try:
        letter = prepare(app, tmp_path)
        letter.write_bytes(b"different bytes at the registered path\n")
        report = app.process_pending()
        assert not email.sent and report.failed
        decision = guard.registry.decisions()[-1]
        assert decision["decision"] == "DENY"
        assert "different content fingerprint" in decision["reason"]
    finally:
        app.close()
        guard.close()


def test_unregistered_covered_attachment_fails_closed(tmp_path):
    guard = runtime(tmp_path)
    gateway = RecordingEmailGateway()
    unknown = tmp_path / "unknown.pdf"
    unknown.write_bytes(b"not registered")
    message = EmailMessage(
        to=["alice-submit@example.edu"], cc=[], subject="x", body="x",
        attachments=[str(unknown)], correlation_id="DIRECT-001",
    )
    try:
        with pytest.raises(SafeMADenied):
            gateway.send(message)
        assert not gateway.sent
        assert guard.registry.decisions()[-1]["raw_invoked"] == 0
    finally:
        guard.close()


def test_no_attachment_email_is_outside_covered_resource_policy(tmp_path):
    guard = runtime(tmp_path)
    gateway = RecordingEmailGateway()
    message = EmailMessage(
        to=["professor@example.edu"], cc=[], subject="Reminder", body="x",
        attachments=[], correlation_id="REMINDER-001",
    )
    try:
        gateway.send(message)
        assert len(gateway.sent) == 1
        decision = guard.registry.decisions()[-1]
        assert decision["decision"] == "ALLOW"
        assert decision["reason"] == "no policy-covered resources"
    finally:
        guard.close()


def test_trusted_cancel_deactivates_destination_context(tmp_path):
    guard = runtime(tmp_path)
    source = ScriptedRequestSource("trusted-world", [event()])
    try:
        source.scan()
        source.events = [RequestEvent(
            event_id="EVENT-002", source_kind="trusted-world", kind="CANCEL_REQUEST",
            target_source_reference="WORLD-REQ-001",
        )]
        source.scan()
        assert guard.registry.contexts()[0]["state"] == "inactive"
    finally:
        guard.close()


def test_sidecar_effect_contains_normalized_arguments(tmp_path):
    guard = runtime(tmp_path)
    app, _, _ = application(tmp_path, event())
    try:
        letter = prepare(app, tmp_path)
        app.process_pending()
        effect = json.loads(guard.registry.decisions()[0]["effect_json"])
        assert effect["kind"] == "DISCLOSE"
        assert effect["channel"] == "EMAIL"
        assert effect["correlation"] == "REQ-000001"
        assert effect["resources"][0]["value"] == str(letter.resolve())
        assert effect["destinations"] == ["alice-submit@example.edu"]
    finally:
        app.close()
        guard.close()


def test_external_runner_persists_metadata_across_cli_processes(tmp_path):
    letter = tmp_path / "alice-letter.pdf"
    letter.write_bytes(b"deterministic Alice recommendation v1\n")
    events = [{
        "event_id": "EVENT-001",
        "source_kind": "trusted-world",
        "kind": "ADD_REQUEST",
        "new_request": {
            "source_reference": "WORLD-REQ-001",
            "applicant_name": "Alice",
            "application_description": "Example University CS",
            "purpose": "PHD_APPLICATION",
            "channel": "EMAIL",
            "destination": "alice-submit@example.edu",
            "deadline": "2027-01-01T00:00:00Z",
        },
    }]
    (tmp_path / "events.json").write_text(json.dumps(events), encoding="utf-8")
    config = {
        "database_path": "app.db",
        "professor_email": "professor@example.edu",
        "display_time_zone": "UTC",
        "request_sources": [{
            "factory": "recsub.testing.doubles:json_file_request_source",
            "options": {"source_kind": "trusted-world", "events_path": "events.json"},
        }],
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
            "options": {"instant": "2026-09-01T12:00:00Z"},
        },
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    sidecar = tmp_path / "safema.db"
    prefix = [
        sys.executable, "-m", "safema.recsub_runner", "--metadata-db", str(sidecar), "--",
        "--config", str(config_path),
    ]
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "safema-v1"), str(ROOT / "v1-impl")]
    )
    for command in (
        ["sync"],
        ["register-letter", "--path", str(letter), "--applicant", "Alice", "--purpose", "PHD_APPLICATION"],
        ["process"],
    ):
        subprocess.run(
            prefix + command, cwd=ROOT, env=environment, check=True,
            capture_output=True, text=True,
        )
    outbound = [json.loads(line) for line in (tmp_path / "outbound.jsonl").read_text().splitlines()]
    assert len(outbound) == 1
    assert outbound[0]["call"]["to"] == ["alice-submit@example.edu"]
    with sqlite3.connect(sidecar) as connection:
        assert connection.execute("SELECT count(*) FROM resource_versions").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM destination_contexts").fetchone()[0] == 1
        assert connection.execute(
            "SELECT decision, raw_invoked FROM decisions"
        ).fetchone() == ("ALLOW", 1)
