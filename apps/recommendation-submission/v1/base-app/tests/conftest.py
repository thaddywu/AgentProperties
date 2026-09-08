"""Shared fixtures.

Every test runs the real application against the deterministic doubles in
:mod:`recsub.testing`; nothing external is contacted.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import pytest

from recsub.config import AppConfig, ComponentSpec, Components
from recsub.service import Application
from recsub.testing import (
    FixedClock,
    RecordingEmailGateway,
    RecordingPortalAgent,
    ScriptedRequestSource,
)

NOW = "2026-11-01T12:00:00Z"
PROFESSOR = "professor@example.edu"
_SPEC = ComponentSpec(factory="recsub.testing.doubles:unused")


def make_config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        database_path=str(tmp_path / "recsub.sqlite3"),
        professor_email=PROFESSOR,
        display_time_zone="America/New_York",
        request_sources=(),
        email_gateway=_SPEC,
        portal_agent=_SPEC,
        clock=_SPEC,
        source_path=str(tmp_path / "config.json"),
    )


@dataclass
class Harness:
    """One application wired to doubles, plus helpers for building fixtures."""

    app: Application
    clock: FixedClock
    email: RecordingEmailGateway
    portal: RecordingPortalAgent
    inbox: ScriptedRequestSource
    portal_source: ScriptedRequestSource
    tmp_path: Path

    def letter_file(self, name: str = "letter.pdf") -> str:
        path = self.tmp_path / "letters" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("(the professor's completed letter)\n", encoding="utf-8")
        return str(path)

    def add_event(self, event: Any, *, source: str = "email_inbox") -> None:
        target = self.inbox if source == "email_inbox" else self.portal_source
        target.events.append(event)

    def add_request(
        self,
        *,
        event_id: str,
        source_reference: str,
        applicant: str = "Ada Lovelace",
        description: str = "MIT EECS PhD",
        purpose: str = "PHD_APPLICATION",
        channel: str = "EMAIL",
        destination: Optional[str] = None,
        deadline: str = "2026-12-01T23:59:00Z",
        source: str = "email_inbox",
    ) -> str:
        """Ingest one add event and return the resulting request ID."""
        if destination is None:
            destination = (
                "admissions@example.edu"
                if channel == "EMAIL"
                else "https://portal.example.edu/submit/" + source_reference
            )
        self.add_event(
            {
                "event_id": event_id,
                "source_kind": "email_inbox" if source == "email_inbox" else "portal_scan",
                "kind": "ADD_REQUEST",
                "new_request": {
                    "source_reference": source_reference,
                    "applicant_name": applicant,
                    "application_description": description,
                    "purpose": purpose,
                    "channel": channel,
                    "destination": destination,
                    "deadline": deadline,
                },
            },
            source=source,
        )
        self.app.sync()
        request = self.app.repository.find_request_by_source(
            "email_inbox" if source == "email_inbox" else "portal_scan", source_reference
        )
        assert request is not None, "the add event was not ingested"
        return request.request_id

    def register(
        self,
        *,
        applicant: str = "Ada Lovelace",
        purpose: str = "PHD_APPLICATION",
        name: str = "letter.pdf",
    ) -> str:
        return self.app.register_letter(
            file_path=self.letter_file(name), applicant_name=applicant, purpose=purpose
        )

    def status(self, request_id: str) -> str:
        return self.app.repository.require_request(request_id).status.value


@pytest.fixture
def harness(tmp_path: Path) -> Harness:
    clock = FixedClock(NOW)
    email = RecordingEmailGateway()
    portal = RecordingPortalAgent()
    inbox = ScriptedRequestSource("email_inbox")
    portal_source = ScriptedRequestSource("portal_scan")
    components = Components(
        request_sources=(inbox, portal_source),
        email_gateway=email,
        portal_agent=portal,
        clock=clock,
    )
    app = Application.open(make_config(tmp_path), components)
    harness = Harness(
        app=app,
        clock=clock,
        email=email,
        portal=portal,
        inbox=inbox,
        portal_source=portal_source,
        tmp_path=tmp_path,
    )
    yield harness
    app.close()
