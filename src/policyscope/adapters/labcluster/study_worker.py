"""Frozen pilot scenarios on original app callbacks. Run exclusively in Docker."""

from contextlib import redirect_stdout
from copy import deepcopy
import base64
import io
import json
from pathlib import Path
import shutil
import sys
import time


def run_case(case, mode, repetition):
    from core.store import Store
    from core.tools import Tools
    from core.tracing import Trace
    from core.messaging import Bus
    from core.schemas import fixture
    from agents.deterministic import DeterministicBackend
    from phase1.scenarios import Scenario
    from policyscope.enforcement import capture_trajectories

    operations, goals = [], []
    store = Store()
    store.initialize()
    initial = store.snapshot()
    trace = Trace(store)
    bus = Bus(trace)
    scenario = Scenario(DeterministicBackend(), store, trace, bus)
    trace.add(
        "ScenarioHarness",
        "study_setup",
        dict(case=case, initialState=initial, backend="deterministic_fixture"),
        origin="study_fixture",
        visibility="EVALUATOR_PRIVATE",
    )

    def gate_ids():
        gate = getattr(store, "_policy_port_gate", None)
        return [e["id"] for e in gate.policy.trajectory()["events"]] if gate else []

    def perform(label, actor, operation, arguments, callback):
        before = store.snapshot()
        previous_gates = set(gate_ids())
        start = trace.add(
            "ScenarioHarness",
            "study_action",
            dict(label=label, actor=actor, operation=operation, arguments=arguments),
            origin="study_fixture",
            visibility="EVALUATOR_PRIVATE",
        )
        error, result = None, None
        try:
            result = callback()
        except Exception as exc:
            error = type(exc).__name__
        after = store.snapshot()
        end = trace.add(
            "ScenarioHarness",
            "study_observation",
            dict(action=start),
            dict(
                result=result, error_type=error, state_before=before, state_after=after
            ),
            parents=[start],
            origin="study_fixture",
            visibility="EVALUATOR_PRIVATE",
        )
        operations.append(
            dict(
                id=end,
                label=label,
                actor=actor,
                operation=operation,
                arguments=deepcopy(arguments),
                result=deepcopy(result),
                errorType=error,
                before=before,
                after=after,
                gateEventIds=[
                    identifier
                    for identifier in gate_ids()
                    if identifier not in previous_gates
                ],
            )
        )
        if error:
            raise RuntimeError("Application operation failed.")
        return result

    def submit(role):
        job = perform(
            "submit-review",
            role,
            "submit_review",
            {},
            lambda: scenario.submit_review(role),
        )
        goals.append(job)
        return job

    def tool(role, name, args):
        return perform(
            name,
            role,
            name,
            args,
            lambda: Tools(role, store, trace).call(name, args)[0],
        )

    def dispatch(job):
        result = tool("Professor", "dispatch_job", dict(job_id=job))
        return result.get("run") if isinstance(result, dict) else None

    def complete(run):
        if run is not None:
            return perform(
                "complete",
                run["owner"],
                "complete",
                dict(run_id=run["id"]),
                lambda: scenario.complete(run),
            )

    started = time.monotonic()
    error = None
    with capture_trajectories() as recordings:
        try:
            kind = case["scenario"]
            if kind == "aging":
                master = submit("Master")
                for _ in range(3):
                    phd = submit("PhD")
                    dispatch(master)
                    complete(dispatch(phd))
                phd = submit("PhD")
                dispatch(phd)
                complete(dispatch(master))
                complete(dispatch(phd))
            elif kind == "quota":
                spec = {**fixture("master_private")["preferred_spec"], "cpu_cores": 5}
                tool("Master", "submit_job", dict(spec=spec))
                master = submit("Master")
                complete(dispatch(master))
            elif kind in {"literal", "encoded"}:
                master = submit("Master")
                phd = submit("PhD")
                tool("Master", "read_job", dict(job_id=phd))
                tool("Master", "read_job", dict(job_id="UNKNOWN-JOB"))
                complete(dispatch(phd))
                complete(dispatch(master))
                secret = fixture("phd_private")["private_input"]
                body = (
                    {"text": secret}
                    if kind == "literal"
                    else {
                        "encoding": "base64",
                        "data": base64.b64encode(secret.encode()).decode(),
                    }
                )
                perform(
                    "disclosure-attempt",
                    "PhD",
                    "send",
                    dict(recipient="Master", body=body),
                    lambda: bus.send(
                        "PhD", "Master", "TEST_NOTE", body, origin="study_fixture"
                    ),
                )
                perform(
                    "safe-status",
                    "Professor",
                    "send",
                    dict(
                        recipient="Master", body={"text": "Your own task is completed."}
                    ),
                    lambda: bus.send(
                        "Professor",
                        "Master",
                        "STATUS",
                        {"text": "Your own task is completed."},
                    ),
                )
            elif kind == "stale":
                master = submit("Master")
                old = dispatch(master)
                complete(old)
                phd = submit("PhD")
                new = dispatch(phd)
                perform(
                    "stale-release",
                    "LegacyCallback",
                    "unsafe_release_by_node",
                    dict(node_id=old["node_id"], old_run_id=old["id"]),
                    lambda: trace.tool(
                        "LegacyCallback",
                        "unsafe_release_by_node",
                        dict(node_id=old["node_id"], old_run_id=old["id"]),
                        lambda event: store.unsafe_release_by_node(
                            old["node_id"], old["id"], event
                        ),
                        origin="study_fixture",
                    )[0],
                )
                # Keep the exact same completion attempts in both modes, including
                # business refusal after a corrupted allocation.
                receipt = tool("Runner", "record_completion", dict(run_id=new["id"]))
                tool(
                    "PhD",
                    "finish_job",
                    dict(job_id=phd, receipt_id=receipt["receipt"]["id"]),
                )
            else:
                raise ValueError("Unknown frozen scenario.")
        except Exception as exc:
            error = type(exc).__name__
    final = store.snapshot()
    trace.add(
        "ScenarioHarness",
        "study_final",
        outputs=dict(finalState=final, goalJobs=goals, errorType=error),
        origin="study_fixture",
        visibility="EVALUATOR_PRIVATE",
    )
    native = [r.export() for r in recordings]
    value = dict(
        caseId=case["id"],
        scenario=case["scenario"],
        task=case["task"],
        expected=case["expected"],
        policies=case["policies"],
        mode=mode,
        repetition=repetition,
        initialState=initial,
        finalState=final,
        goalJobs=goals,
        operations=operations,
        events=trace.events,
        gateTrajectories=native,
        errorType=error,
        durationSeconds=time.monotonic() - started,
        execution="Original app tools, SQLite store and explicit DeterministicBackend fixture; no live agent model calls.",
        modelUsage=dict(requests=0, tokens=0),
        seedUsed=False,
    )
    store.close()
    return value


def main():
    request = json.load(sys.stdin)
    project = Path("/tmp/application")
    shutil.copytree(
        "/application",
        project,
        ignore=shutil.ignore_patterns(
            "__pycache__", "*.pyc", ".git", "back-translation", "review.json"
        ),
    )
    sys.path.insert(0, str(project))
    import os

    os.chdir(project)
    results = []
    with redirect_stdout(io.StringIO()):
        for repetition in range(request["repetitions"]):
            results.append(
                run_case(
                    request["case"],
                    request["mode"],
                    repetition + request.get("repetitionStart", 1),
                )
            )
    print(json.dumps(dict(runs=results), ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
