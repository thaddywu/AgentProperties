from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from recsub.config import AppConfig, ComponentSpec, Components
from recsub.models import NewRequest, RequestEvent
from recsub.service import Application
from recsub.testing.doubles import (
    FixedClock,
    RecordingEmailGateway,
    RecordingPortalAgent,
    ScriptedRequestSource,
)
from safema.control_plane import TrustedControlPlane
from safema.errors import ModelError, SafeMADenied
from safema.policy import evaluate_expression
from safema.runtime import install
from safema.testing import RecordingDisclosureSink
from safema.types import Context

ROOT = Path(__file__).resolve().parents[2]
EFFECTS = ROOT / "safema-v1/models/api-effects-v1.yaml"
ORIGINS = ROOT / "safema-v1/models/trusted-origins-v1.yaml"
POLICY = ROOT / "safema-v1/policies/recommendation-disclosure-v1.yaml"


def runtime(tmp_path: Path, *, effects=EFFECTS, policy=POLICY):
    return install(
        effect_models_path=effects,
        origins_path=ORIGINS,
        policy_path=policy,
        metadata_db=tmp_path / "safema.db",
    )


def event(
    *, applicant="Alice", channel="EMAIL", destination="alice-submit@example.edu"
):
    return RequestEvent(
        event_id="EVENT-001",
        source_kind="trusted-world",
        kind="ADD_REQUEST",
        new_request=NewRequest(
            source_reference="WORLD-REQ-001",
            applicant_name=applicant,
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
    components = Components(
        (source,), email, portal, FixedClock("2026-09-01T12:00:00Z")
    )
    return Application.open(config, components), email, portal


def prepare(
    app: Application,
    tmp_path: Path,
    *,
    app_applicant="Alice",
    trusted_applicant="Alice",
    trusted=True,
) -> Path:
    letter = tmp_path / "letter.pdf"
    letter.write_bytes(b"deterministic recommendation v2\n")
    assert app.sync().applied
    assert app.register_letter(
        file_path=str(letter),
        applicant_name=app_applicant,
        purpose="PHD_APPLICATION",
    ) == "LET-000001"
    if trusted:
        with TrustedControlPlane(tmp_path / "safema.db") as control_plane:
            assert control_plane.register_resource(
                str(letter),
                resource_class="recommendation_letter",
                attributes={"applicant": trusted_applicant, "purpose": "PHD_APPLICATION"},
            ) == 1
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
def test_legal_recsub_flows_reach_raw_adapter(
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
        assert guard.registry.decisions()[-1]["decision"] == "ALLOW"
        assert guard.registry.decisions()[-1]["raw_invoked"] == 1
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
def test_actual_wrong_destination_is_denied_before_raw(
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
    finally:
        app.close()
        guard.close()


def test_base_app_registration_cannot_mint_trusted_resource(tmp_path):
    guard = runtime(tmp_path)
    app, email, _ = application(tmp_path, event())
    try:
        prepare(app, tmp_path, app_applicant="Alice", trusted=False)
        report = app.process_pending()
        assert not guard.registry.resource_rows()
        assert not email.sent and report.failed
        assert guard.registry.decisions()[-1]["decision"] == "DENY"
    finally:
        app.close()
        guard.close()


def test_base_app_forged_applicant_cannot_mint_authorization(tmp_path):
    guard = runtime(tmp_path)
    app, email, _ = application(
        tmp_path, event(applicant="Bob", destination="bob-submit@example.edu")
    )
    try:
        prepare(
            app,
            tmp_path,
            app_applicant="Bob",
            trusted_applicant="Alice",
        )
        report = app.process_pending()
        assert not email.sent and report.failed
        assert guard.registry.decisions()[-1]["decision"] == "DENY"
    finally:
        app.close()
        guard.close()


def _direct_portal_world(tmp_path: Path, *, applicant: str, destination: str):
    source = ScriptedRequestSource(
        "trusted-world",
        [event(applicant=applicant, channel="PORTAL", destination=destination)],
    )
    source.scan()
    letter = tmp_path / "direct-letter.pdf"
    letter.write_bytes(b"direct trusted resource\n")
    with TrustedControlPlane(tmp_path / "safema.db") as control_plane:
        control_plane.register_resource(
            str(letter),
            resource_class="recommendation_letter",
            attributes={"applicant": "Bob"},
        )
    return letter


def test_misleading_correlation_cannot_authorize(tmp_path):
    guard = runtime(tmp_path)
    portal = RecordingPortalAgent()
    try:
        letter = _direct_portal_world(
            tmp_path, applicant="Carol", destination="https://portal.example.edu/carol"
        )
        with pytest.raises(SafeMADenied):
            portal.submit(
                correlation_id="REQ-BOB-SAYS-ALLOW",
                submission_url="https://portal.example.edu/carol",
                file_path=str(letter),
            )
        assert not portal.uploads
        effect = json.loads(guard.registry.decisions()[-1]["effect_json"])
        assert "correlation" not in effect
    finally:
        guard.close()


def test_garbage_correlation_does_not_prevent_valid_authorization(tmp_path):
    guard = runtime(tmp_path)
    portal = RecordingPortalAgent()
    try:
        letter = _direct_portal_world(
            tmp_path, applicant="Bob", destination="https://portal.example.edu/bob"
        )
        portal.submit(
            correlation_id="meaningless-garbage",
            submission_url="https://portal.example.edu/bob",
            file_path=str(letter),
        )
        assert len(portal.uploads) == 1
        effect = json.loads(guard.registry.decisions()[-1]["effect_json"])
        assert "correlation" not in effect
    finally:
        guard.close()


def test_api_without_any_correlation_field_can_be_authorized(tmp_path):
    custom_effects = tmp_path / "effects.yaml"
    custom_effects.write_text(
        """schema: safema.api_effect_models/v1
models:
  - id: no-correlation-sink.v1
    target:
      callable: safema.testing.RecordingDisclosureSink.disclose
    effect:
      kind: DISCLOSE
      resources:
        from: {select: $call.args.file_path}
        cardinality: one
        class: recommendation_letter
        identity_resolver: file_sha256
      contexts:
        from: {select: $call.args.destination}
        cardinality: one
        class: external_destination
      attributes:
        channel: {literal: PORTAL}
""",
        encoding="utf-8",
    )
    guard = runtime(tmp_path, effects=custom_effects)
    sink = RecordingDisclosureSink()
    try:
        letter = _direct_portal_world(
            tmp_path, applicant="Bob", destination="https://portal.example.edu/bob"
        )
        assert sink.disclose(
            file_path=str(letter), destination="https://portal.example.edu/bob"
        )
        assert len(sink.calls) == 1
    finally:
        guard.close()


def test_policy_subset_to_eq_mutation_changes_behavior(tmp_path):
    guard = runtime(tmp_path)
    gateway = RecordingEmailGateway()
    letter = tmp_path / "letter.pdf"
    letter.write_bytes(b"policy mutation resource\n")
    try:
        with TrustedControlPlane(tmp_path / "safema.db") as control_plane:
            control_plane.register_resource(
                str(letter),
                resource_class="recommendation_letter",
                attributes={"applicant": "Alice"},
            )
        guard.registry.put_context(
            Context(
                identity=["trusted", "multi-destination"],
                object_class="recommendation_submission_authority",
                attributes={
                    "applicant": "Alice",
                    "channel": "EMAIL",
                    "active": True,
                    "allowed_destinations": [
                        "alice@example.edu",
                        "department-admin@example.edu",
                    ],
                },
            ),
            origin_id="test.trusted_context_origin",
        )
        from recsub.models import EmailMessage

        message = EmailMessage(
            to=["alice@example.edu"], cc=[], subject="x", body="x",
            attachments=[str(letter)], correlation_id="ignored",
        )
        gateway.send(message)
        assert len(gateway.sent) == 1
    finally:
        guard.close()

    equal_policy = tmp_path / "equal-policy.yaml"
    equal_policy.write_text(
        POLICY.read_text(encoding="utf-8").replace("- subset:", "- eq:"),
        encoding="utf-8",
    )
    guard = runtime(tmp_path, policy=equal_policy)
    gateway = RecordingEmailGateway()
    try:
        with pytest.raises(SafeMADenied):
            gateway.send(message)
        assert not gateway.sent
        assert guard.registry.decisions()[-1]["decision"] == "DENY"
    finally:
        guard.close()


def test_minimal_policy_operator_set_is_executable():
    environment = {"values": [1, 2, 3]}
    assert evaluate_expression(
        {"eq": [{"literal": "x"}, {"literal": "x"}]}, environment
    )
    assert evaluate_expression(
        {"subset": [{"literal": [1, 2]}, {"select": "$values[*]"}]}, environment
    )
    assert evaluate_expression(
        {"exists": {
            "in": {"select": "$values[*]"},
            "as": "value",
            "satisfies": {"eq": [{"select": "$value"}, {"literal": 2}]},
        }},
        environment,
    )
    assert evaluate_expression(
        {"all": [{"literal": True}, {"literal": True}]}, environment
    )
    assert evaluate_expression(
        {"any": [{"literal": False}, {"literal": True}]}, environment
    )


def test_changed_file_content_is_denied(tmp_path):
    guard = runtime(tmp_path)
    app, email, _ = application(tmp_path, event())
    try:
        letter = prepare(app, tmp_path)
        letter.write_bytes(b"substituted content\n")
        report = app.process_pending()
        assert not email.sent and report.failed
        assert guard.registry.decisions()[-1]["raw_invoked"] == 0
    finally:
        app.close()
        guard.close()


def test_trusted_cancel_changes_declarative_active_attribute(tmp_path):
    guard = runtime(tmp_path)
    source = ScriptedRequestSource("trusted-world", [event()])
    try:
        source.scan()
        source.events = [RequestEvent(
            event_id="EVENT-002",
            source_kind="trusted-world",
            kind="CANCEL_REQUEST",
            target_source_reference="WORLD-REQ-001",
        )]
        source.scan()
        context = guard.registry.all_contexts()[0]
        assert context.attributes["active"] is False
    finally:
        guard.close()


def test_unknown_yaml_field_fails_fast(tmp_path):
    invalid = tmp_path / "invalid-effects.yaml"
    invalid.write_text(
        EFFECTS.read_text(encoding="utf-8").replace(
            "      kind: DISCLOSE", "      kind: DISCLOSE\n      silently_ignored: bad", 1
        ),
        encoding="utf-8",
    )
    with pytest.raises(ModelError, match="unsupported fields"):
        runtime(tmp_path, effects=invalid)


def test_unsupported_yaml_operator_and_resolver_fail_fast(tmp_path):
    invalid_policy = tmp_path / "invalid-policy.yaml"
    invalid_policy.write_text(
        POLICY.read_text(encoding="utf-8").replace("- subset:", "- overlaps:"),
        encoding="utf-8",
    )
    with pytest.raises(ModelError, match="unsupported policy operator"):
        runtime(tmp_path, policy=invalid_policy)

    invalid_effects = tmp_path / "invalid-resolver.yaml"
    invalid_effects.write_text(
        EFFECTS.read_text(encoding="utf-8").replace("file_sha256", "magic_identity", 1),
        encoding="utf-8",
    )
    with pytest.raises(ModelError, match="unsupported resolver"):
        runtime(tmp_path, effects=invalid_effects)

    untrusted_attribute = tmp_path / "untrusted-attribute.yaml"
    untrusted_attribute.write_text(
        EFFECTS.read_text(encoding="utf-8").replace(
            "literal: EMAIL", "select: $call.args.message.correlation_id", 1
        ),
        encoding="utf-8",
    )
    with pytest.raises(ModelError, match="application claims"):
        runtime(tmp_path, effects=untrusted_attribute)

    uncovered_effect = tmp_path / "uncovered-effect.yaml"
    uncovered_effect.write_text(
        EFFECTS.read_text(encoding="utf-8").replace("kind: DISCLOSE", "kind: PUBLISH"),
        encoding="utf-8",
    )
    with pytest.raises(ModelError, match="have no policy"):
        runtime(tmp_path, effects=uncovered_effect)


def test_external_control_plane_and_runner_persist_across_processes(tmp_path):
    letter = tmp_path / "letter.pdf"
    letter.write_bytes(b"deterministic recommendation v2\n")
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
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "safema-v1"), str(ROOT / "v1-impl")]
    )
    runner = [
        sys.executable, "-m", "safema.recsub_runner", "--metadata-db", str(sidecar),
        "--", "--config", str(config_path),
    ]
    commands = [
        runner + ["sync"],
        runner + [
            "register-letter", "--path", str(letter), "--applicant", "Alice",
            "--purpose", "PHD_APPLICATION",
        ],
        [
            sys.executable, "-m", "safema.control_plane", "--metadata-db", str(sidecar),
            "--path", str(letter), "--resource-class", "recommendation_letter",
            "--attributes-json", json.dumps({"applicant": "Alice"}),
        ],
        runner + ["process"],
    ]
    for command in commands:
        subprocess.run(
            command, cwd=ROOT, env=environment, check=True,
            capture_output=True, text=True,
        )
    outbound = [
        json.loads(line) for line in (tmp_path / "outbound.jsonl").read_text().splitlines()
    ]
    assert len(outbound) == 1
    with sqlite3.connect(sidecar) as connection:
        assert connection.execute("SELECT count(*) FROM safema_resources").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM safema_contexts").fetchone()[0] == 1
        assert connection.execute(
            "SELECT decision, raw_invoked FROM safema_decisions"
        ).fetchone() == ("ALLOW", 1)
