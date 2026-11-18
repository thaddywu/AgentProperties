"""Read-only NL → admitted Datalog → rows, from log contracts, never app source."""

from copy import deepcopy
import json

from policyweave.core.datalog import read_query
from policyweave.core.policy import CORE, fact
from .session import QuerySession
from .translation import QuestionTranslator, validate_templates
from .answers import render_answer

SCHEMA = {
    "Participant": (
        ["Actor", "Name", "Role"],
        "Recorder-declared participant labels, not authenticated identity.",
    ),
    "Event": (
        ["E", "Sequence", "Kind", "Actor"],
        "Recorded event ID, zero-based source order, kind and actor.",
    ),
    "Recipient": (
        ["E", "Actor"],
        "Explicit recorded recipient; no row does not mean broadcast or successful delivery.",
    ),
    "Content": (
        ["E", "Text"],
        "Recorded visible text, present only when at most 4096 characters.",
    ),
    "Omitted": (
        ["E", "Field"],
        "Field omitted from query projection because it exceeds the bounded symbol size.",
    ),
    "ToolCall": (
        ["E", "Call", "Tool"],
        "Recorded tool request; does not certify execution.",
    ),
    "ToolResult": (
        ["E", "Call"],
        "Recorded response linked to the tool call identifier; not universally business success.",
    ),
    "ModelCall": (
        ["E", "Call"],
        "Recorded model request; does not expose or infer hidden reasoning.",
    ),
    "ModelResult": (
        ["E", "Call"],
        "Recorded visible model response linked to an earlier model request.",
    ),
    "Timestamp": (
        ["E", "Time"],
        "Explicit recorder timestamp; missing timestamps remain unknown.",
    ),
    "RecordedOutcome": (
        ["E", "Outcome"],
        "Recorded gate outcome; applied is adapter confirmation, not proof of business success.",
    ),
    "Observed": (
        ["E"],
        "An event occurs in this supplied log, without a completeness claim.",
    ),
}


def validate_contract(value):
    required = {"binding", "source", "inputs", "scope"}
    if (
        not isinstance(value, dict)
        or not required <= set(value)
        or set(value) - required - {"templates", "entities"}
    ):
        raise ValueError("Analysis requires binding, source, inputs and scope.")
    if not isinstance(value["scope"], str) or not 1 <= len(value["scope"]) <= 4000:
        raise ValueError("Analysis requires bounded scope and limitations.")
    session = QuerySession(
        binding=value["binding"], source=value["source"], inputs=value["inputs"]
    )
    entities = value.get("entities", {})
    if (
        not isinstance(entities, dict)
        or len(entities) > 32
        or any(
            not isinstance(k, str)
            or not isinstance(v, list)
            or len(v) > 256
            or any(not isinstance(x, str) or len(x) > 4096 for x in v)
            for k, v in entities.items()
        )
    ):
        raise ValueError("Invalid entity catalog.")
    validate_templates(value["binding"], value.get("templates", []), entities)
    return session


