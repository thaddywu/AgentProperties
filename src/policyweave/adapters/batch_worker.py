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
    import types
    import policyweave.core.datalog as datalog
    import policyweave.core.policy as policy

    original = datalog.Souffle
    counts = {"calls": 0, "boundaryCalls": {}}
    targets = {(str((project / row["file"]).resolve()), row["symbol"]): row["id"] for row in boundaries} if project else {}

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
            frame, reached = sys._getframe(1) if targets else None, set()
            while frame is not None:
                codes = [frame.f_code]
                # @policy checks before entering its original body. Read only
                # the trusted annotation frame's bound Python function.
                annotation = frame.f_code.co_filename.endswith("/policyweave/enforcement/api.py") and frame.f_code.co_name == "checked"
                adapter = project and Path(frame.f_code.co_filename).resolve().is_relative_to(project / "policy_port")
                if annotation or adapter:
                    for key in ("body", "function", "fn", "callback"):
                        body = frame.f_locals.get(key)
                        if isinstance(body, types.MethodType):
                            body = body.__func__
                        if isinstance(body, types.FunctionType):
                            codes.append(body.__code__)
                for code in codes:
                    name = targets.get((str(Path(code.co_filename).resolve()), code.co_qualname))
                    if name:
                        reached.add(name)
                frame = frame.f_back
            for name in reached:
                counts["boundaryCalls"][name] = counts["boundaryCalls"].get(name, 0) + 1
            return super().evaluate(inputs, rules)

    class EngineModule(types.ModuleType):
        def __setattr__(self, name, value):
            if name == "Souffle":
                raise RuntimeError("Port tests must not replace the policy engine.")
            super().__setattr__(name, value)

    datalog.Souffle = policy.Souffle = NativeEngine
    datalog.__class__ = policy.__class__ = EngineModule
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
