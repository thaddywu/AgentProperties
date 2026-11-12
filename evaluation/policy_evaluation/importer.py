"""Read existing developer-authored app artifacts without importing a host application."""

from copy import deepcopy
import json
from pathlib import Path
import re
from policy_runtime.policy import fingerprint, installed_rules, read_binding


class ReviewApplication:
    policy_origin = "developer-reference"
    setup_fields = []

    def __init__(self, directory):
        root = Path(directory)
        read = lambda name: json.loads((root / name).read_text())
        self.binding = read_binding(read("generated/runtime.json"))
        self.policy = (root / "policy.md").read_text()
        self.source = (root / "rules.dl").read_text()
        plan = read("generated/policy-plan.json")
        output = read("generated/reference-output.json")
        readings = read("review-readings.json")
        policies = []
        starts = {}
        for part in re.split(r"\r?\n\s*\r?\n", self.policy.strip()):
            if part.startswith("#"):
                continue
            match = re.fullmatch(r"(P[1-9][0-9]*)\.\s+([\s\S]+)", part)
            if not match:
                raise ValueError(
                    "Legacy reference requires numbered policy paragraphs."
                )
            text = match[2].strip()
            policies.append(dict(id=match[1], text=text))
            starts[match[1]] = self.policy.index(text)
        documents = [
            dict(path=str(path.relative_to(root)), content=path.read_text())
            for path in [
                root / "app.md",
                root / "policy.md",
                root / "tools.md",
                *sorted((root / "agents").glob("*.md")),
                *sorted((root / "episodes").glob("*.md")),
            ]
        ]
        # Imported IDs/hashes remain separate from new model revisions.
        if (
            readings["sourceHash"] != fingerprint(self.source)
            or readings["contractHash"] != fingerprint(self.binding)
            or readings["programHash"] != fingerprint(output["rules"])
            or readings["planHash"] != fingerprint(plan)
            or plan["sourceHash"] != fingerprint(policies)
            or plan["documentsHash"] != fingerprint(documents)
            or plan["bindingHash"] != fingerprint(self.binding)
        ):
            raise ValueError(
                "Reference artifacts are stale; rebuild and review them first."
            )
        installed_rules(self.binding, "\n".join(r["datalog"] for r in output["rules"]))
        self.documents = [d for d in documents if d["path"] != "policy.md"]
        self.name = readings["application"]
        self.revision = fingerprint(
            dict(source=self.source, documents=documents, readings=readings)
        )
        self.policy_hash = fingerprint(
            dict(
                version=2,
                binding=self.binding,
                source=self.source,
                rules=installed_rules(self.binding, self.source),
            )
        )
        requirements = deepcopy(plan["requirements"])
        by_id = {p["id"]: p["text"] for p in policies}
        for row in requirements:
            # Legacy indices are UTF-16; convert explicitly for the Python document contract.
            original = by_id[row["policyId"]]
            prefix = original.encode("utf-16-le")[: row["start"] * 2].decode(
                "utf-16-le"
            )
            quote = original.encode("utf-16-le")[
                row["start"] * 2 : row["end"] * 2
            ].decode("utf-16-le")
            row.update(
                quote=quote,
                start=starts[row["policyId"]] + len(prefix),
                end=starts[row["policyId"]] + len(prefix) + len(quote),
                categories=["uncertain"],
            )
        behaviors = []
        for row in readings["behaviors"]:
            behaviors.append(
                dict(
                    deepcopy(row),
                    kind="rule",
                    requirementIds=[
                        c["id"]
                        for c in output["coverage"]
                        if set(c["ruleIds"]) & set(row["ruleIds"])
                    ],
                )
            )
        for row in requirements:
            if row["implementation"] != "datalog":
                behaviors.append(
                    dict(
                        id="requirement_" + row["id"],
                        requirementIds=[row["id"]],
                        ruleIds=[],
                        kind="gap"
                        if row["implementation"] in ("unsupported", "ambiguous")
                        else "integration",
                        summary=row["statement"],
                        conditions=readings["obligations"][row["id"]],
                    )
                )
        content = dict(
            version=2,
            origin="reference",
            source=dict(
                name="policy.md",
                text=self.policy,
                hash=fingerprint(self.policy),
                offsetUnit="unicode-code-point",
            ),
            contractHash=fingerprint(self.binding),
            requirements=requirements,
            rules=output["rules"],
            coverage=output["coverage"],
            behaviors=behaviors,
            omittedRequirementIds=[],
            attempts=[],
            validation="static-only",
            runtimeInstalled=False,
        )
        self._reference = dict(content, id=fingerprint(content))

    def reference(self):
        return deepcopy(self._reference)

    def validate_setup(self, setup):
        raise ValueError("This review application has no experiment runner connected.")
