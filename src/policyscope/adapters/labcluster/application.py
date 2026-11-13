"""Load an accepted port; generated Python executes exclusively in its pinned sandbox."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

from policyscope.core.policy import fingerprint, installed_rules, read_binding

from policyscope.adapters.labcluster.artifacts import artifact_hash
from policyscope.adapters.sandbox import Sandbox
from .worker import DEVELOPMENT, HELDOUT


class PortedApplication:
    name = "LabCluster · agentic port"
    policy_origin = "agent-generated"
    runner_info = dict(
        kind="Scripted LabCluster scenarios",
        taskLabel="Scenario note",
        defaultTask="",
        usesSeed=False,
    )
    setup_fields = [
        dict(
            name="scenario",
            label="Scenario",
            options=list(DEVELOPMENT + HELDOUT),
            labels=dict(
                zip(
                    DEVELOPMENT + HELDOUT,
                    (
                        "Normal submission",
                        "Exceed CPU quota",
                        "Disallowed node type",
                        "Read own job",
                        "Read another student's job",
                        "Complete a job",
                        "Public message",
                        "Private message",
                        "Professor to owner",
                        "Professor to other student",
                        "Stale release",
                        "Failed stop",
                        "Forged receipt",
                        "Priority queue",
                        "Information boundary",
                        "Professor stops a job",
                        "Delayed completion",
                        "Exceed memory quota",
                        "Exceed runtime quota",
                        "Exact quota limit",
                        "Nested private content",
                        "Allocation generation mismatch",
                        "Revised job approval",
                    ),
                )
            ),
        )
    ]

    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        read = lambda name: json.loads((self.directory / name).read_text())
        self.report = read("port.json")
        if self.report.get("status") not in (
            "validated",
            "validated-after-repair",
        ) or not self.report.get("reviewAvailable"):
            raise ValueError(
                "This port needs independent validation and back-translation before evaluation."
            )
        self.manifest = read("source-manifest.json")
        self.bundle = read("bundle.json")
        self.review = read("review.json")
        self.evidence = dict(port=deepcopy(self.report), heldout=read("heldout.json"))
        if self.report.get("validationExposed"):
            self.evidence["regression"] = read("regression.json")
        if (self.directory / "image-revalidation.json").exists():
            self.evidence["imageRevalidation"] = read("image-revalidation.json")
        self.artifacts = self.directory / "candidate/policy_port"
        self.binding = read_binding(self.bundle["binding"])
        self.source = self.bundle["source"]
        self.policy_hash = fingerprint(
            dict(
                version=2,
                binding=self.binding,
                source=self.source,
                rules=installed_rules(self.binding, self.source),
            )
        )
        self.revision = fingerprint(
            dict(
                source=self.report["sourceHash"],
                artifacts=self.report["artifactHash"],
                image=self.report["image"],
            )
        )
        self.documents = []
        self.verify()
        self.sandbox = Sandbox(
            self.directory / "candidate", self.artifacts, image=self.report["image"]
        )

    def verify(self):
        if (
            artifact_hash(self.artifacts) != self.report["artifactHash"]
            or self.bundle["artifactHash"] != self.report["artifactHash"]
            or self.review["portArtifactHash"] != self.report["artifactHash"]
            or self.review["contractHash"] != fingerprint(self.binding)
            or self.source != (self.artifacts / "rules.dl").read_text()
            or fingerprint(self.manifest["files"]) != self.report["sourceHash"]
        ):
            raise ValueError(
                "Port artifacts changed. Revalidate and create a new study."
            )
        for name, digest in self.manifest["files"].items():
            for folder in ("original", "candidate"):
                root = self.directory / folder
                path = root / name
                if (
                    root not in path.resolve().parents
                    or path.is_symlink()
                    or hashlib.sha256(path.read_bytes()).hexdigest() != digest
                ):
                    raise ValueError("Pinned original application snapshot changed.")

    def reference(self):
        # The historical method name is shared with developer reference connectors.
        # This review retains origin=model and its exact installed artifact hash.
        path = self.directory / "execution-review.json"
        if path.exists():
            candidate = json.loads(path.read_text())
            content = {k: v for k, v in candidate.items() if k != "id"}
            execution = candidate.get("execution", {})
            if (
                candidate.get("id") != fingerprint(content)
                or candidate.get("portArtifactHash") != self.report["artifactHash"]
                or candidate.get("contractHash") != fingerprint(self.binding)
                or candidate.get("source") != self.review["source"]
                or candidate.get("rules") != self.review["rules"]
                or execution.get("reviewId") != self.review["id"]
                or execution.get("rulesHash") != fingerprint(self.review["rules"])
            ):
                raise ValueError("Execution reading does not match the pinned port.")
            return candidate
        return deepcopy(self.review)

    def validate_setup(self, setup):
        if (
            not isinstance(setup, dict)
            or set(setup) != {"scenario"}
            or setup["scenario"] not in DEVELOPMENT + HELDOUT
        ):
            raise ValueError("Choose a supported LabCluster scenario.")

    def run(self, scenario, mode, seed, emit):
        self.validate_setup(scenario["setup"])
        if mode not in ("baseline", "protected"):
            raise ValueError("Unknown experiment mode.")
        self.verify()
        result = self.sandbox.run(
            dict(
                operation="run",
                case=scenario["setup"]["scenario"],
                mode=mode,
                seed=seed,
            )
        )
        for event in result.get("events", []):
            emit(event)
        if "initialStateHash" not in result or not result.get("passed"):
            raise ValueError(
                "Application scenario failed; inspect recorded events and the port validation report."
            )
        return dict(
            completed=None,
            runner="original-scripted-labcluster",
            modelUsed=False,
            seed=seed,
            seedUsed=False,
            initialStateHash=result["initialStateHash"],
            configurationHash=result["configurationHash"],
            finalState=result["finalState"],
            originalTrace=result["originalTrace"],
            acceptancePassed=result["passed"],
        )

    def inspect(self, snapshot, question):
        raise ValueError(
            "Inspect captured before/after state in the trajectory evidence."
        )
