import json
import unittest

from policy_translation.execution import (
    describe_execution,
    align_execution,
    split_direct_permissions,
)


class ExecutionTests(unittest.TestCase):
    def test_independent_description_repair_and_separate_alignment(self):
        rules = [dict(id="r1", datalog='Allow(Q) :- Request(Q, "student", "read").')]
        evidence = {"adapter.py": "def observe(): return []"}
        binding = dict(predicates={}, decision={})
        procedure = dict(
            id="read",
            title="Read a document",
            ruleIds=["r1"],
            reads=[dict(text="The caller", source="runtime identity")],
            steps=[
                dict(indent=0, text="when the student requests a read:"),
                dict(indent=1, text="grant permission; other refusals still apply"),
            ],
            evidence=[dict(file="adapter.py", quote="def observe(): return []")],
        )
        calls, records = [], []

        def generate(stage, prompt):
            calls.append((stage, prompt))
            if stage == "execution-description":
                self.assertNotIn("PRIVATE_POLICY_INTENT", prompt)
                candidate = dict(procedure)
                if len(calls) == 1:
                    candidate["evidence"] = [
                        dict(file="adapter.py", quote="invented evidence")
                    ]
                return json.dumps(dict(procedures=[candidate]))
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
        self.assertEqual(len(calls), 3)

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
