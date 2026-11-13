"""Real MCP JSON-RPC calls against a bound declaration endpoint, offline."""

import asyncio
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from policyscope.enforcement import Policy, StatementTool

RULES = """.decl Owned(Subject:symbol, Owner:symbol)
.input Owned
Owned("job-a", "planner").
Owned("job-b", "other").
Allow(Q) :- Request(Q, P, "declare_statement"), Parameter(Q, "subject", S), Owned(S, P).
Allow(Q) :- Request(Q, P, "inspect").
"""


@unittest.skipUnless(shutil.which("souffle"), "Native engine required")
class StatementTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        path = Path(self.directory.name) / "rules.dl"
        path.write_text(RULES)
        self.policy = Policy(path, mechanisms=("statements",), local_effects=True)
        self.tool = StatementTool(
            self.policy, principal="planner", kinds=("classification",)
        )

    def tearDown(self):
        self.directory.cleanup()

    def test_self_claims_update_only_own_key_and_do_not_prove_success(self):
        result = self.tool.declare("classification", "job-a", "safe")
        self.assertTrue(result["recorded"])
        self.tool.declare("classification", "job-a", "uncertain")
        rows = self.policy.runtime.query("?- AgentStatement(I, P, K, S, V).")["rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0][1:], ["planner", "classification", "job-a", "uncertain"]
        )
        before = self.policy.runtime.snapshot()
        for kind in ("Role", "Capability", "VerifiedCompletion", "Request", "Allow"):
            with self.assertRaises(ValueError):
                self.tool.declare(kind, "job-a", "true")
        self.assertEqual(self.policy.runtime.snapshot(), before)
        denied = self.tool.declare("classification", "job-b", "safe")
        self.assertFalse(denied.get("recorded", False))
        self.assertEqual(
            len(self.policy.runtime.query("?- AgentStatement(I,P,K,S,V).")["rows"]), 1
        )
        # A statement saying success is not a verified completion fact or extra permission.
        self.tool.declare("classification", "job-a", "completed successfully")
        self.assertFalse(
            self.policy.runtime.check(
                dict(actor="planner", action="release_resource", parameters={})
            )["allowed"]
        )
        self.assertIn("not proof", self.tool.system_card)

    @unittest.skipUnless(importlib.util.find_spec("mcp"), "Optional MCP SDK required")
    def test_real_mcp_cannot_override_bound_identity_or_predicate(self):
        from mcp.server.fastmcp import FastMCP
        from mcp.shared.memory import create_connected_server_and_client_session

        server = FastMCP("bounded-statements")
        self.tool.register_mcp(server)

        async def exercise():
            async with create_connected_server_and_client_session(
                server._mcp_server
            ) as client:
                tools = await client.list_tools()
                tool = next(t for t in tools.tools if t.name == "declare_statement")
                self.assertEqual(
                    set(tool.inputSchema["properties"]), {"kind", "subject", "value"}
                )
                result = await client.call_tool(
                    "declare_statement",
                    dict(kind="classification", subject="job-a", value="safe"),
                    meta={"caller": "administrator"},
                )
                self.assertFalse(result.isError)
                value = result.structuredContent or json.loads(result.content[0].text)
                self.assertEqual(value["speaker"], "planner")
                denied = await client.call_tool(
                    "declare_statement",
                    dict(kind="Capability", subject="job-a", value="admin"),
                )
                self.assertTrue(denied.isError)
                bad = await client.call_tool(
                    "declare_statement",
                    dict(
                        kind="classification",
                        subject="job-a",
                        value="safe",
                        predicate="Capability",
                        speaker="administrator",
                    ),
                )
                self.assertFalse(bad.isError)
                ignored = bad.structuredContent or json.loads(bad.content[0].text)
                self.assertEqual(ignored["speaker"], "planner")
                self.assertEqual(ignored["evidenceType"], "agent_statement")

        asyncio.run(exercise())
        rows = self.policy.runtime.query("?- AgentStatement(I,P,K,S,V).")["rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][1], "planner")
