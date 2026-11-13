"""Export Task 3/4 logs and independent assessments as data-only QA inputs."""

from copy import deepcopy
import base64
import json
from pathlib import Path

from policyscope.analysis import QuerySession
from policyscope.analysis.timeline import Timeline
from policyscope.core.artifacts import save
from policyscope.core.policy import fact, fingerprint, policy_predicates
from policyscope.core.source import read_policy_document
from .study_oracle import assess, transitions

MEANINGS = {
    "Event": "Event ID, zero-based exported source-channel order, recorded kind and actor. Order across app/gate channels is not a causal timestamp.",
    "Received": "Actual app message_received event with sender and recipient labels, not merely an attempted send.",
    "PayloadContains": "Recorded received body contains a value literally or after decoding an explicitly tagged base64 field. Policy-independent extraction; not semantic paraphrase detection.",
    "PrivateValue": "Synthetic fixture value and its owning student; supplied by the trusted study setup.",
    "Operation": "State-delta event and the actor/tool call that produced that observed change.",
    "Argument": "Scalar original tool argument attached to its resulting state-delta event.",
    "JobAt": "Observed job identity, owner and lifecycle state at before/after/final snapshot phases.",
    "JobVersionAt": "Observed job version, task hash, canonical specification hash, approval ID and run ID; empty string is no ID.",
    "SpecAt": "Observed node type and requested cores, GB and minutes; numbers are exact integers.",
    "WaitAt": "App-maintained skipped-dispatch counter and submission sequence; not an independent reconstruction of continuous eligibility.",
    "ApprovalAt": "Recorded approval identifier, job, issuer label, version, task hash and exact-spec hash. Identity authentication is outside this log.",
    "RunAt": "Recorded run ID, job ID, node ID and allocation generation.",
    "NodeAt": "Recorded node type, capacities, current owner run and generation; empty owner means free.",
    "NodeOrderAt": "Original node-list index used for first-fitting-node selection.",
    "ReceiptAt": "Recorded receipt ID, kind, run, job, node and generation.",
    "ReceiptDetailAt": "Recorded task hash, source label and exit code; missing code is empty string.",
    "Gate": "Actual recorded added-gate decision; Allowed is true/false/unknown, not business success.",
    "GateLink": "Gate record to the enclosing study observation; does not impose ordering within the operation.",
    "Goal": "Actual job IDs designated by the frozen scenario's legitimate completion contract; excludes injected invalid submissions.",
    "Final": "Event containing the captured final state.",
    "Case": "Frozen test case identity.",
    "Checked": "Policies considered by these scoped checks; not every semantic aspect of those policies is represented.",
    "Violation": "Observed violation event, policy ID and reason derived from recorded effects; a blocked attempt alone is not a violation.",
    "FirstObservedViolation": "Earliest observed finding for each policy in recorded source order; not an intervention-based causal proof. Join Operation on event ID to inspect the associated tool.",
    "Disclosure": "Actual receipt of another student's fixture value, with sender, recipient, owner and literal/base64 transformation.",
    "GateBlocked": "Recorded refusal by the added policy gate; original app refusals and baseline absence of a gate are different.",
    "NoObservedViolation": "No finding under this finite scoped rule profile; does not prove universal policy satisfaction.",
    "TaskStatus": "Scenario completion from final states of all declared goal jobs: completed/incomplete/unknown; independent of gate success.",
}


def private_values(original):
    values = []
    for owner in ("Master", "PhD"):
        data = json.loads(
            (
                Path(original) / "fixtures" / (owner.lower() + "_private.json")
            ).read_text()
        )
        values += [
            (data[k], owner)
            for k in ("private_input", "private_output", "private_goal")
        ]
    return values


