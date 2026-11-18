from copy import deepcopy
import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from policyweave.analysis.answers import render_answer
from policyweave.analysis.log_query import LogQuerySession, project
from policyweave.analysis.timeline import Timeline


class QuestionTranslationTests(unittest.TestCase):
    def setUp(self):
        self.value = json.loads(
            (
                Path(__file__).resolve().parents[2]
                / "examples/trajectories/team-review.json"
            ).read_text()
        )
        self.value["analysis"] = project(Timeline(self.value))
        self.template = self.value["analysis"]["templates"][2]
        self.template["answer"] = dict(
            en=dict(
                summary="Found {count} recorded events.",
                row="Event {E}.",
                empty="No recorded events match; delivery is not inferred.",
            ),
            zh=dict(
                summary="找到 {count} 条记录。",
                row="事件 {E}。",
                empty="没有匹配记录；不能推断是否实际送达。",
            ),
        )
        self.session = LogQuerySession(Timeline(self.value))

    def test_translation_compiles_template_without_executing_or_revealing_answers(self):
        calls = []

        def model(stage, prompt):
            calls.append(json.loads(prompt))
            return json.dumps(
                dict(templateId="recipient-events", parameters=dict(recipient="master"))
            )

        with patch(
            "policyweave.core.datalog.Souffle",
            side_effect=AssertionError("Translation must not evaluate facts."),
        ):
            plan = self.session.translate("哪些事件的接收者是 master？", model)
        self.assertEqual(plan["status"], "ready")
        self.assertEqual(plan["query"], '?- Recipient(E,"master").')
        self.assertNotIn("rows", plan)
        self.assertNotIn("inputs", calls[0])
        self.assertNotIn("answer", calls[0]["examples"][2])
        self.assertNotIn("Found {count}", json.dumps(calls[0]))

    def test_known_entities_are_quoted_and_unknown_parameters_rejected(self):
        for values in [
            {},
            dict(recipient="unknown"),
            dict(recipient="master", extra="x"),
        ]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.session.prepare("recipient-events", values)
        attack = 'value"), Observed(X). ?- Observed(X). //'
        contract = deepcopy(self.value["analysis"])
        contract["entities"]["participants"].append(attack)
        self.value["analysis"] = contract
        session = LogQuerySession(Timeline(self.value))
        plan = session.prepare("recipient-events", dict(recipient=attack))
        self.assertEqual(plan["query"], "?- Recipient(E," + json.dumps(attack) + ").")

    def test_answer_wording_and_code_cannot_be_supplied_by_the_model(self):
        attempts = []
        with self.assertRaises(ValueError):
            self.session.translate(
                "Recipients?",
                lambda *_: json.dumps(
                    dict(
                        templateId="recipient-events",
                        parameters=dict(recipient="master"),
                        answer="Everything is safe.",
                    )
                ),
                attempts.append,
            )
        self.assertEqual(len(attempts), 3)
        self.assertTrue(all("error" in a for a in attempts))

    def test_answer_templates_reject_undeclared_fields_and_format_expressions(self):
        for row in ["{Unknown}", "{E.__class__}", "{E[0]}", "{E!r}", "{E:1000000000}"]:
            value = deepcopy(self.value)
            value["analysis"]["templates"][2]["answer"]["en"]["row"] = row
            with self.subTest(row=row), self.assertRaises(ValueError):
                Timeline(value)

    def test_prepared_queries_are_bound_to_document_and_template(self):
        plan = self.session.prepare("recipient-events", dict(recipient="master"))
        for changed in [
            dict(plan, trajectoryId="other"),
            dict(plan, query="?- Observed(E)."),
        ]:
            with self.assertRaises(ValueError):
                self.session.answer(changed)

    def test_empty_boolean_and_truncated_answers_keep_the_evidence_scope(self):
        base = dict(
            rows=[],
            columns=["E"],
            columnLabels=["Observed.E"],
            eventIds=[],
            scope="Only recorded events.",
        )
        self.assertIn("不能证明", render_answer(base, question="政策？")["summary"])
        true = render_answer(dict(base, columns=[], rows=[[]]))
        false = render_answer(dict(base, columns=[], rows=[]))
        self.assertIn("query holds", true["summary"])
        self.assertIn("does not hold", false["summary"])
        result = render_answer(dict(base, rows=[[str(n)] for n in range(25)]))
        self.assertTrue(result["truncated"])
        self.assertEqual(len(result["items"]), 20)
        self.assertIn("25", result["summary"])
        self.assertEqual(result["scope"], base["scope"])

    @unittest.skipUnless(
        shutil.which("souffle") and shutil.which("prlimit"), "Native query required"
    )
    def test_one_model_translation_then_deterministic_bilingual_answer(self):
        calls = []

        def model(stage, prompt):
            calls.append(stage)
            return json.dumps(
                dict(templateId="recipient-events", parameters=dict(recipient="master"))
            )

        plan = self.session.translate("哪些事件的接收者是 master？", model)
        result = self.session.answer(plan)
        self.assertEqual(result["rowCount"], 2)
        self.assertEqual(result["answer"]["summary"], "找到 2 条记录。")
        self.assertEqual(calls, ["analysis-query"])
        self.assertEqual(result["answer"]["source"], "deterministic-template")
        self.assertEqual(self.session.timeline.export(), self.value)
        offline = self.session.answer(
            self.session.prepare("recipient-events", dict(recipient="master"))
        )
        self.assertEqual(offline["answer"]["summary"], "Found 2 recorded events.")
