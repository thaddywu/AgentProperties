"""Credential-free, no-network batch check entry point; run only in Docker."""

import contextlib
import io
import json
from pathlib import Path
import shutil
import sys
import traceback
import unittest


def native_engine_guard(boundaries=(), project=None):
    """Reject accidental test doubles for the actual policy decision engine.

    This is a verification guard, not a sandbox against malicious Python tests.
    Docker remains the isolation boundary.
    """
    import contextvars
    import functools
    import itertools
    import types
    import threading
    import policyweave.core.datalog as datalog
    import policyweave.core.policy as policy
    import policyweave.enforcement.api as api
    import policyweave.enforcement.runtime as runtime

    original = datalog.Souffle
    counts = {"calls": 0, "boundaryCalls": {}, "boundaryActions": {}, "boundaryExecutions": {}}
    targets = {}  # one symbol may carry several inventory ids
    for row in boundaries if project else ():
        targets.setdefault((str((project / row["file"]).resolve()), row["symbol"]), []).append(row["id"])
    awaiting = contextvars.ContextVar("frames_awaiting_acall", default=())
    previous_profile, previous_thread_profile = sys.getprofile(), threading.getprofile()

    def profiler(previous):
        def profile(frame, event, arg):
            if event == "call":
                code = frame.f_code
                for name in targets.get((code.co_filename, code.co_qualname.replace(".<locals>.", ".")), ()):
                    counts["boundaryExecutions"][name] = counts["boundaryExecutions"].get(name, 0) + 1
            if previous:
                previous(frame, event, arg)
        return profile

    def unwrapped(value):
        """Codes of a local function or bound method and its functools.wraps chain."""
        for _ in range(8):
            if type(value) is functools.partial:
                value = value.func
            if type(value) is types.MethodType:  # type(), not isinstance: never run a local's __class__
                value = value.__func__
            if type(value) is not types.FunctionType:
                return
            yield value.__code__
            value = value.__dict__.get("__wrapped__")

    def stack(frame):
        while frame is not None:
            yield frame
            frame = frame.f_back

    class EngineMeta(type):
        def __setattr__(cls, name, value):
            if name == "evaluate":
                raise RuntimeError(
                    "Port tests must execute native Souffle; evaluator replacement is forbidden."
                )
            super().__setattr__(name, value)

        def __delattr__(cls, name):
            if name == "evaluate":
                raise RuntimeError("Native evaluator replacement is forbidden.")
            super().__delattr__(name)

    class NativeEngine(original, metaclass=EngineMeta):
        def evaluate(self, inputs, rules):
            counts["calls"] += 1
            caller, reached = sys._getframe(1), set()
            # Policy.acall decides in a worker thread; its caller's frames are in `awaiting`.
            for frame in itertools.chain(stack(caller), awaiting.get()) if targets else ():
                codes = [frame.f_code]
                # @policy checks before entering its original body, and a policy_port wrapper
                # decides before running it: the original is a local (any name) of those frames.
                annotation = frame.f_code.co_filename.endswith("/policyweave/enforcement/api.py") and frame.f_code.co_name == "checked"
                adapter = project and Path(frame.f_code.co_filename).resolve().is_relative_to(project / "policy_port")
                if annotation or adapter:
                    codes.extend(code for value in list(frame.f_locals.values()) for code in unwrapped(value))
                for code in codes:
                    # Inventory paths follow the source AST; Python inserts
                    # <locals> between enclosing functions at runtime.
                    symbol = code.co_qualname.replace(".<locals>.", ".")
                    reached.update(targets.get((str(Path(code.co_filename).resolve()), symbol), ()))
            for name in reached:
                counts["boundaryCalls"][name] = counts["boundaryCalls"].get(name, 0) + 1
            # Gate decisions only: decide() from PolicyRuntime.execute, not construction self-tests, check() or what_if().
            result = super().evaluate(inputs, rules)
            if (reached and caller.f_code is policy.decide.__code__
                    and caller.f_back is not None
                    and caller.f_back.f_code in runtime.PolicyRuntime.execute.__code__.co_consts):
                action = caller.f_locals["intent"]["action"]
                for name in reached:
                    actions = counts["boundaryActions"].setdefault(name, {})
                    actions[action] = actions.get(action, 0) + 1
            return result

    class EngineModule(types.ModuleType):
        def __setattr__(self, name, value):
            if name == "Souffle":
                raise RuntimeError("Port tests must not replace the policy engine.")
            super().__setattr__(name, value)

    datalog.Souffle = policy.Souffle = runtime.Souffle = NativeEngine
    datalog.__class__ = policy.__class__ = runtime.__class__ = EngineModule
    if targets:
        acall = api.Policy.acall

        @functools.wraps(acall)
        async def attributed_acall(*args, **kwargs):
            token = awaiting.set(tuple(stack(sys._getframe(1))))  # still linked before the first await
            try:
                return await acall(*args, **kwargs)
            finally:
                awaiting.reset(token)

        api.Policy.acall = attributed_acall
        sys.setprofile(profiler(previous_profile))
        threading.setprofile(profiler(previous_thread_profile))
    return counts