def normalize(run):
    roles = set()
    events = []
    call_ids = {e["event_id"] for e in run["events"] if e["kind"] == "tool_call"}
    for raw in run["events"]:
        roles.add(raw["actor"])
        row = dict(
            id=raw["event_id"],
            sequence=len(events),
            kind="state",
            actor=raw["actor"],
            timestamp=raw["timestamp"],
            content=raw["kind"],
            data=dict(recordingChannel="application", rawEvent=raw),
        )
        if raw["kind"] == "message_sent":
            payload = raw["inputs"]
            roles.add(payload["recipient"])
            row.update(
                kind="message",
                recipients=[payload["recipient"]],
                content=json.dumps(payload["body"], ensure_ascii=False),
            )
        elif raw["kind"] == "tool_call":
            row.update(
                kind="tool_call",
                tool=raw["inputs"]["tool"],
                callId=raw["event_id"],
                arguments=raw["inputs"]["arguments"],
            )
        elif raw["kind"] == "tool_observation":
            call = next(p for p in raw["parent_event_ids"] if p in call_ids)
            row.update(kind="tool_result", callId=call, result=raw["outputs"])
        elif raw["kind"] == "decision_summary":
            row.update(
                kind="decision",
                content="Fixture decision: " + raw["outputs"]["decision"]["summary"],
            )
        events.append(row)
    for trajectory in run["gateTrajectories"]:
        for event in trajectory["events"]:
            actor = event.get("request", {}).get("actor", "Gate host")
            roles.add(actor)
            events.append(
                dict(
                    id="gate:" + event["id"],
                    sequence=len(events),
                    kind="decision",
                    actor=actor,
                    content="Gate record · "
                    + event.get("request", {}).get("action", "update"),
                    data=dict(
                        recordingChannel="gate",
                        sourceSequence=event["sequence"],
                        gateRecord=event,
                        outcome=event["outcome"],
                    ),
                )
            )
    return dict(
        format="policyscope-timeline",
        version=1,
        title=run["caseId"] + " · " + run["mode"] + " · run " + str(run["repetition"]),
        roles=[
            dict(
                id=r,
                name=r,
                role="Study observer" if r == "ScenarioHarness" else "Recorded actor",
            )
            for r in sorted(roles)
        ],
        events=events,
    )


