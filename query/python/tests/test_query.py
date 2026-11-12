from copy import deepcopy
import json
import shutil
import unittest
from policy_query import QuerySession
from policy_runtime.policy import CORE, fact


@unittest.skipUnless(
    shutil.which("souffle") and shutil.which("prlimit"), "Native Soufflé required"
)
class QueryTests(unittest.TestCase):
    def setUp(self):
        self.binding = dict(
            version=1,
            id="query-test",
            context="Synthetic query binding.",
            predicates=deepcopy(CORE),
            decision=dict(
                request="Request", allow="Allow", deny="Deny", parameters="Parameter"
            ),
            tests=[],
        )
        self.binding["predicates"]["Owner"] = dict(
            kind="input", args=["Document", "Actor"], meaning="Stored document owner."
        )
        self.source = 'Allow(Q) :- Request(Q, A, "read"), Parameter(Q, "document", D), Owner(D, A).'
        self.inputs = [fact("Owner", "d1", "alice")]
        self.session = QuerySession(
            binding=self.binding, source=self.source, inputs=self.inputs
        )

    def test_snapshot_isolation_hypothetical_check_and_no_execution(self):
        self.inputs.clear()
        self.assertEqual(
            self.session.query("?- Owner(D, A).")["rows"], [["d1", "alice"]]
        )
        intent = dict(actor="bob", action="read", parameters={"document": "d1"})
        self.assertFalse(self.session.check(intent)["allowed"])
        self.assertTrue(
            self.session.what_if(intent, [fact("Owner", "d1", "bob")])["allowed"]
        )
        self.assertFalse(self.session.check(intent)["allowed"])
        self.assertFalse(hasattr(self.session, "execute"))

    def test_nl_templates_validate_entities_and_never_execute_model_query(self):
        templates = {
            "owner": dict(
                description="Who owns the document?",
                parameters={"document": "documents"},
                render=lambda p: "?- Owner(" + json.dumps(p["document"]) + ", A).",
            )
        }
        entities = {"documents": ["d1"]}
        result = self.session.ask(
            "Who owns d1?",
            templates,
            entities,
            lambda *_: json.dumps(
                dict(templateId="owner", parameters={"document": "d1"})
            ),
        )
        self.assertEqual(result["result"]["rows"], [["alice"]])
        for value in [
            dict(templateId="owner", parameters={"document": "unknown"}),
            dict(query="malicious query"),
            dict(templateId="unknown", parameters={}),
        ]:
            with self.assertRaises(ValueError):
                self.session.ask(
                    "Question", templates, entities, lambda *_: json.dumps(value)
                )

    def test_queries_cannot_mutate_policy_or_access_unknown_predicates(self):
        for source in ["Allow(Q) :- Request(Q,A,E).", "?- Secret(A)."]:
            with self.assertRaises(ValueError):
                self.session.query(source)
