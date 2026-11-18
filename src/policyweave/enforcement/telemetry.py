"""Optional app-neutral observation of real calls, messages and policy gates.

The host owns instrumentation and identity. Recording never authenticates a
participant, invokes a tool, infers delivery, or manufactures model context.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from datetime import datetime, timezone
import threading
import uuid

from policyweave.core.policy import canonical, fact
from policyweave.core.contracts import TIMELINE_FORMAT, TIMELINE_KINDS, PARTICIPANT_KINDS

_TRACE = ContextVar("policyweave_execution_trace", default=None)
_CALL = ContextVar("policyweave_observed_call", default=None)
_OPERATION = ContextVar("policyweave_observed_operation", default=None)


def current_trace():
    return _TRACE.get()


class ExecutionTrace:
    """One bounded episode, exportable as the existing data-only timeline."""

    def __init__(self, title="Recorded execution"):
        self.title = title
        self._roles, self._events, self._policies = {}, [], set()
        self._sources, self._dependencies = set(), set()
        self._lock = threading.RLock()

    def participant(self, identifier, *, kind="agent", name=None):
        if (not isinstance(identifier, str) or not 1 <= len(identifier) <= 128
                or not isinstance(kind, str) or kind not in PARTICIPANT_KINDS
                or (name is not None and (not isinstance(name, str) or not 1 <= len(name) <= 200))):
            raise ValueError("Declare a bounded participant and supported kind.")
        with self._lock:
            self._roles[identifier] = dict(id=identifier, name=name or identifier, kind=kind)

    def model_output(self, actor, output, *, stage=None):
        return self.event("llm_output", actor, result=output,
                          data=dict(stage=stage) if stage else {})

    def event(self, kind, actor, *, data=None, **fields):
        if not isinstance(kind, str) or kind not in TIMELINE_KINDS:
            raise ValueError("Unknown observation event kind.")
        if not isinstance(actor, str) or not 1 <= len(actor) <= 128:
            raise ValueError("Recorded actor IDs require 1–128 characters.")
        with self._lock:
            if len(self._events) >= 10000:
                raise ValueError("Execution episode exceeds 10,000 events.")
            row = dict(
                id=uuid.uuid4().hex,
                sequence=len(self._events),
                kind=kind,
                actor=actor,
                timestamp=datetime.now(timezone.utc).isoformat(),
                **deepcopy(fields),
            )
            if data is not None:
                row["data"] = deepcopy(data)
            canonical(row)  # Only JSON data, never reprs of application objects.
            self._roles.setdefault(actor, dict(id=actor, name=actor, kind="agent"))
            for recipient in row.get("recipients", []):
                if not isinstance(recipient, str) or not 1 <= len(recipient) <= 128:
                    raise ValueError("Invalid recorded recipient.")
                self._roles.setdefault(recipient, dict(id=recipient, name=recipient, kind="agent"))
            self._events.append(row)
            return row["id"]

    @contextmanager
    def operation(self, actor, tool, arguments, *, source="host instrumentation"):
        identifier = uuid.uuid4().hex
        parent_call = _CALL.get()
        self.event(
            "tool_call",
            actor,
            tool=tool,
            callId=identifier,
            arguments=arguments,
            data=dict(source=source, **({"parentCallId": parent_call} if parent_call else {})),
        )
        token = _CALL.set(identifier)
        result = dict()
        operation_token = _OPERATION.set((actor, tool, result))
        try:
            yield result
        except BaseException as error:
            self.event(
                "tool_result",
                actor,
                callId=identifier,
                result=dict(errorType=type(error).__name__),
                data=dict(source=source, outcome="unknown"),
            )
            raise
        else:
            self.event(
                "tool_result",
                actor,
                callId=identifier,
                result=result.get("value"),
                data=dict(source=source, outcome=result.get("outcome", "unconfirmed")),
            )
        finally:
            _OPERATION.reset(operation_token)
            _CALL.reset(token)

    def message(self, sender, recipients, content, *, phase="sent", message_id=None):
        if phase not in {"attempted", "sent", "received", "blocked"}:
            raise ValueError("Unknown message observation phase.")
        if not isinstance(recipients, list) or len(set(recipients)) != len(recipients):
            raise ValueError("List explicit, distinct recipients; [] is not broadcast.")
        if phase == "received" and len(recipients) != 1:
            raise ValueError("A receipt observation names exactly one recipient.")
        return self.event(
            "message",
            sender,
            recipients=recipients,
            content=content if isinstance(content, str) else canonical(content),
            data=dict(phase=phase, messageId=message_id or "", callId=_CALL.get()),
        )

    def source(self, principal, data_id):
        """Trusted input-origin observation, not a classifier or an agent claim."""
        self._sources.add((principal, data_id))
        self.event(
            "state", principal, data=dict(observation="data_source", dataId=data_id)
        )

    def facts(self, actor, rows, *, source):
        """Explicit app-owned analysis facts; the exporter prepends this event ID."""
        return self.event(
            "state",
            actor,
            data=dict(observation="analysis_facts", facts=rows, source=source),
        )

    def context(self, actor, context_id, *, inputs, outputs, complete):
        """Observe the actual supplied context; every output may depend on every input.

        Inputs must be version-specific IDs for content actually supplied, including
        tool results and retained history. Unknown coverage stays explicitly unknown.
        """
        if (
            type(complete) is not bool
            or not isinstance(inputs, list)
            or not isinstance(outputs, list)
        ):
            raise ValueError(
                "Record explicit input/output data IDs and context coverage."
            )
        if any(
            not isinstance(v, str) or not 1 <= len(v) <= 128 for v in inputs + outputs
        ):
            raise ValueError("Context data IDs require bounded strings.")
        self._dependencies.update((out, inp) for out in outputs for inp in inputs)
        self.event(
            "state",
            actor,
            data=dict(
                observation="model_context",
                contextId=context_id,
                inputs=inputs,
                outputs=outputs,
                complete=complete,
                basis="conservative-context-may",
            ),
        )

    def provenance_facts(self):
        """Reuse the existing provenance foundation; unknown contexts are not certified clean."""
        return [fact("Source", *row) for row in sorted(self._sources)] + [
            fact("DependsOn", *row) for row in sorted(self._dependencies)
        ]

    def register_policy(self, header):
        identity = header["traceId"]
        if identity not in self._policies:
            self.participant("PolicyWeave", kind="runtime")
            self.event(
                "state",
                "PolicyWeave",
                data=dict(
                    observation="policy_installed",
                    policyTrace=identity,
                    recording={key: header[key] for key in ("format", "version", "scope")},
                    policy=header["policy"],
                    initialInputs=header["initialInputs"],
                ),
            )
            self._policies.add(identity)

    def gate(self, header, event):
        identity = header["traceId"]
        self.register_policy(header)
        request = event.get("request", {})
        self.event(
            "state",
            request.get("actor", "PolicyWeave"),
            data=dict(
                observation="policy_result",
                policyTrace=identity,
                callId=_CALL.get(),
                gateRecord=event,
            ),
        )

    def decision(self, audit):
        self.event(
            "decision",
            audit["request"]["actor"],
            data=dict(
                observation="policy_decision",
                callId=_CALL.get(),
                gateId=audit["id"],
                decision=audit["decision"],
            ),
        )

    def export(self, directory=None):
        with self._lock:
            value = deepcopy(
                dict(
                    format=TIMELINE_FORMAT,
                    version=1,
                    title=self.title,
                    roles=list(self._roles.values()),
                    events=self._events,
                )
            )
        if directory is not None:
            from pathlib import Path
            from policyweave.core.artifacts import save

            root = Path(directory)
            root.mkdir(parents=True, exist_ok=True, mode=0o700)
            if any((root / name).exists() for name in ("trajectory.json", "trajectory.jsonl")):
                raise FileExistsError("Choose a fresh trajectory output directory.")
            save(root / "trajectory.json", value)
            header = {key: item for key, item in value.items() if key != "events"}
            with (root / "trajectory.jsonl").open("x", encoding="utf-8") as stream:
                (root / "trajectory.jsonl").chmod(0o600)
                for item in [header, *value["events"]]:
                    stream.write(canonical(item) + "\n")
        return value


@contextmanager
def record_execution(title="Recorded execution"):
    trace = ExecutionTrace(title)
    token = _TRACE.set(trace)
    try:
        yield trace
    finally:
        _TRACE.reset(token)


@contextmanager
def observe_operation(actor, tool, arguments):
    trace = current_trace()
    if trace is None:
        yield None
    elif (active := _OPERATION.get()) is not None and active[:2] == (actor, tool):
        yield active[2]
    else:
        with trace.operation(actor, tool, arguments, source="@policy") as outcome:
            yield outcome
