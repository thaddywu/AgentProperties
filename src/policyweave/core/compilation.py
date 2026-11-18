"""Compile a declared policy document with selected foundations."""

from .policy import CATALOG, compile_policy, policy_predicates
from .datalog import parse
from .source import read_policy_document


def validate_rules(path):
    """Compile declarations/clauses only; native execution belongs in Docker."""
    source = path.read_text()
    _, rule_source, configuration = read_policy_document(source)
    clauses = parse(rule_source)[0]
    used = {a["predicate"] for r in clauses for a in [r["head"], *r["body"]]}
    used.update(f["predicate"] for f in configuration)
    mechanisms = [
        name
        for name, module in CATALOG.items()
        if used.intersection(module["predicates"])
    ]
    binding = dict(
        version=1,
        id="port-validation",
        context="Candidate syntax validation.",
        predicates=policy_predicates(source, mechanisms=mechanisms),
        decision=dict(
            request="Request", parameters="Parameter", allow="Allow", deny="Deny"
        ),
        tests=[],
        configuration=configuration,
    )
    if mechanisms:
        binding["mechanisms"] = mechanisms
    if "fsm" in mechanisms:
        binding.update(fsmState="runtime", fsmTarget="resource")
    compile_policy(binding, source)
    return clauses
