import json
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from policyweave.workbench.example import Application
from policyweave.workbench.importer import ReviewApplication
from policyweave.workbench.server import Server
from policyweave.workbench.study import Study
from policyweave.policy_viewer.review import review_units
from policyweave.core.policy import CORE, fingerprint, read_binding


class StudyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.app = Application()
        self.study = Study(self.directory.name, self.app)

    def tearDown(self):
        self.directory.cleanup()

    def test_judgment_versions_unknowns_and_required_reasons(self):
        review = self.study.data["reviews"][0]
        with self.assertRaises(ValueError):
            self.study.judge(
                review["id"], "r1", dict(rating="partially_correct", note="")
            )
        self.study.judge(
            review["id"],
            "r1",
            dict(
                categories=["permission", "information_flow"],
                support="unsure",
                rating="unsure",
                note="Needs confirmation.",
            ),
        )
        self.study.judge(
            review["id"],
            "r1",
            dict(categories=["permission"], rating="fully_correct", note="Confirmed."),
        )
        summary = self.study.summary()["reviews"][0]
        self.assertEqual(summary["categories"]["permission"], 1)
        self.assertEqual(summary["categories"]["information_flow"], 0)
        self.assertEqual(summary["unrated"], 1)
        reloaded = Study(self.directory.name, self.app)
        self.assertEqual(len(reloaded.data["judgments"][review["id"]]["r1"]), 2)
        with self.assertRaises(ValueError):
            self.study.judge("wrong-review", "r1", {})

    def test_sentence_judgments_preserve_legacy_and_custom_categories(self):
        review = self.study.data["reviews"][0]
        unit = self.study.data["reviewUnits"][review["id"]]["units"][0]
        self.study.judge(review["id"], "r1", dict(rating="fully_correct"))
        judgment = dict(
            rating="partially_correct",
            note="Missing exception.",
            categories=["permission", "other"],
            otherCategory="Retention",
        )
        self.study.judge(review["id"], unit["id"], judgment)
        self.study.judge(review["id"], unit["id"], judgment)
        loaded = Study(self.directory.name, self.app)
        self.assertEqual(len(loaded.data["judgments"][review["id"]][unit["id"]]), 1)
        summary = loaded.summary()["reviews"][0]
        self.assertEqual(summary["ratings"]["fully_correct"], 1)
        self.assertEqual(summary["sentenceReview"]["ratings"]["partially_correct"], 1)
        self.assertEqual(summary["sentenceReview"]["categories"]["other"], 1)
        with self.assertRaises(ValueError):
            self.study.judge(review["id"], unit["id"], dict(categories=["other"]))
        with self.assertRaises(ValueError):
            self.study.judge(review["id"], unit["id"], dict(rating="not_covered"))
        with self.assertRaises(ValueError):
            self.study.judge(review["id"], "sentence:0:999", judgment)

    def test_source_order_unicode_omissions_and_coarse_matches(self):
        source = "# Policy\n\n😀 Read your file. Delete your file.\nUnmapped 中文。另一个要求！"
        end = source.index("\nUnmapped")
        review = dict(
            source=dict(text=source),
            requirements=[
                dict(
                    id="P1",
                    start=source.index("😀"),
                    end=end,
                    statement="Read and delete.",
                )
            ],
            behaviors=[dict(id="b1", requirementIds=["P1"])],
        )
        units = review_units(review)["units"]
        self.assertEqual(
            [u["quote"] for u in units],
            [
                "😀 Read your file.",
                "Delete your file.",
                "Unmapped 中文。",
                "另一个要求！",
            ],
        )
        for unit in units:
            self.assertEqual(source[unit["start"] : unit["end"]], unit["quote"])
        self.assertEqual(units[0]["mapping"], "broader")
        self.assertEqual(units[1]["behaviorIds"], ["b1"])
        self.assertEqual(units[2]["behaviorIds"], [])

    @unittest.skipUnless(
        shutil.which("souffle") and shutil.which("prlimit"), "Native Soufflé required"
    )
    def test_real_backend_baseline_protected_and_independent_human_labels(self):
        scenario = self.study.add_scenario(
            dict(
                task="Read private document",
                setup=dict(actor="alice", document="doc-b", state="active"),
                expected="No private content",
                split="heldout",
                seed=42,
            )
        )
        pair = self.study.run_pair(scenario["id"])[0]
        original, protected = (
            pair["runs"][m]["events"][0] for m in ("baseline", "protected")
        )
        self.assertEqual(original["outcome"], "executed")
        self.assertEqual(protected["outcome"], "blocked")
        self.assertIsNone(protected["value"])
        self.assertTrue(original["fixtureOracle"]["actualViolation"])
        self.assertFalse(protected["fixtureOracle"]["actualViolation"])
        self.assertEqual(
            sum(r["actualViolations"] for r in self.study.summary()["runs"]), 0
        )  # oracle is not a human rating
        self.study.judge_event(
            pair["id"],
            "baseline",
            original["id"],
            dict(violation="yes", shouldAllow="no", note="Private content returned."),
        )
        self.study.judge_event(
            pair["id"],
            "protected",
            protected["id"],
            dict(violation="no", shouldAllow="no", note="No content returned."),
        )
        runs = self.study.summary()["runs"]
        self.assertEqual(runs[0]["actualViolations"], 1)
        self.assertEqual(runs[1]["preventedAttempts"], 1)
        self.study.judge_run(
            pair["id"], "protected", dict(completed="no", note="Read refused.")
        )
        self.assertEqual(self.study.summary()["runs"][1]["humanCompletion"], "no")
        self.assertEqual(
            Study(self.directory.name, self.app).export()["pairs"][0]["runs"][
                "protected"
            ]["judgments"][-1]["completed"],
            "no",
        )
        with self.assertRaises(ValueError):
            self.study.judge_run(
                pair["id"], "protected", dict(completed="maybe", note="")
            )
        with self.assertRaises(ValueError):
            self.study.judge_event(
                pair["id"],
                "protected",
                protected["id"],
                dict(violation="yes", shouldAllow="no", note=""),
            )
        query = self.app.inspect(original["snapshot"], "owners")
        self.assertEqual(len(query["rows"]), 2)

    @unittest.skipUnless(
        shutil.which("souffle") and shutil.which("prlimit"), "Native Soufflé required"
    )
    def test_normal_task_runs_in_both_modes_and_state_resets(self):
        scenario = self.study.add_scenario(
            dict(
                task="Read own active document",
                setup=dict(actor="alice", document="doc-a", state="active"),
                expected="Read succeeds",
                split="development",
                seed=4,
            )
        )
        pairs = self.study.run_pair(scenario["id"], 2)
        self.assertEqual(pairs[1]["order"], ["protected", "baseline"])
        self.assertEqual(pairs[1]["seed"], 5)
        for pair in pairs:
            for run in pair["runs"].values():
                self.assertEqual(run["status"], "completed")
                self.assertTrue(run["result"]["completed"])
                self.assertFalse(run["events"][0]["fixtureOracle"]["actualViolation"])

    def test_mismatched_initial_state_is_not_a_comparable_pair(self):
        self.app.run = lambda scenario, mode, seed, emit: dict(
            completed=False, initialStateHash=mode, configurationHash="same-config"
        )
        scenario = self.study.add_scenario(
            dict(
                task="Read",
                setup=dict(actor="alice", document="doc-a", state="active"),
                expected="Read succeeds",
                split="heldout",
                seed=2,
            )
        )
        pair = self.study.run_pair(scenario["id"])[0]
        self.assertFalse(pair["comparable"])
        self.assertFalse(self.study.summary()["runs"][0]["comparable"])

    def test_runner_failure_is_not_success_and_pins_are_checked(self):
        scenario = self.study.add_scenario(
            dict(
                task="Read",
                setup=dict(actor="alice", document="doc-a", state="active"),
                expected="Read succeeds",
                split="development",
                seed=4,
            )
        )

        def broken(*args):
            raise RuntimeError("private implementation detail")

        self.app.run = broken
        pair = self.study.run_pair(scenario["id"])[0]
        self.assertEqual(pair["runs"]["baseline"]["status"], "failed")
        self.assertNotIn("private implementation", json.dumps(pair))
        self.app.revision = "changed"
        with self.assertRaises(ValueError):
            Study(self.directory.name, self.app)

    def test_reference_import_preserves_source_and_hashes(self):
        root = Path(self.directory.name) / "reference"
        (root / "generated").mkdir(parents=True)
        text = "Permit reads."
        source = 'Allow(Q) :- Request(Q,P,"read").\n'
        documents = [("app.md", "Synthetic document reader."),
                     ("policy.md", "P1. " + text + "\n"), ("tools.md", "read()")]
        for name, content in [*documents, ("rules.dl", source)]:
            (root / name).write_text(content)
        binding = read_binding(dict(version=1, id="reference-test", context="Synthetic reader.",
            predicates=CORE, decision=dict(request="Request", parameters="Parameter", allow="Allow", deny="Deny"), tests=[]))
        plan = dict(sourceHash=fingerprint([dict(id="P1", text=text)]), bindingHash=fingerprint(binding),
            documentsHash=fingerprint([dict(path=name, content=content) for name, content in documents]),
            requirements=[dict(id="r1", policyId="P1", source=text, start=0, end=len(text),
                statement=text, implementation="datalog", relation="equivalent", assumptions=[], predicates=["Request", "Allow"])])
        rules = [dict(id="read", datalog=source.strip())]
        output = dict(rules=rules, coverage=[dict(id="r1", ruleIds=["read"])])
        readings = dict(application="Synthetic reader", sourceHash=fingerprint(source), contractHash=fingerprint(binding),
            programHash=fingerprint(rules), planHash=fingerprint(plan), obligations={},
            behaviors=[dict(id="read", ruleIds=["read"], summary=text, conditions=[])])
        for name, value in [("generated/runtime.json", binding), ("generated/policy-plan.json", plan),
                            ("generated/reference-output.json", output), ("review-readings.json", readings)]:
            (root / name).write_text(json.dumps(value))
        app = ReviewApplication(root)
        review = app.reference()
        self.assertEqual(len(review["requirements"]), 1)
        for row in review["requirements"]:
            self.assertEqual(app.policy[row["start"] : row["end"]], row["quote"])
        self.assertEqual(app.setup_fields, [])
        (root / "rules.dl").write_text(source + "// Changed after review.\n")
        with self.assertRaisesRegex(ValueError, "stale"):
            ReviewApplication(root)


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.server = Server(
            ("127.0.0.1", 0), Study(self.directory.name, Application())
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.directory.cleanup()

    def test_failed_model_attempts_are_private_and_never_fall_back(self):
        self.server.generate = lambda *args: "invalid-json"
        study = self.server.study
        request = Request(
            self.base + "/api/translate",
            data=json.dumps(dict(text="PRIVATE_SOURCE_MARKER")).encode(),
            headers={
                "Content-Type": "application/json",
                "X-Study-Token": self.server.token,
            },
        )
        with self.assertRaises(HTTPError):
            urlopen(request)
        exported = study.export()
        self.assertEqual(len(exported["reviews"]), 1)
        self.assertEqual(len(exported["failures"]), 1)
        self.assertNotIn("PRIVATE_SOURCE_MARKER", json.dumps(exported))
        private = (
            Path(self.directory.name) / exported["failures"][0]["recordFile"]
        ).read_text()
        self.assertIn("PRIVATE_SOURCE_MARKER", private)

    def test_static_ui_and_local_token_boundary(self):
        with urlopen(self.base + "/") as response:
            self.assertIn(b"<title>Policy review</title>", response.read())
            self.assertIn(
                "frame-ancestors 'none'", response.headers["Content-Security-Policy"]
            )
        with urlopen(self.base + "/api/study") as response:
            state = json.load(response)
        self.assertFalse(state["modelAvailable"])
        for headers in [
            {"Content-Type": "application/json"},
            {
                "Content-Type": "application/json",
                "X-Study-Token": state["token"],
                "Origin": "https://external.invalid",
            },
        ]:
            with self.assertRaises(HTTPError) as caught:
                urlopen(
                    Request(self.base + "/api/scenario", data=b"{}", headers=headers)
                )
            self.assertEqual(caught.exception.code, 403)

        request = Request(
            self.base + "/api/judgment",
            data=json.dumps(
                dict(
                    reviewId=state["study"]["reviews"][0]["id"],
                    requirementId="r1",
                    judgment=dict(categories=["permission"], note=""),
                )
            ).encode(),
            headers={
                "Content-Type": "application/json",
                "X-Study-Token": state["token"],
            },
        )
        with urlopen(request) as response:
            self.assertTrue(json.load(response)["saved"])
        with self.assertRaises(HTTPError) as caught:
            urlopen(
                Request(self.base + "/api/study", headers={"Host": "external.invalid"})
            )
        self.assertEqual(caught.exception.code, 403)

    def test_forwarded_local_port_keeps_origin_boundary_and_download_headers(self):
        with urlopen(Request(self.base + "/api/export", headers={"Host": "localhost:55555"})) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers["Content-Disposition"], 'attachment; filename="policy-study.json"')
        for headers in (
            {"Host": "localhost:55555", "Origin": "http://localhost:44444"},
            {"Host": "localhost:55555", "Origin": "https://external.invalid"},
            {"Host": "external.invalid:55555", "X-Forwarded-Host": "localhost:55555"},
            {"Host": "localhost:65536"},
            {"Host": "localhost:55555@external.invalid"},
        ):
            with self.assertRaises(HTTPError) as caught:
                urlopen(Request(self.base + "/api/export", headers=headers))
            self.assertEqual(caught.exception.code, 403)
