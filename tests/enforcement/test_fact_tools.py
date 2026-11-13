"""Policy-authorized input writes cannot mint their own authority or overwrite."""

from pathlib import Path
import asyncio
import importlib.util
import json
import shutil
import tempfile
import unittest

from policyscope.enforcement import FactTool, Policy

RULES = """.decl Assigned(Op:symbol, Reviewer:symbol)
.input Assigned
Assigned("move-a", "arbiter").
.decl Approval(Op:symbol, Issuer:symbol, Decision:symbol)
.input Approval
.key Approval(Op, Issuer)
.decl Finished(Op:symbol)
.input Finished
.key Finished(Op)
Allow(Q) :- Request(Q, P, "put"), Parameter(Q, "predicate", "Approval"), Parameter(Q, "Op", O), Assigned(O, P), Parameter(Q, "Issuer", P), Parameter(Q, "Decision", "allow").
Allow(Q) :- Request(Q, P, "delete"), Parameter(Q, "predicate", "Approval"), Parameter(Q, "Op", O), Approval(O, P, D), Parameter(Q, "Issuer", P), Parameter(Q, "Decision", D), not Finished(O).
Allow(Q) :- Request(Q, P, "move"), Parameter(Q, "Op", O), Approval(O, "arbiter", "allow").
"""


@unittest.skipUnless(shutil.which("souffle"), "Native engine required")
class FactToolTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        path = Path(self.temporary.name) / "rules.dl"
        path.write_text(RULES)
        self.policy = Policy(path, local_effects=True)
        self.tool = FactTool(self.policy, principal="arbiter", predicates=["Approval"])

    def tearDown(self):
        self.temporary.cleanup()

    def approvals(self):
        return self.policy.runtime.query("?- Approval(O, I, D).")["rows"]

    def test_predicate_row_issuer_and_delete_permissions_are_independent(self):
        for values in (["move-b", "arbiter", "allow"], ["move-a", "other", "allow"]):
            self.assertFalse(self.tool.put("Approval", values).get("recorded", False))
        with self.assertRaises(ValueError):
            self.tool.put("Finished", ["move-a"])
        self.assertTrue(
            self.tool.put("Approval", ["move-a", "arbiter", "allow"])["changed"]
        )
        self.assertFalse(
            self.tool.put("Approval", ["move-a", "arbiter", "allow"])["changed"]
        )
        other = FactTool(self.policy, principal="other", predicates=["Approval"])
        self.assertFalse(
            other.delete("Approval", ["move-a", "arbiter", "allow"]).get(
                "recorded", False
            )
        )
        self.policy.put("Finished", "move-a")
        self.assertFalse(
            self.tool.delete("Approval", ["move-a", "arbiter", "allow"]).get(
                "recorded", False
            )
        )
        self.assertEqual(self.approvals(), [["move-a", "arbiter", "allow"]])

    def test_delete_cannot_remove_different_tuple_with_same_key_and_audit_remains(self):
        self.tool.put("Approval", ["move-a", "arbiter", "allow"])
        self.assertFalse(
            self.tool.delete("Approval", ["move-a", "arbiter", "deny"]).get(
                "recorded", False
            )
        )
        before = len(self.policy.events)
        self.assertTrue(
            self.tool.delete("Approval", ["move-a", "arbiter", "allow"])["recorded"]
        )
        self.assertEqual(self.approvals(), [])
        self.assertGreater(len(self.policy.events), before)

    def test_put_is_not_upsert_even_when_both_values_are_authorized(self):
        # This host fixture lets the new request pass the gate; conflict handling
        # must still prevent implicit update of a keyed current record.
        self.policy.put("Approval", "move-a", "arbiter", "deny")
        result = self.tool.put("Approval", ["move-a", "arbiter", "allow"])
        self.assertEqual(result["reason"], "key_conflict")
        self.assertEqual(self.approvals(), [["move-a", "arbiter", "deny"]])

    def test_proposed_fact_does_not_authorize_its_own_insertion(self):
        path = Path(self.temporary.name) / "self.dl"
        path.write_text(""".decl Approval(Op:symbol, Issuer:symbol, Decision:symbol)
.input Approval
.key Approval(Op, Issuer)
Allow(Q) :- Request(Q, P, "put"), Approval("move-a", P, "allow").
""")
        policy = Policy(path, local_effects=True)
        tool = FactTool(policy, principal="arbiter", predicates=["Approval"])
        self.assertFalse(
            tool.put("Approval", ["move-a", "arbiter", "allow"]).get("recorded", False)
        )
        self.assertEqual(policy.runtime.query("?- Approval(O,I,D).")["rows"], [])

    def test_core_derived_and_static_inputs_cannot_be_exposed(self):
        for name in ("Request", "Allow", "Assigned"):
            with self.assertRaises(ValueError):
                FactTool(self.policy, principal="arbiter", predicates=[name])
        observer = Policy(
            Path(self.temporary.name) / "rules.dl", facts=lambda *args: []
        )
        with self.assertRaises(ValueError):
            FactTool(observer, principal="arbiter", predicates=["Approval"])

    @unittest.skipUnless(importlib.util.find_spec("mcp"), "Optional MCP SDK required")
    def test_real_mcp_put_delete_keep_principal_bound_and_enforce_rows(self):
        from mcp.server.fastmcp import FastMCP
        from mcp.shared.memory import create_connected_server_and_client_session

        server = FastMCP("fact-writes")
        self.tool.register_mcp(server)

        async def exercise():
            async with create_connected_server_and_client_session(
                server._mcp_server
            ) as client:
                tools = await client.list_tools()
                self.assertEqual({t.name for t in tools.tools}, {"put", "delete"})
                allowed = await client.call_tool(
                    "put",
                    dict(predicate="Approval", values=["move-a", "arbiter", "allow"]),
                    meta={"caller": "administrator"},
                )
                self.assertFalse(allowed.isError)
                self.assertEqual(self.approvals(), [["move-a", "arbiter", "allow"]])
                denied = await client.call_tool(
                    "put",
                    dict(
                        predicate="Approval",
                        values=["move-a", "administrator", "allow"],
                    ),
                )
                self.assertFalse(denied.isError, denied.content)
                denied_value = denied.structuredContent or json.loads(
                    denied.content[0].text
                )
                self.assertFalse(denied_value.get("recorded", False))
                missing = await client.call_tool(
                    "delete", dict(predicate="Approval", values=["move-a"])
                )
                self.assertTrue(missing.isError)
                deleted = await client.call_tool(
                    "delete",
                    dict(predicate="Approval", values=["move-a", "arbiter", "allow"]),
                )
                self.assertFalse(deleted.isError)
                self.assertEqual(self.approvals(), [])

        asyncio.run(exercise())
