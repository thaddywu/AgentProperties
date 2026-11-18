"""The admitted finite Datalog grammar and bounded native Soufflé execution.

Source is parsed as data. Only this module's emitter can produce native directives.
All constants cross the native boundary as hex symbols, including uppercase text,
Unicode, quotes and control characters. No model text becomes a command or path.
"""

import csv
from copy import deepcopy
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

NAME = re.compile(r"[A-Za-z][A-Za-z_0-9]*\Z")
TOKEN = re.compile(
    r'\s+|//[^\n]*|%[^\n]*|"(?:\\.|[^"\\])*"|:-|\?-|!=|<=|>=|[<>]|[A-Za-z_][A-Za-z_0-9]*|-?\d+(?:\.\d+)?|[(),.]'
)


def read_query(binding, source):
    """Admit exactly one data-only query without invoking the native engine."""
    query, columns = parse(source, query=True)
    for atom in query[0]["body"]:
        schema = binding["predicates"].get(atom["predicate"])
        if not schema or len(schema["args"]) != len(atom["args"]):
            raise ValueError("Unknown query predicate or wrong arity.")
    stratify(query)
    return query, columns


def query_facts(binding, rules, inputs, source):
    """Low-level read-only evaluation shared by legacy runtime APIs and policy-query."""
    query, columns = read_query(binding, source)
    combined = deepcopy(rules) + query
    stratify(combined)
    closure = Souffle().evaluate([encoded_fact(f) for f in inputs], combined)
    return {
        "columns": columns,
        "rows": [
            list(map(decode, f["args"]))
            for f in closure
            if f["predicate"] == "QueryResult"
        ],
    }


def variable(value):
    return bool(value) and "A" <= value[0] <= "Z"


def encode(value):
    return "c:" + value


def decode(value):
    return value[2:] if value.startswith("c:") else value


def encoded_fact(fact):
    return {**fact, "args": [encode(v) for v in fact["args"]]}


def encoded_rule(rule):
    term = lambda v: v if variable(v) else encode(v)
    return {
        **rule,
        **(
            {
                "comparisons": [
                    {**c, "left": term(c["left"]), "right": term(c["right"])}
                    for c in rule["comparisons"]
                ]
            }
            if rule.get("comparisons")
            else {}
        ),
        "head": {**rule["head"], "args": list(map(term, rule["head"]["args"]))},
        "body": [{**a, "args": list(map(term, a["args"]))} for a in rule["body"]],
        "distinct": [[term(a), term(b)] for a, b in rule["distinct"]],
    }


