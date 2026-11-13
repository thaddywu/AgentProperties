from copy import deepcopy
import json
from pathlib import Path
import shutil
import unittest

from policyscope.analysis.log_query import LogQuerySession, project
from policyscope.analysis.timeline import Timeline


@unittest.skipUnless(
    shutil.which("souffle") and shutil.which("prlimit"), "Native evaluator required"
)
class LogQueryTests(unittest.TestCase):
    def setUp(self):
        self.value = json.loads(
            (
                Path(__file__).resolve().parents[2]
                / "examples/trajectories/team-review.json"
            ).read_text()
        )
        self.value["events"][0]["content"] = "SYNTHETIC-SECRET-ONLY-IN-FACTS"
        self.timeline = Timeline(self.value)
        self.session = LogQuerySession(self.timeline)

    def test_arbitrary_read_only_join_and_source_isolation(self):
        query = "?- ToolCall(E,C,T), ToolResult(R,C)."
        result = self.session.query(query)
        self.assertEqual(result["rows"], [["c1", "dispatch-1", "dispatch_job", "r1"]])
        self.assertEqual(result["eventIds"], ["c1", "r1"])
        self.assertEqual(
            result["columnLabels"],
            [
                "ToolCall.E",
                "ToolCall.Call / ToolResult.Call",
                "ToolCall.Tool",
                "ToolResult.E",
            ],
        )
        self.assertEqual(self.timeline.export(), self.value)
        self.assertEqual(self.session.query('?- Recipient(E,"master").')["rowCount"], 2)

    def test_question_translator_receives_schema_rules_and_entities_only(self):
        def model(stage, prompt):
            self.assertEqual(stage, "analysis-query")
            payload = json.loads(prompt)
            self.assertNotIn("inputs", payload)
            self.assertNotIn("SYNTHETIC-SECRET-ONLY-IN-FACTS", prompt)
            self.assertEqual(payload["rules"], "Observed(E) :- Event(E,S,K,A).")
            return json.dumps(
                dict(
                    query='?- Content("m1",Text).',
                    explanation="Read the recorded content of m1.",
                )
            )

        result = self.session.ask("What was recorded in m1?", model)
        self.assertEqual(result["rows"], [["SYNTHETIC-SECRET-ONLY-IN-FACTS"]])
        self.assertEqual(result["status"], "answered")

    def test_unsupported_queries_and_structural_repairs_keep_failures(self):
        attempts = []
        calls = []

        def model(stage, prompt):
            calls.append(prompt)
            return (
                json.dumps(dict(query="?- Unknown(X).", explanation="Bad schema"))
                if len(calls) == 1
                else json.dumps(
                    dict(query="?- Observed(E).", explanation="Recorded events")
                )
            )

        result = self.session.ask("List the events.", model, record=attempts.append)
        self.assertEqual(result["rowCount"], 6)
        self.assertIn("error", attempts[0])
        self.assertEqual(len(attempts), 2)
        response = self.session.ask(
            "Prove all future safety.",
            lambda *_: json.dumps(
                dict(unsupported="A finite log does not prove future behavior.")
            ),
        )
        self.assertEqual(response["status"], "unsupported")
        self.assertNotIn("rows", response)
        for query in [
            "Allow(Q) :- Request(Q,A,E).",
            "?- Unknown(X).",
            '.include "host.py"',
            "?- Event(E,S,K,A). ?- Observed(E).",
        ]:
            with self.subTest(query=query), self.assertRaises(ValueError):
                self.session.query(query)

    def test_data_contract_validates_examples_and_does_not_execute_renderers(self):
        value = deepcopy(self.value)
        value["analysis"] = project(self.timeline)
        value["analysis"]["templates"] = [
            dict(id="events", question="List events", query="?- Observed(E).")
        ]
        result = LogQuerySession(Timeline(value)).query("?- Observed(E).")
        self.assertEqual(result["rowCount"], 6)
        value["analysis"]["templates"][0]["render"] = "arbitrary Python"
        with self.assertRaises(ValueError):
            Timeline(value)

    def test_long_content_stays_visible_but_omission_is_explicit_in_query_facts(self):
        value = deepcopy(self.value)
        value["events"][0]["content"] = "x" * 5000
        timeline = Timeline(value)
        session = LogQuerySession(timeline)
        self.assertEqual(len(timeline.event("m1")["content"]), 5000)
        self.assertEqual(session.query("?- Omitted(E,F).")["rows"], [["m1", "content"]])
        self.assertEqual(session.query('?- Content("m1",T).')["rows"], [])
