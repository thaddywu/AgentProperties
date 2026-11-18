"""Project app-neutral observations and explicit app facts into historical rules."""

from copy import deepcopy
from pathlib import Path
import re

from policyweave.core.policy import canonical, fact, fingerprint, policy_predicates
from policyweave.core.source import read_policy_document
from .timeline import Timeline

DEFAULT_RULES = Path(__file__).with_name("execution.dl").read_text()
SCOPE = "Host-observed calls, explicit message phases and recorded gate outcomes. Arguments are JSON values at JSON-pointer paths. FactChange is a delta for one policy trace and before/after phase, never a union of historical EDB. MayOrigin is conservative propagation over supplied dependencies; missing/unknown contexts do not certify clean data. No application completion or policy-satisfaction semantics are inferred."


def execution_analysis(value, *, rules="", templates=None, entities=None, scope=SCOPE):
    timeline = Timeline(value)
    source = (
        rules
        if re.search(r"\.decl\s+Invocation\s*\(", rules)
        else DEFAULT_RULES + "\n" + rules
    )
    predicates = policy_predicates(source)
    configuration = read_policy_document(source)[2]
    inputs = deepcopy(configuration)
    seen_facts, states = set(), {}
    schemas = {}

    def emit(name, *args):
        if name not in predicates:
            if name in policy_predicates(DEFAULT_RULES):
                return  # Older explicit profiles expose only their declared projection.
            raise ValueError("Analysis facts require a declared predicate: " + name)
        inputs.append(fact(name, *args))

    def arguments(eid, value, path=""):
        encoded = canonical(value)
        if len(encoded) <= 4096:
            emit("Argument", eid, path or "/", encoded)
        else:
            emit("ProjectionOmitted", eid, path or "/")
        if isinstance(value, dict):
            for key, item in value.items():
                arguments(
                    eid,
                    item,
                    path + "/" + str(key).replace("~", "~0").replace("/", "~1"),
                )
        elif isinstance(value, list):
            for index, item in enumerate(value):
                arguments(eid, item, path + "/" + str(index))

    def changes(eid, trace, phase, rows):
        current = {fingerprint(row): row for row in rows}
        previous = states.get(trace, {})
        for key, row in current.items():
            if key not in seen_facts:
                emit("FactRow", key, row["predicate"])
                for index, value in enumerate(row["args"]):
                    emit("FactCell", key, index, str(value))
                    schema = schemas[trace].get(row["predicate"], {})
                    types = schema.get("types", ["symbol"] * len(row["args"]))
                    if types[index] == "number":
                        emit("NumberCell", key, index, int(value))
                seen_facts.add(key)
            if key not in previous:
                emit("FactChange", eid, trace, phase, "put", key)
        for key in previous.keys() - current.keys():
            emit("FactChange", eid, trace, phase, "delete", key)
        states[trace] = current

    for event in timeline.export()["events"]:
        eid, data = event["id"], event.get("data", {})
        if event["kind"] == "tool_call":
            emit("Invocation", eid, event["callId"], event["actor"], event["tool"])
            arguments(eid, event["arguments"])
        elif event["kind"] == "tool_result":
            emit(
                "CallOutcome", eid, event["callId"], data.get("outcome", "unconfirmed")
            )
            result = event["result"]
            for name, item in (
                result.items() if isinstance(result, dict) else [("/", result)]
            ):
                if not isinstance(item, (dict, list)) and len(canonical(item)) <= 4096:
                    emit("ResultField", eid, name, canonical(item))
        elif event["kind"] == "message":
            for recipient in event["recipients"]:
                emit(
                    "Message",
                    eid,
                    event["actor"],
                    recipient,
                    data.get("phase", "unrecorded"),
                    data.get("messageId", ""),
                )
        observation = data.get("observation")
        if observation == "policy_installed":
            schemas[data["policyTrace"]] = data["policy"]["binding"]["predicates"]
            changes(eid, data["policyTrace"], "initial", data["initialInputs"])
        elif observation == "policy_decision":
            decision = data["decision"]
            request = decision["request"]
            if data.get("callId") is not None:
                emit("GateCall", eid, data["callId"])
            for reason in decision["reasons"]:
                emit("RefusalReason", eid, reason)
            for name, value in request.get("parameters", {}).items():
                emit("RequestArgument", eid, name, value)
            emit(
                "GateDecision",
                eid,
                data["gateId"],
                request["actor"],
                request["action"],
                str(decision["allowed"]).lower(),
            )
        elif observation == "policy_result":
            gate = data["gateRecord"]
            emit("GateOutcome", eid, gate["id"], data["policyTrace"], gate["outcome"])
            for phase, key in [("before", "inputs"), ("after", "committedInputs")]:
                if gate.get(key) is not None:
                    changes(eid, data["policyTrace"], phase, gate[key])
        elif observation == "data_source":
            emit("DataSource", data["dataId"], event["actor"])
        elif observation == "model_context":
            emit(
                "ContextCoverage", eid, data["contextId"], str(data["complete"]).lower()
            )
            for output in data["outputs"]:
                emit("ContextOutput", eid, output)
                for input_ in data["inputs"]:
                    emit("Dependency", output, input_)
        elif observation == "analysis_facts":
            for row in data["facts"]:
                emit(row["predicate"], eid, *row["args"])
    result = timeline.export()
    result["analysis"] = dict(
        binding=dict(
            version=1,
            id="execution-observations",
            context="Recorded execution analysis.",
            predicates=predicates,
            decision=dict(
                request="Request", parameters="Parameter", allow="Allow", deny="Deny"
            ),
            tests=[],
            configuration=configuration,
        ),
        source=source,
        inputs=inputs,
        scope=scope,
        templates=templates
        if templates is not None
        else [
            dict(
                id="calls",
                question="Which protected functions were called?",
                query="?- Invocation(E,C,A,T).",
            ),
            dict(
                id="refusals",
                question="Which requests did the gate refuse?",
                query="?- Refused(E,A,T).",
            ),
            dict(
                id="messages",
                question="Which message sends and receipts were observed?",
                query="?- Message(E,S,R,P,M).",
            ),
            dict(
                id="possible-sources",
                question="What are the recorded possible origins of data?",
                query="?- MayOrigin(D,O).",
            ),
        ],
        entities=entities or {},
    )
    return Timeline(result).export()
