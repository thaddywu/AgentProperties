import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from policy_runtime.policy import CORE, read_binding
from policy_translation import TranslationFailure, translate, validate_requirements
from policy_translation.adapters.compatible import Connection


def binding():
    return read_binding(
        dict(
            version=1,
            id="translation-test",
            context="Synthetic test binding.",
            predicates=CORE,
            decision=dict(
                request="Request", allow="Allow", deny="Deny", parameters="Parameter"
            ),
            tests=[],
        )
    )


def requirement(quote, **changes):
    return dict(
        dict(
            id="r1",
            quote=quote,
            statement="Permit reading.",
            implementation="datalog",
            relation="equivalent",
            categories=["permission"],
            assumptions=[],
            predicates=["Request", "Allow"],
        ),
        **changes,
    )


class TranslationTests(unittest.TestCase):
    def test_roundtrip_mapping_repair_and_independent_backtranslation(self):
        original = "UNIQUE_SOURCE_SECRET: permit reading."
        records = []
        rules_calls = 0

        def generate(stage, prompt):
            nonlocal rules_calls
            self.assertNotIn('"tests"', prompt)
            self.assertNotIn("HOLDOUT_SECRET", prompt)
            if stage == "requirements":
                return json.dumps({"requirements": [requirement(original)]})
            if stage == "rules":
                rules_calls += 1
                return json.dumps(
                    {
                        "rules": [
                            {
                                "id": "allow_read",
                                "datalog": 'Allow(Q) :- Request(Q, A, "read").',
                            }
                        ],
                        "coverage": []
                        if rules_calls == 1
                        else [{"id": "r1", "ruleIds": ["allow_read"]}],
                    }
                )
            self.assertNotIn("UNIQUE_SOURCE_SECRET", prompt)
            return json.dumps(
                {
                    "behaviors": [
                        {
                            "id": "read",
                            "ruleIds": ["allow_read"],
                            "summary": "Reading is permitted.",
                            "conditions": [],
                        }
                    ]
                }
            )

        trusted = binding()
        trusted["tests"] = [
            dict(
                name="HOLDOUT_SECRET-positive",
                inputs=[],
                request=dict(actor="a", action="read"),
                allowed=True,
            ),
            dict(
                name="HOLDOUT_SECRET-negative",
                inputs=[],
                request=dict(actor="a", action="write"),
                allowed=False,
            ),
        ]
        review = translate(original, trusted, generate, record=records.append)
        self.assertEqual(review["behaviors"][0]["requirementIds"], ["r1"])
        self.assertEqual(len(records), 4)
        self.assertIn("unreferenced", records[1]["error"])
        self.assertFalse(review["runtimeInstalled"])

    def test_unicode_offsets_and_omitted_text(self):
        source = "😀 Read. Do not reveal private text."
        rows, omitted = validate_requirements(
            {"requirements": [requirement("😀 Read.")]}, source, binding()
        )
        self.assertEqual(rows[0]["end"], 7)
        self.assertEqual(source[rows[1]["start"] : rows[1]["end"]], rows[1]["quote"])
        self.assertEqual(omitted, [rows[1]["id"]])
        self.assertEqual(rows[1]["implementation"], "ambiguous")

    def test_input_writes_rejected_and_failure_retained(self):
        def generate(stage, prompt):
            if stage == "requirements":
                return json.dumps({"requirements": [requirement("Read.")]})
            return json.dumps(
                {
                    "rules": [
                        {
                            "id": "bad",
                            "datalog": "Request(Q, A, E) :- Request(Q, A, E).",
                        }
                    ],
                    "coverage": [{"id": "r1", "ruleIds": ["bad"]}],
                }
            )

        with self.assertRaises(TranslationFailure) as caught:
            translate("Read.", binding(), generate)
        self.assertEqual(len(caught.exception.attempts), 3)
        self.assertIn("write inputs", str(caught.exception))

    def test_transport_failure_does_not_retry_or_leak_exception(self):
        calls = []

        def generate(*args):
            calls.append(1)
            raise RuntimeError("secret-token-must-not-leak")

        with self.assertRaises(TranslationFailure) as caught:
            translate("Read.", binding(), generate)
        self.assertEqual(len(calls), 1)
        self.assertNotIn("secret-token", str(caught.exception.attempts))

    def test_ambiguous_repeated_quote_and_false_mechanism_rejected(self):
        with self.assertRaises(ValueError):
            validate_requirements(
                {"requirements": [requirement("aa")]}, "aaa", binding()
            )
        with self.assertRaises(ValueError):
            validate_requirements(
                {"requirements": [requirement("Read.")]}, "Read. Read.", binding()
            )
        with self.assertRaises(ValueError):
            validate_requirements(
                {
                    "requirements": [
                        requirement(
                            "Read.", implementation="mechanism", mechanism="fsm"
                        )
                    ]
                },
                "Read.",
                binding(),
            )

    def test_empty_targets_make_no_rule_or_backtranslation_calls(self):
        stages = []

        def generate(stage, prompt):
            stages.append(stage)
            return json.dumps(
                {
                    "requirements": [
                        requirement(
                            "Eventual progress.",
                            implementation="unsupported",
                            relation="unresolved",
                            categories=["other"],
                            predicates=[],
                            assumptions=[
                                "A snapshot check cannot guarantee eventual progress."
                            ],
                        )
                    ]
                }
            )

        review = translate("Eventual progress.", binding(), generate)
        self.assertEqual(stages, ["requirements"])
        self.assertEqual(review["behaviors"][0]["kind"], "gap")


class ConnectionTests(unittest.TestCase):
    def test_local_compatible_transport_and_redacted_usage(self):
        captured = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                captured.append(
                    json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                )
                raw = json.dumps(
                    {
                        "choices": [
                            {"finish_reason": "stop", "message": {"content": "{}"}}
                        ],
                        "usage": {
                            "prompt_tokens": 3,
                            "completion_tokens": 2,
                            "secret": "do not retain",
                        },
                    }
                ).encode()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = Connection(
                dict(
                    baseUrl=f"http://127.0.0.1:{server.server_port}/v1",
                    modelId="fake-local-model",
                    reasoningEffort="high",
                )
            )
            self.assertEqual(connection("requirements", "prompt"), "{}")
            self.assertNotIn("secret", str(connection.usage))
            self.assertEqual(captured[0]["model"], "fake-local-model")
            self.assertEqual(captured[0]["reasoning_effort"], "high")
            self.assertEqual(connection.metadata["reasoningEffort"], "high")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_nonlocal_cleartext_and_url_credentials_rejected(self):
        for url in [
            "http://example.invalid/v1",
            "https://user:password@example.invalid/v1",
        ]:
            with self.assertRaises(ValueError):
                Connection(dict(baseUrl=url, modelId="fake"))