def main():
    project = Path("/tmp/application")
    shutil.copytree(
        "/source", project, ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
    )
    if Path("/original").exists():
        shutil.copytree(
            "/original",
            "/tmp/original",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    sys.path.insert(0, str(project))
    import os

    os.chdir(project)
    log = io.StringIO()
    from policyweave.enforcement import capture_trajectories, record_execution

    with (
        contextlib.redirect_stdout(log),
        contextlib.redirect_stderr(log),
        capture_trajectories() as recordings,
        record_execution("Port verification") as execution,
    ):
        try:
            inventory = Path("/opt/port-inventory.json")
            boundaries = json.loads(inventory.read_text())["boundaries"] if inventory.exists() else []
            counts = native_engine_guard(boundaries, project)
            if os.environ.get("CHECK_SET") == "independent":
                import importlib.util

                spec = importlib.util.spec_from_file_location(
                    "independent_tests", "/opt/independent_tests.py"
                )
                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module
                spec.loader.exec_module(module)
                suite = unittest.defaultTestLoader.loadTestsFromModule(module)
            else:
                suite = unittest.defaultTestLoader.discover(
                    str(project / "policy_port"),
                    pattern="test_port.py",
                    top_level_dir=str(project),
                )
            result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
            report = dict(
                passed=result.wasSuccessful(),
                tests=result.testsRun,
                failures=len(result.failures),
                errors=len(result.errors),
                skipped=len(result.skipped),
            )
            report["nativeEngineCalls"] = counts["calls"]
            report["nativeBoundaryCalls"] = counts["boundaryCalls"]
            report["nativeBoundaryActions"] = counts["boundaryActions"]
            report["boundaryExecutions"] = counts["boundaryExecutions"]
            if not counts["calls"]:
                report["passed"] = False
                report["verificationError"] = (
                    "No actual native policy evaluation was observed."
                )
        except Exception:
            traceback.print_exc()
            report = dict(passed=False, tests=0, errors=1)
    report["log"] = log.getvalue()[-60000:]
    artifacts = {}
    for name in ("policy_port/trajectories.json", "policy_port/results.json"):
        path = project / name
        if path.exists() and path.stat().st_size < 2_000_000:
            try:
                artifacts[name] = json.loads(path.read_text())
            except (ValueError, UnicodeError):
                pass
    report["artifacts"] = artifacts
    trajectories = []
    complete = True
    for recording in recordings:
        try:
            value = recording.export()
        except ValueError:
            complete = False
            continue
        if value["events"]:
            trajectories.append(value)
    report["trajectoryCoverage"] = dict(
        captured=len(trajectories),
        complete=complete,
        scope="Recorders created in this capture context; not proof of complete application mediation.",
    )
    if not complete:
        report["trajectoryCoverage"]["reason"] = (
            "A recorder failed; evidence is incomplete."
        )
    if len(json.dumps(trajectories, ensure_ascii=False).encode()) > 64_000_000:
        report["trajectoryCoverage"].update(
            complete=False,
            reason="Evidence export exceeds 64 MB; run shorter independent case groups.",
        )
        trajectories = []
    report["policyTrajectories"] = trajectories
    execution_value = execution.export()
    if execution_value["events"]:
        report["executionTrajectory"] = execution_value
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