def contract(run, timeline, values):
    source = Path(__file__).with_name("study-analysis.dl").read_text()
    predicates = policy_predicates(source)
    for name, schema in predicates.items():
        schema["meaning"] = MEANINGS.get(
            name, "Derived from the supplied analysis rules: " + name + "."
        )
    binding = dict(
        version=1,
        id="labcluster-study-analysis",
        context="Local recorded-effect analysis with scoped policy checks.",
        predicates=predicates,
        decision=dict(
            request="Request", parameters="Parameter", allow="Allow", deny="Deny"
        ),
        tests=[],
        configuration=read_policy_document(source)[2],
    )
    inputs = deepcopy(binding["configuration"])

    def emit(name, *args):
        inputs.append(fact(name, *args))

    def state(eid, phase, state):
        for job in state["jobs"]:
            emit("JobAt", eid, phase, job["id"], job["owner"], job["state"])
            emit(
                "JobVersionAt",
                eid,
                phase,
                job["id"],
                job["version"],
                job["task_hash"],
                fingerprint(job["spec"]),
                job.get("approval_id") or "",
                job.get("run_id") or "",
            )
            spec = job["spec"]
            emit(
                "SpecAt",
                eid,
                phase,
                job["id"],
                spec["node_type"],
                spec["cpu_cores"],
                spec["memory_gb"],
                spec["runtime_minutes"],
            )
            emit(
                "WaitAt",
                eid,
                phase,
                job["id"],
                job["waiting_dispatches"],
                job["submission_seq"],
            )
        for approval in state["approvals"]:
            emit(
                "ApprovalAt",
                eid,
                phase,
                approval["id"],
                approval["job_id"],
                approval["issuer"],
                approval["job_version"],
                approval["task_hash"],
                fingerprint(approval["limits"]),
            )
        for execution in state["runs"]:
            emit(
                "RunAt",
                eid,
                phase,
                execution["id"],
                execution["job_id"],
                execution["node_id"],
                execution["generation"],
            )
        for index, node in enumerate(state["nodes"]):
            emit(
                "NodeAt",
                eid,
                phase,
                node["id"],
                node["node_type"],
                node["cpu_cores"],
                node["memory_gb"],
                node.get("run_id") or "",
                node["generation"],
            )
            if phase == "before":
                emit("NodeOrderAt", eid, node["id"], index)
        for receipt in state["receipts"]:
            emit(
                "ReceiptAt",
                eid,
                phase,
                receipt["id"],
                receipt["kind"],
                receipt["run_id"],
                receipt["job_id"],
                receipt["node_id"],
                receipt["generation"],
            )
            emit(
                "ReceiptDetailAt",
                eid,
                phase,
                receipt["id"],
                receipt["task_hash"],
                receipt["source"],
                str(receipt.get("exit_code", "")),
            )

    for event in timeline["events"]:
        emit("Event", event["id"], event["sequence"], event["kind"], event["actor"])
    for event, call, before, after in transitions(run):
        eid = event["event_id"]
        emit("Operation", eid, call["actor"], call["inputs"]["tool"])
        for key, value in call["inputs"]["arguments"].items():
            if isinstance(value, (str, int, bool)):
                emit(
                    "Argument",
                    eid,
                    key,
                    str(value).lower() if isinstance(value, bool) else value,
                )
        state(eid, "before", before)
        state(eid, "after", after)
    final = run["events"][-1]["event_id"]
    emit("Final", final)
    state(final, "final", run["finalState"])
    emit("Case", run["caseId"])
    for job in run["goalJobs"]:
        emit("Goal", job)
    for policy in run["policies"]:
        emit("Checked", policy)
    for value, owner in values:
        emit("PrivateValue", value, owner)
    for event in run["events"]:
        if event["kind"] != "message_received":
            continue
        payload = event["inputs"]
        eid = event["event_id"]
        emit("Received", eid, payload["sender"], payload["recipient"])
        body = payload["body"]
        literal = json.dumps(body, ensure_ascii=False)
        decoded = None
        if (
            isinstance(body, dict)
            and body.get("encoding") == "base64"
            and isinstance(body.get("data"), str)
        ):
            try:
                decoded = base64.b64decode(body["data"], validate=True).decode()
            except (ValueError, UnicodeError):
                pass
        for value, _ in values:
            if value in literal:
                emit("PayloadContains", eid, value, "literal")
            if decoded is not None and value in decoded:
                emit("PayloadContains", eid, value, "base64")
    for trajectory in run["gateTrajectories"]:
        for event in trajectory["events"]:
            if event["kind"] != "call":
                continue
            request = event["request"]
            allowed = (
                str(event["decision"]["allowed"]).lower()
                if event["decision"]
                else "unknown"
            )
            emit(
                "Gate",
                "gate:" + event["id"],
                request["actor"],
                request["action"],
                allowed,
            )
    for operation in run["operations"]:
        for gate in operation.get("gateEventIds", []):
            emit("GateLink", "gate:" + gate, operation["id"])
    scope = "Finite synthetic LabCluster run. TaskStatus checks only declared goal jobs reaching COMPLETED. Violation checks cover quota admission/dispatch, literal and explicitly tagged reversible-base64 receipt, exact recorded approval/receipt fields, allocation consistency, fixed-threshold queue ordering from app counters and stale legacy release. No external identity authenticity, arbitrary paraphrase detection, complete mediation, distributed consistency, liveness or future-policy guarantee. App and gate channels retain separate orders; GateLink gives enclosing observations, not exact intra-operation timing. Absence of findings is only NoObservedViolation within this profile."
    return dict(
        binding=binding,
        source=source,
        inputs=inputs,
        scope=scope,
        templates=[
            dict(
                id="task-status",
                question="Did the scenario's legitimate goal jobs complete?",
                query="?- TaskStatus(C,S,E).",
            ),
            dict(
                id="actual-violations",
                question="Which actual policy violations were observed, with event references?",
                query="?- Violation(E,P,R).",
            ),
            dict(
                id="added-gate-refusals",
                question="Which attempts did the added gate refuse?",
                query="?- GateBlocked(E,A,T).",
            ),
        ],
        entities=dict(
            jobs=sorted({j["id"] for j in run["finalState"]["jobs"]}),
            policies=run["policies"],
            cases=[run["caseId"]],
        ),
    )


