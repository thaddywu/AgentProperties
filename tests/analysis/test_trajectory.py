"""Actual gate capture/replay across changing facts; models never execute code."""

from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from policyscope.analysis import TrajectorySession
from policyscope.core.policy import fingerprint
from policyscope.enforcement import BridgeError, Policy, capture_trajectories
from policyscope.workbench.pipeline import analyze_publication

SOURCE = """
.decl Owner(Document:symbol, Actor:symbol)
.input Owner
.key Owner(Document)
Owner("d1", "alice").
Allow(Q) :- Request(Q, A, "read"), Parameter(Q, "document", D), Owner(D, A).
"""


@unittest.skipUnless(
    shutil.which("souffle") and shutil.which("prlimit"), "Native Soufflé required"
)
class TrajectoryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "rules.dl"
        self.path.write_text(SOURCE)

    def policy(self, **kwargs):
        value = Policy(self.path, **kwargs)
        self.addCleanup(value.runtime.close)
        return value

    def test_capture_uses_gate_time_facts_and_preserves_deletion_and_key_replacement(
        self,
    ):
        calls = []
        with capture_trajectories() as recordings:
            policy = self.policy(local_effects=True)
            self.assertEqual(
                policy.call(
                    "alice",
                    "read",
                    {"document": "d1"},
                    lambda: calls.append("first") or "body",
                ),
                "body",
            )
            policy.delete("Owner", "d1")
            self.assertEqual(
                policy.call(
                    "alice", "read", {"document": "d1"}, lambda: calls.append("bypass")
                )["code"],
                "UNAVAILABLE",
            )
            policy.put("Owner", "d1", "bob")
            self.assertEqual(
                policy.call(
                    "bob",
                    "read",
                    {"document": "d1"},
                    lambda: calls.append("second") or "body",
                ),
                "body",
            )
        self.assertEqual(calls, ["first", "second"])
        self.assertEqual(len(recordings), 1)
        value = json.loads(json.dumps(recordings[0].export()))
        analysis = TrajectorySession(value)
        self.assertTrue(analysis.verify()["allMatched"])
        self.assertEqual(analysis.verify()["decisions"], 3)
        events = value["events"]
        self.assertEqual(
            analysis.query(events[0]["id"], "?- Owner(D, A). ")["rows"],
            [["d1", "alice"]],
        )
        self.assertEqual(
            analysis.query(events[2]["id"], "?- Owner(D, A). ")["rows"], []
        )
        self.assertEqual(
            analysis.query(events[4]["id"], "?- Owner(D, A). ")["rows"], [["d1", "bob"]]
        )
        self.assertEqual(
            analysis.changes(events[1]["id"])["removed"],
            [dict(predicate="Owner", args=["d1", "alice"])],
        )
        self.assertFalse(analysis.replay(events[2]["id"])["effectCalled"])
        self.assertEqual(
            analysis.run(
                dict(operation="facts", eventId=events[0]["id"], predicate="Allow")
            )["facts"][0]["args"],
            [events[0]["id"]],
        )
        self.assertEqual(
            analysis.query(events[0]["id"], "?- Allow(Q).")["rows"], [[events[0]["id"]]]
        )
        self.assertEqual(
            analysis.run(
                dict(operation="facts", eventId=events[0]["id"], predicate="Request")
            )["facts"],
            [dict(predicate="Request", args=[events[0]["id"], "alice", "read"])],
        )
        self.assertIn(
            dict(predicate="Parameter", args=[events[0]["id"], "document", "d1"]),
            analysis.run(dict(operation="facts", eventId=events[0]["id"]))["facts"],
        )
        exported = policy.trajectory()
        exported["events"].clear()
        self.assertEqual(len(policy.trajectory()["events"]), 5)

    def test_uncertain_execution_stays_unknown_and_does_not_certify_rollback(self):
        policy = self.policy(trace=True)

        def uncertain():
            raise RuntimeError("Possible business effect; outcome unknown.")

        with self.assertRaises(BridgeError) as error:
            policy.call("alice", "read", {"document": "d1"}, uncertain)
        self.assertEqual(error.exception.code, "execution_uncertain")
        value = policy.trajectory()
        event = value["events"][0]
        self.assertEqual(event["outcome"], "unknown")
        self.assertTrue(event["effectCalled"])
        self.assertIsNone(event["committedInputs"])
        analysis = TrajectorySession(value)
        self.assertTrue(analysis.replay(event["id"])["matches"])
        with self.assertRaises(ValueError):
            analysis.snapshot(event["id"], "committedInputs")
        with self.assertRaises(ValueError):
            analysis.changes(event["id"])
        with self.assertRaises(BridgeError):
            policy.call("alice", "read", {"document": "d1"}, lambda: "must not execute")
        self.assertEqual(len(policy.trajectory()["events"]), 1)

    def test_declined_business_result_is_different_from_policy_refusal(self):
        policy = self.policy(trace=True, completed=lambda r: r["ok"])
        self.assertFalse(
            policy.call("alice", "read", {"document": "d1"}, lambda: {"ok": False})[
                "ok"
            ]
        )
        event = policy.trajectory()["events"][0]
        self.assertTrue(event["decision"]["allowed"])
        self.assertEqual(event["outcome"], "not_applied")
        self.assertTrue(TrajectorySession(policy.trajectory()).verify()["allMatched"])

    def test_external_observations_are_frozen_before_each_gate(self):
        rows = [dict(predicate="Owner", args=["d1", "alice"])]
        # The observed profile owns Owner, so no static Owner seed is used.
        self.path.write_text(SOURCE.replace('Owner("d1", "alice").', ""))
        policy = self.policy(facts=lambda *_: deepcopy(rows), trace=True)
        policy.call("alice", "read", {"document": "d1"}, lambda: "body")
        rows.clear()
        policy.call("alice", "read", {"document": "d1"}, lambda: "bypass")
        trace = policy.trajectory()
        analysis = TrajectorySession(trace)
        self.assertTrue(analysis.verify()["allMatched"])
        self.assertTrue(trace["events"][0]["inputs"])
        self.assertFalse(trace["events"][1]["inputs"])
        self.assertFalse(trace["events"][1]["decision"]["allowed"])

    def test_hypothetical_changes_and_qa_do_not_mutate_the_trace_or_call_business_code(
        self,
    ):
        calls = []
        policy = self.policy(trace=True)
        policy.call("bob", "read", {"document": "d1"}, lambda: calls.append(True))
        value = policy.trajectory()
        event = value["events"][0]
        analysis = TrajectorySession(value)
        changed = analysis.what_if(
            event["id"],
            remove=[dict(predicate="Owner", args=["d1", "alice"])],
            add=[dict(predicate="Owner", args=["d1", "bob"])],
        )
        self.assertTrue(changed["decision"]["allowed"])
        self.assertTrue(changed["hypothetical"])
        self.assertFalse(analysis.replay(event["id"])["replayed"]["allowed"])

        def model(stage, prompt):
            if stage == "trajectory-question":
                self.assertIs(
                    json.loads(prompt)["context"]["events"][0]["effectCalled"], False
                )
                return json.dumps(
                    dict(plan=dict(operation="decision", eventId=event["id"]))
                )
            payload = json.loads(prompt)
            self.assertEqual(payload["result"]["outcome"], "blocked")
            return json.dumps(
                dict(
                    answer="The read had no explicit permission and its callback was not invoked.",
                    eventIds=[event["id"]],
                    limitations=[
                        "Recorded observations are not independently authenticated."
                    ],
                )
            )

        answer = analysis.ask("Why was this read refused?", model)
        self.assertTrue(answer["result"]["matches"])
        self.assertEqual(calls, [])
        self.assertEqual(policy.trajectory(), value)
        for plan in [
            dict(operation="execute", eventId=event["id"]),
            dict(operation="facts", eventId="invented"),
            dict(operation="decision", eventId=event["id"], code="anything"),
            dict(operation="facts", eventId=event["id"], predicate=[]),
            dict(operation="facts", eventId=event["id"], phase={}),
        ]:
            with self.assertRaises(ValueError):
                analysis.run(plan)

        def invalid(stage, prompt):
            if stage == "trajectory-question":
                return model(stage, prompt)
            return json.dumps(
                dict(
                    answer="An invented outcome", eventIds=["invented"], limitations=[]
                )
            )

        with self.assertRaises(ValueError):
            analysis.ask("Question", invalid)

    def test_hashes_detect_edits_but_replay_is_needed_for_rehashed_false_decisions(
        self,
    ):
        policy = self.policy(trace=True)
        policy.call("bob", "read", {"document": "d1"}, lambda: "bypass")
        value = policy.trajectory()
        edited = deepcopy(value)
        edited["events"][0]["inputs"].clear()
        with self.assertRaises(ValueError):
            TrajectorySession(edited)
        forged = deepcopy(value)
        event = forged["events"][0]
        event["decision"]["allowed"] = True
        event["decision"]["reasons"] = []
        event["outcome"] = "applied"
        event["effectCalled"] = True
        event["hash"] = fingerprint({k: v for k, v in event.items() if k != "hash"})
        forged["id"] = fingerprint({k: v for k, v in forged.items() if k != "id"})
        self.assertFalse(TrajectorySession(forged).verify()["allMatched"])
        with self.assertRaises(ValueError):
            TrajectorySession(dict(events=[]))
        invalid_version = dict(value, version=True)
        invalid_version["id"] = fingerprint(
            {k: v for k, v in invalid_version.items() if k != "id"}
        )
        with self.assertRaises(ValueError):
            TrajectorySession(invalid_version)

    def test_capture_is_opt_in_and_an_empty_trace_is_not_successful_replay(self):
        policy = self.policy()
        with self.assertRaises(ValueError):
            policy.trajectory()
        policy = self.policy(trace=True)
        self.assertFalse(TrajectorySession(policy.trajectory()).verify()["allMatched"])
        with self.assertRaises(ValueError):
            self.policy(trace="false")

    def test_recording_failure_stops_retries_and_releases_runtime_lock(self):
        for update in (False, True):
            with self.subTest(update=update):
                policy = self.policy(trace=True)
                calls = []
                with patch.object(
                    policy.runtime._recording,
                    "append",
                    side_effect=ValueError("sink failed"),
                ):
                    with self.assertRaises(BridgeError) as error:
                        if update:
                            policy.put("Owner", "d1", "bob")
                        else:
                            policy.call(
                                "alice",
                                "read",
                                {"document": "d1"},
                                lambda: calls.append(True),
                            )
                    self.assertEqual(error.exception.code, "execution_uncertain")
                self.assertEqual(len(calls), 0 if update else 1)
                with self.assertRaises(ValueError):
                    policy.trajectory()
                with self.assertRaises(BridgeError) as stopped:
                    policy.call(
                        "alice", "read", {"document": "d1"}, lambda: calls.append(True)
                    )
                self.assertEqual(stopped.exception.code, "session_failed")

    def test_pipeline_replays_real_callbacks_and_rejects_incomplete_execution_evidence(
        self,
    ):
        policy = self.policy(trace=True)
        calls = []
        policy.call("alice", "read", {"document": "d1"}, lambda: calls.append(True))
        policy.call("bob", "read", {"document": "d1"}, lambda: calls.append(False))
        setup_only = self.policy(trace=True)
        setup_only.put("Owner", "d1", "bob")
        report = dict(
            passed=True,
            tests=2,
            skipped=0,
            nativeEngineCalls=2,
            trajectoryCoverage=dict(complete=True),
            policyTrajectories=[policy.trajectory(), setup_only.trajectory()],
        )
        work = Path(self.directory.name)
        check = work / "publication-check-0.json"
        # Private runner reports can exceed the ordinary 4 MB model-artifact cap.
        report["artifacts"] = {"synthetic": "x" * 4_000_000}
        check.write_text(json.dumps(report))

        def model(stage, prompt):
            if stage == "trajectory-question":
                return json.dumps(dict(plan=dict(operation="overview")))
            ids = json.loads(prompt)["result"]["evidenceIds"]
            return json.dumps(
                dict(
                    answer="One callback returned; one request was blocked.",
                    eventIds=ids,
                    limitations=[],
                )
            )

        result = analyze_publication(work, generate=model)
        self.assertEqual(result["outcomes"], dict(applied=1, blocked=1))
        self.assertEqual(result["matchedDecisions"], 2)
        self.assertEqual(result["qaQuestions"], 3)
        self.assertEqual(result["trajectories"], 2)
        self.assertEqual(calls, [True])
        trajectory_file = work / "trajectory.json"
        trajectory_file.write_text(json.dumps(policy.trajectory()))
        cli = subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "policyscope",
                "analyze",
                str(trajectory_file),
                "--verify",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(cli.returncode, 0, cli.stderr)
        self.assertEqual(json.loads(cli.stdout)["matched"], 2)
        empty = self.policy(trace=True).trajectory()
        trajectory_file.write_text(json.dumps(empty))
        cli = subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "policyscope",
                "analyze",
                str(trajectory_file),
                "--verify",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(cli.returncode, 1, cli.stderr)
        report["trajectoryCoverage"]["complete"] = False
        check.write_text(json.dumps(report))
        with self.assertRaises(ValueError):
            analyze_publication(work, generate=model)
        report["trajectoryCoverage"]["complete"] = True
        report["policyTrajectories"] = [setup_only.trajectory()]
        check.write_text(json.dumps(report))
        with self.assertRaisesRegex(ValueError, "No completed gate decision"):
            analyze_publication(work, generate=model)
