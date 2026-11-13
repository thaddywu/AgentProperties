import json
from pathlib import Path
import shutil
import tempfile
import unittest
from policyscope.workbench.cases import read_cases, run_cases
from policyscope.workbench.example import Application
from policyscope.workbench.study import Study


class CaseFileTests(unittest.TestCase):
    def setUp(self):
        self.app = Application()
        self.value = json.loads(
            (
                Path(__file__).resolve().parents[2]
                / "examples/cases/document-tests.json"
            ).read_text()
        )

    def test_data_only_and_complete_validation_before_running(self):
        for invalid in (
            dict(self.value, command="echo unsafe"),
            dict(version=1, cases=[dict(self.value["cases"][0], command="anything")]),
        ):
            with self.assertRaises(ValueError):
                read_cases(invalid, self.app)
        self.value["cases"][1]["setup"]["actor"] = "unknown"
        with tempfile.TemporaryDirectory() as directory:
            study = Study(directory, self.app)
            with self.assertRaises(ValueError):
                run_cases(study, self.value)
            self.assertEqual(study.export()["scenarios"], [])
            self.assertEqual(study.export()["pairs"], [])

    @unittest.skipUnless(shutil.which("souffle"), "Native engine required")
    def test_headless_cases_keep_intent_and_evidence_without_human_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            study = Study(directory, self.app)
            pairs = run_cases(study, self.value)
            self.assertEqual(len(pairs), 2)
            self.assertTrue(all(p["comparable"] for p in pairs))
            self.assertEqual(
                pairs[1]["runs"]["protected"]["events"][0]["outcome"], "blocked"
            )
            self.assertEqual(
                study.export()["scenarios"][1]["caseId"], "read-other-document"
            )
            self.assertEqual(sum(r["reviewed"] for r in study.summary()["runs"]), 0)
            self.assertEqual(len(Study(directory, self.app).export()["pairs"]), 2)
