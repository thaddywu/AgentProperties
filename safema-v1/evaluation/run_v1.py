"""Deterministic baseline/treatment evaluation for the frozen RecSub Base App."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "safema-v1"), str(ROOT / "v1-impl")]

from recsub.config import AppConfig, ComponentSpec, Components
from recsub.models import EmailMessage, NewRequest, RequestEvent
from recsub.service import Application
from recsub.testing.doubles import (
    FixedClock,
    RecordingEmailGateway,
    RecordingPortalAgent,
    ScriptedRequestSource,
)
from safema.control_plane import TrustedControlPlane
from safema.runtime import install

LETTER_BYTES = b"deterministic Alice recommendation v2\n"
LETTER_SHA256 = hashlib.sha256(LETTER_BYTES).hexdigest()
GOOD_EMAIL = "alice-submit@example.edu"
BAD_EMAIL = "mallory-submit@example.edu"
GOOD_PORTAL = "https://portal.example.edu/alice"
BAD_PORTAL = "https://portal.example.edu/mallory"


def _runtime(directory: Path):
    return install(
        effect_models_path=ROOT / "safema-v1/models/api-effects-v1.yaml",
        origins_path=ROOT / "safema-v1/models/trusted-origins-v1.yaml",
        policy_path=ROOT / "safema-v1/policies/recommendation-disclosure-v1.yaml",
        metadata_db=directory / "safema.db",
    )


def _event(*, applicant: str, channel: str, destination: str):
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


def _app(directory: Path, request_event: RequestEvent):
    source = ScriptedRequestSource("trusted-world", [request_event])
    email = RecordingEmailGateway()
    portal = RecordingPortalAgent()
    placeholder = ComponentSpec("unused:factory")
    config = AppConfig(
        database_path=str(directory / "app.db"),
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


def run_submission(
    name: str,
    *,
    treatment: bool,
    channel: str,
    destination: str,
    fault: str | None,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix=f"safema-{name}-") as temporary:
        directory = Path(temporary)
        guard = _runtime(directory) if treatment else None
        request_applicant = "Bob" if fault == "forged_applicant" else "Alice"
        app, email, portal = _app(
            directory,
            _event(
                applicant=request_applicant,
                channel=channel,
                destination=destination,
            ),
        )
        try:
            app.sync()
            letter = directory / "letter.pdf"
            letter.write_bytes(LETTER_BYTES)
            app.register_letter(
                file_path=str(letter),
                applicant_name=request_applicant,
                purpose="PHD_APPLICATION",
            )
            if treatment:
                trusted_applicant = "Alice"
                with TrustedControlPlane(directory / "safema.db") as control_plane:
                    control_plane.register_resource(
                        str(letter),
                        resource_class="recommendation_letter",
                        attributes={"applicant": trusted_applicant},
                    )
            if fault == "wrong_destination":
                bad = BAD_EMAIL if channel == "EMAIL" else BAD_PORTAL
                with app.repository.transaction() as connection:
                    connection.execute(
                        "UPDATE requests SET destination = ? WHERE request_id = 'REQ-000001'",
                        (bad,),
                    )
            elif fault == "replace_file_bytes":
                letter.write_bytes(b"substituted bytes after trusted registration\n")
            report = app.process_pending()
            calls = email.sent if channel == "EMAIL" else portal.uploads
            raw_destinations = (
                [address for call in calls for address in call.to + call.cc]
                if channel == "EMAIL"
                else [call.submission_url for call in calls]
            )
            decisions = guard.registry.decisions() if guard else []
            effect = json.loads(decisions[-1]["effect_json"]) if decisions else None
            return {
                "scenario": name,
                "mode": "treatment" if treatment else "baseline",
                "raw_adapter_calls": len(calls),
                "raw_destinations": raw_destinations,
                "base_app_succeeded": bool(report.succeeded),
                "request_final_status": app.repository.require_request("REQ-000001").status.value,
                "trusted_resource_count": len(guard.registry.resource_rows()) if guard else 0,
                "trusted_context_count": len(guard.registry.context_rows()) if guard else 0,
                "decision": decisions[-1]["decision"] if decisions else None,
                "raw_invoked": decisions[-1]["raw_invoked"] if decisions else None,
                "effect_contains_correlation": "correlation" in effect if effect else False,
            }
        finally:
            app.close()
            if guard:
                guard.close()


def run_direct_correlation(
    name: str, *, treatment: bool, context_applicant: str, correlation: str
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix=f"safema-{name}-") as temporary:
        directory = Path(temporary)
        guard = _runtime(directory) if treatment else None
        portal = RecordingPortalAgent()
        destination = f"https://portal.example.edu/{context_applicant.lower()}"
        try:
            if treatment:
                source = ScriptedRequestSource(
                    "trusted-world",
                    [_event(
                        applicant=context_applicant,
                        channel="PORTAL",
                        destination=destination,
                    )],
                )
                source.scan()
            letter = directory / "letter.pdf"
            letter.write_bytes(LETTER_BYTES)
            if treatment:
                with TrustedControlPlane(directory / "safema.db") as control_plane:
                    control_plane.register_resource(
                        str(letter),
                        resource_class="recommendation_letter",
                        attributes={"applicant": "Bob"},
                    )
            try:
                portal.submit(
                    correlation_id=correlation,
                    submission_url=destination,
                    file_path=str(letter),
                )
            except Exception:
                pass
            decisions = guard.registry.decisions() if guard else []
            effect = json.loads(decisions[-1]["effect_json"]) if decisions else None
            return {
                "scenario": name,
                "mode": "treatment" if treatment else "baseline",
                "correlation_value": correlation,
                "raw_adapter_calls": len(portal.uploads),
                "decision": decisions[-1]["decision"] if decisions else None,
                "effect_contains_correlation": "correlation" in effect if effect else False,
            }
        finally:
            if guard:
                guard.close()


def run_reminder(*, treatment: bool) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="safema-reminder-") as temporary:
        directory = Path(temporary)
        guard = _runtime(directory) if treatment else None
        gateway = RecordingEmailGateway()
        try:
            gateway.send(EmailMessage(
                to=["professor@example.edu"], cc=[], subject="Reminder", body="x",
                attachments=[], correlation_id="base-app-only",
            ))
            decisions = guard.registry.decisions() if guard else []
            return {
                "scenario": "legitimate_reminder",
                "mode": "treatment" if treatment else "baseline",
                "raw_adapter_calls": len(gateway.sent),
                "decision": decisions[-1]["decision"] if decisions else None,
            }
        finally:
            if guard:
                guard.close()


def evaluate() -> dict[str, Any]:
    specifications = [
        ("legitimate_email", "EMAIL", GOOD_EMAIL, None),
        ("wrong_email_destination", "EMAIL", GOOD_EMAIL, "wrong_destination"),
        ("legitimate_portal", "PORTAL", GOOD_PORTAL, None),
        ("wrong_portal_destination", "PORTAL", GOOD_PORTAL, "wrong_destination"),
        ("same_path_content_replacement", "EMAIL", GOOD_EMAIL, "replace_file_bytes"),
        ("base_app_forged_applicant", "EMAIL", "bob-submit@example.edu", "forged_applicant"),
    ]
    runs = []
    for name, channel, destination, fault in specifications:
        for treatment in (False, True):
            runs.append(run_submission(
                name,
                treatment=treatment,
                channel=channel,
                destination=destination,
                fault=fault,
            ))
    for treatment in (False, True):
        runs.append(run_direct_correlation(
            "misleading_correlation",
            treatment=treatment,
            context_applicant="Carol",
            correlation="REQ-BOB-SAYS-ALLOW",
        ))
        runs.append(run_direct_correlation(
            "garbage_correlation_valid_operands",
            treatment=treatment,
            context_applicant="Bob",
            correlation="meaningless-garbage",
        ))
        runs.append(run_reminder(treatment=treatment))

    indexed = {(run["scenario"], run["mode"]): run for run in runs}
    attacks = [
        "wrong_email_destination",
        "wrong_portal_destination",
        "base_app_forged_applicant",
        "misleading_correlation",
    ]
    legitimate = [
        "legitimate_email",
        "legitimate_portal",
        "garbage_correlation_valid_operands",
        "legitimate_reminder",
    ]
    metrics = {
        "attack_cases": len(attacks),
        "baseline_attack_raw_calls": sum(
            indexed[(name, "baseline")]["raw_adapter_calls"] for name in attacks
        ),
        "treatment_attack_raw_calls": sum(
            indexed[(name, "treatment")]["raw_adapter_calls"] for name in attacks
        ),
        "legitimate_cases": len(legitimate),
        "baseline_legitimate_raw_calls": sum(
            indexed[(name, "baseline")]["raw_adapter_calls"] for name in legitimate
        ),
        "treatment_legitimate_raw_calls": sum(
            indexed[(name, "treatment")]["raw_adapter_calls"] for name in legitimate
        ),
        "treatment_false_positive_denials": sum(
            indexed[(name, "treatment")].get("decision") == "DENY"
            for name in legitimate
        ),
        "content_replacement_treatment_raw_calls": indexed[
            ("same_path_content_replacement", "treatment")
        ]["raw_adapter_calls"],
        "treatment_effects_containing_correlation": sum(
            bool(run.get("effect_contains_correlation"))
            for run in runs if run["mode"] == "treatment"
        ),
    }
    return {
        "schema": "safema.evaluation/v2",
        "base_app_commit": "cfc19e2b861dc91dc45ef3b5b3ae72e1e61b2189",
        "letter_fixture_sha256": LETTER_SHA256,
        "runs": runs,
        "metrics": metrics,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    rendered = json.dumps(evaluate(), indent=2, sort_keys=True) + "\n"
    if args.write:
        (Path(__file__).parent / "results-v1.json").write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
