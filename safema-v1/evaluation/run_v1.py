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
from safema.runtime import install

LETTER_BYTES = b"deterministic Alice recommendation v1\n"
LETTER_SHA256 = hashlib.sha256(LETTER_BYTES).hexdigest()
GOOD_EMAIL = "alice-submit@example.edu"
BAD_EMAIL = "mallory-submit@example.edu"
GOOD_PORTAL = "https://portal.example.edu/alice"
BAD_PORTAL = "https://portal.example.edu/mallory"


def _runtime(directory: Path):
    return install(
        effect_models_path=ROOT / "safema-v1/models/api-effects-v1.yaml",
        origins_path=ROOT / "safema-v1/models/trusted-origins-v1.yaml",
        policy_path=ROOT / "safema-v1/policies/same-principal-active-destination-v1.yaml",
        metadata_db=directory / "safema.db",
    )


def _app(directory: Path, *, channel: str, destination: str):
    source = ScriptedRequestSource(
        "trusted-world",
        [RequestEvent(
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
        )],
    )
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


def run_submission(name: str, *, treatment: bool, channel: str, good: str, fault: str | None):
    with tempfile.TemporaryDirectory(prefix=f"safema-{name}-") as temporary:
        directory = Path(temporary)
        guard = _runtime(directory) if treatment else None
        app, email, portal = _app(directory, channel=channel, destination=good)
        try:
            sync = app.sync()
            letter = directory / "alice-letter.pdf"
            letter.write_bytes(LETTER_BYTES)
            letter_id = app.register_letter(
                file_path=str(letter), applicant_name="Alice", purpose="PHD_APPLICATION"
            )
            if fault == "wrong_destination":
                bad = BAD_EMAIL if channel == "EMAIL" else BAD_PORTAL
                with app.repository.transaction() as connection:
                    connection.execute(
                        "UPDATE requests SET destination = ? WHERE request_id = 'REQ-000001'",
                        (bad,),
                    )
            elif fault == "replace_file_bytes":
                letter.write_bytes(b"substituted content after trusted registration\n")
            report = app.process_pending()
            calls = email.sent if channel == "EMAIL" else portal.uploads
            if channel == "EMAIL":
                raw_destinations = [address for call in calls for address in call.to + call.cc]
            else:
                raw_destinations = [call.submission_url for call in calls]
            decisions = guard.registry.decisions() if guard else []
            resources = guard.registry.resources() if guard else []
            contexts = guard.registry.contexts() if guard else []
            reason = decisions[-1]["reason"] if decisions else None
            if reason:
                reason = reason.replace(str(letter.resolve()), "<letter_path>")
            return {
                "scenario": name,
                "mode": "treatment" if treatment else "baseline",
                "base_request_id": "REQ-000001",
                "base_letter_id": letter_id,
                "sync_events_applied": len(sync.applied),
                "trusted_letter_sha256": LETTER_SHA256 if treatment else None,
                "metadata_resource_bindings": len(resources),
                "metadata_active_contexts": sum(c["state"] == "active" for c in contexts),
                "safema_decision": decisions[-1]["decision"] if decisions else None,
                "safema_decision_id": decisions[-1]["decision_id"] if decisions else None,
                "safema_reason": reason,
                "raw_adapter_calls": len(calls),
                "raw_destinations": raw_destinations,
                "base_app_succeeded": bool(report.succeeded),
                "base_app_failed": bool(report.failed),
                "request_final_status": app.repository.require_request("REQ-000001").status.value,
            }
        finally:
            app.close()
            if guard:
                guard.close()


def run_reminder_sink(*, treatment: bool):
    with tempfile.TemporaryDirectory(prefix="safema-reminder-") as temporary:
        directory = Path(temporary)
        guard = _runtime(directory) if treatment else None
        gateway = RecordingEmailGateway()
        try:
            gateway.send(EmailMessage(
                to=["professor@example.edu"], cc=[], subject="Deadline reminder", body="x",
                attachments=[], correlation_id="REMINDER-001",
            ))
            decisions = guard.registry.decisions() if guard else []
            return {
                "scenario": "legitimate_reminder_no_attachment",
                "mode": "treatment" if treatment else "baseline",
                "safema_decision": decisions[-1]["decision"] if decisions else None,
                "safema_reason": decisions[-1]["reason"] if decisions else None,
                "raw_adapter_calls": len(gateway.sent),
                "raw_destinations": gateway.sent[0].to if gateway.sent else [],
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
    ]
    runs = []
    for name, channel, good, fault in specifications:
        runs.append(run_submission(name, treatment=False, channel=channel, good=good, fault=fault))
        runs.append(run_submission(name, treatment=True, channel=channel, good=good, fault=fault))
    runs.extend([run_reminder_sink(treatment=False), run_reminder_sink(treatment=True)])

    by_key = {(run["scenario"], run["mode"]): run for run in runs}
    wrong = ["wrong_email_destination", "wrong_portal_destination"]
    legitimate = ["legitimate_email", "legitimate_portal", "legitimate_reminder_no_attachment"]
    metrics = {
        "wrong_destination_cases": len(wrong),
        "baseline_wrong_destination_raw_calls": sum(
            by_key[(name, "baseline")]["raw_adapter_calls"] for name in wrong
        ),
        "treatment_wrong_destination_raw_calls": sum(
            by_key[(name, "treatment")]["raw_adapter_calls"] for name in wrong
        ),
        "treatment_wrong_destination_denials": sum(
            by_key[(name, "treatment")]["safema_decision"] == "DENY" for name in wrong
        ),
        "legitimate_cases": len(legitimate),
        "baseline_legitimate_raw_calls": sum(
            by_key[(name, "baseline")]["raw_adapter_calls"] for name in legitimate
        ),
        "treatment_legitimate_raw_calls": sum(
            by_key[(name, "treatment")]["raw_adapter_calls"] for name in legitimate
        ),
        "treatment_false_positive_denials": sum(
            by_key[(name, "treatment")]["safema_decision"] == "DENY"
            for name in legitimate
        ),
        "content_replacement_baseline_raw_calls": by_key[
            ("same_path_content_replacement", "baseline")
        ]["raw_adapter_calls"],
        "content_replacement_treatment_raw_calls": by_key[
            ("same_path_content_replacement", "treatment")
        ]["raw_adapter_calls"],
    }
    return {
        "schema": "safema.evaluation/v1",
        "base_app_commit": "cfc19e2b861dc91dc45ef3b5b3ae72e1e61b2189",
        "letter_fixture_sha256": LETTER_SHA256,
        "runs": runs,
        "metrics": metrics,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="write results-v1.json")
    args = parser.parse_args()
    result = evaluate()
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.write:
        (Path(__file__).parent / "results-v1.json").write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
