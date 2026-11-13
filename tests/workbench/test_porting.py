import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from policyscope.adapters.labcluster.agent import Porter, save_json, source_files
from policyscope.adapters.labcluster.artifacts import (
    adapter_tree,
    artifact_hash,
    rule_diagnostics,
)
from policyscope.adapters.labcluster.worker import flatten


class PortingTests(unittest.TestCase):
    def test_rule_feedback_identifies_unsafe_clause_and_budget(self):
        errors = rule_diagnostics("Bad(X) :- Input(X), not Other(Y).")
        self.assertEqual(errors[0]["line"], 1)
        self.assertIn("Unsafe", errors[0]["error"])
        errors = rule_diagnostics("\n".join("Good(X) :- Input(X)." for _ in range(100)))
        self.assertIn("at most 99", errors[0]["error"])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.names = [
            "core/tools.py",
            "core/store.py",
            "core/messaging.py",
            "core/tracing.py",
            "fixtures/cluster.json",
        ]
        for name in self.names:
            p = self.source / name
            p.parent.mkdir(exist_ok=True)
            p.write_text("{}" if name.endswith(".json") else "# Synthetic source\n")
        self.policy = self.root / "policy.md"
        self.policy.write_text(
            "\n\n".join(f"## P{i} Test\nSynthetic policy {i}." for i in range(1, 7))
        )

    def porter(self, generate=lambda stage, prompt: "{}", turns=8):
        with (
            patch(
                "policyscope.adapters.labcluster.agent.source_files",
                return_value=self.names,
            ),
            patch(
                "policyscope.adapters.labcluster.agent.subprocess.check_output",
                return_value="fixture-revision\n",
            ),
            patch("policyscope.adapters.labcluster.agent.Sandbox") as sandbox,
        ):
            sandbox.return_value.image = "sha256:fixture"
            self.sandbox = sandbox.return_value
            self.sandbox.run.return_value = {"passed": True}
            porter = Porter(
                self.source, self.policy, self.root / "port", generate, max_turns=turns
            )
            self.sandbox.run.reset_mock()
            return porter

    def inspect(self, porter):
        for path in (
            "policy.md",
            "source/core/tools.py",
            "source/core/store.py",
            "source/core/messaging.py",
        ):
            porter.tool("read_file", {"path": path})

    def test_authority_paths_and_required_inspection(self):
        porter = self.porter()
        with self.assertRaisesRegex(ValueError, "policy.md"):
            porter.tool("write_file", {"path": "candidate/adapter.py", "content": "x"})
        for path in (
            "../../secret",
            "source/../policy.md",
            "source/.env",
            "candidate/../core/store.py",
        ):
            with self.assertRaises(ValueError):
                porter.tool("read_file", {"path": path})
        self.inspect(porter)
        with self.assertRaises(ValueError):
            porter.tool(
                "write_file", {"path": "source/core/store.py", "content": "mutated"}
            )
        with self.assertRaises(ValueError):
            porter.tool("run_checks", {"suite": "heldout"})
        with self.assertRaises(ValueError):
            porter.tool("shell", {"command": "anything"})

    def test_edits_invalidate_checks_and_source_changes_reject(self):
        porter = self.porter()
        self.inspect(porter)
        porter.tool(
            "write_file",
            {
                "path": "candidate/adapter.py",
                "content": "def observe(snapshot, request, fixtures):\n    return []\n",
            },
        )
        porter.checks = dict(
            static=artifact_hash(porter.artifacts),
            development=artifact_hash(porter.artifacts),
        )
        porter.tool(
            "write_file",
            {
                "path": "candidate/rules.dl",
                "content": 'Allow(Q) :- Request(Q, "Master", "read").\n',
            },
        )
        with self.assertRaisesRegex(ValueError, "exact current"):
            porter.tool("finish", {})
        (porter.candidate / "core/store.py").write_text("changed")
        with self.assertRaisesRegex(ValueError, "business code changed"):
            porter.tool("run_checks", {"suite": "development"})
        self.sandbox.run.assert_not_called()

    def test_agent_repairs_using_feedback_not_a_one_shot(self):
        responses = [
            {
                "actions": [
                    {"tool": "read_file", "arguments": {"path": path}}
                    for path in (
                        "policy.md",
                        "source/core/tools.py",
                        "source/core/store.py",
                        "source/core/messaging.py",
                    )
                ]
            },
            {
                "actions": [
                    {
                        "tool": "write_file",
                        "arguments": {
                            "path": "candidate/adapter.py",
                            "content": "broken",
                        },
                    },
                    {"tool": "run_checks", "arguments": {"suite": "static"}},
                ]
            },
            {
                "actions": [
                    {
                        "tool": "write_file",
                        "arguments": {
                            "path": "candidate/adapter.py",
                            "content": "repaired",
                        },
                    },
                    {"tool": "run_checks", "arguments": {"suite": "static"}},
                    {"tool": "run_checks", "arguments": {"suite": "development"}},
                ]
            },
            {"actions": [{"tool": "finish", "arguments": {}}]},
        ]
        prompts = []

        def model(stage, prompt):
            prompts.append(json.loads(prompt))
            return json.dumps(responses[len(prompts) - 1])

        porter = self.porter(model)
        self.sandbox.run.side_effect = [
            {"error": "synthetic parse failure"},
            {"binding": {"predicates": {}}, "rules": [], "plan": {}},
            {"passed": True},
        ]
        porter.finalize = Mock(return_value={"status": "validated"})
        self.assertEqual(porter.run()["status"], "validated")
        self.assertEqual(len(prompts), 4)
        self.assertIn("synthetic parse failure", json.dumps(prompts[2]))
        self.assertEqual((porter.artifacts / "adapter.py").read_text(), "repaired")
        self.assertNotIn("heldout", json.dumps(prompts[0]["tools"]))

    def test_pure_mapper_rejects_execution_and_introspection(self):
        adapter_tree(
            'def observe(snapshot, request, fixtures):\n    return [fact("Owner", j["id"], j["owner"]) for j in snapshot["jobs"]]\n'
        )
        for source in (
            "import os\n",
            'def observe(snapshot, request, fixtures):\n    return open("secret").read()\n',
            "def observe(snapshot, request, fixtures):\n    return snapshot.__class__\n",
            'def observe(snapshot, request, fixtures):\n    globals()["x"] = 1\n',
        ):
            with self.assertRaises(ValueError):
                adapter_tree(source)

    def test_targeted_repair_requires_current_unique_text(self):
        porter = self.porter()
        self.inspect(porter)
        porter.tool(
            "write_file", {"path": "candidate/adapter.py", "content": "first\nsecond\n"}
        )
        porter.checks = {"static": artifact_hash(porter.artifacts)}
        porter.tool(
            "replace_text",
            {"path": "candidate/adapter.py", "old": "second", "new": "repaired"},
        )
        self.assertEqual(
            (porter.artifacts / "adapter.py").read_text(), "first\nrepaired\n"
        )
        self.assertFalse(porter.checks)
        with self.assertRaisesRegex(ValueError, "exactly once"):
            porter.tool(
                "replace_text",
                {"path": "candidate/adapter.py", "old": "second", "new": "stale"},
            )

    def test_exposed_validation_is_archived_and_requires_regression_checks(self):
        porter = self.porter()
        for name in ("adapter.py", "rules.dl", "plan.json"):
            (porter.artifacts / name).write_text("original candidate")
        failed = {
            "passed": False,
            "cases": [{"case": "synthetic boundary", "passed": False}],
        }
        save_json(porter.output / "heldout.json", failed)
        save_json(porter.output / "port.json", {"status": "heldout-failed"})
        with self.assertRaisesRegex(ValueError, "repair-validation"):
            Porter.resume(porter.output, lambda stage, prompt: "{}", max_turns=8)
        with patch("policyscope.adapters.labcluster.agent.Sandbox") as sandbox:
            sandbox.return_value.image = "sha256:fixture"
            sandbox.return_value.run.return_value = {"passed": True}
            resumed = Porter.resume(
                porter.output,
                lambda stage, prompt: "{}",
                max_turns=8,
                repair_validation=True,
            )
            self.assertTrue(resumed.validation_exposed)
            archive = porter.output / "validation-history/initial"
            self.assertEqual(json.loads((archive / "heldout.json").read_text()), failed)
            self.assertEqual((archive / "rules.dl").read_text(), "original candidate")
            resumed.checks = dict(
                static=artifact_hash(resumed.artifacts),
                development=artifact_hash(resumed.artifacts),
            )
            with self.assertRaises(ValueError):
                resumed.tool("finish", {})
            resumed.tool("run_checks", {"suite": "regression"})
            self.assertTrue(resumed.tool("finish", {})["readyForIndependentValidation"])
            self.assertEqual(
                json.loads((porter.output / "heldout.json").read_text()), failed
            )

    def test_snapshot_rejects_symlink_and_parameter_aliases(self):
        link = self.source / "core/store.py"
        link.unlink()
        link.symlink_to(self.policy)
        with patch(
            "policyscope.adapters.labcluster.agent.subprocess.check_output",
            return_value="\0".join(self.names).encode(),
        ):
            with self.assertRaisesRegex(ValueError, "symlinks"):
                source_files(self.source)
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            flatten({"spec_cpu": "1", "spec": {"cpu": 2}})
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            flatten({"spec": {"cpu": 2}, "spec_cpu": "1"})


if __name__ == "__main__":
    unittest.main()
