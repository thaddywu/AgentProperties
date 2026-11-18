import json
from pathlib import Path
import shutil
import tempfile
import unittest

from policyweave.enforcement import Policy, caller_context, fact, record_execution
from policyweave.analysis.execution import execution_analysis
from policyweave.analysis.inspection import inspect
from policyweave.analysis.log_query import LogQuerySession
from policyweave.analysis.timeline import Timeline
from policyweave.analysis.trajectory import TrajectorySession


@unittest.skipUnless(
    shutil.which("souffle") and shutil.which("prlimit"), "Native engine required"
)
class TelemetryTests(unittest.TestCase):
    def test_real_decorated_calls_typed_arguments_messages_and_gate_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            rules = Path(directory) / "policy.dl"
            rules.write_text('Allow(Q) :- Request(Q,"student","read").')
            # Construct before capture: later calls still register the exact policy.
            policy = Policy(rules)
            effects = []

            @policy
            def read(document, options=None):
                effects.append(document)
                return dict(ok=True, document=document)

            with record_execution("Synthetic episode") as trace:
                with caller_context("student"):
                    with trace.operation("student", "read", dict(document="d1", options=dict(enabled=True, threshold=3, items=["x"]))) as outcome:
                        original = read("d1", dict(enabled=True, threshold=3, items=["x"]))
                        outcome["value"] = original
                with caller_context("other"):
                    blocked = read("d2")
                trace.message(
                    "student",
                    ["reviewer"],
                    "Recorded send",
                    phase="sent",
                    message_id="m1",
                )
                trace.message(
                    "student",
                    ["reviewer"],
                    "Recorded send",
                    phase="received",
                    message_id="m1",
                )
            self.assertEqual(effects, ["d1"])
            self.assertEqual(original, dict(ok=True, document="d1"))
            self.assertFalse(blocked["ok"])
            value = trace.export()
            calls = [e for e in value["events"] if e["kind"] == "tool_call"]
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[0]["arguments"]["options"]["items"], ["x"])
            timeline = Timeline(value)
            self.assertEqual(timeline.export(), value)
            summaries = {e["id"]: e for e in timeline.describe()["events"]}
            self.assertEqual(summaries[calls[0]["id"]]["outcome"], "applied")
            self.assertEqual(summaries[calls[1]["id"]]["outcome"], "blocked")
            linked = timeline.gate(calls[1]["id"])
            self.assertEqual(linked[0].export(), policy.trajectory())
            self.assertNotEqual(linked[1], calls[1]["id"])
            database = inspect(timeline, calls[1]["id"])
            self.assertEqual(database["scope"], "gate")
            self.assertFalse(database["decision"]["effectCalled"])
            parameters = next(r["rows"] for r in database["edb"] if r["name"] == "Parameter")
            self.assertIn([linked[1], "document", "d2"], parameters)
            self.assertIsNone(timeline.gate(value["events"][-1]["id"]))
            # Embedded evidence must pass the same native validation as a gate file.
            corrupted = json.loads(json.dumps(value))
            record = next(e["data"]["gateRecord"] for e in corrupted["events"]
                          if e.get("data", {}).get("observation") == "policy_result")
            record["outcome"] = "blocked"
            with self.assertRaises(ValueError):
                Timeline(corrupted)
            unlinked = json.loads(json.dumps(value))
            for event in unlinked["events"]:
                if event.get("data", {}).get("observation") == "policy_result":
                    event["data"]["callId"] = None
            self.assertIsNone(Timeline(unlinked).gate(calls[1]["id"]))
            mismatched = json.loads(json.dumps(value))
            for event in mismatched["events"]:
                if (event.get("data", {}).get("observation") == "policy_result"
                        and event["data"]["callId"] == calls[1]["callId"]):
                    event["data"]["callId"] = calls[0]["callId"]
            with self.assertRaises(ValueError):
                Timeline(mismatched)
            installed = next(
                i
                for i, e in enumerate(value["events"])
                if e.get("data", {}).get("observation") == "policy_installed"
            )
            decision = next(
                i for i, e in enumerate(value["events"]) if e["kind"] == "decision"
            )
            self.assertLess(installed, decision)
            session = LogQuerySession(Timeline(execution_analysis(value)))
            self.assertEqual(
                session.query("?- Refused(E,A,T).")["rows"][0][1:], ["other", "read"]
            )
            arguments = session.query('?- Argument(E,"/options/enabled",J).')["rows"]
            self.assertEqual(arguments, [[calls[0]["id"], "true"]])
            self.assertEqual(
                len(session.query('?- Message(E,S,R,"received",M).')["rows"]), 1
            )
            self.assertTrue(
                TrajectorySession(policy.trajectory()).verify()["allMatched"]
            )

    def test_single_export_roundtrips_jsonl_and_keeps_participant_types(self):
        from policyweave.analysis.timeline import decode_trajectory
        with tempfile.TemporaryDirectory() as directory:
            with record_execution() as trace:
                trace.participant("Runner", kind="agent")
                trace.participant("Synthetic transport", kind="tool")
                trace.model_output("Runner", dict(text="Visible decision"))
                trace.message("Runner", ["Synthetic transport"], dict(body="Exact body"), phase="sent")
            value = trace.export(directory)
            restored = decode_trajectory((Path(directory) / "trajectory.jsonl").read_text())
            self.assertEqual(restored, value)
            self.assertEqual(json.loads((Path(directory) / "trajectory.json").read_text()), value)
            self.assertEqual(Timeline(restored).roles[0]["kind"], "agent")
            with self.assertRaises(FileExistsError):
                trace.export(directory)

    def test_context_may_dependency_survives_encoding_and_missing_context_is_unknown(
        self,
    ):
        with record_execution() as trace:
            trace.source("student", "private-v1")
            trace.context(
                "student",
                "c1",
                inputs=["private-v1"],
                outputs=["encoded-output"],
                complete=True,
            )
            trace.context(
                "student",
                "c2",
                inputs=["encoded-output"],
                outputs=["message-v1"],
                complete=False,
            )
            trace.message(
                "student",
                ["peer"],
                "opaque base64-like data",
                phase="sent",
                message_id="m1",
            )
        value = execution_analysis(trace.export())
        query = LogQuerySession(Timeline(value))
        self.assertEqual(
            query.query('?- MayOrigin("message-v1",O).')["rows"], [["student"]]
        )
        self.assertEqual(query.query('?- UnknownOrigin("message-v1").')["rows"],[[]])
        self.assertEqual(
            len(query.query('?- ContextCoverage(E,C,"false").')["rows"]), 1
        )
        self.assertEqual(query.query('?- Message(E,S,R,"received",M).')["rows"], [])
        # The same graph reuses the existing provenance foundation's input interface.
        self.assertIn(
            fact("DependsOn", "message-v1", "encoded-output"), trace.provenance_facts()
        )

    def test_app_specific_rules_consume_explicit_event_scoped_facts_only(self):
        with record_execution() as trace:
            trace.facts(
                "observer",
                [fact("JobState", "job1", "COMPLETED")],
                source="synthetic authoritative store",
            )
        rules = """
.decl JobState(E:symbol, Job:symbol, State:symbol)
.input JobState
.decl Finished(E:symbol, Job:symbol)
Finished(E,J) :- JobState(E,J,"COMPLETED").
"""
        value = execution_analysis(trace.export(), rules=rules)
        # A standalone exported .dl can reconstruct the same projection.
        restored = execution_analysis(trace.export(), rules=value["analysis"]["source"])
        self.assertEqual(restored["analysis"]["inputs"], value["analysis"]["inputs"])
        query = LogQuerySession(Timeline(json.loads(json.dumps(value))))
        self.assertEqual(query.query("?- Finished(E,J).")["rows"][0][1], "job1")
        self.assertNotIn("application", query.contract["binding"]["predicates"])
