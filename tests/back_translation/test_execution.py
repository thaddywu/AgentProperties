import json
import unittest
from copy import deepcopy

from policyweave.policy_viewer.alignment import align_execution
from policyweave.back_translation.execution import (
    describe_execution,
    split_direct_permissions,
)
from policyweave.back_translation.workflow import describe_checks, execution_workflow, validate_presentation


class ExecutionTests(unittest.TestCase):
    def test_independent_description_repair_and_separate_alignment(self):
        rules = [dict(id="r1", datalog='Allow(Q) :- Request(Q, "student", "read").')]
        evidence = {"adapter.py": "def observe(): return []"}
        binding = dict(predicates={}, decision={})
        procedure = dict(
            id="read",
            title="Read a document",
            summary="Records: The gate reads the runtime caller and requested action.",
            ruleIds=["r1"],
            reads=[dict(text="The caller", source="runtime identity")],
            steps=[
                dict(indent=0, text="Rules: A student read request derives Allow; a missing grant refuses entry."),
            ],
            evidence=[dict(file="adapter.py", quote="def observe(): return []")],
        )
        calls, records = [], []
        chain = dict(
            id="read",
            title="Read a document",
            ruleIds=["r1"],
            reads=procedure["reads"],
            conditions=["The caller is the student."],
            branches=[
                dict(
                    ruleIds=["r1"],
                    condition="Student requests read.",
                    outcome="Permit this branch.",
                )
            ],
            enforcement="Check before reading.",
            dependencies=[],
            gaps=[],
            evidence=procedure["evidence"],
        )

        def generate(stage, prompt):
            calls.append((stage, prompt))
            if stage == "execution-reconstruction":
                self.assertNotIn("PRIVATE_POLICY_INTENT", prompt)
                candidate = deepcopy(chain)
                if len(calls) == 1:
                    candidate["evidence"] = [
                        dict(file="adapter.py", quote="invented evidence")
                    ]
                return json.dumps(
                    dict(checks=[candidate], limitations=[], unresolvedInputs=[])
                )
            if stage == "execution-description":
                self.assertNotIn("PRIVATE_POLICY_INTENT", prompt)
                self.assertNotIn('"implementation"', prompt)
                return json.dumps(dict(procedures=[procedure]))
            self.assertIn("PRIVATE_POLICY_INTENT", prompt)
            self.assertNotIn("def observe", prompt)
            return json.dumps(
                dict(
                    links=[
                        dict(sentenceId="s1", procedureIds=["read"]),
                        dict(sentenceId="s2", procedureIds=[]),
                    ]
                )
            )

        procedures = describe_execution(
            rules, binding, evidence, generate, records.append
        )
        # The alignment pass needs descriptions, not their implementation citations.
        aligned = align_execution(
            [
                dict(id="s1", quote="PRIVATE_POLICY_INTENT"),
                dict(id="s2", quote="Unmapped"),
            ],
            procedures,
            generate,
        )
        self.assertEqual(aligned[1]["procedureIds"], [])
        self.assertIn("error", records[0])
        self.assertEqual(len(calls), 4)

    def test_presentation_cannot_reassign_checks_or_replace_frozen_evidence(self):
        rules = [dict(id="r1", datalog='Allow(Q) :- Request(Q, "student", "read").')]
        evidence = {"adapter.py": "check before read"}
        chain = dict(
            id="read",
            title="Read",
            ruleIds=["r1"],
            reads=[],
            conditions=["Student caller"],
            branches=[],
            enforcement="Before read",
            dependencies=["Original tool may fail."],
            gaps=["Identity is supplied."],
            evidence=[dict(file="adapter.py", quote="check before read")],
        )
        published, attempts = {}, []
        presentation_calls = 0

        def generate(stage, prompt):
            nonlocal presentation_calls
            if stage == "execution-reconstruction":
                return json.dumps(
                    dict(checks=[chain], limitations=[], unresolvedInputs=[])
                )
            self.assertNotIn('"privatePlan"', prompt)
            presentation_calls += 1
            return json.dumps(
                dict(
                    procedures=[
                        dict(
                            id="invented" if presentation_calls == 1 else "read",
                            title="Read",
                            summary="Records: The gate reads the supplied caller role before the read.",
                            ruleIds=["invented"],
                            evidence=[dict(file="fake", quote="fake")],
                            steps=[
                                dict(
                                    text="x" * 361
                                    if presentation_calls == 2
                                    else "Rules: The student role derives Allow; no grant refuses entry."
                                )
                            ],
                            examples=[],
                        )
                    ]
                )
            )

        reading = execution_workflow(
            rules,
            dict(privatePlan="excluded"),
            evidence,
            generate,
            attempts.append,
            lambda n, v: published.update({n: v}),
        )
        self.assertEqual(reading["procedures"][0]["ruleIds"], ["r1"])
        self.assertEqual(reading["procedures"][0]["evidence"], chain["evidence"])
        self.assertEqual(published["workflow.json"]["status"], "verified")
        self.assertEqual(published["checks.json"]["checks"][0]["gaps"], chain["gaps"])
        self.assertEqual(sum("error" in entry for entry in attempts), 2)

    def test_failed_reconstruction_never_reaches_presentation(self):
        published, calls = {}, []

        def generate(stage, prompt):
            calls.append(stage)
            return "{}"

        with self.assertRaises(ValueError):
            execution_workflow(
                [], {}, {}, generate, publish=lambda n, v: published.update({n: v})
            )
        self.assertEqual(calls, ["execution-reconstruction"] * 3)
        self.assertEqual(published["workflow.json"]["status"], "failed")
        self.assertNotIn("backtranslation.json", published)

    def test_presentation_uses_frozen_conditions_and_host_owned_evidence(self):
        rules = [dict(id="r1", datalog='Allow(Q) :- Request(Q,"student","read"), Field(Q,"owner","student").')]
        evidence = {"adapter.py": "read owner before returning data"}
        chains = dict(checks=[dict(
            id="read", title="Read own data", ruleIds=["r1"], reads=[],
            conditions=["The requested owner is the student."], branches=[],
            enforcement="Check before the read.", dependencies=[],
            gaps=["Messages are not inspected."],
            evidence=[dict(file="adapter.py", quote=evidence["adapter.py"])],
        )], limitations=[], unresolvedInputs=[])
        frozen = deepcopy(chains)
        attempts, calls = [], []

        def generate(stage, prompt):
            payload = json.loads(prompt.split("\nRepair this candidate:", 1)[0])
            self.assertNotIn("implementation", payload)
            self.assertEqual(payload["checks"][0]["conditions"], frozen["checks"][0]["conditions"])
            self.assertNotIn("evidence", payload["checks"][0])
            self.assertNotIn("ruleIds", payload["checks"][0])
            self.assertEqual(payload["limitations"], frozen["limitations"])
            self.assertEqual(set(payload["predicates"]), {"Allow", "Deny", "Request", "Parameter", "Field"})
            calls.append(stage)
            return json.dumps(dict(procedures=[dict(
                id="invented" if len(calls) == 1 else "read", title="Read own data",
                summary="Records: The read gate records the caller and requested owner.",
                steps=[dict(text='Rules: Field(Q,"owner","student") is required for Allow; missing ownership blocks the read. Messages are not inspected.')],
                examples=[],
            )]))

        result = describe_checks(chains, rules, evidence, generate, attempts.append)
        self.assertIn("check IDs", attempts[0]["error"])
        self.assertEqual(chains, frozen)
        self.assertEqual(result[0]["evidence"], frozen["checks"][0]["evidence"])
        self.assertIn("Messages are not inspected", result[0]["steps"][0]["text"])

    def test_presentation_does_not_impose_word_count_or_short_title_limits(self):
        rules = [dict(id="r1", datalog='Allow(Q) :- Request(Q,"student","read"), Approval(Q).')]
        evidence = {"adapter.py": "check before read"}
        chains = dict(checks=[dict(
            id="read", title="Read", ruleIds=["r1"], reads=[],
            evidence=[dict(file="adapter.py", quote=evidence["adapter.py"])],
        )])
        row = dict(id="read", title="Approval for the job before the dispatch call", summary="Records: The gate reads the request.",
                   steps=[dict(text="Rules: Approval(Q) is required for Allow; missing evidence blocks the read.")], examples=[])
        validate_presentation(dict(procedures=[row]), chains, rules, evidence)
        oversized = deepcopy(row)
        oversized["summary"] = "Records: " + "fact " * 59
        oversized["steps"] = [dict(text="Rules: " + "match " * 57)]
        validate_presentation(dict(procedures=[oversized]), chains, rules, evidence)

    def test_interrupt_retains_failed_workflow_without_publishing_reading(self):
        published = {}

        def generate(stage, prompt):
            raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            execution_workflow(
                [],
                {},
                {},
                generate,
                publish=lambda name, value: published.update({name: value}),
            )
        self.assertEqual(published["workflow.json"]["status"], "failed")
        self.assertNotIn("backtranslation.json", published)

    def test_permission_split_and_thresholds_do_not_strengthen_denial(self):
        rules = [
            dict(id="read", datalog='Allow(Q) :- Request(Q, "student", "read").'),
            dict(id="write", datalog='Allow(Q) :- Request(Q, "student", "write").'),
            dict(
                id="limit",
                datalog='Deny(Q, "limit") :- Request(Q, "student", "write"), Size(N), N > 8.',
            ),
        ]
        procedures = [
            dict(id="permissions", ruleIds=["read", "write"], evidence=[], reads=[]),
            dict(
                id="limit",
                ruleIds=["limit"],
                evidence=[],
                reads=[],
                steps=[
                    dict(indent=0, text="refuse if a recorded size is greater than 8")
                ],
            ),
        ]
        result = split_direct_permissions(
            procedures, rules, {"rules.dl": "\n".join(r["datalog"] for r in rules)}
        )
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["ruleIds"], ["read"])
        self.assertEqual(result[1]["ruleIds"], ["write"])
        self.assertEqual(result[2]["steps"], procedures[1]["steps"])
        self.assertEqual(
            result[2]["reads"][-1],
            dict(text="Fixed comparison values: 8", sources=["rule constant"]),
        )
