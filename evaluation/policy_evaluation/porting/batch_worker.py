"""Credential-free, no-network batch check entry point; run only in Docker."""

import contextlib
import io
import json
from pathlib import Path
import shutil
import sys
import traceback
import unittest


def native_engine_guard():
    """Reject accidental test doubles for the actual policy decision engine.

    This is a verification guard, not a sandbox against malicious Python tests.
    Docker remains the isolation boundary.
    """
    import types
    import policy_runtime.datalog as datalog
    import policy_runtime.policy as policy
    original = datalog.Souffle
    counts = {'calls': 0}

    class EngineMeta(type):
        def __setattr__(cls, name, value):
            if name == 'evaluate':
                raise RuntimeError('Port tests must execute native Souffle; evaluator replacement is forbidden.')
            super().__setattr__(name, value)

        def __delattr__(cls, name):
            if name == 'evaluate':
                raise RuntimeError('Native evaluator replacement is forbidden.')
            super().__delattr__(name)

    class NativeEngine(original, metaclass=EngineMeta):
        def evaluate(self, inputs, rules):
            counts['calls'] += 1
            return super().evaluate(inputs, rules)

    class EngineModule(types.ModuleType):
        def __setattr__(self, name, value):
            if name == 'Souffle':
                raise RuntimeError('Port tests must not replace the policy engine.')
            super().__setattr__(name, value)

    datalog.Souffle = policy.Souffle = NativeEngine
    datalog.__class__ = policy.__class__ = EngineModule
    return counts


def main():
    project = Path('/tmp/application')
    shutil.copytree('/source', project, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    if Path('/original').exists():
        shutil.copytree('/original', '/tmp/original', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    sys.path.insert(0, str(project))
    import os
    os.chdir(project)
    log = io.StringIO()
    with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
        try:
            counts = native_engine_guard()
            if os.environ.get('CHECK_SET') == 'independent':
                import importlib.util
                spec = importlib.util.spec_from_file_location('independent_tests', '/opt/independent_tests.py')
                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module
                spec.loader.exec_module(module)
                suite = unittest.defaultTestLoader.loadTestsFromModule(module)
            else:
                suite = unittest.defaultTestLoader.discover(str(project/'policy_port'), pattern='test_port.py', top_level_dir=str(project))
            result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
            report = dict(passed=result.wasSuccessful(), tests=result.testsRun,
                          failures=len(result.failures), errors=len(result.errors), skipped=len(result.skipped))
            report['nativeEngineCalls'] = counts['calls']
            if not counts['calls']:
                report['passed'] = False
                report['verificationError'] = 'No actual native policy evaluation was observed.'
        except Exception:
            traceback.print_exc()
            report = dict(passed=False, tests=0, errors=1)
    report['log'] = log.getvalue()[-60000:]
    artifacts = {}
    for name in ('policy_port/trajectories.json', 'policy_port/results.json'):
        path = project/name
        if path.exists() and path.stat().st_size < 2_000_000:
            try:artifacts[name] = json.loads(path.read_text())
            except (ValueError, UnicodeError):pass
    report['artifacts'] = artifacts
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
