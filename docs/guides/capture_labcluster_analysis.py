"""Capture only synthetic, non-payload analysis evidence for the walkthrough PDF."""

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "runtime" / "python"))
sys.path.insert(0, str(ROOT / "apps" / "labcluster-port"))
sys.path.insert(0, str(ROOT / "apps/labcluster-port/tests"))
from upstream import load_upstream


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("labcluster-analysis.json"))
    args = parser.parse_args()
    app = load_upstream(args.upstream)
    try:
        professor = app.tools("Professor")
        jobs = {}
        for role in ("Master", "PhD"):
            spec = {"title": "Synthetic walkthrough task", "node_type": "CPU", "cpu_cores": 2,
                    "memory_gb": 4, "runtime_minutes": 10}
            submitted, _ = app.tools(role).call("submit_job", {"spec": spec})
            job = submitted["job"]
            approved, _ = professor.call("approve_job", {"job_id": job["id"], "expected_version": 1, "approve": True})
            assert approved["ok"]
            jobs[role] = job["id"]
        calls = app.effect_calls
        master_intent = {"actor": "Professor", "action": "dispatch_job", "parameters": {"job_id": jobs["Master"]}}
        # Capture authoritative input versions without invoking any business operation.
        analysis = app.runtime.capture(master_intent)
        (args.output.parent / "predicate-registration.json").write_text(json.dumps(app.runtime.describe_predicates(), ensure_ascii=False, indent=2) + "\n")
        query_text = ["?- WithinJobQuota(J).", "?- MatchingApproval(J).", "?- Priority(J, P).",
                      "?- Eligible(J, N).", "?- Outranked(J, N).", "?- Dispatchable(J)."]
        queries = [{"query": q, **analysis.query(q)} for q in query_text]
        phd_intent = {**master_intent, "parameters": {"job_id": jobs["PhD"]}}
        before = analysis.check(master_intent)["allowed"]
        phd_before = analysis.check(phd_intent)["allowed"]
        snapshot = analysis.facts()
        hypothetical = deepcopy(snapshot)
        for fact in hypothetical:
            if fact["predicate"] == "Waiting" and fact["args"][0] == jobs["Master"]:
                fact["args"][1] = "3"
        promoted = analysis.what_if(master_intent, hypothetical)["allowed"]
        phd_promoted = analysis.what_if(phd_intent, hypothetical)["allowed"]
        assert (before, phd_before, promoted, phd_promoted) == (False, True, True, False)
        assert app.effect_calls == calls and app.runtime.snapshot() == snapshot
        assert next(q["rows"] for q in queries if q["query"] == "?- Dispatchable(J).") == [[jobs["PhD"]]]
        evidence = {
            "kind": "Executed synthetic backend/query evidence; authored reference rules; no model called",
            "scope": "One simulated cluster captured by an administrator without business callbacks",
            "observationVersions": dict(analysis.versions), "inputHash": analysis.input_hash,
            "policyHash": app.runtime.policy_hash, "jobs": jobs,
            "sourceHash": hashlib.sha256((ROOT / "apps/labcluster-port/rules.dl").read_bytes()).hexdigest(),
            "bindingHash": hashlib.sha256(json.dumps(app.runtime.binding, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "queries": queries,
            "whatIf": {"change": "Master compatible-skip counter becomes 3 in a complete hypothetical snapshot",
                       "masterAllowedBefore": before, "phdAllowedBefore": phd_before,
                       "masterAllowedHypothetically": promoted, "phdAllowedHypothetically": phd_promoted,
                       "liveMasterStillDenied": not app.runtime.check(master_intent)["allowed"],
                       "businessCallbacksDuringAnalysis": app.effect_calls - calls,
                       "liveSnapshotUnchanged": app.runtime.snapshot() == snapshot},
        }
        args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
        print("Captured query and What-if results; no private payloads exported.")
    finally:
        app.close()


if __name__ == "__main__":
    main()
