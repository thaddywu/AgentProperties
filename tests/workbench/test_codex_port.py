"""Offline checks for repository snapshots and operator-selected job boundaries."""

import json
from pathlib import Path
import subprocess
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from policyscope.policy_adder.codex import CodexPort, choose_policy
from policyscope.policy_adder.repository import PortJobs, RepositoryApplication
from policyscope.workbench.study import Study


class CodexPortTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "app"
        self.source.mkdir()
        subprocess.run(["git", "init", "-q", str(self.source)], check=True)
        (self.source / "policy.md").write_text(
            "Only the reviewer may approve an operation.\n"
        )
        (self.source / "app.md").write_text("A synthetic app.")
        (self.source / "tool.py").write_text("def run(): return True\n")
        (self.source / ".env").write_text("DO_NOT_COPY=synthetic\n")
        subprocess.run(["git", "-C", str(self.source), "add", "."], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(self.source),
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "commit",
                "-qm",
                "fixture",
            ],
            check=True,
        )
        self.port = CodexPort(
            self.root / "port",
            dict(baseUrl="http://127.0.0.1/v1", modelId="fixture"),
            codex="true",
        )
        self.port.prepare(self.source)

    def tearDown(self):
        self.temp.cleanup()

    def test_snapshot_preserves_policy_excludes_credentials_and_rejects_parent_git(
        self,
    ):
        self.assertFalse((self.port.output / "original/.env").exists())
        framework = self.port.output / "framework/policyscope"
        self.assertTrue((framework / "enforcement/api.py").is_file())
        self.assertTrue((framework / "core/foundations.json").is_file())
        self.assertFalse((framework / "policy_adder").exists())
        self.assertEqual(
            (self.port.output / "candidate/policy.md").read_text(),
            (self.source / "policy.md").read_text(),
        )
        nested = self.source / "nested"
        nested.mkdir()
        (nested / "policy.md").write_text("nested")
        with self.assertRaises(ValueError):
            CodexPort(
                self.root / "nested-port", self.port.settings, codex="true"
            ).prepare(nested)

    def test_boundary_change_and_stale_review_are_rejected(self):
        app = RepositoryApplication(self.port.output)
        study = Study(self.root / "study", app)
        self.assertEqual(
            len(study.data["reviewUnits"][app.reference()["id"]]["units"]), 1
        )
        (self.port.output / "candidate/policy.md").write_text("Changed requirement.")
        self.assertTrue(self.port.boundary_errors())
        (self.port.output / "original/tool.py").write_text("modified original")
        with self.assertRaises(ValueError):
            RepositoryApplication(self.port.output)

    def test_backtranslation_snapshot_excludes_policy_plan_tests_and_keeps_implementation(
        self,
    ):
        package = self.port.output / "candidate/policy_port"
        package.mkdir()
        (package / "rules.dl").write_text('Allow(Q) :- Request(Q,P,"read").')
        (package / "adapter.py").write_text("x = 1\n")
        (package / "port.json").write_text('{"forward_plan":"exclude"}')
        (package / "test_port.py").write_text('x = "exclude test"')
        (package / "offline_fixtures.py").write_text("test_only_engine_double = True")
        (package / "plan.json").write_text('{"forward_plan":"must also be excluded"}')
        config = self.port.output / "candidate/config"
        config.mkdir()
        (config / "policy.json").write_text('{"runtime_limit":20}')
        agents = self.port.output / "candidate/agents"
        agents.mkdir()
        (agents / "reviewer.md").write_text(
            "Use the recording tool for assigned operations."
        )
        # Stop before the native validation/model call; inspect the independently
        # created input snapshot, never execute app source on the host.
        with patch(
            "policyscope.back_translation.codex.validate_rules",
            side_effect=ValueError("stop"),
        ):
            with self.assertRaises(ValueError):
                self.port.backtranslate()
        reverse = next((self.port.output / "reverse").iterdir()) / "source"
        self.assertTrue((reverse / "tool.py").exists())
        self.assertTrue((reverse / "policy_port/adapter.py").exists())
        self.assertTrue((reverse / "config/policy.json").exists())
        self.assertTrue((reverse / "agents/reviewer.md").exists())
        for name in (
            "policy.md",
            "policy_port/port.json",
            "policy_port/test_port.py",
            "policy_port/plan.json",
            "policy_port/offline_fixtures.py",
        ):
            self.assertFalse((reverse / name).exists(), name)

    def test_job_cannot_select_paths_commands_or_overlap(self):
        study = Study(self.root / "study", RepositoryApplication(self.port.output))
        jobs = PortJobs(self.port, study)
        with self.assertRaises(ValueError):
            jobs.start("../../tool.py")
        jobs.lock.acquire()
        try:
            with self.assertRaises(ValueError):
                jobs.start("translate")
        finally:
            jobs.lock.release()
        self.assertTrue(jobs.status()["canTranslate"])

    def test_previous_translation_is_retained_and_not_overwritten(self):
        path = self.port.output / "translation.json"
        path.write_text('{"status":"failed"}')
        with self.assertRaises(ValueError):
            self.port.translate()
        self.assertEqual(json.loads(path.read_text())["status"], "failed")

    @unittest.skipUnless(shutil.which("souffle"), "Native engine required")
    def test_worker_rejects_engine_doubles_hidden_in_test_helpers(self):
        root = Path(__file__).resolve().parents[2]
        code = """from unittest.mock import patch
from pathlib import Path
import tempfile
from policyscope.adapters.batch_worker import native_engine_guard
counts = native_engine_guard()
try:
    with patch('policyscope.core.datalog.Souffle.evaluate', lambda *a: []):
        raise AssertionError('Engine replacement was allowed')
except RuntimeError:
    pass
from policyscope.enforcement import Policy
with tempfile.TemporaryDirectory() as d:
    p = Path(d) / 'rules.dl'
    p.write_text('Allow(Q) :- Request(Q,P,"read").')
    policy = Policy(p)
    assert policy.runtime.check(dict(actor='reader',action='read',parameters={}))['allowed']
assert counts['calls'] > 0
"""
        environment = dict(
            os.environ, PYTHONPATH=os.pathsep.join(str(root / p) for p in ("src",))
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env=environment,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
