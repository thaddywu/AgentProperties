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

from policyweave.policy_adder.codex import CodexPort, choose_policy, copy_source
from policyweave.policy_adder.repository import PortJobs, RepositoryApplication
from policyweave.workbench.study import Study


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
        (self.source / "connection.yaml").write_text("openai:\n  apiKey: synthetic-key\n")
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
        self.assertFalse((self.port.output / "original/connection.yaml").exists())
        framework = self.port.output / "framework/policyweave"
        self.assertTrue((framework / "enforcement/api.py").is_file())
        self.assertTrue((framework / "core/foundations.json").is_file())
        self.assertTrue((framework / "workbench/runner.py").is_file())
        self.assertFalse((framework / "workbench/static").exists())
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

    def test_explicit_application_description_survives_excluded_submission_folder(self):
        submission = self.source / "submission"
        submission.mkdir()
        (submission / "app.md").write_text(
            "Canonical synthetic application description."
        )
        subprocess.run(
            ["git", "-C", str(self.source), "add", "submission/app.md"], check=True
        )
        port = CodexPort(
            self.root / "nested-doc-port", self.port.settings, codex="true"
        )
        port.prepare(self.source, app_doc="submission/app.md")
        self.assertEqual(
            (port.output / "candidate/submission/app.md").read_text(),
            (submission / "app.md").read_text(),
        )
        self.assertEqual(
            json.loads((port.output / "source.json").read_text())["appDoc"],
            "submission/app.md",
        )
        self.assertIn(
            "candidate/submission/app.md", (port.output / "prompt.txt").read_text()
        )

    def test_snapshot_keeps_large_runtime_data_and_image_bytes(self):
        data = self.source / "data"
        data.mkdir()
        (data / "stop_times.txt").write_bytes(b"departure,arrival\n" * 150_000)
        (data / "schedule.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\xff")
        subprocess.run(["git", "-C", str(self.source), "add", "data"], check=True)
        destination = self.root / "asset-snapshot"
        copy_source(self.source, destination)
        for name in ("stop_times.txt", "schedule.png"):
            self.assertEqual((destination / "data" / name).read_bytes(), (data / name).read_bytes())

    def test_snapshot_rejects_total_size_overflow_instead_of_omitting_data(self):
        path = self.source / "large.txt"
        with path.open("wb") as stream:
            stream.truncate(40_000_001)
        subprocess.run(["git", "-C", str(self.source), "add", "large.txt"], check=True)
        with self.assertRaisesRegex(ValueError, "snapshot exceeds"):
            copy_source(self.source, self.root / "oversized-snapshot")

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
        (self.port.output / "candidate/connection.yml").write_text("anthropic:\n  apiKey: synthetic-key\n")
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
            "policyweave.back_translation.codex.validate_rules",
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
            "connection.yml",
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

    def test_backtranslation_rejects_implementation_changes_during_snapshot(self):
        package = self.port.output / "candidate/policy_port"
        package.mkdir()
        (package / "rules.dl").write_text('Allow(Q) :- Request(Q,P,"read").')
        copy = shutil.copy2

        def copy_then_change(source, destination):
            result = copy(source, destination)
            if source == self.port.output / "candidate/tool.py":
                source.write_text("def run(): return False\n")
            return result

        with patch("policyweave.back_translation.codex.shutil.copy2", side_effect=copy_then_change):
            with self.assertRaisesRegex(ValueError, "changed while creating"):
                self.port.backtranslate()
        self.assertFalse((self.port.output / "backtranslation.json").exists())

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
from policyweave.adapters.batch_worker import native_engine_guard
from policyweave.enforcement import Policy, caller_context
with tempfile.TemporaryDirectory() as d:
    tool = Path(d) / 'tool.py'
    source = ('def plain(policy): return policy.execute("reader", "read", {}, lambda _: True)\\n'
              'def decorated(): return True\\n'
              'def factory():\\n    def nested(policy): return policy.execute("reader", "read", {}, lambda _: True)\\n    return nested\\n'
              'def decorated_factory():\\n    def nested(): return True\\n    return nested\\n'
              'def produce(): return "actual observation"\\n')
    scope = {}
    exec(compile(source, str(tool), 'exec'), scope)
    counts = native_engine_guard([
        dict(id='plain', file='tool.py', symbol='plain'),
        dict(id='decorated', file='tool.py', symbol='decorated'),
        dict(id='nested', file='tool.py', symbol='factory.nested'),
        dict(id='nested_decorated', file='tool.py', symbol='decorated_factory.nested'),
        dict(id='producer', file='tool.py', symbol='produce'),
    ], Path(d))
    try:
        with patch('policyweave.core.datalog.Souffle.evaluate', lambda *a: []):
            raise AssertionError('Engine replacement was allowed')
    except RuntimeError:
        pass
    p = Path(d) / 'rules.dl'
    p.write_text('Allow(Q) :- Request(Q,P,"read").')
    policy = Policy(p)
    assert counts['calls'] > 0, 'Initialization must use the guarded native engine too'
    assert policy.runtime.check(dict(actor='reader',action='read',parameters={}))['allowed']
    assert not counts['boundaryCalls'], 'Standalone gates must not count as application integration'
    assert scope['plain'](policy)
    with caller_context('reader'):
        assert policy(name='read')(scope['decorated'])()
        assert policy(name='read')(scope['decorated_factory']())()
    assert scope['factory']()(policy)
    assert scope['produce']() == 'actual observation'
    assert set(counts['boundaryCalls']) == {'plain', 'decorated', 'nested', 'nested_decorated'}
    assert counts['boundaryExecutions']['producer'] == 1
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
