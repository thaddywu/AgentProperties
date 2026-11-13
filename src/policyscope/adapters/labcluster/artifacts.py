"""Validate generated artifacts without giving generated code host authority."""

import ast
import json
import re
from copy import deepcopy
from pathlib import Path

from policyscope.enforcement import fact
from policyscope.core.datalog import decode, parse, stratify, variable
from policyscope.core.policy import (
    fingerprint,
    installed_rules,
    policy_predicates,
    read_binding,
)
from policyscope.core.source import read_policy_document

FILES = ("adapter.py", "rules.dl", "plan.json")


def rule_diagnostics(source):
    """Locate ordinary single-line clause errors; never execute generated code."""
    errors = []
    count = sum(":-" in line for line in source.splitlines())
    if count > 99:
        errors.append(
            {
                "error": f"Approximately {count} clauses; this engine admits at most 99. Reuse helpers or remove redundant clauses."
            }
        )
    for number, line in enumerate(source.splitlines(), 1):
        if ":-" not in line or not line.rstrip().endswith("."):
            continue
        try:
            rules, _ = parse(line)
            stratify(rules)
        except ValueError as error:
            errors.append(
                {
                    "line": number,
                    "error": str(error),
                    "clause": line,
                    "hint": "Every head, negative and comparison variable must occur in a positive relation in the SAME clause. To check existence without binding all fields, derive a smaller relation in another clause first.",
                }
            )
        if len(errors) == 5:
            break
    return errors


METHODS = {
    "get",
    "items",
    "values",
    "keys",
    "append",
    "extend",
    "lower",
    "upper",
    "strip",
    "startswith",
    "endswith",
    "replace",
    "join",
    "loads",
    "dumps",
}
BUILTINS = {
    name: value
    for name, value in dict(
        str=str,
        int=int,
        bool=bool,
        list=list,
        dict=dict,
        tuple=tuple,
        set=set,
        len=len,
        range=range,
        enumerate=enumerate,
        sorted=sorted,
        min=min,
        max=max,
        sum=sum,
        any=any,
        all=all,
        isinstance=isinstance,
        zip=zip,
        abs=abs,
    ).items()
}


def adapter_tree(source):
    if len(source) > 40_000:
        raise ValueError("Adapter is too large.")
    tree = ast.parse(source, filename="adapter.py")
    helpers = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    if "observe" not in helpers:
        raise ValueError("Define observe(snapshot, request, fixtures).")
    for node in tree.body:
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            continue
        if not isinstance(node, ast.FunctionDef):
            raise ValueError(
                "Adapter top level may contain only pure function definitions and a docstring. Put constants inside functions."
            )
        if (
            node.decorator_list
            or node.returns
            or node.args.defaults
            or node.args.kw_defaults
            or any(a.annotation for a in node.args.args)
        ):
            raise ValueError(
                "Use plain functions without decorators, defaults or annotations."
            )
    forbidden = (
        ast.Import,
        ast.ImportFrom,
        ast.ClassDef,
        ast.Global,
        ast.Nonlocal,
        ast.With,
        ast.AsyncWith,
        ast.AsyncFunctionDef,
        ast.Await,
        ast.Try,
        ast.Raise,
        ast.Delete,
        ast.Yield,
        ast.YieldFrom,
    )
    for node in ast.walk(tree):
        if isinstance(node, forbidden):
            raise ValueError(
                "Adapter may only map supplied JSON values to facts; imports, effects and exception handlers are unavailable."
            )
        if isinstance(node, ast.Name) and node.id.startswith("_"):
            raise ValueError("Private/introspection names are unavailable.")
        if isinstance(node, ast.Attribute) and (
            node.attr not in METHODS or not isinstance(node.ctx, ast.Load)
        ):
            raise ValueError(
                "Only ordinary JSON/string/list access methods are available."
            )
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id not in {
                *BUILTINS,
                *helpers,
                "fact",
            }:
                raise ValueError("Unknown adapter function: " + node.func.id)
            if not isinstance(node.func, (ast.Name, ast.Attribute)):
                raise ValueError("Indirect adapter calls are unavailable.")
    observe = next(
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "observe"
    )
    if [a.arg for a in observe.args.args] != ["snapshot", "request", "fixtures"]:
        raise ValueError("observe must take exactly snapshot, request, fixtures.")
    return tree


