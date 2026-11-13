"""Data-only observation logs and a viewing adapter for recorded policy gates."""

from copy import deepcopy
from datetime import datetime
import re

from policyscope.core.policy import canonical, fingerprint
from .trajectory import TrajectorySession

FORMAT = "policyscope-timeline"
KINDS = {"message", "tool_call", "tool_result", "state", "decision"}


def bounded(value, limit=128, *, empty=False):
    if not isinstance(value, str) or len(value) > limit or (not empty and not value):
        raise ValueError("Expected bounded text.")
    return value


class Timeline:
    """Validate and expose an immutable log. Nothing in a log becomes executable."""

    def __init__(self, value):
        if not isinstance(value, dict):
            raise ValueError("Expected a trajectory object.")
        self.identity = fingerprint(value)
        self._original = deepcopy(value)
        if value.get("format") == "policyscope-trajectory":
            self._policy(value)
        else:
            self._observations(value)
        self._events = {e["id"]: e for e in self._rows}

    def _observations(self, value):
        if (
            value.get("format") != FORMAT
            or type(value.get("version")) is not int
            or value["version"] != 1
            or not {"format", "version", "roles", "events"} <= set(value)
            or set(value)
            - {"format", "version", "title", "roles", "events", "analysis"}
        ):
            raise ValueError("Expected a version-1 timeline.")
        self.title = bounded(value.get("title", "Trajectory"), 200)
        self.scope = "Recorded observations; roles and recipients are recorder-supplied labels. Delivery, identity and completeness are not independently verified."
        roles = value["roles"]
        if not isinstance(roles, list) or not 1 <= len(roles) <= 256:
            raise ValueError("Declare 1–256 participants.")
        known = set()
        for role in roles:
            if (
                not isinstance(role, dict)
                or not {"id", "name"} <= set(role)
                or set(role) - {"id", "name", "role"}
            ):
                raise ValueError("Invalid participant fields.")
            identifier = bounded(role["id"])
            bounded(role["name"], 200)
            if "role" in role:
                bounded(role["role"], 200)
            if identifier in known:
                raise ValueError("Duplicate participant.")
            known.add(identifier)
        rows = value["events"]
        if not isinstance(rows, list) or len(rows) > 10000:
            raise ValueError("At most 10,000 events.")
        ids, calls, results = set(), set(), set()
        required = {"id", "sequence", "kind", "actor"}
        optional = {
            "recipients",
            "timestamp",
            "content",
            "tool",
            "callId",
            "arguments",
            "result",
            "data",
        }
        for sequence, event in enumerate(rows):
            if (
                not isinstance(event, dict)
                or not required <= set(event)
                or set(event) - required - optional
            ):
                raise ValueError("Invalid event fields.")
            identifier = bounded(event["id"])
            if (
                identifier in ids
                or type(event["sequence"]) is not int
                or event["sequence"] != sequence
            ):
                raise ValueError(
                    "Events need distinct IDs and contiguous sequence numbers."
                )
            ids.add(identifier)
            if not isinstance(event["actor"], str) or event["actor"] not in known:
                raise ValueError("Unknown actor.")
            kind = bounded(event["kind"])
            if kind not in KINDS:
                raise ValueError("Unknown event kind.")
            recipients = event.get("recipients", [])
            if (
                not isinstance(recipients, list)
                or not all(isinstance(r, str) and r in known for r in recipients)
                or len(set(recipients)) != len(recipients)
            ):
                raise ValueError("Recipients must reference declared participants.")
            if "timestamp" in event:
                stamp = bounded(event["timestamp"], 64)
                if not re.fullmatch(
                    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})",
                    stamp,
                ):
                    raise ValueError("Expected a timestamp with an explicit timezone.")
                parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                if parsed.utcoffset() is None or "T" not in stamp:
                    raise ValueError("Timestamps need an explicit timezone.")
            if "content" in event:
                bounded(event["content"], 200000, empty=True)
            for field in ("tool", "callId"):
                if field in event:
                    bounded(event[field], 200 if field == "tool" else 128)
            if kind == "message" and (
                "recipients" not in event or "content" not in event
            ):
                raise ValueError(
                    "Messages need content and recipients; [] means unrecorded."
                )
            if kind in {"tool_call", "tool_result"}:
                call = bounded(event.get("callId"))
                if kind == "tool_call":
                    bounded(event.get("tool"), 200)
                    if call in calls or "arguments" not in event:
                        raise ValueError(
                            "Tool calls need unique call IDs and arguments."
                        )
                    calls.add(call)
                else:
                    if call not in calls or call in results or "result" not in event:
                        raise ValueError("A result must match one earlier tool call.")
                    results.add(call)
            for name in ("arguments", "result", "data"):
                if name in event and len(canonical(event[name]).encode()) > 1_000_000:
                    raise ValueError("Event data exceeds 1 MB.")
        self.roles, self._rows = deepcopy(roles), deepcopy(rows)
        if "analysis" in value:
            from .log_query import validate_contract

            validate_contract(value["analysis"])

    def _policy(self, value):
        TrajectorySession(value)
        self.title, self.scope = "Policy trajectory", value["scope"]
        actors = {e["request"]["actor"] for e in value["events"] if e["kind"] == "call"}
        host = "host"
        while host in actors:
            host = "_" + host
        if any(e["kind"] == "update" for e in value["events"]):
            actors.add(host)
        self.roles = [dict(id=a, name=a, role="Recorded actor") for a in sorted(actors)]
        self._rows = [
            dict(
                id=e["id"],
                sequence=e["sequence"],
                kind="decision" if e["kind"] == "call" else "state",
                actor=e["request"]["actor"] if e["kind"] == "call" else host,
                content=e["request"]["action"]
                if e["kind"] == "call"
                else "Fact update",
                data=e,
            )
            for e in value["events"]
        ]

    def describe(self):
        return deepcopy(
            dict(
                id=self.identity,
                format=self._original["format"],
                title=self.title,
                scope=self.scope,
                roles=self.roles,
                events=[
                    {
                        k: v
                        for k, v in e.items()
                        if k not in {"data", "arguments", "result", "content"}
                    }
                    | dict(
                        preview=e.get(
                            "content",
                            canonical(e["arguments"])
                            if "arguments" in e
                            else canonical(e["result"])
                            if "result" in e
                            else "",
                        )[:240],
                        tool=e.get("tool"),
                        outcome=e.get("data", {}).get("outcome")
                        if isinstance(e.get("data"), dict)
                        and isinstance(e["data"].get("outcome"), str)
                        else None,
                    )
                    for e in self._rows
                ],
            )
        )

    def event(self, identifier):
        if not isinstance(identifier, str) or identifier not in self._events:
            raise ValueError("Unknown event.")
        return deepcopy(self._events[identifier])

    def export(self):
        return deepcopy(self._original)
