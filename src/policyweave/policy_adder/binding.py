"""Host validation of source-backed inventories and fixed-EDB port bindings.

Evidence is parsed as data; application Python is never imported on the host.
Source citations establish provenance, not semantic truth or complete mediation.
"""

import ast
from copy import deepcopy
from difflib import get_close_matches
import re

from policyweave.core.artifacts import artifact_text
from policyweave.core.datalog import NAME, parse, variable
from policyweave.core.policy import CATALOG, CORE, field_contract, fingerprint
from policyweave.core.source import read_policy_document


KINDS = {"tool", "message", "model_context", "reply", "background"}
DISPOSITIONS = {"supported", "partial", "unsupported", "ambiguous"}
STOCK = {**CORE, **{n: s for m in CATALOG.values() for n, s in m["predicates"].items()}}
CONFIGURATION_INPUTS = {"PrincipalGroup", "ResourceGroup", "Capability", "InitialState", "AllowedTransition"}
MAX_DERIVED = 0


class BindingError(ValueError):
    """A rejected plan section that can be repaired without replacing others."""

    def __init__(self, message, sections):
        super().__init__(message)
        self.sections = sorted(set(sections))


def bounded(value, limit=4000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError("Expected a bounded, nonblank binding description.")
    return value


def identifier(value):
    if not isinstance(value, str) or not NAME.fullmatch(value) or len(value) > 64:
        raise ValueError("Invalid binding identifier: " + repr(value)[:160])
    return value


def evidence(value, original, framework, policy):
    if not isinstance(value, dict) or set(value) != {"origin", "file", "quote"}:
        raise ValueError("Evidence needs origin, file and exact quote.")
    origin = value["origin"]
    if origin not in {"application", "framework", "policy"}:
        raise ValueError("Unknown evidence origin.")
    value = dict(value)
    prefix = "framework/policyweave/" if origin == "framework" else "original/"
    if isinstance(value["file"], str) and value["file"].startswith(prefix):
        value["file"] = value["file"][len(prefix):]
    if origin == "policy" and value["file"] != policy:
        raise ValueError("Policy evidence must identify the original policy.")
    root = framework if origin == "framework" else original
    text = artifact_text(root, value["file"])
    quote = bounded(value["quote"], 8000)
    start = text.find(quote)
    if start < 0 or text.find(quote, start + 1) >= 0:
        candidates = [line for line in text.splitlines() if quote in line]
        if not candidates:
            candidates = get_close_matches(quote.splitlines()[0], text.splitlines(), n=3, cutoff=0.3)
        raise ValueError("Evidence must quote one exact, unique source span in "
                         + value["file"] + ": " + repr(quote)[:300]
                         + " (matches: " + str(text.count(quote)) + "). Actual candidate lines: "
                         + repr(candidates)[:1000])
    return dict(value, start=start, end=start + len(quote))


def _symbol(source, symbol):
    found = []

    def visit(body, prefix=""):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = prefix + node.name
                if name == symbol:
                    found.append(node)
                visit(node.body, name + ".")

    visit(ast.parse(source).body)
    if len(found) != 1 or not isinstance(found[0], (ast.FunctionDef, ast.AsyncFunctionDef)):
        raise ValueError("Boundary must identify one actual Python function or method.")
    return found[0]


def validate_inventory(value, original, framework, policy):
    if not isinstance(value, dict) or set(value) != {"boundaries", "gaps"}:
        raise ValueError("Inventory requires boundaries and gaps.")
    rows = value["boundaries"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 100:
        raise ValueError("Inventory requires 1–100 actual boundaries.")
    result, seen = [], set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "id", "kind", "file", "symbol", "parameters", "identity", "effect", "outcome", "evidence"
        }:
            raise ValueError("Boundary contract has missing or unknown fields.")
        name = identifier(row["id"])
        if name in seen or row["kind"] not in KINDS:
            raise ValueError("Use distinct boundary IDs and kinds: " + ", ".join(sorted(KINDS)))
        seen.add(name)
        node = _symbol(artifact_text(original, row["file"]), bounded(row["symbol"], 200))
        parameters = [a.arg for a in node.args.posonlyargs + node.args.args + node.args.kwonlyargs]
        if parameters and parameters[0] in {"self", "cls"}:
            parameters.pop(0)
        parameters += [a.arg for a in (node.args.vararg, node.args.kwarg) if a]
        if row["parameters"] != parameters:
            raise ValueError("Boundary parameters differ from the actual source signature.")
        proof = evidence(row["evidence"], original, framework, policy)
        if proof["origin"] != "application" or proof["file"] != row["file"]:
            raise ValueError("Boundary evidence must come from its application file.")
        source = artifact_text(original, row["file"])
        lines = source.splitlines(keepends=True)
        begin, end = sum(map(len, lines[:node.lineno - 1])), sum(map(len, lines[:node.end_lineno]))
        if proof["start"] < begin or proof["end"] > end:
            raise ValueError("Boundary evidence is outside the named function.")
        for key in ("identity", "effect", "outcome"):
            bounded(row[key])
        result.append(dict(row, evidence=proof))
    gaps = value["gaps"]
    if not isinstance(gaps, list) or len(gaps) > 100:
        raise ValueError("Inventory gaps must be a bounded list.")
    for gap in gaps:
        bounded(gap)
    return dict(boundaries=result, gaps=deepcopy(gaps))


def validate_plan(value, inventory, original, framework, policy):
    if not isinstance(value, dict) or set(value) != {
        "mechanisms", "configuration", "calls", "observations", "derived", "invariants", "requirements", "agent_writes"
    }:
        raise ValueError("Binding plan has missing or unknown fields.")
    # Report independent citation mistakes together so one repair need not
    # regenerate an otherwise valid plan for each incorrect quotation.
    citation_errors = []

    def inspect_proofs(node, path="plan"):
        if isinstance(node, dict):
            if set(node) == {"origin", "file", "quote"}:
                try:
                    evidence(node, original, framework, policy)
                except (ValueError, OSError) as error:
                    citation_errors.append(path + " (" + repr(node.get("file"))[:160] + "): " + str(error))
            else:
                for key, item in node.items():
                    inspect_proofs(item, path + "." + key)
        elif isinstance(node, list):
            for i, item in enumerate(node):
                inspect_proofs(item, path + "[" + str(i) + "]")

    inspect_proofs(value)
    for write in value["agent_writes"]:
        if write.get("evidence", {}).get("origin") != "policy":
            citation_errors.append("agent_writes authority must quote the ORIGINAL POLICY, not the framework guide or an available API.")
    actions = set()
    boundaries = {row["id"] for row in inventory["boundaries"]}
    for call in value["calls"]:
        action = call.get("action")
        try:
            identifier(action)
        except ValueError as error:
            citation_errors.append(str(error))
        if action in actions:
            citation_errors.append("Duplicate action " + repr(action) + "; use distinct gate names for different boundaries.")
        actions.add(action)
        if call.get("boundary") not in boundaries:
            citation_errors.append("Unknown boundary " + repr(call.get("boundary")) + "; actual IDs: " + repr(sorted(boundaries)))
    if citation_errors:
        citation_errors = list(dict.fromkeys(citation_errors))
        sections = {key for key in value if any("plan." + key in error for error in citation_errors)}
        if any("Duplicate action" in error or "Unknown boundary" in error or "Invalid binding identifier" in error for error in citation_errors):
            sections.update(("calls", "requirements"))
        if any("agent_writes authority" in error for error in citation_errors):
            sections.add("agent_writes")
        raise BindingError("Invalid binding evidence/contracts:\n" + "\n".join(citation_errors)[:5000], sections)
    plan = deepcopy(value)
    mechanisms = plan["mechanisms"]
    if (not isinstance(mechanisms, list) or "observations" not in mechanisms
            or len(set(mechanisms)) != len(mechanisms) or any(m not in CATALOG for m in mechanisms)):
        raise ValueError("Select shared catalog mechanisms, including observations.")
    selected = {n for m in mechanisms for n, s in CATALOG[m]["predicates"].items() if s["kind"] == "input"}
    configuration = plan["configuration"]
    if not isinstance(configuration, list) or len(configuration) > 500:
        raise BindingError("Configuration must be a bounded list of reviewed static input facts.", ["configuration"])
    seen_configuration = set()
    for row in configuration:
        if not isinstance(row, dict) or set(row) != {"predicate", "args", "meaning", "evidence"}:
            raise BindingError("Configuration needs predicate, args, meaning and source evidence.", ["configuration"])
        name, args = row["predicate"], row["args"]
        if (name not in CONFIGURATION_INPUTS & selected or not isinstance(args, list)
                or len(args) != len(STOCK[name]["args"])):
            raise BindingError("Configure selected PrincipalGroup/ResourceGroup/Capability/InitialState/AllowedTransition only; observations require real producers.", ["configuration"])
        for arg in args:
            bounded(arg, 1024)
        key = (name, tuple(args))
        if key in seen_configuration:
            raise BindingError("Duplicate static configuration fact.", ["configuration"])
        seen_configuration.add(key)
        bounded(row["meaning"])
        row["evidence"] = evidence(row["evidence"], original, framework, policy)
        if row["evidence"]["origin"] not in {"policy", "application"}:
            raise BindingError("Application roles and grants require original policy/application evidence, not framework examples.", ["configuration"])
    boundary_ids = {r["id"] for r in inventory["boundaries"]}
    actions = set()
    for call in plan["calls"]:
        required = {"action", "boundary", "parameters", "principal", "before", "after", "success", "failure"}
        if not isinstance(call, dict) or set(call) - {"role"} != required:
            raise ValueError("Calls require complete parameter, producer and result contracts.")
        if call.get("role", "gate") not in {"gate", "producer"}:
            raise BindingError("Call role must be gate or producer.", ["calls"])
        action = identifier(call["action"])
        if action in actions or call["boundary"] not in boundary_ids:
            raise ValueError("Call " + action + " needs a unique action and a discovered boundary ID; got "
                             + repr(call["boundary"]) + ", available: " + ", ".join(sorted(boundary_ids)))
        actions.add(action)
        for key in ("principal", "before", "after", "success", "failure"):
            bounded(call[key])
        names = set()
        for parameter in call["parameters"]:
            if not isinstance(parameter, dict) or set(parameter) != {"name", "path", "type", "evidence"}:
                raise ValueError("Parameters need actual paths, types and evidence.")
            name = identifier(parameter["name"])
            path = parameter["path"]
            if (not isinstance(path, list) or not 1 <= len(path) <= 8
                    or any(not isinstance(p, str) or not NAME.fullmatch(p) for p in path)
                    or name != "_".join(path) or name in names
                    or parameter["type"] not in {"symbol", "number", "boolean", "json"}):
                raise ValueError("Invalid or ambiguous actual parameter mapping.")
            names.add(name)
            parameter["evidence"] = evidence(parameter["evidence"], original, framework, policy)
        if len(names) > 32:
            raise ValueError("A call exceeds the runtime parameter limit.")
    if not actions or len(actions) > 100:
        raise ValueError("Binding requires 1–100 calls.")
    required_actions = set()
    for boundary in inventory["boundaries"]:
        if boundary["kind"] != "tool":
            continue
        node = _symbol(artifact_text(original, boundary["file"]), boundary["symbol"])
        for comparison in (n for n in ast.walk(node) if isinstance(n, ast.Compare)):
            if (isinstance(comparison.left, ast.Name)
                    and comparison.left.id in {"name", "tool", "tool_name"}
                    and len(comparison.ops) == 1 and isinstance(comparison.ops[0], ast.Eq)
                    and isinstance(comparison.comparators[0], ast.Constant)
                    and isinstance(comparison.comparators[0].value, str)):
                required_actions.add(comparison.comparators[0].value)
    if required_actions - actions:
        raise ValueError("Bind actual dispatcher tool actions, not only its generic function: " + ", ".join(sorted(required_actions - actions)))
    fields = {}
    observations = plan["observations"]
    if not isinstance(observations, list) or len(observations) > 128:
        raise ValueError("Observation contracts must be bounded.")
    for observation in observations:
        if not isinstance(observation, dict) or set(observation) != {
            "predicate", "name", "cardinality", "type", "unit", "observed_at", "meaning", "scope", "missing", "timing", "producer", "evidence"
        }:
            raise ValueError("Observations require field semantics, scope, timing and actual producers.")
        kind, name = observation["predicate"], identifier(observation["name"])
        if kind != "Field":
            raise ValueError("New EDB predicates are forbidden; bind Field.")
        for key in ("meaning", "scope", "missing", "producer"):
            bounded(observation[key])
        if observation["timing"] not in {"before", "after", "host"}:
            raise ValueError("Unknown observation timing.")
        observation["evidence"] = evidence(observation["evidence"], original, framework, policy)
        if name in fields:
            raise ValueError("Fields need unique names.")
        fields[name] = dict(cardinality=observation["cardinality"], type=observation["type"],
                            unit=observation["unit"], observedAt=observation["observed_at"])
    field_contract(fields)
    if plan["derived"] != [] or plan["invariants"] != []:
        raise BindingError("No new EDB or IDB schema is allowed; derived and invariants must be [].", ["derived", "invariants"])
    requirements = plan["requirements"]
    if not isinstance(requirements, list) or not 1 <= len(requirements) <= 200:
        raise ValueError("Requirements must explicitly preserve supported clauses and gaps.")
    policy_text = artifact_text(original, policy)
    seen, covered = set(), set()
    sections = list(re.finditer(r"^(?:##\s+)?(P\d+)(?:[. (])", policy_text, re.M))
    for row in requirements:
        if not isinstance(row, dict) or set(row) != {"id", "quote", "disposition", "calls", "reason"}:
            raise ValueError("Each requirement needs a source quote, disposition, calls and reason.")
        name = identifier(row["id"])
        if name in seen or row["disposition"] not in DISPOSITIONS or any(c not in actions for c in row["calls"]):
            raise ValueError("Requirement references or disposition are invalid.")
        seen.add(name)
        bounded(row["reason"])
        proof = evidence(dict(origin="policy", file=policy, quote=row["quote"]), original, framework, policy)
        for i, match in enumerate(sections):
            end = sections[i + 1].start() if i + 1 < len(sections) else len(policy_text)
            if proof["start"] < end and proof["end"] > match.start():
                covered.add(match[1])
    if covered != {m[1] for m in sections}:
        raise ValueError("Every original P-numbered policy needs a disposition, including gaps.")
    writes = plan["agent_writes"]
    if not isinstance(writes, list) or len(writes) > 32:
        raise ValueError("Agent recording authority must be explicitly bounded.")
    for write in writes:
        if not isinstance(write, dict) or set(write) != {"principal", "kind", "subject", "authority", "evidence"}:
            raise ValueError("Agent writes need principal, subject and policy authority.")
        if write["kind"] != "existing_decision":
            raise ValueError("Agents cannot insert host observations or invent decision schemas.")
        for key in ("principal", "subject", "authority"):
            bounded(write[key])
        write["evidence"] = evidence(write["evidence"], original, framework, policy)
    plan["observationContract"] = dict(fields=fields)
    plan["callContract"] = {c["action"]: {p["name"]: p["type"] for p in c["parameters"]} for c in plan["calls"]}
    return plan


def validate_program(source, plan):
    declarations, rule_source, configuration = read_policy_document(source)
    if plan["derived"] or declarations:
        raise ValueError("No new EDB or IDB schema is allowed.")
    selected = {n for m in plan["mechanisms"] for n, s in CATALOG[m]["predicates"].items() if s["kind"] == "input"}
    if any(row["predicate"] not in selected for row in configuration):
        raise ValueError("Configuration may contain only selected stock input facts.")
    if any(row["predicate"] in {"Field", "Event"} for row in configuration):
        raise ValueError("Observed facts require actual producers, not generated EDB seeds.")
    configured = [{"predicate": r["predicate"], "args": r["args"]} for r in plan["configuration"]]
    if (len(configuration) != len(configured)
            or {fingerprint(r) for r in configuration} != {fingerprint(r) for r in configured}):
        raise ValueError("Rules must retain exactly the frozen role/group/grant/FSM configuration.")
    rules, _ = parse(rule_source)
    producers = {call["action"] for call in plan["calls"] if call.get("role", "gate") == "producer"}
    for rule in rules:
        for atom in rule["body"]:
            if atom["predicate"] == "Request":
                action = atom["args"][2]
                if not variable(action) and action.removeprefix("c:") in producers:
                    raise ValueError("A producer-only call cannot be a requested policy action: " + action.removeprefix("c:"))
    from policyweave.core.policy import compile_policy, installed_rules, policy_predicates

    binding = dict(
        version=1, id="fixed-port", context="Source-backed frozen port contract.",
        predicates=policy_predicates(source, mechanisms=plan["mechanisms"]),
        mechanisms=plan["mechanisms"], observationContract=plan["observationContract"],
        callContract=plan["callContract"],
        decision=dict(request="Request", parameters="Parameter", allow="Allow", deny="Deny"),
        configuration=configuration, tests=[], invariants=plan["invariants"],
    )
    if "fsm" in plan["mechanisms"]:
        binding.update(fsmActions=sorted({r["args"][1] for r in configuration if r["predicate"] == "AllowedTransition"}), fsmTarget="resource", fsmState="runtime")
    compiled = compile_policy(binding, source)
    for rule in installed_rules(binding, source):
        for atom in [rule["head"], *rule["body"]]:
            if atom["predicate"] == "Field":
                name = atom["args"][1]
                if not variable(name):
                    key = name[2:] if name.startswith("c:") else name
                    registry = plan["observationContract"]["fields"]
                    if key not in registry:
                        raise ValueError("Rules reference an observation outside the frozen registry.")
    return compiled


def factory_source(plan):
    """Host-owned factory freezes schemas while allowing actual observation hooks."""
    return (
        '"""Host-generated fixed policy factory. Do not edit."""\n'
        "from pathlib import Path\n"
        "from policyweave.enforcement import Policy as _Policy\n\n"
        f"CONTRACT = {plan['observationContract']!r}\n"
        f"CALLS = {plan['callContract']!r}\n"
        f"MECHANISMS = {tuple(plan['mechanisms'])!r}\n"
        f"INVARIANTS = {tuple(plan['invariants'])!r}\n\n"
        "def make_policy(**options):\n"
        "    if {'bundle', 'mechanisms', 'invariants', 'observation_contract', 'call_contract'} & options.keys():\n"
        "        raise ValueError('Cannot override the frozen policy binding.')\n"
        "    return _Policy(Path(__file__).with_name('rules.dl'), mechanisms=MECHANISMS,\n"
        "                   invariants=INVARIANTS, observation_contract=CONTRACT, call_contract=CALLS, **options)\n"
    )
