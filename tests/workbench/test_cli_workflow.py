"""Offline contracts for separated port/reverse workflows and student evidence."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from policyweave.core.artifacts import files, save
from policyweave.policy_adder import student
from policyweave.policy_adder.codex import CodexPort
from policyweave.policy_adder.repository import RepositoryApplication
from policyweave.workbench import back_translate
from policyweave.workbench.runner import run_case, summarize
from policyweave.workbench.student_review import BundleApplication
from tests.workbench import test_student_workflow as fixture


class SeparatedWorkflowTests(unittest.TestCase):
    setUp = fixture.StudentWorkflowTests.setUp
    tearDown = fixture.StudentWorkflowTests.tearDown

    def test_port_only_skips_reverse_and_alignment(self):
        with (
            patch.object(student, "CodexPort", return_value=self.port),
            patch.object(self.port, "prepare"),
            patch.object(self.port, "translate", return_value=dict(passed=True)),
            patch.object(self.port, "check", return_value=dict(passed=True)),
            patch.object(self.port, "backtranslate") as reverse,
            patch.object(self.port, "review") as align,
        ):
            student.run(self.base, self.target, self.port.settings,
                        work=self.port.output, back_trans=False)
        reverse.assert_not_called()
        align.assert_not_called()
        self.assertTrue((self.target / "policy_port/rules.dl").is_file())
        self.assertFalse((self.target / "back-translation").exists())
        self.assertFalse((self.target / "policy.md").exists())

    def test_runner_cannot_be_changed_by_port(self):
        for name in ("runner.py", "harness.py"):
            path = self.port.output / "original" / name
            path.write_text("def run(): return True\n")
        manifest = json.loads((self.port.output / "source.json").read_text())
        manifest["files"] = files(self.port.output / "original")
        save(self.port.output / "source.json", manifest)
        for name in ("runner.py", "harness.py"):
            (self.port.output / "candidate" / name).write_text(
                "from policy_port import adapter\ndef run(): return True\n"
            )
        errors = self.port.boundary_errors()
        for name in ("runner.py", "harness.py"):
            self.assertIn("Original policy/document/test changed: " + name, errors)

    def test_standalone_reverse_publishes_readable_bundle_outside_app(self):
        app = self.root / "installed"
        student.clean_candidate(self.port.output / "candidate", app)
        reading = json.loads((self.port.output / "review.json").read_text())["execution"]
        work, output = self.root / "reading-work", self.root / "back-trans"
        calls = []

        def reverse(port):
            calls.append("reverse")
            self.assertFalse((port.output / "candidate/policy.md").exists())
            directory = port.output / "reverse/fixture"
            directory.mkdir(parents=True)
            manifest = {n: h for n, h in files(port.output / "candidate").items()
                        if n.endswith((".py", ".dl"))}
            save(directory / "source-manifest.json", manifest)
            save(port.output / "backtranslation.json", dict(
                directory="reverse/fixture", candidateFiles=files(port.output / "candidate"),
            ))
            return dict(passed=True)

        def align(port):
            calls.append("align")
            reference = RepositoryApplication(port.output).initial_review()
            reference["execution"] = reading
            save(port.output / "review.json", reference)

        before = files(app)
        with patch.object(CodexPort, "backtranslate", reverse), patch.object(CodexPort, "review", align):
            back_translate.run(app, self.base / "policy.md", output,
                               self.port.settings, work=work, codex="true")
        self.assertEqual(calls, ["reverse", "align"])
        self.assertEqual(files(app), before)
        bundle = BundleApplication(output, self.base / "policy.md")
        self.assertTrue(bundle.reference()["execution"]["procedures"])
        self.assertEqual({"manifest.json", "alignment.json", "execution.json"},
                         {p.name for p in output.iterdir()})
        (app / "app.py").write_text("changed")
        with self.assertRaisesRegex(ValueError, "implementation changed"):
            BundleApplication(output, self.base / "policy.md")

    def test_nonempty_reverse_output_fails_before_any_model(self):
        app = self.port.output / "candidate"
        output = self.root / "reading"
        output.mkdir()
        (output / "keep").write_text("existing")
        with patch.object(CodexPort, "backtranslate") as model:
            with self.assertRaisesRegex(ValueError, "absent or empty"):
                back_translate.run(app, self.base / "policy.md", output,
                                   self.port.settings, codex="true")
        model.assert_not_called()
        self.assertEqual((output / "keep").read_text(), "existing")


class RunnerTests(unittest.TestCase):
    def test_shared_cli_repeats_cases_and_checks_actual_completion(self):
        from policyweave.workbench.runner import main
        seen = []
        def execute(side, case, sample, output_dir):
            seen.append((side, case, sample))
            (output_dir / "app-output.json").write_text(json.dumps(dict(case=case, sample=sample)))
            return case == "a"
        def assess(result):
            return result
        with tempfile.TemporaryDirectory() as output:
            result = main(execute, assess, cases=["a", "b"], argv=["--side", "original", "--sample", "2", "--output_dir", output])
            self.assertEqual(result, 1)
            self.assertEqual(seen, [("original", "a", 1), ("original", "a", 2), ("original", "b", 1), ("original", "b", 2)])
            self.assertTrue((Path(output) / "b/original/sample-2/result.json").is_file())
            self.assertEqual(json.loads((Path(output) / "b/original/sample-2/app-output.json").read_text()),
                             dict(case="b", sample=2))

    def test_original_needs_only_student_execution_and_assessment(self):
        with tempfile.TemporaryDirectory() as output:
            seen = []
            def execute(*args):
                seen.append(args)
                return {"stored": True}
            def assess(result):
                return result["stored"]
            record = run_case(execute, assess, side="original", case="c1", output=output)
            self.assertEqual(seen, [("original", "c1", 1, Path(output).resolve() / "c1/original/sample-1")])
            self.assertEqual(record["executionStatus"], "completed")
            self.assertEqual(record["trajectories"], [])
            self.assertTrue(record["taskCompleteness"])
            directory = Path(output) / "c1/original/sample-1"
            self.assertEqual(json.loads((directory / "result.json").read_text()), dict(task_complete=True))
            self.assertEqual(json.loads((directory / "run.json").read_text()), record)
            with self.assertRaises(FileExistsError):
                run_case(execute, assess, side="original", case="c1", output=output)

    def test_missing_port_instrumentation_does_not_report_success(self):
        from policyweave.analysis.timeline import Timeline, decode_trajectory

        with tempfile.TemporaryDirectory() as output:
            record = run_case(lambda *a: True, lambda result: result,
                side="ported", case="c1", output=output)
            self.assertEqual(record["executionStatus"], "failed")
            self.assertTrue(record["taskCompleteness"])
            self.assertIn("trajectory.jsonl", record["trajectories"])
            Timeline(decode_trajectory((Path(output) / "c1/ported/sample-1/trajectory.jsonl").read_text()))

    def test_execution_exception_keeps_evidence_without_exception_text(self):
        def execute(*args):
            raise RuntimeError("synthetic-private-value")
        with tempfile.TemporaryDirectory() as output:
            record = run_case(execute, lambda _: self.fail("Must not assess a failed execution"),
                              side="ported", case="c1", output=output)
            self.assertEqual(record["errorType"], "RuntimeError")
            self.assertNotIn("synthetic-private-value", json.dumps(record))
            self.assertIsNone(record["taskCompleteness"])
            self.assertEqual(json.loads((Path(output) / "c1/ported/sample-1/result.json").read_text()),
                             dict(task_complete=False))

    def test_summary_scans_all_current_results_and_counts_samples_individually(self):
        with tempfile.TemporaryDirectory() as output:
            run_case(lambda *args: True, lambda result: result,
                     side="original", case="c1", output=output)
            run_case(lambda *args: False, lambda result: result,
                     side="original", case="c1", sample=2, output=output)
            # Historical samples outside the latest CLI selection count too.
            directory = Path(output) / "another-case/ported/sample-42"
            directory.mkdir(parents=True)
            save(directory / "result.json", dict(task_complete=True))
            # An unfinished directory and unrelated files do not add samples.
            (Path(output) / "c1/original/sample-3").mkdir()
            save(Path(output) / "result.json", dict(task_complete=True))
            summary = summarize(output)
            self.assertEqual(summary, dict(original=dict(completed=1, total=2),
                                           ported=dict(completed=1, total=1)))
            (directory / "result.json").unlink()
            self.assertEqual(summarize(output)["ported"], dict(completed=0, total=0))

    def test_summary_rejects_invalid_results_instead_of_counting_truthy_values(self):
        with tempfile.TemporaryDirectory() as output:
            directory = Path(output) / "c1/original/sample-1"
            directory.mkdir(parents=True)
            for value in (dict(task_complete="true"), dict(task_complete=1),
                          dict(task_complete=True, extra="unused"), {}):
                save(directory / "result.json", value)
                with self.subTest(value=value), self.assertRaises(ValueError):
                    summarize(output)

    def test_each_cli_invocation_prints_cumulative_totals_for_both_sides(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from policyweave.workbench.runner import main

        with tempfile.TemporaryDirectory() as output:
            for case, expected in (("a", "1/1"), ("b", "1/2")):
                with redirect_stdout(StringIO()) as stream:
                    main(lambda side, case, *args: case == "a", lambda result: result,
                         cases=["a", "b"], argv=["--case", case, "--side", "original", "--output_dir", output])
                self.assertEqual(stream.getvalue(),
                                 f"Until now, original app: {expected} runs completed the task.\n"
                                 "Until now, ported app: 0/0 runs completed the task.\n")
            self.assertEqual(json.loads((Path(output) / "b/original/sample-1/result.json").read_text()),
                             dict(task_complete=False))

    @unittest.skipUnless(shutil.which("souffle") and shutil.which("prlimit"), "Native engine required")
    def test_ported_exports_actual_gates_and_independent_completion(self):
        from policyweave.enforcement import Policy, caller_context
        from policyweave.analysis.timeline import Timeline
        from policyweave.analysis.trajectory import TrajectorySession

        with tempfile.TemporaryDirectory() as output:
            rules = Path(output) / "rules.dl"
            rules.write_text('Allow(Q) :- Request(Q,"student","read").')
            effects = []
            def execute(*args):
                policy = Policy(rules)
                @policy
                def read(document):
                    effects.append(document)
                    return dict(ok=True)
                with caller_context("student"):
                    read("one")
                with caller_context("other"):
                    read("two")
                return effects
            record = run_case(execute, lambda result: result == ["one", "two"],
                side="ported", case="c1", output=output)
            self.assertEqual(record["executionStatus"], "completed")
            self.assertFalse(record["taskCompleteness"])
            directory = Path(output) / "c1/ported/sample-1"
            Timeline(json.loads((directory / "trajectory.json").read_text()))
            verified = TrajectorySession(json.loads((directory / "gate-1.json").read_text())).verify()
            self.assertTrue(verified["allMatched"])
            self.assertEqual(effects, ["one"])


class CommandTests(unittest.TestCase):
    def test_installed_commands_expose_the_student_flags_outside_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            for command, flags in (
                ("port", ["--input", "--output", "--connection", "--no-back-trans"]),
                ("translate-harness", ["--input", "--output", "--original-app", "--ported-app"]),
                ("back-translate", ["--ported-app", "--policy", "--output", "--connection"]),
                ("review", ["--policy", "--back-translation"]),
                ("view-translation", ["--policy", "--back-translation"]),
                ("inspect", ["--traj"]),
            ):
                result = subprocess.run([sys.executable, "-B", "-m", "policyweave", command, "--help"],
                                        cwd=directory, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                for flag in flags:
                    self.assertIn(flag, result.stdout)

    def test_review_policy_cannot_silently_open_synthetic_example(self):
        for command in ("review", "view-translation"):
            with self.subTest(command=command):
                result = subprocess.run([sys.executable, "-B", "-m", "policyweave", command,
                                         "--policy", "policy.md"], capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 2)
                self.assertIn("--back-translation", result.stderr)

    def test_view_translation_reports_missing_bundle_without_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([
                sys.executable, "-B", "-m", "policyweave", "view-translation",
                "--back-translation", "missing", "--policy", "policy.md",
            ], cwd=directory, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stderr.strip())
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