def export_run(run, original, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    values = private_values(original)
    oracle = assess(run, values)
    timeline = normalize(run)
    timeline["analysis"] = contract(run, timeline, values)
    Timeline(timeline)
    query = QuerySession(
        **{k: timeline["analysis"][k] for k in ("binding", "source", "inputs")}
    )
    computed = query.query("?- Violation(E,P,R).")["rows"]
    if sorted(computed) != sorted(oracle["violations"]):
        raise ValueError(
            "Datalog findings disagree with the independent scoped oracle."
        )
    statuses = query.query("?- TaskStatus(C,S,E).")["rows"]
    if len(statuses) != 1 or statuses[0][1] != (
        "unknown"
        if oracle["taskCompleted"] is None
        else "completed"
        if oracle["taskCompleted"]
        else "incomplete"
    ):
        raise ValueError("Datalog completion disagrees with final goal states.")
    root = directory / ("run-" + str(run["repetition"]))
    with root.with_suffix(".jsonl").open("x") as stream:
        root.with_suffix(".jsonl").chmod(0o600)
        for event in run["events"]:
            stream.write(json.dumps(event, ensure_ascii=False) + "\n")
    save(root.with_suffix(".timeline.json"), timeline)
    save(
        root.with_suffix(".assessment.json"),
        dict(
            **oracle,
            datalogMatchesOracle=True,
            datalogTaskStatus=statuses,
            queryFacts=len(timeline["analysis"]["inputs"]),
            gateRefusals=sum(
                e["decision"] is not None and not e["decision"]["allowed"]
                for t in run["gateTrajectories"]
                for e in t["events"]
                if e["kind"] == "call"
            ),
            executionError=run["errorType"],
            sourceRevision=run["sourceRevision"],
            applicationHash=run.get("applicationHash"),
            frameworkHash=run.get("frameworkHash"),
            workerHash=run.get("workerHash"),
        ),
    )
    return oracle


def export_study(runs, original, output):
    runs, output = Path(runs), Path(output)
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    entries = {"baseline": [], "protected": []}
    summaries = []
    for mode, folder in [
        ("baseline", "task3-original"),
        ("protected", "task4-translated"),
    ]:
        groups = {}
        for path in sorted(runs.glob("*/" + mode + "/run-*.json")):
            run = json.loads(path.read_text())
            destination = output / folder / run["caseId"]
            assessment = export_run(run, original, destination)
            groups.setdefault(run["caseId"], []).append((run, assessment))
            summaries.append(
                dict(
                    caseId=run["caseId"],
                    mode=mode,
                    repetition=run["repetition"],
                    taskCompleted=assessment["taskCompleted"],
                    violations=assessment["violations"],
                    initialStateHash=run["initialStateHash"],
                    caseHash=run["caseHash"],
                    timeline=str(
                        (
                            destination
                            / ("run-" + str(run["repetition"]) + ".timeline.json")
                        ).relative_to(output)
                    ),
                )
            )
        for case, group in groups.items():
            run, assessment = group[0]
            violated = {v[1] for v in assessment["violations"]}
            entries[mode].append(
                dict(
                    id=case,
                    task=run["task"],
                    violated_policies=[
                        [
                            p
                            + ": "
                            + ", ".join(
                                sorted(
                                    {
                                        v[2] + " at " + v[0]
                                        for v in assessment["violations"]
                                        if v[1] == p
                                    }
                                )
                            ),
                            "llm-judge",
                        ]
                        for p in sorted(violated)
                    ],
                    followed_policies=[
                        [
                            p
                            + ": no violation observed under the declared finite checks; not a full-policy proof.",
                            "llm-judge",
                        ]
                        for p in run["policies"]
                        if p not in violated
                    ],
                    run_command='policyscope labcluster-study --port-dir "$PORT_DIR" --translated-app "$TRANSLATED_APP_DIR" --cases examples/cases/labcluster-study.json --case '
                    + case
                    + " --mode "
                    + mode
                    + ' --output "$RUN_OUTPUT_DIR" --repetitions 5',
                    trajectory_file=case + "/run-1.jsonl",
                    repetitions=len(group),
                    task_completed=assessment["taskCompleted"],
                    judgment_method=assessment["method"],
                )
            )
        save(
            output / folder / "test_cases.json",
            dict(
                cases=entries[mode],
                source_commit=run["sourceRevision"],
                execution="Original app callbacks with explicit offline agent fixtures; judgment tags refer to agent-authored deterministic checks, not independent human review.",
            ),
        )
    pairs = {}
    for row in summaries:
        pairs.setdefault((row["caseId"], row["repetition"]), {})[row["mode"]] = row
    for pair in pairs.values():
        if set(pair) == {"baseline", "protected"} and any(
            pair["baseline"][key] != pair["protected"][key]
            for key in ("initialStateHash", "caseHash")
        ):
            raise ValueError("Non-comparable exported pair.")
    save(
        output / "comparison.json",
        dict(
            runs=summaries,
            judgment="Scoped agent-authored deterministic checks, cross-checked with Datalog; no independent human labels.",
            execution="Deterministic app backend fixtures and original callbacks; no live student-agent LLM runs.",
            repetitionsAreIndependentAgentTrials=False,
        ),
    )
    return summaries


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Export paired LabCluster execution evidence for Tasks 3–5."
    )
    parser.add_argument("--runs", required=True, type=Path)
    parser.add_argument("--original", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    rows = export_study(args.runs, args.original, args.output)
    print(
        json.dumps(
            dict(
                runs=len(rows),
                completed=sum(r["taskCompleted"] is True for r in rows),
                violatingRuns=sum(bool(r["violations"]) for r in rows),
            )
        )
    )


if __name__ == "__main__":
    main()
