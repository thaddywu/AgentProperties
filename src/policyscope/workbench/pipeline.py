"""Compose all five modules; keep application code in the isolated port runner."""

import argparse
import json
from pathlib import Path
import uuid

from policyscope.analysis import TrajectorySession
from policyscope.core.artifacts import artifact_text, save
from policyscope.policy_adder.student import load_connection, run as add_policy
from policyscope.policy_viewer import review_units
from .student_review import BundleApplication


QUESTIONS = (
    "Summarize the recorded calls and their outcomes.",
    "Which calls were blocked, and were their callbacks invoked?",
    "Explain the decision for the first recorded call, distinguishing permission from business success.",
)


def analyze_publication(work, *, generate, questions=QUESTIONS):
    """Replay every recorded decision and ask bounded QA on a representative trace.

    This consumes private runner evidence, without importing the student app.
    Callers must separately validate the published bundle against that evidence.
    """
    work = Path(work)
    if not questions:
        raise ValueError("Provide at least one trajectory QA question.")
    checks = sorted(
        work.glob("publication-check-*.json"), key=lambda p: p.stat().st_mtime_ns
    )
    if not checks:
        raise ValueError("Published execution evidence is missing.")
    # Full fact snapshots expand in the private pretty-printed runner report.
    report = json.loads(
        artifact_text(work, checks[-1].name, max_bytes=64 * 1024 * 1024)
    )
    if (
        not report.get("passed")
        or not report.get("tests")
        or not report.get("nativeEngineCalls")
    ):
        raise ValueError("Published application needs passing native execution checks.")
    traces = report.get("policyTrajectories", [])
    if not report.get("trajectoryCoverage", {}).get("complete") or not traces:
        raise ValueError("Published execution needs complete captured gate evidence.")
    directory = work / "trajectory-analysis" / uuid.uuid4().hex[:12]
    directory.mkdir(mode=0o700, parents=True)
    verified = []
    outcomes = {}
    for index, trace in enumerate(traces):
        session = TrajectorySession(trace)
        verification = session.verify()
        if (
            verification["decisions"] and not verification["allMatched"]
        ) or verification["unresolvedEvents"]:
            raise ValueError("Recorded decisions did not replay completely.")
        save(directory / f"trajectory-{index}.json", trace)
        verified.append(verification)
        for event in trace["events"]:
            if event["kind"] == "call":
                outcome = event["outcome"]
                outcomes[outcome] = outcomes.get(outcome, 0) + 1
    save(directory / "replay.json", verified)
    if not any(v["decisions"] for v in verified):
        raise ValueError("No completed gate decision was recorded.")

    def score(trace):
        calls = [e for e in trace["events"] if e["kind"] == "call"]
        return (
            any(e["outcome"] == "blocked" for e in calls),
            any(e["outcome"] == "applied" for e in calls),
            len(calls),
        )

    selected = max(traces, key=score)
    session = TrajectorySession(selected)
    attempts, answers = [], []

    def recorded_generate(stage, prompt):
        response = generate(stage, prompt)
        attempts.append(dict(stage=stage, prompt=prompt, response=response))
        save(directory / "model-attempts.json", attempts)
        return response

    for index, question in enumerate(questions):
        answer = session.ask(question, recorded_generate)
        save(directory / f"answer-{index}.json", dict(answer, question=question))
        if "clarification" in answer:
            raise ValueError("QA requires clarification; inspect the retained answer.")
        answers.append(answer)
    return dict(
        tests=report["tests"],
        skipped=report.get("skipped", 0),
        nativeEngineCalls=report["nativeEngineCalls"],
        trajectories=len(traces),
        replayedDecisions=sum(v["decisions"] for v in verified),
        matchedDecisions=sum(v["matched"] for v in verified),
        outcomes=outcomes,
        qaQuestions=len(answers),
        qaTrajectoryId=session.identity["trajectoryId"],
        analysisDirectory=str(directory.relative_to(work)),
        scope=selected["scope"],
    )


def run(base, target, settings, *, work, generate=None, questions=QUESTIONS, **options):
    """Publish a port, validate its viewer bundle, then replay and question its logs."""
    work = Path(work).resolve()
    work.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    status = work.parent / (work.name + "-pipeline-status.json")
    stage = "prepare"

    def progress(name):
        nonlocal stage
        stage = name
        save(status, dict(stage=name, status="running"))

    try:
        target = add_policy(
            base, target, settings, work=work, progress=progress, **options
        )
        progress("policy-viewer")
        source = json.loads(artifact_text(work, "source.json"))
        application = BundleApplication(
            target / "back-translation", Path(base) / source["policy"]
        )
        reference = application.reference()
        units = review_units(reference)["units"]
        if not units or not reference["execution"]["procedures"]:
            raise ValueError("Viewer needs source units and independent descriptions.")
        progress("trajectory-qa")
        if generate is None:
            from policyscope.adapters.compatible import Connection

            generate = Connection(settings)
        summary = analyze_publication(work, generate=generate, questions=questions)
        summary.update(
            status="passed",
            modules=dict(
                policyAdder=True,
                backTranslation=True,
                policyViewer=True,
                enforcement=True,
                trajectoryQA=True,
            ),
            sourceSentences=len(units),
            executionProcedures=len(reference["execution"]["procedures"]),
            reuse=bool(options.get("reuse")),
            validation="Execution checks and recorded decision replay; model descriptions and QA prose are not semantic proofs.",
        )
        save(work / "pipeline-summary.json", summary)
        save(work / summary["analysisDirectory"] / "summary.json", summary)
        save(
            work / summary["analysisDirectory"] / "usage.json",
            getattr(generate, "usage", []),
        )
        save(status, dict(stage="complete", status="passed"))
        return summary
    except Exception as error:
        # Detailed exception text may contain private endpoint or application data.
        save(status, dict(stage=stage, status="failed", errorType=type(error).__name__))
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Run all five policy modules on one application."
    )
    parser.add_argument("base_app_dir", type=Path)
    parser.add_argument("enforced_app_dir", type=Path)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--connection", required=True, type=Path)
    parser.add_argument("--policy", default="policy.md")
    parser.add_argument("--app-doc", default="app.md")
    parser.add_argument("--image", default="policy-portin:batch-v1")
    parser.add_argument("--codex", default="codex")
    parser.add_argument("--repairs", type=int, default=2)
    parser.add_argument(
        "--reuse-port",
        action="store_true",
        help="Use completed forward/reverse artifacts in --work-dir; recheck publication.",
    )
    parser.add_argument(
        "--question", action="append", help="Repeat for custom trajectory questions."
    )
    args = parser.parse_args()
    result = run(
        args.base_app_dir,
        args.enforced_app_dir,
        load_connection(args.connection),
        work=args.work_dir,
        reuse=args.work_dir if args.reuse_port else None,
        policy=args.policy,
        app_doc=args.app_doc,
        image=args.image,
        codex=args.codex,
        repairs=args.repairs,
        questions=args.question or QUESTIONS,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
