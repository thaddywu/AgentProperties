"""Portable binding validation and version-2 bundle compilation."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import uuid

from .datalog import NAME, Souffle, decode, encoded_fact, encoded_rule, parse, stratify
from .source import read_policy_source, read_policy_document

CATALOG = json.loads(Path(__file__).with_name("foundations.json").read_text())
INTERNAL = {"QueryResult", "RuntimeSentinel"}
CORE = {
    "Request": {"kind": "input", "args": ["Q", "Principal", "EventKind"], "meaning": "Runtime-owned immutable request."},
    "Parameter": {"kind": "input", "args": ["Q", "Name", "Value"], "meaning": "Runtime-bound request argument."},
    "Allow": {"kind": "derived", "args": ["Q"], "meaning": "Explicit request permission."},
    "Deny": {"kind": "derived", "args": ["Q", "Reason"], "meaning": "Explicit request refusal; overrides Allow."},
}
FSM_INPUTS = {k for k, v in CATALOG["fsm"]["predicates"].items() if v["kind"] == "input"}


def mechanism_predicates(name):
    """Declare a selected foundation without duplicating its schema in an adapter."""
    if name not in CATALOG:
        raise ValueError("Unknown policy mechanism.")
    return {k: {"kind": v["kind"], "args": list(v["args"]),
                "meaning": v.get("meaning", "Selected lifecycle foundation.")}
            for k, v in CATALOG[name]["predicates"].items()}


def policy_predicates(source, *, mechanisms=()):
    """Load app declarations from its rule file and add selected shared schemas."""
    predicates, _ = read_policy_source(source)
    shared = {}
    for mechanism in mechanisms:
        shared.update(mechanism_predicates(mechanism))
    if shared.keys() & predicates.keys():
        raise ValueError("Selected foundation schemas are supplied by the runtime, not redeclared.")
    return {**deepcopy(CORE), **shared, **predicates}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def text(value, limit=1024, *, empty=False):
    if not isinstance(value, str) or (not value and not empty) or len(value.encode("utf-16-le")) // 2 > limit:
        raise ValueError("Expected a bounded string.")
    value.encode("utf-8")


def validate_intent(intent):
    if not isinstance(intent, dict):
        raise ValueError("Invalid action intent.")
    for key in ("actor", "action"):
        text(intent.get(key))
    if "resource" in intent:
        text(intent["resource"])
    params = intent.get("parameters", {})
    if not isinstance(params, dict) or len(params) > 32:
        raise ValueError("Invalid operation parameters.")
    for key, value in params.items():
        if not isinstance(key, str) or not NAME.fullmatch(key) or len(key) > 64:
            raise ValueError("Invalid parameter name.")
        text(value, 4096, empty=True)


def validate_inputs(binding, facts):
    if not isinstance(facts, list) or len(facts) > 5000:
        raise ValueError("At most 5000 input facts.")
    gate = binding["decision"]
    for fact in facts:
        if not isinstance(fact, dict):
            raise ValueError("Invalid input fact.")
        name, args = fact.get("predicate"), fact.get("args")
        schema = binding["predicates"].get(name) if isinstance(name, str) else None
        if not schema or schema["kind"] != "input" or name in (gate["request"], gate.get("parameters")) or not isinstance(args, list) or len(args) != len(schema["args"]):
            raise ValueError("Only declared, non-request input facts may be supplied.")
        for index, arg in enumerate(args):
            text(arg, 4096, empty=True)
            if schema.get("types", ["symbol"] * len(args))[index] == "number":
                if not re.fullmatch(r"0|-?[1-9][0-9]*", arg) or len(arg) > 20 or not -(2**63) <= int(arg) < 2**63:
                    raise ValueError("Numeric facts require canonical signed 64-bit integers.")


def read_binding(value):
    value = deepcopy(value)
    if isinstance(value, dict) and isinstance(value.get("decision"), dict) and isinstance(value.get("predicates"), dict) and "parameters" not in value["decision"]:
        value["decision"]["parameters"] = "Parameter"
        value["predicates"].setdefault("Parameter", deepcopy(CORE["Parameter"]))
    if not isinstance(value, dict) or type(value.get("version")) is not int or value["version"] != 1 or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", value.get("id", "")):
        raise ValueError("Invalid version-1 binding.")
    text(value.get("context"), 12_000)
    if not value["context"].strip():
        raise ValueError("Empty binding context.")
    schemas, gate = value.get("predicates"), value.get("decision")
    if not isinstance(schemas, dict) or not 1 <= len(schemas) <= 64 or not isinstance(gate, dict) or set(gate) - {"request", "allow", "deny", "parameters"}:
        raise ValueError("Invalid binding schema.")
    for name, schema in schemas.items():
        if not NAME.fullmatch(name) or name in INTERNAL or not isinstance(schema, dict) or schema.get("kind") not in ("input", "derived"):
            raise ValueError("Invalid predicate declaration.")
        args = schema.get("args")
        if not isinstance(args, list) or len(args) > 8 or any(not isinstance(v, str) or not NAME.fullmatch(v) for v in args):
            raise ValueError("Invalid predicate arguments.")
        if "types" in schema and (not isinstance(schema["types"], list) or len(schema["types"]) != len(args) or any(t not in ("symbol", "number") for t in schema["types"])):
            raise ValueError("Invalid predicate field types.")
        key = schema.get('key')
        if 'key' in schema and (schema['kind'] != 'input' or not isinstance(key, list) or any(not isinstance(field, str) for field in key) or len(set(key)) != len(key) or any(field not in args for field in key)):
            raise ValueError('Invalid input key declaration.')
        text(schema.get("meaning"), 2000)
        if not schema["meaning"].strip():
            raise ValueError("Empty predicate meaning.")
    if any(not isinstance(v, str) for v in gate.values()) or len(set(gate.values())) != len(gate):
        raise ValueError("Gate predicates must differ.")
    for slot, kind, arity in [("request", "input", 3), ("allow", "derived", 1), ("deny", "derived", 2), *([("parameters", "input", 3)] if "parameters" in gate else [])]:
        schema = schemas.get(gate.get(slot))
        if not schema or schema["kind"] != kind or len(schema["args"]) != arity:
            raise ValueError("Invalid gate declaration.")
    mechanisms = value.get("mechanisms", [])
    if not isinstance(mechanisms, list) or ("mechanisms" in value and not mechanisms) or any(not isinstance(m, str) or m not in CATALOG for m in mechanisms) or len(set(mechanisms)) != len(mechanisms):
        raise ValueError("Invalid mechanism selection.")
    for mechanism in mechanisms:
        for name, expected in CATALOG[mechanism]["predicates"].items():
            actual = schemas.get(name)
            if name in gate.values() or not actual or actual["kind"] != expected["kind"] or len(actual["args"]) != len(expected["args"]):
                raise ValueError("Mechanism schema mismatch or gate overlap.")
    if "fsmActions" in value:
        actions = value["fsmActions"]
        if "fsm" not in mechanisms or not isinstance(actions, list) or len(actions) > 64:
            raise ValueError("Invalid FSM action selection.")
        for action in actions:
            text(action)
        if len(set(actions)) != len(actions):
            raise ValueError("Duplicate FSM action.")
    if "fsmTarget" in value:
        text(value["fsmTarget"])
        if "fsm" not in mechanisms or not NAME.fullmatch(value["fsmTarget"]):
            raise ValueError("FSM target must name a request parameter.")
    if "fsmState" in value and ("fsm" not in mechanisms or value["fsmState"] not in ("runtime", "backend")):
        raise ValueError("FSM state authority must be runtime or backend on an FSM binding.")
    tests = value.get("tests")
    if not isinstance(tests, list) or (tests and (not 2 <= len(tests) <= 100 or not any(t.get("allowed") is True for t in tests) or not any(t.get("allowed") is False for t in tests))):
        raise ValueError("Binding needs independent allow and deny cases.")
    names = set()
    if not isinstance(value.get("invariants", []), list) or any(schemas.get(name, {}).get("kind") != "derived" for name in value.get("invariants", [])):
        raise ValueError("Invariants must name declared derived relations that remain empty.")
    validate_inputs(value, value.get("configuration", []))
    for case in tests:
        text(case.get("name"), 4096)
        if case["name"] in names or type(case.get("allowed")) is not bool:
            raise ValueError("Invalid acceptance case.")
        names.add(case["name"])
        validate_intent(case.get("request"))
        validate_inputs(value, case.get("inputs"))
    return deepcopy(value)


def rule(identifier, head, body):
    return {"id": identifier, "head": head, "body": body, "distinct": [], "stratum": 0}


def fact(name, *args, **extra):
    return {"predicate": name, "args": ["" if value is None else str(value) for value in args], **extra}


def installed_rules(binding, source):
    declared, rule_source, configuration = read_policy_document(source)
    if any(item not in binding.get("configuration", []) for item in configuration):
        raise ValueError("Static policy facts do not match the reviewed configuration.")
    for name, schema in declared.items():
        expected = binding["predicates"].get(name)
        if not expected or any(schema[key] != expected[key] for key in ("kind", "args")):
            raise ValueError("Policy declarations do not match the trusted binding.")
        if schema.get('key') != expected.get('key'):
            raise ValueError('Policy keys do not match the trusted binding.')
        if schema.get("types", ["symbol"] * len(schema["args"])) != expected.get("types", ["symbol"] * len(expected["args"])):
            raise ValueError("Policy field types do not match the trusted binding.")
    application, _ = parse(rule_source)
    schemas, gate = binding["predicates"], binding["decision"]
    mechanisms = binding.get("mechanisms", [])
    protected = {k for m in mechanisms for k in CATALOG[m]["predicates"]}
    for r in application:
        for atom in [r["head"], *r["body"]]:
            schema = schemas.get(atom["predicate"])
            if not schema or len(schema["args"]) != len(atom["args"]):
                raise ValueError("Unknown predicate or wrong arity.")
        if schemas[r["head"]["predicate"]]["kind"] != "derived" or r["head"]["predicate"] in protected:
            raise ValueError("Policy cannot write inputs or replace a foundation.")
    fixed = [r for name in ("fsm", "capability", "provenance") if name in mechanisms for r in deepcopy(CATALOG[name]["rules"])]
    combined = [encoded_rule(r) for r in fixed] + application
    stratify(combined)
    return combined


def validate_state(binding, inputs):
    validate_inputs(binding, inputs)
    for name, schema in binding['predicates'].items():
        if 'key' not in schema: continue
        indices = [schema['args'].index(field) for field in schema['key']]
        seen = {}
        for row in inputs:
            if row['predicate'] != name: continue
            key = tuple(row['args'][i] for i in indices)
            if key in seen and seen[key] != row['args']: raise ValueError('Conflicting keyed input: ' + name)
            seen[key] = row['args']
    if "fsm" in binding.get("mechanisms", []):
        states, types, transitions, initials = {}, {}, {}, {}
        for f in inputs:
            name, args = f["predicate"], f["args"]
            if name in ("ResourceType", "ResourceState"):
                mapping = states if name == "ResourceState" else types
                if args[0] in mapping and mapping[args[0]] != args[1]:
                    raise ValueError("Conflicting lifecycle input.")
                mapping[args[0]] = args[1]
            if name == "AllowedTransition":
                if "fsmActions" in binding and args[1] not in binding["fsmActions"]:
                    raise ValueError("FSM selection must include every transition action.")
                key = tuple(args[:3])
                if key in transitions and transitions[key] != args[3]:
                    raise ValueError("Ambiguous transition.")
                transitions[key] = args[3]
            if name == "InitialState":
                if args[0] in initials and initials[args[0]] != args[1]:
                    raise ValueError("Conflicting initial state for resource type.")
                initials[args[0]] = args[1]
        if states.keys() != types.keys():
            raise ValueError("Each resource needs one type and current state.")


def needs_transition(binding, action):
    return "fsm" in binding.get("mechanisms", []) and ("fsmActions" not in binding or action in binding["fsmActions"])


def decide(binding, policy_hash, rules, inputs, intent, request_id=None, reads=()):
    validate_intent(intent)
    gate = binding["decision"]
    if intent.get("parameters") and "parameters" not in gate:
        raise ValueError("Binding does not declare parameters.")
    request = {**deepcopy(intent), "id": request_id or str(uuid.uuid4())}
    args = [request["id"], intent["actor"], intent["action"]]
    dynamic = [fact(gate["request"], *args)]
    parameters = dict(intent.get("parameters", {}))
    if "resource" in intent:
        if "resource" in parameters and parameters["resource"] != intent["resource"]:
            raise ValueError("Conflicting resource parameter.")
        parameters["resource"] = intent["resource"]
    if parameters and "parameters" not in gate:
        raise ValueError("Request parameters must be declared.")
    dynamic += [fact(gate["parameters"], request["id"], k, v) for k, v in parameters.items()]
    closure = Souffle().evaluate([encoded_fact(f) for f in [*inputs, *dynamic]], rules)
    if any(f["predicate"] in binding.get("invariants", []) for f in closure):
        closure.append(encoded_fact(fact(gate["deny"], request["id"], "invariant_violation")))
    transition = None
    if needs_transition(binding, intent["action"]):
        resource = intent.get("resource", parameters.get(binding.get("fsmTarget", "resource")))
        candidates = [f for f in closure if f["predicate"] == "CanTransition"
                      and list(map(decode, f["args"][:2])) == [resource, intent["action"]]]
        if len(candidates) == 1:
            transition = dict(zip(("from", "to"), map(decode, candidates[0]["args"][2:])))
            transition["resource"] = resource
        else:
            closure.append(encoded_fact(fact(gate["deny"], request["id"], "invalid_transition")))
    evidence = [f for f in closure if f["predicate"] in (gate["allow"], gate["deny"]) and decode(f["args"][0]) == request["id"]]
    reasons = [decode(f["args"][1]) for f in evidence if f["predicate"] == gate["deny"]]
    allowed = not reasons and any(f["predicate"] == gate["allow"] for f in evidence)
    result = {"allowed": allowed, "policyHash": policy_hash, "request": request, "reasons": reasons or ([] if allowed else ["no_explicit_allow"])}
    if reads:
        result["derived"] = {name: [list(map(decode, f["args"])) for f in closure if f["predicate"] == name] for name in reads}
    if allowed and transition:
        result["transition"] = transition
    return result


def compile_policy(binding, source):
    binding = read_binding(binding)
    rules = installed_rules(binding, source)
    identity = fingerprint({"version": 2, "binding": binding, "source": source, "rules": rules})
    for case in binding["tests"]:
        validate_state(binding, case["inputs"])
        if decide(binding, identity, rules, case["inputs"], case["request"])["allowed"] != case["allowed"]:
            raise ValueError("Acceptance case failed: " + case["name"])
    return {"version": 2, "binding": binding, "source": source, "hash": identity}