def parse(source, *, query=False):
    if not isinstance(source, str) or len(source.encode("utf-16-le")) // 2 > 20_000:
        raise ValueError("Program exceeds 20,000 characters.")
    tokens, offset = [], 0
    while offset < len(source):
        match = TOKEN.match(source, offset)
        if not match:
            raise ValueError("Unsupported Datalog syntax.")
        token, offset = match[0], match.end()
        if not token.isspace() and not token.startswith(("//", "%")):
            tokens.append(token)
    pos, anon, rules, columns = 0, 0, [], None

    def peek():
        return tokens[pos] if pos < len(tokens) else None

    def take(expected=None):
        nonlocal pos
        token = peek()
        if token is None or (expected is not None and token != expected):
            raise ValueError("Unexpected Datalog token.")
        pos += 1
        return token

    def term():
        nonlocal anon
        token = take()
        if token == "_":
            anon += 1
            return f"Anon${anon - 1}"
        if token.startswith('"'):
            value = json.loads(token)
            value.encode("utf-8")
            return encode(value)
        if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*|-?\d+(?:\.\d+)?", token):
            raise ValueError("Invalid Datalog term.")
        return token if variable(token) else encode(token)

    def atom():
        name = take()
        if not NAME.fullmatch(name) or name == "QueryResult":
            raise ValueError("Invalid or reserved predicate.")
        take("(")
        args = []
        if peek() != ")":
            args.append(term())
            while peek() == ",":
                take(",")
                args.append(term())
        take(")")
        return {"predicate": name, "args": args}

    def body():
        atoms, distinct, comparisons = [], [], []
        while True:
            if peek() == "not":
                take("not")
                atoms.append({**atom(), "negative": True})
            elif pos + 1 < len(tokens) and tokens[pos + 1] == "!=":
                a = term()
                take("!=")
                distinct.append([a, term()])
            elif pos + 1 < len(tokens) and tokens[pos + 1] in ("<", "<=", ">", ">="):
                left, operator = term(), take()
                comparisons.append(
                    {"left": left, "operator": operator, "right": term()}
                )
            else:
                atoms.append(atom())
            if peek() != ",":
                break
            take(",")
        return (
            [a for a in atoms if not a.get("negative")]
            + [a for a in atoms if a.get("negative")],
            distinct,
            comparisons,
        )

    while peek() is not None:
        if peek() == "?-":
            if not query or columns is not None or rules:
                raise ValueError("Use one read-only query.")
            take("?-")
            atoms, distinct, comparisons = body()
            terms = (
                [v for a in atoms for v in a["args"]]
                + [v for pair in distinct for v in pair]
                + [c[k] for c in comparisons for k in ("left", "right")]
            )
            columns = list(
                dict.fromkeys(
                    v for v in terms if variable(v) and not v.startswith("Anon$")
                )
            )
            head = {"predicate": "QueryResult", "args": columns}
            identifier = "query"
        else:
            if query:
                raise ValueError("Expected a read-only query.")
            head = atom()
            take(
                ":-"
            )  # Facts, native directives and embedded queries are never policy source.
            atoms, distinct, comparisons = body()
            identifier = f"user_{len(rules)}"
        rules.append(
            {
                "id": identifier,
                "head": head,
                "body": atoms,
                "distinct": distinct,
                "stratum": 0,
                **({"comparisons": comparisons} if comparisons else {}),
            }
        )
        take(".")
    if not rules or len(rules) > 99 or (query and columns is None):
        raise ValueError("Expected a bounded, nonempty rule program.")
    return rules, columns


def stratify(rules):
    arities = {}
    for rule in rules:
        bound = {
            v
            for a in rule["body"]
            if not a.get("negative")
            for v in a["args"]
            if variable(v)
        }
        checked = (
            rule["head"]["args"]
            + [v for a in rule["body"] if a.get("negative") for v in a["args"]]
            + [v for pair in rule["distinct"] for v in pair]
            + [c[k] for c in rule.get("comparisons", []) for k in ("left", "right")]
        )
        if any(variable(v) and v not in bound for v in checked):
            raise ValueError("Unsafe Datalog variable.")
        for atom in [rule["head"], *rule["body"]]:
            name, arity = atom["predicate"], len(atom["args"])
            if name in arities and arities[name] != arity:
                raise ValueError("Inconsistent predicate arity.")
            arities[name] = arity
    strata = dict.fromkeys(arities, 0)
    for _ in range(len(strata) + 1):
        changed = False
        for rule in rules:
            head = rule["head"]["predicate"]
            for atom in rule["body"]:
                required = strata[atom["predicate"]] + bool(atom.get("negative"))
                if required > strata[head]:
                    strata[head], changed = required, True
        if not changed:
            for rule in rules:
                rule["stratum"] = strata[rule["head"]["predicate"]]
            return
    raise ValueError("Unstratified negation.")


