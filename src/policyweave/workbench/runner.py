"""Trusted student-runner helper; execution and completion criteria stay app-owned."""

from contextlib import ExitStack
import json
from pathlib import Path
import re

from policyweave.core.artifacts import artifact_text, save
from policyweave.enforcement.recording import capture_trajectories
from policyweave.enforcement.telemetry import record_execution


def case_names(cases):
    """Validate scenario identifiers before using them as directory names."""
    names = list(cases)
    if (not names or any(not isinstance(name, str)
                        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", name)
                        or name in {".", ".."} for name in names)
            or len(set(names)) != len(names)):
        raise ValueError("Provide distinct, bounded scenario IDs.")
    return names


def summarize(output):
    """Count all current result files, one sample per file, for each app side."""
    root = Path(output)
    summary = {side: dict(completed=0, total=0) for side in ("original", "ported")}
    for side, counts in summary.items():
        for path in root.glob(f"*/{side}/sample-*/result.json"):
            if not re.fullmatch(r"sample-[1-9][0-9]*", path.parent.name):
                continue
            value = json.loads(artifact_text(root, path.relative_to(root)))
            if (not isinstance(value, dict) or set(value) != {"task_complete"}
                    or type(value["task_complete"]) is not bool):
                raise ValueError("Run results must contain only a Boolean task_complete.")
            counts["total"] += 1
            counts["completed"] += value["task_complete"]
    return summary


def print_summary(output):
    for side, counts in summarize(output).items():
        print(f"Until now, {side} app: {counts['completed']}/{counts['total']} runs completed the task.")


def run_case(execute, assess, *, side, case, sample=1, output="results"):
    """Run one app episode and assess actual effects with app-owned callbacks.

    execute(side, case, sample, output_dir) owns selection, reset and invocation.
    output_dir is the absolute per-run Path for intermediate files and app output.
    assess(result) returns a bool indicating whether the task completed.
    Child processes need their own instrumentation and export integration.
    """
    if side not in {"original", "ported"}:
        raise ValueError("Choose original or ported.")
    case_names([case])
    if type(sample) is not int or sample < 1:
        raise ValueError("Sample must be a positive integer.")
    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory = root / case / side / ("sample-" + str(sample))
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    record = dict(version=1, side=side, case=case, sample=sample,
                  executionStatus="failed", taskCompleteness=None, trajectories=[])
    trace, recordings = None, []
    try:
        with ExitStack() as stack:
            if side == "ported":
                trace = stack.enter_context(record_execution(case))
                trace.participant("PolicyWeave", kind="runtime")
                trace.event("state", "PolicyWeave", data=dict(observation="run_start", case=case, side=side, sample=sample))
                recordings = stack.enter_context(capture_trajectories())
            result = execute(side, case, sample, directory)
        assessment = assess(result)
        if type(assessment) is not bool:
            raise ValueError("Completion assessment must return a Boolean.")
        record["taskCompleteness"] = assessment
        if side == "ported" and not recordings:
            raise ValueError("Ported run captured no policy gates.")
        record["executionStatus"] = "completed"
    except Exception as error:
        # Arbitrary app exception strings may contain credentials.
        record["errorType"] = type(error).__name__
    finally:
        try:
            if trace is not None:
                trace.event("state", "PolicyWeave", data=dict(observation="run_end", executionStatus=record["executionStatus"], taskCompleteness=record["taskCompleteness"], errorType=record.get("errorType")))
                trace.export(directory)
                record["trajectories"].extend(["trajectory.jsonl", "trajectory.json"])
            for index, recorder in enumerate(recordings):
                name = f"gate-{index + 1}.json"
                value = recorder.export()
                save(directory / name, value)
                record["trajectories"].append(name)
        except Exception as error:
            record.update(executionStatus="failed", errorType=type(error).__name__)
        save(directory / "run.json", record)
        save(directory / "result.json", dict(task_complete=record["taskCompleteness"] is True))
    return record


def main(execute, assess, *, cases, argv=None):
    """Shared CLI; students provide only scenario execution and actual-effect checks."""
    import argparse

    names = case_names(cases)
    parser = argparse.ArgumentParser(description="Run application scenarios and completion checks.")
    parser.add_argument("--case", choices=names)
    parser.add_argument("--side", choices=["original", "ported"], required=True)
    parser.add_argument("--output_dir", "--output-dir", default="runs")
    parser.add_argument("--sample", type=int, default=1)
    args = parser.parse_args(argv)
    if args.sample < 1:
        parser.error("--sample must be a positive repetition count.")
    records = [
        run_case(execute, assess, side=args.side, case=case, sample=sample, output=args.output_dir)
        for case in ([args.case] if args.case else names)
        for sample in range(1, args.sample + 1)
    ]
    try:
        print_summary(args.output_dir)
    except (OSError, ValueError):
        parser.exit(1, "Cannot summarize saved runs; check result.json files.\n")
    return int(any(record["executionStatus"] != "completed"
                   or record["taskCompleteness"] is not True
                   for record in records))
