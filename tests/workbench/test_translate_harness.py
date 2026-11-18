"""Offline harness adaptation preserves checks and adds shared execution services."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from policyweave.workbench.translate_harness import translate, validate_translation


SOURCE = '''def start_app():
    from application_startup import ROOT
    assert ROOT == APP_DIR
    return (APP_DIR / "complete.txt").read_text() == "yes"

def check_result(result):
    return result is True

def main():
    pass
'''
ADAPTED = SOURCE + '''
def _policyweave_execute(side, case, sample, output_dir):
    return check_result(start_app())
'''


class HarnessTranslationTests(unittest.TestCase):
    def test_generated_cli_selects_app_and_automatically_summarizes_existing_results(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original, ported = root / "original", root / "ported"
            original.mkdir()
            ported.mkdir()
            for application in (original, ported):
                (application / "application_startup.py").write_text(
                    "from pathlib import Path\nROOT = Path(__file__).resolve().parent\n"
                )
            (original / "complete.txt").write_text("yes")
            (ported / "complete.txt").write_text("no")
            source, output = root / "run.py", root / "translated_harness.py"
            source.write_text(SOURCE)
            def generate(stage, prompt):
                self.assertEqual(stage, "translate-harness")
                self.assertEqual(json.loads(prompt)["harness"], SOURCE)
                return json.dumps(dict(source=ADAPTED, cases=["S02"], startupFunctions=[], limitations=[]))
            translate(source, output, original_app=original, ported_app=ported, generate=generate)
            self.assertEqual(source.read_text(), SOURCE)
            runs = root / "runs"
            historical = runs / "another/ported/sample-8"
            historical.mkdir(parents=True)
            (historical / "result.json").write_text('{"task_complete": true}')
            command = [sys.executable, "-B", str(output), "--side", "original", "--output_dir", str(runs)]
            env = {key: value for key, value in os.environ.items()
                   if key not in {"ORIGINAL_APP_DIR", "PORTED_APP_DIR"}}
            result = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "Until now, original app: 1/1 runs completed the task.\n"
                             "Until now, ported app: 1/1 runs completed the task.\n")
            # Explicit translation paths stay authoritative in another shell.
            inherited = {**env, "ORIGINAL_APP_DIR": str(ported), "PORTED_APP_DIR": str(original)}
            selected = subprocess.run([*command, "--output_dir", str(root / "inherited")],
                                      cwd=root, env=inherited, capture_output=True, text=True, timeout=10)
            self.assertEqual(selected.returncode, 0, selected.stderr)
            self.assertIn("original app: 1/1", selected.stdout)
            paired = subprocess.run([sys.executable, "-B", str(output), "--side", "ported", "--sample", "2",
                                     "--output_dir", str(root / "paired")],
                                      cwd=root, env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(paired.returncode, 1, paired.stderr)
            self.assertIn("ported app: 0/2", paired.stdout)
            moved = root / "moved"
            moved.mkdir()
            for path in (original, ported, source, output):
                shutil.move(path, moved / path.name)
            relocated = subprocess.run(
                [sys.executable, "-B", str(moved / output.name), "--side", "original",
                 "--output_dir", str(moved / "runs")],
                cwd=root, env=env, capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(relocated.returncode, 0, relocated.stderr)
            self.assertIn("original app: 1/1", relocated.stdout)

    def test_manifest_cases_are_complete_and_keep_the_declared_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original, ported = root / "original", root / "ported"
            original.mkdir()
            ported.mkdir()
            source = root / "run.py"
            source.write_text(SOURCE)
            (root / "test_cases.json").write_text(json.dumps(dict(cases=[dict(id="S01"), dict(id="S02")])))
            def response(cases):
                return json.dumps(dict(source=ADAPTED, cases=cases, startupFunctions=[], limitations=[]))
            with self.assertRaisesRegex(ValueError, "test contract"):
                translate(source, root / "missing.py", original_app=original, ported_app=ported,
                          generate=lambda *args: response(["S01"]))
            self.assertFalse((root / "missing.py").exists())
            report = translate(source, root / "complete.py", original_app=original, ported_app=ported,
                               generate=lambda *args: response(["S02", "S01"]))
            self.assertEqual(report["cases"], ["S01", "S02"])

    def test_rewritten_completion_check_and_removed_assertions_are_rejected(self):
        value = dict(source=ADAPTED.replace("return result is True", "return True"),
                     cases=["S02"], startupFunctions=[], limitations=[])
        with self.assertRaisesRegex(ValueError, "function changed"):
            validate_translation(SOURCE, value)
        value["startupFunctions"] = ["check_result"]
        with self.assertRaisesRegex(ValueError, "startup functions"):
            validate_translation(SOURCE, value)
        value = dict(source=ADAPTED, cases=["S02"], startupFunctions=[], limitations=[])
        with self.assertRaisesRegex(ValueError, "assertions"):
            validate_translation(SOURCE.replace("    pass", "    assert False"), value)

    def test_existing_output_is_retained_without_a_model_call(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "run.py", root / "translated.py"
            source.write_text(SOURCE)
            output.write_text("keep")
            with self.assertRaisesRegex(ValueError, "new output"):
                translate(source, output, original_app=root, ported_app=root,
                          generate=lambda *args: self.fail("No model call expected"))
            self.assertEqual(output.read_text(), "keep")
