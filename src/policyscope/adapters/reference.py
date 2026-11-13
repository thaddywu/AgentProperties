"""Build developer-reviewed artifacts from a policy-first source map, without model calls."""

import json
from pathlib import Path

from policyscope.enforcement import Policy
from policyscope.core.policy import fingerprint

from .annotated_policy import entries


def build(root):
    ROOT = Path(root).resolve()
    manifest = json.loads((ROOT / "walkthrough.json").read_text())
    source = (ROOT / "rules.dl").read_text()
    contract = Policy(
        ROOT / "rules.dl",
        target=manifest.get("target", "resource"),
        invariants=tuple(manifest.get("invariants", [])),
    ).runtime.binding
    policies = [
        {"id": f"P{i}", "text": p.split(". ", 1)[1].strip()}
        for i, p in enumerate((ROOT / "policy.md").read_text().strip().split("\n\n"), 1)
    ]
    annotated = entries(source)
    rules = {r["id"]: r for r in annotated if r["kind"] == "rule"}
    from policyscope.core.datalog import parse
    from policyscope.core.source import read_policy_document

    _, clauses, _ = read_policy_document(source)
    parsed, _ = parse(clauses)
    assert len(parsed) == len(rules), (
        "Every executable clause needs a policy annotation."
    )
    requirements, coverage = [], []
    for row in manifest["requirements"]:
        original = next(p["text"] for p in policies if p["id"] == row["policyId"])
        start = row.get("start", original.index(row["source"]))
        end = row.get("end", start + len(row["source"]))
        assert original[start:end] == row["source"]
        selected = list(dict.fromkeys(row["ruleIds"] + row["relatedRuleIds"]))
        implementation = row["implementation"]
        if row["ruleIds"]:
            implementation = "datalog"
        assumptions = [
            row["detail"],
            "Only adapted tools are mediated; backend identity and records are authoritative.",
        ]
        relation = row["relation"]
        if implementation == "datalog":
            assert selected, "Do not invent empty Datalog coverage."
            atoms = [
                atom
                for identity in selected
                for rule in parse(rules[identity]["datalog"])[0]
                for atom in [rule["head"], *rule["body"]]
            ]
            inputs = sorted(
                {
                    a["predicate"]
                    for a in atoms
                    if contract["predicates"][a["predicate"]]["kind"] == "input"
                }
            )
            coverage.append(
                {
                    "id": row["id"],
                    "ruleIds": selected,
                    "notes": row["detail"]
                    + " Developer-authored reference; no model called.",
                }
            )
        else:
            inputs = []
        item = {key: row[key] for key in ("id", "policyId", "source")}
        item.update(start=start, end=end)
        item.update(
            statement=row["title"],
            implementation=implementation,
            relation=relation,
            assumptions=assumptions,
            predicates=inputs,
        )
        if implementation == "mechanism":
            item.update(
                mechanism="fsm",
                predicates=[
                    "ResourceType",
                    "ResourceState",
                    "AllowedTransition",
                    "CanTransition",
                ],
            )
        requirements.append(item)
    document_names = [
        "app.md",
        "policy.md",
        "tools.md",
        *sorted(str(p.relative_to(ROOT)) for p in (ROOT / "agents").glob("*.md")),
    ]
    documents = [
        {"path": name, "content": (ROOT / name).read_text()} for name in document_names
    ]
    plan = {
        "version": 1,
        "sourceHash": fingerprint(policies),
        "bindingHash": fingerprint(contract),
        "documentsHash": fingerprint(documents),
        "requirements": requirements,
    }
    review = {
        "version": 1,
        "planHash": fingerprint(plan),
        "approvedRequirements": [r["id"] for r in requirements],
        "acknowledgedGaps": [
            r["id"] for r in requirements if r["relation"] != "equivalent"
        ],
        "obligations": {
            r["id"]: next(
                row["detail"]
                for row in manifest["requirements"]
                if row["id"] == r["id"]
            )
            + " Verify with the original bound tools in tests/verify.py; remaining paths are explicitly excluded."
            for r in requirements
            if r["implementation"] in ("adapter", "mechanism")
        },
    }
    assert {identity for c in coverage for identity in c["ruleIds"]} == set(rules)
    reference = {
        "rules": [{"id": r["id"], "datalog": r["datalog"]} for r in rules.values()],
        "coverage": coverage,
    }
    for name, value in [
        ("runtime.json", contract),
        ("policy-plan.json", plan),
        ("policy-review.json", review),
        ("reference-output.json", reference),
    ]:
        (ROOT / "generated" / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", type=Path)
    build(parser.parse_args().app)
