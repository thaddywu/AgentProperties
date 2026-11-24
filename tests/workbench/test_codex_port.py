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
        (data / "stop_times.txt").write_bytes(b"departure,arrival\n" * 2_500_000)
        (data / "schedule.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\xff")
        subprocess.run(["git", "-C", str(self.source), "add", "data"], check=True)
        destination = self.root / "asset-snapshot"
        copy_source(self.source, destination)
        for name in ("stop_times.txt", "schedule.png"):
            self.assertEqual((destination / "data" / name).read_bytes(), (data / name).read_bytes())

    def test_snapshot_rejects_total_size_overflow_instead_of_omitting_data(self):
        path = self.source / "large.txt"
        with path.open("wb") as stream:
            stream.truncate(200_000_001)
        subprocess.run(["git", "-C", str(self.source), "add", "large.txt"], check=True)
        with self.assertRaisesRegex(ValueError, "snapshot exceeds"):
            copy_source(self.source, self.root / "oversized-snapshot")

    def test_snapshot_keeps_tracked_templates_locks_and_extensionless_runtime_files(self):
        included = {
            "prompts/system.j2": b"Help {{ role }} with the task.",
            "uv.lock": b"version = 1\n",
            ".python-version": b"3.12\n",
            "Dockerfile": b"FROM scratch\n",
            "assets/fixture.bin": b"\x00\xff\x80",
            "launch.sh": b"#!/bin/sh\nexit 0\n",
        }
        excluded = [".env.local", ".netrc", ".npmrc", "id_ed25519", "signing.pem",
                    "tls.key", "config/auth.json", "config/connections.yml", "client-secret", ".ssh/config"]
        for name, content in included.items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        for name in excluded:
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("synthetic private fixture")
        (self.source / "launch.sh").chmod(0o755)
        (self.source / "linked.j2").symlink_to(self.source / "prompts/system.j2")
        subprocess.run(["git", "-C", str(self.source), "add", "."], check=True)
        (self.source / "untracked.j2").write_text("must not copy")
        destination = self.root / "complete-snapshot"
        copy_source(self.source, destination)
        for name, content in included.items():
            self.assertEqual((destination / name).read_bytes(), content)
        self.assertTrue(os.access(destination / "launch.sh", os.X_OK))
        for name in [*excluded, "linked.j2", "untracked.j2"]:
            self.assertFalse((destination / name).exists(), name)

    def test_snapshot_does_not_follow_a_replaced_parent_directory(self):
        prompts = self.source / "prompts"
        prompts.mkdir()
        (prompts / "system.j2").write_text("tracked template")
        subprocess.run(["git", "-C", str(self.source), "add", "prompts"], check=True)
        shutil.rmtree(prompts)
        private = self.root / "outside"
        private.mkdir()
        (private / "system.j2").write_text("synthetic private fixture")
        prompts.symlink_to(private, target_is_directory=True)
        destination = self.root / "no-link-snapshot"
        copy_source(self.source, destination)
        self.assertFalse((destination / "prompts/system.j2").exists())

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

    def test_planning_keeps_large_source_complete_and_still_bounds_context(self):
        source = 'PAYLOAD = ' + repr("synthetic source " * 40_000) + '\n'
        (self.source / "large.py").write_text(source)
        subprocess.run(["git", "-C", str(self.source), "add", "large.py"], check=True)
        port = CodexPort(self.root / "large-plan", self.port.settings, codex="true")
        port.prepare(self.source)
        with patch("policyweave.adapters.compatible.build_opener") as opener:
            opener.return_value.open.return_value.__enter__.return_value.read.return_value = json.dumps(
                dict(choices=[dict(finish_reason="stop", message=dict(content='{"ok":true}'))])).encode()
            self.assertEqual(port.plan("inventory", "plan", "inventory-attempt-0"), {"ok": True})
            payload = json.loads(opener.return_value.open.call_args.args[0].data)
            context = json.loads(payload["messages"][-1]["content"])
            self.assertEqual(context["source"]["large.py"], source)
            self.assertEqual(opener.return_value.open.call_args.kwargs["timeout"], 1800)
        (self.source / "overflow.py").write_text('PAYLOAD = ' + repr("x" * 1_600_000))
        subprocess.run(["git", "-C", str(self.source), "add", "overflow.py"], check=True)
        oversized = CodexPort(self.root / "oversized-plan", self.port.settings, codex="true")
        oversized.prepare(self.source)
        with patch("policyweave.adapters.compatible.build_opener") as opener:
            with self.assertRaisesRegex(ValueError, "2,000,000"):
                oversized.plan("inventory", "plan", "inventory-attempt-0")
            opener.assert_not_called()

    @unittest.skipUnless(shutil.which("souffle"), "Native engine required")
    def test_worker_rejects_engine_doubles_hidden_in_test_helpers(self):
        root = Path(__file__).resolve().parents[2]
        code = """import asyncio
from unittest.mock import patch
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
              'def produce(): return "actual observation"\\n'
              'def renamed(): return True\\n'
              'def wrapped(): return True\\n'
              'def partial_bound(): return True\\n'
              'def validation(rules):\\n    from policyweave.enforcement import Policy\\n    Policy(rules)\\n    return True\\n'
              'def check_only(policy): return policy.runtime.check(dict(actor="reader", action="read", parameters={}))\\n'
              'def preview(policy): return policy.runtime.what_if(dict(actor="reader", action="read", parameters={}), policy.runtime.snapshot())\\n'
              'def wrong_action(policy): return policy.execute("reader", "write", {}, lambda _: True)\\n'
              'async def awaited(policy):\\n    async def safe(): return True\\n'
              '    return await policy.acall("reader", "read", {}, safe)\\n')
    scope, adapter = {}, {}
    exec(compile(source, str(tool), 'exec'), scope)
    (Path(d) / 'policy_port').mkdir()
    exec(compile('import functools\\n'  # wrappers hold the original under any name, or only via wraps()
                 'class Odd:\\n    __class__ = property(lambda self: 1 / 0)\\n'  # isinstance() on this local would raise
                 'def gate(original, policy):\\n    def checked(odd=Odd()): return policy.call("reader", "read", {}, lambda: original())\\n    return checked\\n'
                 'def gate_wraps(original, policy):\\n    @functools.wraps(original)\\n'
                 '    def checked(): return policy.call("reader", "read", {}, lambda: checked.__wrapped__())\\n    return checked\\n',
                 str(Path(d) / 'policy_port' / 'adapter.py'), 'exec'), adapter)
    counts = native_engine_guard([
        dict(id='plain', file='tool.py', symbol='plain'),
        dict(id='plain_twin', file='tool.py', symbol='plain'),
        dict(id='awaited', file='tool.py', symbol='awaited'),
        dict(id='decorated', file='tool.py', symbol='decorated'),
        dict(id='nested', file='tool.py', symbol='factory.nested'),
        dict(id='nested_decorated', file='tool.py', symbol='decorated_factory.nested'),
        dict(id='producer', file='tool.py', symbol='produce'),
        dict(id='renamed', file='tool.py', symbol='renamed'),
        dict(id='wrapped', file='tool.py', symbol='wrapped'),
        dict(id='partial_bound', file='tool.py', symbol='partial_bound'),
        dict(id='validation', file='tool.py', symbol='validation'),
        dict(id='check_only', file='tool.py', symbol='check_only'),
        dict(id='preview', file='tool.py', symbol='preview'),
        dict(id='wrong_action', file='tool.py', symbol='wrong_action'),
    ], Path(d))
    try:
        with patch('policyweave.core.datalog.Souffle.evaluate', lambda *a: []):
            raise AssertionError('Engine replacement was allowed')
    except RuntimeError:
        pass
    p = Path(d) / 'rules.dl'
    p.write_text('Allow(Q) :- Request(Q,P,"read").\\nAllow(Q) :- Request(Q,P,"write").')
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
    assert adapter['gate'](scope['renamed'], policy)() and adapter['gate_wraps'](scope['wrapped'], policy)()
    from functools import partial
    assert adapter['gate'](partial(scope['partial_bound']), policy)()
    assert asyncio.run(scope['awaited'](policy))
    gated = {'plain', 'plain_twin', 'decorated', 'nested', 'nested_decorated', 'awaited', 'renamed', 'wrapped', 'partial_bound'}
    assert set(counts['boundaryCalls']) == gated
    assert counts['boundaryActions'] == {name: {'read': 1} for name in gated}, counts['boundaryActions']
    assert counts['boundaryExecutions']['producer'] == 1
    assert counts['boundaryExecutions']['plain'] == counts['boundaryExecutions']['plain_twin'] == 1
    assert scope['validation'](p)
    assert scope['check_only'](policy)['allowed']
    assert scope['preview'](policy)['allowed']
    assert counts['boundaryActions'] == {name: {'read': 1} for name in gated}, counts['boundaryActions']
    assert scope['wrong_action'](policy)
    assert counts['boundaryActions']['wrong_action'] == {'write': 1}
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
