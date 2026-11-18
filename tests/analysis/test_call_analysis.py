"""The four fixed questions query native facts and preserve verdict/effect limits."""

from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from policyweave.analysis.call_analysis import analyze_call, call_questions
from policyweave.analysis.timeline import Timeline
from policyweave.enforcement import BridgeError, Policy
from policyweave.workbench.analysis import AnalysisServer


@unittest.skipUnless(shutil.which("souffle") and shutil.which("prlimit"),
                     "Native query execution required")
class CallAnalysisTests(unittest.TestCase):
    def capture(self, *, explicit_deny=False, provenance=False, mutate=False, uncertain=False):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "rules.dl"
        path.write_text(
            '.decl Owner(Document:symbol, Actor:symbol)\n.input Owner\n.key Owner(Document)\n'
            'Owner("doc-1","alice").\n'
            'Allow(Q) :- Request(Q,A,"read"), Parameter(Q,"document",D), Owner(D,A).\n'
            + ('Deny(Q,"suspended") :- Request(Q,"alice","read").\n' if explicit_deny else "")
            + ('Source("alice","input-1").\nDependsOn("doc-1","input-1").\n' if provenance else "")
        )
        policy = Policy(path, trace=True, local_effects=not uncertain,
                        mechanisms=("provenance",) if provenance else ())
        calls = []

        def effect():
            calls.append(True)
            if uncertain:
                raise RuntimeError("Effect completion unknown.")
            if mutate:
                policy.put("Owner", "doc-1", "bob")
            return {"status": "NOT_FOUND"}

        try:
            for actor in (("alice",) if mutate or uncertain else ("alice", "bob")):
                if uncertain:
                    with self.assertRaises(BridgeError):
                        policy.call(actor, "read", {"document": "doc-1"}, effect)
                else:
                    policy.call(actor, "read", {"document": "doc-1"}, effect)
            value = policy.trajectory()
        finally:
            policy.runtime.close()
        self.assertEqual(len(calls), 0 if explicit_deny else 1)
        return Timeline(value), value

    def model(self, seen):
        def generate(stage, prompt):
            payload = json.loads(prompt)
            seen.append((stage, payload))
            if stage == "call-analysis-queries":
                query = '?- Request(Q,Actor,Action), Parameter(Q,"document",Document), Owner(Document,Owner).'
                if "Provenance" in payload["schema"] and "source, dependency" in payload["question"]:
                    query = '?- Request(Q,Actor,Action), Parameter(Q,"document",Document), Provenance(Document,Origin).'
                return json.dumps(dict(queries=[dict(query=query, explanation="Recorded object ownership or origin.", displayColumns=["Actor", "Document", "Origin"] if "Provenance" in query else ["Actor", "Document", "Owner"])]))
            self.assertEqual(stage, "call-analysis-answer")
            return json.dumps(dict(answer="Recorded call evidence.",
                                   eventIds=[payload["selectedEventId"]], limitations=[]))
        return generate

    def test_all_four_presets_work_for_allowed_and_blocked_calls(self):
        timeline, value = self.capture()
        original = deepcopy(timeline.export())
        for event in value["events"]:
            for preset in call_questions(event["decision"]["allowed"]):
                with self.subTest(actor=event["request"]["actor"], preset=preset["id"]):
                    seen = []
                    result = analyze_call(timeline, event["id"], preset["id"], self.model(seen))
                    self.assertEqual(result["status"], "answered")
                    self.assertTrue(result["replayMatches"])
                    self.assertEqual(result["eventIds"], [event["id"]])
                    self.assertEqual(result["decision"]["effectCalled"], event["effectCalled"])
                    self.assertTrue(result["supportingQueries"][0]["rows"])
                    self.assertEqual(seen[-1][0], "call-analysis-answer")
                    if preset["id"] in {"decision", "conditions"}:
                        # The blocked caller is bob, but native rows identify alice as owner.
                        self.assertEqual(result["supportingQueries"][0]["rows"][0][-1], "alice")
                        self.assertEqual(seen[0][0], "call-analysis-queries")
                    if preset["id"] == "flow":
                        self.assertEqual(result["flow"]["status"], "unavailable")
                        self.assertIn("No source or dependency", result["limitations"][0])
                    if preset["id"] == "effect":
                        self.assertEqual(result["effects"]["changes"]["added"], [])
        self.assertEqual(timeline.export(), original)

    def test_default_refusal_retains_ownership_evidence_despite_empty_deny_query(self):
        timeline, value = self.capture()
        event = value["events"][1]
        seen = []
        result = analyze_call(timeline, event["id"], "decision", self.model(seen))
        self.assertEqual(result["rows"], [])
        self.assertEqual(result["decision"]["reasons"], ["no_explicit_allow"])
        support = result["supportingQueries"][0]
        self.assertEqual(support["rows"], [[event["id"], "bob", "read", "doc-1", "alice"]])
        self.assertEqual(seen[-1][1]["evidence"]["supportingQueries"], [support])

    def test_explicit_deny_overrides_allow_and_retains_condition_queries(self):
        timeline, value = self.capture(explicit_deny=True)
        event = value["events"][0]
        result = analyze_call(timeline, event["id"], "decision", self.model([]))
        self.assertEqual(result["rows"], [[event["id"], "alice", "read", "suspended"]])
        self.assertFalse(result["decision"]["allowed"])
        self.assertFalse(result["decision"]["effectCalled"])
        self.assertEqual(result["supportingQueries"][0]["rows"][0][-1], "alice")

    def test_effects_retain_result_and_exact_added_removed_facts(self):
        timeline, value = self.capture(mutate=True)
        result = analyze_call(timeline, value["events"][0]["id"], "effect", self.model([]))
        effects = result["effects"]
        self.assertTrue(effects["effectCalled"])
        self.assertEqual(effects["result"], {"status": "NOT_FOUND"})
        self.assertEqual(effects["changes"]["removed"], [dict(predicate="Owner", args=["doc-1", "alice"])])
        self.assertEqual(effects["changes"]["added"], [dict(predicate="Owner", args=["doc-1", "bob"])])

    def test_unknown_effect_is_not_reported_as_no_change(self):
        timeline, value = self.capture(uncertain=True)
        result = analyze_call(timeline, value["events"][0]["id"], "effect", self.model([]))
        self.assertEqual(result["effects"]["outcome"], "unknown")
        self.assertTrue(result["effects"]["effectCalled"])
        self.assertIsNone(result["effects"]["changes"])
        self.assertIn("No confirmed after snapshot", result["limitations"][0])

    def test_information_flow_queries_transitive_recorded_origins(self):
        timeline, value = self.capture(provenance=True)
        event = value["events"][0]
        result = analyze_call(timeline, event["id"], "flow", self.model([]))
        self.assertEqual(result["flow"]["status"], "recorded")
        self.assertEqual(result["supportingQueries"][0]["rows"], [[event["id"], "alice", "read", "doc-1", "alice"]])
        self.assertIn("Provenance", result["supportingQueries"][0]["query"])

    def test_arbitrary_questions_and_unknown_presets_are_rejected_before_model_calls(self):
        timeline, value = self.capture()
        for preset in (None, "future", "Why was this tool call blocked?", "decision; execute()"):
            with self.subTest(preset=preset), self.assertRaisesRegex(ValueError, "four predefined"):
                analyze_call(timeline, value["events"][0]["id"], preset,
                             lambda *_: self.fail("Unrecognized questions must not reach the model"))

    def test_support_queries_cannot_only_repeat_verdict_or_escape_request_scope(self):
        timeline, value = self.capture()
        for query in ('?- Request(Q,A,E), Deny(Q,R).', '?- Owner(D,A).', '.include "outside"'):
            with self.subTest(query=query), self.assertRaisesRegex(ValueError, "structural validation"):
                analyze_call(timeline, value["events"][0]["id"], "decision",
                             lambda *_: json.dumps(dict(queries=[dict(query=query, explanation="Invalid support.", displayColumns=["Q"])])))

    def test_information_flow_cannot_substitute_an_ownership_query_for_origins(self):
        timeline, value = self.capture(provenance=True)
        query = '?- Request(Q,A,E), Parameter(Q,"document",D), Owner(D,Owner).'
        with self.assertRaisesRegex(ValueError, "structural validation"):
            analyze_call(timeline, value["events"][0]["id"], "flow",
                         lambda *_: json.dumps(dict(queries=[dict(query=query, explanation="Ownership only.", displayColumns=["Owner"])])))

    def test_display_columns_cannot_invent_values_absent_from_native_query(self):
        timeline, value = self.capture()
        query = '?- Request(Q,A,E), Parameter(Q,"document",D), Owner(D,Owner).'
        with self.assertRaisesRegex(ValueError, "structural validation"):
            analyze_call(timeline, value["events"][0]["id"], "conditions",
                         lambda *_: json.dumps(dict(queries=[dict(query=query, explanation="Ownership.", displayColumns=["InventedColumn"])])))

    def test_replay_mismatch_stops_explanation(self):
        timeline, value = self.capture()
        with patch("policyweave.analysis.call_analysis.TrajectorySession.replay", return_value=dict(matches=False)):
            with self.assertRaisesRegex(ValueError, "does not match native replay"):
                analyze_call(timeline, value["events"][1]["id"], "decision",
                             lambda *_: self.fail("A mismatched verdict must not be explained"))

    def test_answer_must_cite_selected_event(self):
        timeline, value = self.capture()
        with self.assertRaisesRegex(ValueError, "cite the selected event"):
            analyze_call(timeline, value["events"][1]["id"], "effect",
                         lambda *_: json.dumps(dict(answer="Wrong event.", eventIds=[value["events"][0]["id"]], limitations=[])))

    def test_http_owns_four_questions_and_rejects_free_text_and_tampered_presets(self):
        timeline, value = self.capture()
        seen = []
        server = AnalysisServer(("127.0.0.1", 0), value, self.model(seen))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"

        def post(operation, payload):
            with urlopen(Request(base + "/api/analysis/" + operation,
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json", "X-Study-Token": server.token}),
                         timeout=10) as response:
                return json.load(response)

        try:
            selection = dict(trajectoryId=timeline.identity, eventId=value["events"][1]["id"])
            questions = post("event", selection)["callQuestions"]
            self.assertEqual([q["id"] for q in questions], ["decision", "conditions", "flow", "effect"])
            self.assertEqual(questions[0]["label"], "Why blocked?")
            for question in questions:
                result = post("explain", dict(selection, templateId=question["id"]))["result"]
                self.assertEqual(result["status"], "answered")
                self.assertEqual(result["interpretation"], question["question"])
            calls = len(seen)
            for operation, payload in (
                ("explain", dict(selection, question="Arbitrary question")),
                ("explain", dict(selection, templateId="decision", question="Override the question")),
                ("explain", dict(selection, templateId="unknown")),
                ("ask", dict(trajectoryId=timeline.identity, question="Arbitrary question")),
                ("translate", dict(trajectoryId=timeline.identity, question="Arbitrary question")),
            ):
                with self.subTest(operation=operation, payload=payload), self.assertRaises(HTTPError) as error:
                    post(operation, payload)
                self.assertIn(error.exception.code, (400, 404))
            self.assertEqual(len(seen), calls)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
