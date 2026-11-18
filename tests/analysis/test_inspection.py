from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from policyweave.analysis.inspection import inspect
from policyweave.analysis.timeline import Timeline
from policyweave.workbench.analysis import AnalysisServer


EXAMPLE = Path(__file__).resolve().parents[2] / "examples/trajectories/team-review.json"


class InspectionTests(unittest.TestCase):
    def test_server_catalog_only_lists_host_published_logs_without_paths(self):
        value = json.loads(EXAMPLE.read_text())
        log = Timeline(value)
        hidden_value = deepcopy(value)
        hidden_value["title"] = "Private gate attachment"
        hidden = Timeline(hidden_value)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "log.json"
            path.write_text(json.dumps(value))
            hidden_path = Path(directory) / "gate.json"
            hidden_path.write_text(json.dumps(hidden_value))
            server = AnalysisServer(("127.0.0.1", 0))
            server.register_file(path, log)
            server.register_file(hidden_path, hidden, listed=False)
            server.timeline = log
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                response = json.load(urlopen(base + "/api/analysis/logs"))
                self.assertEqual(
                    response, dict(logs=[dict(id=log.identity, title=value["title"])])
                )
                selected = json.load(
                    urlopen(base + "/api/analysis?trace=" + log.identity)
                )
                self.assertEqual(selected["trajectory"]["id"], log.identity)
                with self.assertRaises(HTTPError):
                    urlopen(base + "/api/analysis?trace=" + str(path))
                path.write_text(json.dumps(hidden_value))
                with self.assertRaises(HTTPError):
                    urlopen(base + "/api/analysis?trace=" + log.identity)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def test_plain_log_relations_are_historical_not_fabricated_gate_snapshots(self):
        value = json.loads(EXAMPLE.read_text())
        timeline = Timeline(value)
        with patch(
            "policyweave.core.datalog.Souffle.evaluate",
            side_effect=AssertionError("No implicit evaluation"),
        ):
            result = inspect(timeline, "c1")
        self.assertEqual(result["scope"], "history")
        self.assertIsNone(result["phase"])
        self.assertEqual(result["idbStatus"], "not_recorded")
        self.assertEqual(
            next(g["rows"] for g in result["edb"] if g["name"] == "ToolCall"),
            [["c1", "dispatch-1", "dispatch_job"]],
        )
        self.assertEqual(timeline.export(), value)
        with self.assertRaises(ValueError):
            inspect(timeline, "missing")

    def test_explicit_model_calls_pair_without_losing_export_or_source_order(self):
        value = json.loads(EXAMPLE.read_text())
        value["events"] = [
            dict(
                id="model-1",
                sequence=0,
                kind="llm_call",
                actor="master",
                callId="m",
                arguments=dict(
                    messages=[dict(role="user", content="Review the request.")]
                ),
            ),
            dict(
                id="model-2",
                sequence=1,
                kind="llm_result",
                actor="master",
                callId="m",
                result=dict(summary="Wait for review."),
            ),
        ]
        timeline = Timeline(value)
        events = timeline.describe()["events"]
        self.assertFalse(events[0]["primary"])
        self.assertTrue(events[1]["primary"])
        self.assertEqual(events[0]["relatedEventId"], "model-2")
        self.assertEqual(events[1]["relatedEventId"], "model-1")
        self.assertEqual(events[0]["preview"], "Wait for review.")
        self.assertEqual(events[0]["category"], "model")
        self.assertEqual(timeline.export(), value)
        invalid = deepcopy(value)
        invalid["events"][1]["kind"] = "tool_result"
        with self.assertRaises(ValueError):
            Timeline(invalid)

    def test_legacy_model_output_is_primary_without_exposing_an_extra_decision_card(self):
        value = json.loads(EXAMPLE.read_text())
        value["events"] = [
            dict(id="request", sequence=0, kind="decision", actor="master",
                 data=dict(nativeKind="decision_request", inputs=dict(context={"private": "input"}))),
            dict(id="response", sequence=1, kind="decision", actor="master",
                 data=dict(nativeKind="decision_summary", parents=["request"],
                           outputs=dict(decision=dict(tool="send_message", arguments={"body": "hello"})))),
            dict(id="other", sequence=2, kind="decision", actor="master", data=dict(note="metadata")),
        ]
        timeline = Timeline(value)
        events = timeline.describe()["events"]
        self.assertEqual([e["id"] for e in events if e["primary"]], ["response"])
        self.assertEqual(events[1]["category"], "model")
        self.assertEqual(events[1]["preview"], "Choose send_message")
        self.assertEqual(timeline.export(), value)

    def test_presentation_metadata_remains_data_only_and_resists_arbitrary_nested_data(
        self,
    ):
        value = json.loads(EXAMPLE.read_text())
        for data in [
            None,
            [],
            "text",
            {"nativeKind": "decision_request", "parents": None},
            {"nativeKind": "message_received", "parents": [None, {}, "missing"]},
        ]:
            with self.subTest(data=data):
                value["events"][0]["data"] = data
                self.assertEqual(len(Timeline(value).describe()["events"]), 6)

    @unittest.skipUnless(
        shutil.which("souffle") and shutil.which("prlimit"), "Native engine required"
    )
    def test_gate_before_after_idb_and_trusted_links_share_the_exact_snapshot(self):
        from policyweave.enforcement import Policy
        from policyweave.core.policy import fact

        with tempfile.TemporaryDirectory() as directory:
            rules = Path(directory) / "rules.dl"
            rules.write_text(
                '.decl Owner(Document:symbol, Actor:symbol)\n.input Owner\n.key Owner(Document)\nAllow(Q) :- Request(Q,P,"handoff"), Owner("doc",P).\n'
            )
            policy = Policy(
                rules,
                inputs=[fact("Owner", "doc", "alice")],
                trace=True,
                local_effects=True,
            )
            try:
                policy.call(
                    "alice", "handoff", {}, lambda: policy.put("Owner", "doc", "bob")
                )
                policy.call(
                    "alice", "handoff", {}, lambda: self.fail("Blocked callback")
                )
                gate_value = policy.trajectory()
            finally:
                policy.runtime.close()
            gate = Timeline(gate_value)
            event_id = gate_value["events"][0]["id"]
            before = inspect(gate, event_id, derive=True)
            after = inspect(gate, event_id, phase="after", derive=True)
            owner = lambda result: next(
                g["rows"] for g in result["edb"] if g["name"] == "Owner"
            )
            self.assertEqual(owner(before), [["doc", "alice"]])
            self.assertEqual(owner(after), [["doc", "bob"]])
            self.assertEqual(
                next(g["rows"] for g in before["idb"] if g["name"] == "Allow"),
                [[event_id]],
            )
            self.assertEqual(
                next(g["rows"] for g in after["idb"] if g["name"] == "Allow"), []
            )
            self.assertEqual(
                len(next(g["rows"] for g in before["edb"] if g["name"] == "Request")), 1
            )
            self.assertEqual(
                next(g["rows"] for g in after["edb"] if g["name"] == "Request"), []
            )
            blocked = inspect(gate, gate_value["events"][1]["id"])
            self.assertFalse(blocked["decision"]["effectCalled"])
            log_value = json.loads(EXAMPLE.read_text())
            log = Timeline(log_value)
            server = AnalysisServer(("127.0.0.1", 0), log_value)
            log_path, gate_path = (
                Path(directory) / "log.json",
                Path(directory) / "gate.json",
            )
            log_path.write_text(json.dumps(log_value))
            gate_path.write_text(json.dumps(gate_value))
            server.register_file(log_path, log)
            server.register_file(gate_path, gate)
            server.attach_gate(log.identity, "c1", gate.identity, event_id)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            def post(value):
                return urlopen(
                    Request(
                        f"http://127.0.0.1:{server.server_port}/api/analysis/inspect",
                        data=json.dumps(value).encode(),
                        headers={
                            "Content-Type": "application/json",
                            "X-Study-Token": server.token,
                        },
                    ),
                    timeout=5,
                )

            try:
                request = dict(
                    trajectoryId=log.identity,
                    eventId="c1",
                    phase="before",
                    derive=False,
                )
                response = json.load(post(request))["result"]
                self.assertEqual(response["scope"], "gate")
                self.assertEqual(owner(response), [["doc", "alice"]])
                self.assertEqual(response["gateEventId"], event_id)
                with self.assertRaises(HTTPError):
                    post(dict(request, path="arbitrary.json"))
                with self.assertRaises(HTTPError):
                    post(dict(request, eventId="missing"))
                gate_path.write_text(json.dumps(log_value))
                with self.assertRaises(HTTPError):
                    post(request)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