def load_observer(source):
    # Only called inside the no-network container. AST checks are an additional restriction,
    # not the sandbox boundary. No Store, filesystem handles, credentials or callbacks enter it.
    environment = {"__builtins__": BUILTINS, "fact": fact, "json": json}
    exec(compile(adapter_tree(source), "adapter.py", "exec"), environment)
    return environment["observe"]


def serialize_rule(rule):
    def term(value):
        return (
            value if variable(value) else json.dumps(decode(value), ensure_ascii=False)
        )

    def atom(value):
        return value["predicate"] + "(" + ", ".join(map(term, value["args"])) + ")"

    body = [("not " if a.get("negative") else "") + atom(a) for a in rule["body"]]
    body += [term(a) + " != " + term(b) for a, b in rule["distinct"]]
    body += [
        term(c["left"]) + " " + c["operator"] + " " + term(c["right"])
        for c in rule.get("comparisons", [])
    ]
    return atom(rule["head"]) + " :- " + ", ".join(body) + "."


def describe(candidate):
    candidate = Path(candidate)
    source = (candidate / "rules.dl").read_text()
    adapter_tree((candidate / "adapter.py").read_text())
    _, clauses, configuration = read_policy_document(source)
    binding = read_binding(
        dict(
            version=1,
            id="agentic-labcluster",
            context="Generated snapshot adapter for LabCluster; bound identities and operations come from the unchanged application dispatcher. The candidate is tested in an isolated simulator, not universally verified.",
            predicates=policy_predicates(source),
            decision=dict(
                request="Request", parameters="Parameter", allow="Allow", deny="Deny"
            ),
            configuration=configuration,
            tests=[],
        )
    )
    installed_rules(binding, source)
    parsed, _ = parse(clauses)
    rules = [
        dict(id=f"rule{i + 1}", datalog=serialize_rule(rule))
        for i, rule in enumerate(parsed)
    ]
    return dict(
        binding=binding,
        rules=rules,
        source=source,
        artifactHash=artifact_hash(candidate),
    )


def artifact_hash(candidate):
    root = Path(candidate)
    return fingerprint(
        {
            name: (root / name).read_text() if (root / name).exists() else None
            for name in FILES
        }
    )


def sections(policy):
    matches = list(re.finditer(r"^## (P[1-6])\b[^\n]*", policy, re.M))
    if [m[1] for m in matches] != [f"P{i}" for i in range(1, 7)]:
        raise ValueError(
            "The LabCluster profile expects the original six policy sections P1–P6."
        )
    return [
        dict(
            id=m[1],
            start=m.start(),
            end=matches[i + 1].start() if i + 1 < len(matches) else len(policy),
            text=policy[
                m.start() : matches[i + 1].start()
                if i + 1 < len(matches)
                else len(policy)
            ],
        )
        for i, m in enumerate(matches)
    ]


def validate_plan(plan, rules):
    rows = plan.get("coverage") if isinstance(plan, dict) else None
    if (
        not isinstance(rows, list)
        or {r.get("policyId") for r in rows if isinstance(r, dict)}
        != {f"P{i}" for i in range(1, 7)}
        or len(rows) != 6
    ):
        raise ValueError("plan.json needs exactly one coverage row for each P1–P6.")
    identifiers, referenced = {r["id"] for r in rules}, set()
    for row in rows:
        if (
            row.get("status")
            not in ("partial", "delegated", "unsupported", "supported")
            or not isinstance(row.get("notes"), str)
            or not row["notes"].strip()
        ):
            raise ValueError(
                "Each coverage row needs status and concrete scope/limitations notes."
            )
        ids = row.get("ruleIds")
        if (
            not isinstance(ids, list)
            or any(not isinstance(v, str) for v in ids)
            or set(ids) - identifiers
        ):
            raise ValueError(
                "Coverage references unknown rule IDs; static checks list rule1, rule2, etc. in clause order."
            )
        referenced.update(ids)
    if referenced != identifiers:
        raise ValueError(
            "Every generated rule needs a source-policy mapping: "
            + ", ".join(sorted(identifiers - referenced))
        )
    if (
        not isinstance(plan.get("limitations"), list)
        or not plan["limitations"]
        or any(not isinstance(v, str) or not v.strip() for v in plan["limitations"])
    ):
        raise ValueError(
            "Record concrete limitations, including direct Store access and non-synthetic information flow."
        )
    return deepcopy(plan)