class Souffle:
    """Requires the `souffle` and `prlimit` executables on PATH; no Node dependency."""

    def evaluate(self, inputs, rules):
        arities = {}
        for atom in inputs + [a for r in rules for a in [r["head"], *r["body"]]]:
            name, arity = atom["predicate"], len(atom["args"])
            if not NAME.fullmatch(name) or (name in arities and arities[name] != arity):
                raise ValueError("Invalid predicate schema.")
            arities[name] = arity
        declarations = [
            f".decl {name}({', '.join(f'a{i}:symbol' for i in range(arity))})"
            for name, arity in arities.items()
        ]
        outputs = sorted({r["head"]["predicate"] for r in rules})
        declarations += [f".output {name}(IO=file, rfc4180=true)" for name in outputs]

        def symbol(value):
            raw = decode(value)
            if (
                re.fullmatch(r"0|-?[1-9][0-9]*", raw)
                and len(raw) < 21
                and -(2**63) <= int(raw) < 2**63
            ):
                return json.dumps("n" + raw)
            return '"v' + value.encode("utf-8").hex() + '"'

        def emit_atom(atom, variables=None):
            terms = [
                variables[v] if variables is not None and variable(v) else symbol(v)
                for v in atom["args"]
            ]
            return atom["predicate"] + "(" + ", ".join(terms) + ")"

        lines = declarations + [emit_atom(a) + "." for a in inputs]
        for rule in rules:
            variables = {
                v: f"V{i}"
                for i, v in enumerate(
                    dict.fromkeys(
                        v
                        for a in [rule["head"], *rule["body"]]
                        for v in a["args"]
                        if variable(v)
                    )
                )
            }
            body = [
                ("!" if a.get("negative") else "") + emit_atom(a, variables)
                for a in rule["body"]
            ]
            body += [
                (variables[a] if variable(a) else symbol(a))
                + " != "
                + (variables[b] if variable(b) else symbol(b))
                for a, b in rule["distinct"]
            ]
            for comparison in rule.get("comparisons", []):
                left, right = (
                    variables[v] if variable(v) else symbol(v)
                    for v in (comparison["left"], comparison["right"])
                )
                body += [
                    f'match("^n(0|-?[1-9][0-9]*)$", {left})',
                    f'match("^n(0|-?[1-9][0-9]*)$", {right})',
                    f"to_number(substr({left}, 1, strlen({left}) - 1)) {comparison['operator']} to_number(substr({right}, 1, strlen({right}) - 1))",
                ]
            lines.append(
                emit_atom(rule["head"], variables) + " :- " + ", ".join(body) + "."
            )
        source = "\n".join(lines)
        if len(source.encode()) > 4_194_304:
            raise ValueError("Native input limit exceeded.")
        with TemporaryDirectory(prefix="policy-souffle-") as directory:
            root = Path(directory)
            path = root / "program.dl"
            path.write_text(source, encoding="utf-8")
            with (root / "stderr").open("wb") as stderr:
                try:
                    result = subprocess.run(
                        [
                            "prlimit",
                            "--as=1073741824",
                            "--cpu=5",
                            "--fsize=8388608",
                            "--",
                            "souffle",
                            "-j",
                            "1",
                            "-D",
                            directory,
                            str(path),
                        ],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=stderr,
                        timeout=7,
                        check=False,
                    )
                except (OSError, subprocess.TimeoutExpired):
                    raise RuntimeError(
                        "Soufflé unavailable or execution limit exceeded."
                    ) from None
            if result.returncode:
                raise RuntimeError(
                    "Soufflé rejected the program or exceeded its execution limits."
                )
            paths = [root / (name + ".csv") for name in outputs]
            if sum(p.stat().st_size for p in paths) > 8_388_608:
                raise RuntimeError("Native output limit exceeded.")
            facts = {(a["predicate"], *a["args"]) for a in inputs}
            for name, path in zip(outputs, paths):
                with path.open(encoding="utf-8", newline="") as stream:
                    for row in csv.reader(stream):
                        values = (
                            [
                                (
                                    encode(v[1:])
                                    if v.startswith("n")
                                    else bytes.fromhex(v[1:]).decode("utf-8")
                                )
                                for v in row
                            ]
                            if arities[name]
                            else []
                        )
                        facts.add((name, *values))
                        if len(facts) > 10_000:
                            raise RuntimeError("Derived fact limit exceeded.")
            return [{"predicate": a[0], "args": list(a[1:])} for a in sorted(facts)]