def project(timeline):
    description = timeline.describe()
    predicates = deepcopy(CORE)
    for name, (args, meaning) in SCHEMA.items():
        predicates[name] = dict(
            kind="derived" if name == "Observed" else "input",
            args=args,
            meaning=meaning,
        )
    predicates["Event"]["types"] = ["symbol", "number", "symbol", "symbol"]
    binding = dict(
        version=1,
        id="trajectory-observations",
        context="Read-only log observations.",
        predicates=predicates,
        decision=dict(
            request="Request", parameters="Parameter", allow="Allow", deny="Deny"
        ),
        tests=[],
    )
    rows = [
        fact("Participant", r["id"], r["name"], r.get("role", ""))
        for r in description["roles"]
    ]
    for meta in description["events"]:
        event = timeline.event(meta["id"])
        identifier = event["id"]
        rows.append(
            fact("Event", identifier, event["sequence"], event["kind"], event["actor"])
        )
        rows += [fact("Recipient", identifier, r) for r in event.get("recipients", [])]
        for field, predicate in [("content", "Content"), ("timestamp", "Timestamp")]:
            if field in event:
                rows.append(
                    fact(predicate, identifier, event[field])
                    if len(event[field]) <= 4096
                    else fact("Omitted", identifier, field)
                )
        if event["kind"] == "tool_call":
            rows.append(fact("ToolCall", identifier, event["callId"], event["tool"]))
        if event["kind"] == "tool_result":
            rows.append(fact("ToolResult", identifier, event["callId"]))
        if event["kind"] == "llm_call":
            rows.append(fact("ModelCall", identifier, event["callId"]))
        if event["kind"] == "llm_result":
            rows.append(fact("ModelResult", identifier, event["callId"]))
        if event["kind"] == "llm_output":
            text = event["result"] if isinstance(event["result"], str) else json.dumps(event["result"], ensure_ascii=False, sort_keys=True)
            rows.append(fact("Content", identifier, text) if len(text) <= 4096 else fact("Omitted", identifier, "result"))
        if meta.get("outcome"):
            rows.append(fact("RecordedOutcome", identifier, meta["outcome"]))
    return dict(
        binding=binding,
        source="Observed(E) :- Event(E,S,K,A).",
        inputs=rows,
        scope="Only generic event, message and tool observations are projected. No domain policy or task-completion rules are supplied; policy-satisfaction and completion claims are unsupported. "
        + description["scope"],
        templates=[
            dict(
                id="events",
                question="Which events were recorded?",
                query="?- Event(E,S,K,A).",
            ),
            dict(
                id="recipients",
                question="Who were the recorded message recipients?",
                query="?- Recipient(E,A).",
            ),
            dict(
                id="recipient-events",
                question="Which events name this recipient?",
                query="?- Recipient(E,{recipient}).",
                parameters=dict(recipient="participants"),
            ),
        ],
        entities=dict(
            participants=[r["id"] for r in description["roles"]],
            events=[e["id"] for e in description["events"][:200]],
        ),
    )


class LogQuerySession:
    def __init__(self, timeline):
        self.timeline = timeline
        self.contract = timeline.export().get("analysis") or project(timeline)
        self.session = validate_contract(self.contract)
        self.translator = QuestionTranslator(self.contract)
        self.event_ids = {e["id"] for e in timeline.describe()["events"]}

    def query(self, source):
        result = self.session.query(source)
        parsed, _ = read_query(self.contract["binding"], source)
        labels = []
        for variable in result["columns"]:
            fields = list(
                dict.fromkeys(
                    atom["predicate"]
                    + "."
                    + self.contract["binding"]["predicates"][atom["predicate"]]["args"][
                        i
                    ]
                    for atom in parsed[0]["body"]
                    if not atom.get("negative")
                    for i, term in enumerate(atom["args"])
                    if term == variable
                )
            )
            labels.append(" / ".join(fields) or variable)
        references = sorted(
            {cell for row in result["rows"] for cell in row if cell in self.event_ids}
        )
        answer = dict(
            status="answered",
            query=source,
            **result,
            rowCount=len(result["rows"]),
            columnLabels=labels,
            eventIds=references,
            trajectoryId=self.timeline.identity,
            scope=self.contract["scope"],
            validation="Read-only syntax, declared schema and bounded execution. Event references are returned values, not a proof tree; empty rows do not establish global policy satisfaction.",
        )

        answer["answer"] = render_answer(answer)
        return answer

    def translate(self, question, generate, record=lambda row: None):
        return dict(
            self.translator.translate(question, generate, record),
            trajectoryId=self.timeline.identity,
        )

    def prepare(self, template_id, parameters):
        plan = self.translator.compile(template_id, parameters)
        return dict(
            plan, question=plan["interpretation"], trajectoryId=self.timeline.identity
        )

    def answer(self, plan):
        if plan.get("trajectoryId") != self.timeline.identity:
            raise ValueError("Question belongs to another trajectory.")
        if plan["status"] != "ready":
            return plan
        template = None
        if "templateId" in plan:
            compiled = self.translator.compile(plan["templateId"], plan["parameters"])
            if compiled["query"] != plan["query"]:
                raise ValueError("Compiled template query changed.")
            template = self.translator.templates[plan["templateId"]]
        result = self.query(plan["query"])
        result.update(question=plan["question"], interpretation=plan["interpretation"])
        if template:
            result.update(templateId=plan["templateId"], parameters=plan["parameters"])
        result["answer"] = render_answer(
            result, template=template, question=plan["question"]
        )
        return result

    def ask(self, question, generate, record=lambda row: None):
        return self.answer(self.translate(question, generate, record))
