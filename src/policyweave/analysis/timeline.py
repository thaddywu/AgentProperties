"""Data-only observation logs and a viewing adapter for recorded policy gates."""

from copy import deepcopy
from datetime import datetime
import json
import re

from policyweave.core.policy import canonical, fingerprint
from policyweave.core.contracts import TIMELINE_FORMAT, TIMELINE_KINDS, PARTICIPANT_KINDS
from .trajectory import TrajectorySession

# Keep persisted v1 identifiers stable across the PolicyWeave rename.
FORMAT = TIMELINE_FORMAT
KINDS = TIMELINE_KINDS
MAX_TRAJECTORY_BYTES = 512 * 1024 * 1024


def bounded(value, limit=128, *, empty=False):
    if not isinstance(value, str) or len(value) > limit or (not empty and not value):
        raise ValueError("Expected bounded text.")
    return value


def decode_trajectory(text):
    """Read one JSON document or a JSONL header followed by observation events."""
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_TRAJECTORY_BYTES:
        raise ValueError("Expected a trajectory of at most 512 MiB.")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        lines = text.splitlines()
        if not 2 <= len(lines) <= 10001:
            raise ValueError("Invalid trajectory JSON or JSONL.") from None
        try:
            header, *events = [json.loads(line) for line in lines]
            if not isinstance(header, dict) or header.get("format") != FORMAT or "events" in header:
                raise ValueError("Expected a timeline header.")
            return dict(header, events=events)
        except (json.JSONDecodeError, TypeError):
            raise ValueError("Invalid trajectory JSONL.") from None


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
        self._gate_links = self._recorded_gates()

    def _recorded_gates(self):
        """Connect captured runtime evidence by explicit trace and call IDs only."""
        headers, records, links = {}, {}, {}
        for event in self._rows:
            data = event.get("data")
            if not isinstance(data, dict):
                continue
            trace = data.get("policyTrace")
            if not isinstance(trace, str):
                continue
            if data.get("observation") == "policy_installed" and "recording" in data:
                metadata = data["recording"]
                if (
                    not isinstance(metadata, dict)
                    or metadata.get("format") != "policyscope-trajectory"
                    or not {"policy", "initialInputs"} <= data.keys()
                ):
                    raise ValueError("Recorded policy trace identity does not match.")
                header = dict(metadata, traceId=trace, policy=data["policy"], initialInputs=data["initialInputs"])
                if trace in headers and headers[trace] != header:
                    raise ValueError("Recorded policy headers conflict.")
                headers[trace] = header
            elif data.get("observation") == "policy_result":
                records.setdefault(trace, []).append(data)
        calls = {
            event["callId"]: event
            for event in self._rows
            if event["kind"] == "tool_call"
        }
        for trace, header in headers.items():
            captured = records.get(trace, [])
            if any(not isinstance(row.get("gateRecord"), dict) for row in captured):
                raise ValueError("Recorded gate evidence is missing.")
            value = dict(header, events=[row["gateRecord"] for row in captured])
            value["id"] = fingerprint(value)
            gate = Timeline(value)  # Reuse exact policy/event/hash validation.
            for row in captured:
                call_id = row.get("callId")
                call = calls.get(call_id) if isinstance(call_id, str) else None
                record = row["gateRecord"]
                if call is not None and record["kind"] == "call":
                    if call["actor"] != record["request"]["actor"]:
                        raise ValueError("Recorded gate and tool actors do not match.")
                    links.setdefault(call_id, []).append((gate, record["id"]))
        return links

    def gate(self, event_id):
        """Return one exact captured gate; ambiguous or absent evidence stays absent."""
        event = self._events.get(event_id) if isinstance(event_id, str) else None
        if event is None:
            raise ValueError("Unknown event.")
        if self._original["format"] == "policyscope-trajectory":
            return self, event_id
        links = self._gate_links.get(event.get("callId"), [])
        return links[0] if len(links) == 1 else None

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
                or set(role) - {"id", "name", "role", "kind"}
            ):
                raise ValueError("Invalid participant fields.")
            identifier = bounded(role["id"])
            bounded(role["name"], 200)
            if "role" in role:
                bounded(role["role"], 200)
            if "kind" in role and (not isinstance(role["kind"], str) or role["kind"] not in PARTICIPANT_KINDS):
                raise ValueError("Unknown participant kind.")
            if identifier in known:
                raise ValueError("Duplicate participant.")
            known.add(identifier)
        rows = value["events"]
        if not isinstance(rows, list) or len(rows) > 10000:
            raise ValueError("At most 10,000 events.")
        ids, calls, results = set(), {}, set()
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
            if kind == "llm_output" and "result" not in event:
                raise ValueError("Model output needs its visible result.")
            if kind in {"tool_call", "tool_result", "llm_call", "llm_result"}:
                call = bounded(event.get("callId"))
                if kind in {"tool_call", "llm_call"}:
                    if kind == "tool_call":
                        bounded(event.get("tool"), 200)
                    if call in calls or "arguments" not in event:
                        raise ValueError(
                            "Tool calls need unique call IDs and arguments."
                        )
                    calls[call] = kind
                else:
                    expected = "tool_call" if kind == "tool_result" else "llm_call"
                    if (
                        calls.get(call) != expected
                        or call in results
                        or "result" not in event
                    ):
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
        summaries = self._summaries()
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
                    | summaries[e["id"]]
                    for e in self._rows
                ],
            )
        )

    def _summaries(self):
        """Presentation only: retain original event IDs/order and untouched export."""

        def mapping(value):
            return value if isinstance(value, dict) else {}

        rows = {e["id"]: e for e in self._rows}
        results = {
            e.get("callId"): e
            for e in self._rows
            if e["kind"] in {"tool_result", "llm_result"}
        }
        calls = {
            e.get("callId"): e
            for e in self._rows
            if e["kind"] in {"tool_call", "llm_call"}
        }
        responses = {}
        requests = {}
        sent_messages = {}
        for event in self._rows:
            data = mapping(event.get("data"))
            message_id = data.get("messageId")
            if event["kind"] == "message" and data.get("phase") == "sent" and isinstance(message_id, str) and message_id:
                key = (event["actor"], tuple(event["recipients"]), message_id)
                sent_messages.setdefault(key, []).append(event)
            parents = data.get("parents")
            if data.get("nativeKind") == "decision_summary" and isinstance(
                parents, list
            ):
                for parent in parents:
                    parent_data = (
                        mapping(rows.get(parent, {}).get("data"))
                        if isinstance(parent, str)
                        else {}
                    )
                    if parent_data.get("nativeKind") == "decision_request":
                        responses[parent] = event
                        requests[event["id"]] = rows[parent]
        summaries = {}
        for event in self._rows:
            kind = event["kind"]
            data = event.get("data") if isinstance(event.get("data"), dict) else {}
            inputs = data.get("inputs") if isinstance(data.get("inputs"), dict) else {}
            outputs = (
                data.get("outputs") if isinstance(data.get("outputs"), dict) else {}
            )
            native = data.get("nativeKind")
            if not isinstance(native, str):
                native = None
            category = {
                "tool_call": "tool",
                "tool_result": "tool",
                "llm_call": "model",
                "llm_result": "model",
                "llm_output": "model",
            }.get(kind, kind)
            primary = kind in {"message", "tool_call", "llm_result", "llm_output"}
            title = event.get("tool") or {
                "message": "Message",
                "decision": "Event",
                "state": "State",
                "llm_call": "LLM call",
                "llm_result": "LLM output",
                "llm_output": "LLM output",
            }.get(kind, kind)
            preview = event.get("content", "")
            related = (
                (calls if kind in {"tool_result", "llm_result"} else results).get(
                    event.get("callId")
                )
                if event.get("callId")
                else None
            )
            if kind == "tool_call":
                parent_call = data.get("parentCallId")
                if isinstance(parent_call, str) and parent_call in calls and calls[parent_call]["sequence"] < event["sequence"]:
                    primary = False
                preview = (
                    " · ".join(
                        f"{key}: {canonical(value) if not isinstance(value, (dict, list)) else str(len(value)) + ' fields'}"
                        for key, value in list(event["arguments"].items())[:4]
                    )
                    if isinstance(event["arguments"], dict)
                    else ""
                )
            if (
                kind == "llm_call"
                and related
                and isinstance(related.get("result"), dict)
            ):
                preview = related["result"].get("summary", "")
            if kind == "llm_call" and related is None:
                primary = True  # An unfinished request must remain visible.
            if kind in {"llm_result", "llm_output"}:
                result = event["result"]
                preview = result.get("summary", canonical(result)) if isinstance(result, dict) else str(result)
            if native in {"decision_request", "decision_summary"}:
                category = "model"
                title = "LLM output"
                if native == "decision_request":
                    related = responses.get(event["id"])
                    primary = related is None
                else:
                    related = requests.get(event["id"])
                    primary = True
                decision = outputs.get("decision")
                if isinstance(decision, dict):
                    preview = decision.get("summary") or (
                        "Choose " + decision["tool"]
                        if isinstance(decision.get("tool"), str)
                        else ""
                    )
                if native == "decision_request" and related:
                    result = mapping(mapping(related.get("data")).get("outputs")).get(
                        "decision"
                    )
                    if isinstance(result, dict):
                        preview = result.get("summary") or (
                            "Choose " + result["tool"]
                            if isinstance(result.get("tool"), str)
                            else ""
                        )
            elif native == "message_received":
                parents = data.get("parents")
                if isinstance(parents, list):
                    primary = not any(
                        rows.get(p, {}).get("kind") == "message"
                        for p in parents
                        if isinstance(p, str)
                    )
            if kind == "message" and data.get("phase") == "received" and isinstance(data.get("messageId"), str):
                sent = sent_messages.get((event["actor"], tuple(event["recipients"]), data["messageId"]), [])
                if len(sent) == 1 and sent[0]["sequence"] < event["sequence"] and sent[0]["content"] == event["content"]:
                    primary = False
            if (
                isinstance(preview, str)
                and preview.startswith("{")
                and category == "message"
            ):
                try:
                    body = json.loads(preview)
                    if isinstance(body, dict):
                        preview = body.get("message", body.get("text", preview))
                except ValueError:
                    pass
            request = data.get("request")
            if isinstance(request, dict):
                category, title, primary = "tool", request.get("action", title), True
            summaries[event["id"]] = dict(
                category=category,
                primary=primary,
                title=str(title)[:200],
                preview=str(preview)[:240],
                relatedEventId=related["id"] if related else None,
                messagePhase=data.get("phase") or {"message_sent": "sent", "message_received": "received"}.get(native),
            )
            linked = data.get("gates")
            if (
                isinstance(linked, list)
                and len(linked) == 1
                and isinstance(linked[0], dict)
            ):
                outcome = linked[0].get("outcome")
                if isinstance(outcome, str):
                    summaries[event["id"]]["outcome"] = outcome
            gate = self.gate(event["id"])
            if gate is not None:
                record = gate[0].event(gate[1])["data"]
                summaries[event["id"]]["outcome"] = record["outcome"]
        return summaries

    def event(self, identifier):
        if not isinstance(identifier, str) or identifier not in self._events:
            raise ValueError("Unknown event.")
        return deepcopy(self._events[identifier])

    def export(self):
        return deepcopy(self._original)
