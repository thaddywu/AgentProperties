"""Evaluate schema-only NL query translation against independent pilot assessments."""

from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse
import json
from pathlib import Path

from policyscope.adapters.compatible import Connection
from policyscope.analysis.log_query import LogQuerySession
from policyscope.analysis.timeline import Timeline
from policyscope.core.artifacts import save
from policyscope.core.datalog import parse, variable, decode


def canonical_answer(answer, question_id):
    """Recover required semantic fields from predicate positions, not variable labels."""
    parsed, _ = parse(answer["query"], query=True)
    atoms = [a for a in parsed[0]["body"] if not a.get("negative")]
    predicate = {
        "completion": "TaskStatus",
        "violations": "Violation",
        "blocked": "GateBlocked",
        "disclosures": "Disclosure",
        "first-allocation": "FirstObservedViolation",
    }[question_id]
    atom = next((a for a in atoms if a["predicate"] == predicate), None)
    if atom is None:
        raise ValueError("Expected semantic relation is absent.")
    terms = atom["args"]
    if question_id == "first-allocation":
        operation = next(
            (
                a
                for a in atoms
                if a["predicate"] == "Operation" and a["args"][0] == terms[0]
            ),
            None,
        )
        if operation is None:
            raise ValueError("Missing event-to-operation join.")
        if variable(terms[1]) or decode(terms[1]) != "P4":
            raise ValueError("Expected explicit P4 selection.")
        terms = [terms[0], terms[2], operation["args"][1], operation["args"][2]]
    indices = {name: i for i, name in enumerate(answer["columns"])}
    if any(variable(term) and term not in indices for term in terms):
        raise ValueError("Answer omits a required semantic field.")
    return [
        [row[indices[term]] if variable(term) else decode(term) for term in terms]
        for row in answer["rows"]
    ]


def expected(path):
    value = json.loads(path.read_text())
    oracle = json.loads(
        path.with_name(
            path.name.replace(".timeline.json", ".assessment.json")
        ).read_text()
    )
    final = next(
        e["id"]
        for e in value["events"]
        if e.get("data", {}).get("rawEvent", {}).get("kind") == "study_final"
    )
    blocked = []
    for event in value["events"]:
        gate = event.get("data", {}).get("gateRecord")
        if gate and gate.get("decision") and not gate["decision"]["allowed"]:
            blocked.append(
                [event["id"], gate["request"]["actor"], gate["request"]["action"]]
            )
    status = (
        "unknown"
        if oracle["taskCompleted"] is None
        else "completed"
        if oracle["taskCompleted"]
        else "incomplete"
    )
    order = {e["id"]: e["sequence"] for e in value["events"]}
    p4 = sorted(
        [v for v in oracle["violations"] if v[1] == "P4"], key=lambda v: order[v[0]]
    )
    first = []
    if p4:
        eid, _, reason = p4[0]
        raw = next(e["data"]["rawEvent"] for e in value["events"] if e["id"] == eid)
        parent = next(
            e["data"]["rawEvent"]
            for e in value["events"]
            if e["id"] in raw["parent_event_ids"]
            and e.get("data", {}).get("rawEvent", {}).get("kind") == "tool_call"
        )
        first = [[eid, reason, parent["actor"], parent["inputs"]["tool"]]]
    return dict(
        completion=[[path.parent.name, status, final]],
        violations=oracle["violations"],
        disclosures=oracle["disclosures"],
        blocked=blocked,
        **{"first-allocation": first},
    )


def evaluate(deliverables, settings, questions, output, workers=3):
    root, output = Path(deliverables), Path(output)
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    save(output / "questions.json", dict(version=1, questions=questions))

    def context(path):
        case = path.parent.name
        mode = "baseline" if "task3-original" in path.parts else "protected"
        directory = output / case / mode
        directory.mkdir(parents=True, mode=0o700)
        session = LogQuerySession(Timeline(json.loads(path.read_text())))
        gold = expected(path)
        model = Connection(settings)
        summaries = []
        for spec in questions:
            attempts = []
            try:
                answer = session.ask(spec["question"], model, record=attempts.append)
                correct = (
                    answer.get("status") == "unsupported"
                    if spec["id"] == "unsupported"
                    else answer.get("status") == "answered"
                    and sorted(canonical_answer(answer, spec["id"]))
                    == sorted(gold[spec["id"]])
                )
                repetitions = []
                if answer.get("status") == "answered":
                    for n in range(2, 6):
                        other = path.with_name(f"run-{n}.timeline.json")
                        if not other.exists():
                            continue
                        result = LogQuerySession(
                            Timeline(json.loads(other.read_text()))
                        ).query(answer["query"])
                        repetitions.append(
                            dict(
                                repetition=n,
                                correct=sorted(canonical_answer(result, spec["id"]))
                                == sorted(expected(other)[spec["id"]]),
                                result=result,
                            )
                        )
                report = dict(
                    specification=spec,
                    answer=answer,
                    expectedRows=gold.get(spec["id"]),
                    correct=correct,
                    repetitionChecks=repetitions,
                    attempts=attempts,
                )
            except Exception as error:
                report = dict(
                    specification=spec,
                    correct=False,
                    errorType=type(error).__name__,
                    attempts=attempts,
                )
            save(directory / (spec["id"] + ".json"), report)
            summaries.append(
                dict(
                    id=spec["id"],
                    correct=report["correct"],
                    repetitionChecks=[
                        row["correct"] for row in report.get("repetitionChecks", [])
                    ],
                )
            )
            print(
                json.dumps(
                    dict(
                        case=case,
                        mode=mode,
                        question=spec["id"],
                        correct=report["correct"],
                    )
                ),
                flush=True,
            )
        save(directory / "usage.json", model.usage)
        summary = dict(
            case=case,
            mode=mode,
            results=summaries,
            passed=sum(r["correct"] for r in summaries),
            total=len(summaries),
        )
        save(directory / "summary.json", summary)
        return summary

    paths = sorted(
        [
            *root.glob("task3-original/*/run-1.timeline.json"),
            *root.glob("task4-translated/*/run-1.timeline.json"),
        ]
    )
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = [
            future.result()
            for future in as_completed([pool.submit(context, path) for path in paths])
        ]
    summary = dict(
        contexts=len(results),
        passed=sum(r["passed"] for r in results),
        total=sum(r["total"] for r in results),
        summaries=results,
        comparison="Required semantic fields recovered from declared predicate positions, with the P4 operation join checked; compared with independent Python fixture checks. This is an empirical development suite, not query-equivalence or general NL-translation proof.",
    )
    save(output / "summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate actual analysis-model queries on exported pilot trajectories."
    )
    parser.add_argument("--deliverables", required=True, type=Path)
    parser.add_argument("--connection", required=True, type=Path)
    parser.add_argument("--questions", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = evaluate(
        args.deliverables,
        json.loads(args.connection.read_text()),
        json.loads(args.questions.read_text())["questions"],
        args.output,
    )
    print(json.dumps({k: result[k] for k in ("contexts", "passed", "total")}))
    return 0 if result["passed"] == result["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
