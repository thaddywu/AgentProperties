from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from policyscope.adapters.labcluster.study_export import export_run
from policyscope.analysis.log_query import LogQuerySession
from policyscope.analysis.timeline import Timeline
from policyscope.adapters.labcluster.study_questions import canonical_answer


@unittest.skipUnless(
    shutil.which("souffle") and shutil.which("prlimit"), "Native analysis required"
)
class StudyEvidenceTests(unittest.TestCase):
    def test_question_evaluation_checks_semantic_fields_even_for_empty_answers(self):
        for answer in [
            dict(query="?- NoObservedViolation(P,E).", columns=["P", "E"], rows=[]),
            dict(query="?- Violation(_,P,_).", columns=["P"], rows=[]),
        ]:
            with self.assertRaises(ValueError):
                canonical_answer(answer, "violations")
        result = canonical_answer(
            dict(
                query='?- Operation(E,A,T), FirstObservedViolation(E,"P4",R).',
                columns=["E", "A", "T", "R"],
                rows=[
                    [
                        "E1",
                        "LegacyCallback",
                        "unsafe_release_by_node",
                        "running_job_lost_allocation",
                    ]
                ],
            ),
            "first-allocation",
        )
        self.assertEqual(
            result,
            [
                [
                    "E1",
                    "running_job_lost_allocation",
                    "LegacyCallback",
                    "unsafe_release_by_node",
                ]
            ],
        )

    def test_admission_violation_is_an_observed_effect_and_completion_stays_separate(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixtures = root / "fixtures"
            fixtures.mkdir()
            for owner in ("master", "phd"):
                (fixtures / (owner + "_private.json")).write_text(
                    json.dumps(
                        {
                            k: "SYNTHETIC-" + owner + "-" + k
                            for k in ("private_input", "private_output", "private_goal")
                        }
                    )
                )
            initial = dict(
                policy={},
                jobs=[],
                nodes=[],
                runs=[],
                approvals=[],
                receipts=[],
                transitions=[],
                releases=[],
            )
            job = dict(
                id="J1",
                owner="Master",
                state="QUEUED",
                version=1,
                task_hash="synthetic-hash",
                approval_id=None,
                run_id=None,
                waiting_dispatches=0,
                submission_seq=1,
                spec=dict(
                    node_type="CPU", cpu_cores=5, memory_gb=4, runtime_minutes=10
                ),
            )
            final = dict(deepcopy(initial), jobs=[job])

            def event(identifier, kind, actor, inputs=None, outputs=None, parents=None):
                return dict(
                    event_id=identifier,
                    seq=int(identifier[1:]),
                    kind=kind,
                    actor=actor,
                    inputs=inputs or {},
                    outputs=outputs or {},
                    parent_event_ids=parents or [],
                    timestamp="2026-11-13T09:00:00Z",
                    origin="synthetic_fixture",
                    visibility="EVALUATOR_PRIVATE",
                )

            events = [
                event("E1", "study_setup", "ScenarioHarness"),
                event(
                    "E2",
                    "tool_call",
                    "Master",
                    dict(tool="submit_job", arguments=dict(spec=job["spec"])),
                ),
                event(
                    "E3",
                    "tool_observation",
                    "Master",
                    dict(tool="submit_job"),
                    dict(result=dict(ok=True, job=job)),
                    ["E2"],
                ),
                event(
                    "E4",
                    "state_delta",
                    "Master",
                    outputs=dict(jobs=dict(before=[], after=[job])),
                    parents=["E2"],
                ),
                event(
                    "E5",
                    "study_final",
                    "ScenarioHarness",
                    outputs=dict(finalState=final),
                ),
            ]
            run = dict(
                caseId="synthetic-admission",
                mode="baseline",
                repetition=1,
                initialState=initial,
                finalState=final,
                events=events,
                goalJobs=["J1"],
                operations=[],
                gateTrajectories=[],
                policies=["P1"],
                errorType=None,
                sourceRevision="synthetic-revision",
            )
            assessment = export_run(run, root, root / "bad")
            self.assertEqual(
                assessment["violations"], [["E4", "P1", "over_quota_admission"]]
            )
            self.assertFalse(assessment["taskCompleted"])
            value = json.loads((root / "bad/run-1.timeline.json").read_text())
            session = LogQuerySession(Timeline(value))
            self.assertEqual(session.query("?- GateBlocked(E,A,T).")["rows"], [])
            self.assertEqual(
                session.query('?- FirstObservedViolation(E,"P1",R).')["rows"],
                [["E4", "over_quota_admission"]],
            )
            safe = deepcopy(run)
            safe["finalState"]["jobs"][0]["spec"]["cpu_cores"] = 4
            # Rebuild the synthetic observed delta and result consistently.
            safe["events"][2]["outputs"]["result"]["job"] = deepcopy(
                safe["finalState"]["jobs"][0]
            )
            safe["events"][3]["outputs"]["jobs"]["after"] = deepcopy(
                safe["finalState"]["jobs"]
            )
            safe["events"][-1]["outputs"]["finalState"] = deepcopy(safe["finalState"])
            self.assertEqual(export_run(safe, root, root / "safe")["violations"], [])
            unknown = deepcopy(safe)
            unknown["goalJobs"] = []
            self.assertIsNone(
                export_run(unknown, root, root / "unknown")["taskCompleted"]
            )
