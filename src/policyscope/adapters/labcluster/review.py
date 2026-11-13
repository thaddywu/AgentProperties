#!/usr/bin/env python3
"""Generate an independent execution reading and align it in a separate model call."""

import argparse
import json
from pathlib import Path
from copy import deepcopy

from policyscope.core.policy import fingerprint
from policyscope.adapters.compatible import Connection
from policyscope.policy_viewer.alignment import execution_review
from policyscope.adapters.labcluster.application import PortedApplication
from policyscope.adapters.labcluster.artifacts import artifact_hash
from policyscope.adapters.labcluster.agent import save_json
from policyscope.policy_viewer.review import review_units


def build(directory, generate):
    app = PortedApplication(directory)
    base = json.loads((app.directory / "review.json").read_text())
    evidence = {
        "adapter.py": (app.artifacts / "adapter.py").read_text(),
        "rules.dl": (app.artifacts / "rules.dl").read_text(),
    }
    # Implementation evidence only: no policy, README, plan or forward history.
    for name in (
        "store.py",
        "tools.py",
        "messaging.py",
        "schemas.py",
        "access.py",
        "trace.py",
    ):
        path = app.directory / "original/core" / name
        if path.exists():
            evidence["core/" + name] = path.read_text()
    evidence["runtime-boundary.txt"] = (
        "Trace.tool and Bus.send are mediated. The original bound actor/action/parameters "
        "supply request identity, not the generated mapper. Before/after each callback, "
        "observe receives copied Store.snapshot state, current request and original fixtures. "
        "Explicit Allow AND no Deny is required. Deny wins. Missing Allow refuses. "
        "Only an allowed request invokes the original callback; original guards remain. "
        "Direct Store calls, other channels and semantic paraphrases are outside this boundary."
    )
    records = []
    output = app.directory / "execution-review-attempts.json"

    def record(entry):
        records.append(entry)
        save_json(output, dict(attempts=records, usage=getattr(generate, "usage", [])))

    execution = execution_review(
        base, app.binding, evidence, review_units(base)["units"], generate, record
    )
    app.verify()
    candidate = deepcopy(base)
    candidate.pop("id", None)
    candidate["execution"] = execution
    candidate["model"] = getattr(generate, "metadata", {})
    candidate["executionUsage"] = getattr(generate, "usage", [])
    candidate["id"] = fingerprint(candidate)
    save_json(app.directory / "execution-review.json", candidate)
    print(
        json.dumps(
            dict(
                procedures=len(execution["procedures"]),
                sentences=len(execution["links"]),
                artifactHash=artifact_hash(app.artifacts),
                usage=getattr(generate, "usage", []),
            )
        )
    )
    return candidate


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ported-app", required=True, type=Path)
    parser.add_argument("--connection", required=True, type=Path)
    args = parser.parse_args()
    build(args.ported_app, Connection(json.loads(args.connection.read_text())))
