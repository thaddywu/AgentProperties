"""Read-only relation views over explicit gate snapshots or historical log facts."""

from copy import deepcopy

from policyweave.core.datalog import Souffle, decode, encoded_fact
from policyweave.core.policy import CATALOG, decide, fact, installed_rules
from .log_query import LogQuerySession
from .trajectory import TrajectorySession


def relations(binding, rows, kind):
    # Current framework labels keep older captures readable without rewriting evidence.
    shared = {
        name: schema
        for mechanism in binding.get("mechanisms", [])
        for name, schema in CATALOG[mechanism]["predicates"].items()
    }
    grouped = {}
    for row in rows:
        name, args = row["predicate"], row["args"]
        schema = binding["predicates"].get(name)
        if schema is None or schema["kind"] != kind:
            continue
        if len(args) != len(schema["args"]) or any(
            not isinstance(a, str) for a in args
        ):
            raise ValueError("Relation rows must match the recorded schema.")
        grouped.setdefault(name, []).append(args)
    return [
        dict(
            name=name,
            columns=schema["args"],
            meaning=shared.get(name, schema).get("meaning", ""),
            rows=sorted(grouped.get(name, [])),
        )
        for name, schema in sorted(binding["predicates"].items())
        if schema["kind"] == kind
    ]


def inspect(timeline, event_id, *, phase="before", derive=False, gate=None):
    """Never resolves files or imports app code; gate links come from the host."""
    if phase not in {"before", "after"} or type(derive) is not bool:
        raise ValueError("Choose a snapshot phase and a boolean derivation option.")
    timeline.event(event_id)
    if gate is None:
        gate = timeline.gate(event_id)
    if gate is not None:
        gate_timeline, gate_event_id = gate
        session = TrajectorySession(gate_timeline.export())
        event = session.event(gate_event_id)
        binding, source = session.binding, session.source
        rows = deepcopy(event["inputs" if phase == "before" else "committedInputs"])
        if rows is None:
            return dict(
                available=False,
                scope="gate",
                phase=phase,
                reason="This snapshot was not confirmed.",
            )
        decision = event.get("decision") or {}
        derived = []
        status = "not_recorded"
        if phase == "before" and event["kind"] == "call":
            request, contract = event["request"], binding["decision"]
            rows.append(
                fact(
                    contract["request"],
                    request["id"],
                    request["actor"],
                    request["action"],
                )
            )
            parameters = dict(request.get("parameters", {}))
            if "resource" in request:
                parameters.setdefault("resource", request["resource"])
            rows.extend(
                fact(contract["parameters"], request["id"], k, v)
                for k, v in parameters.items()
            )
            captured = decision.get("derived")
            if captured is not None:
                derived = [
                    dict(predicate=name, args=args)
                    for name, values in captured.items()
                    for args in values
                ]
                status = "recorded"
            if derive:
                result = decide(
                    binding,
                    session.policy_hash,
                    session.rules,
                    event["inputs"],
                    {k: v for k, v in request.items() if k != "id"},
                    request["id"],
                    tuple(
                        n
                        for n, s in binding["predicates"].items()
                        if s["kind"] == "derived"
                    ),
                )
                derived = [
                    dict(predicate=name, args=args)
                    for name, values in result["derived"].items()
                    for args in values
                ]
                status = "recomputed"
        elif derive:
            closure = Souffle().evaluate([encoded_fact(f) for f in rows], session.rules)
            derived = [
                dict(predicate=f["predicate"], args=[decode(a) for a in f["args"]])
                for f in closure
            ]
            status = "recomputed"
        return dict(
            available=True,
            scope="gate",
            phase=phase,
            eventId=event_id,
            gateEventId=gate_event_id,
            gateTrajectoryId=gate_timeline.identity,
            policyHash=session.policy_hash,
            edb=relations(binding, rows, "input"),
            idb=relations(binding, derived, "derived"),
            idbStatus=status,
            recordedPredicates=sorted(decision.get("derived", {}))
            if phase == "before"
            else [],
            rules=source,
            decision=dict(
                allowed=decision.get("allowed"),
                reasons=decision.get("reasons", []),
                outcome=event["outcome"],
                effectCalled=event.get("effectCalled"),
            ),
        )
    # Historical projections are explicitly whole-log observations, not an invented event EDB.
    session = LogQuerySession(timeline)
    contract = session.contract
    binding, source, rows = contract["binding"], contract["source"], contract["inputs"]
    derived = []
    if derive:
        closure = Souffle().evaluate(
            [encoded_fact(f) for f in rows], installed_rules(binding, source)
        )
        derived = [
            dict(predicate=f["predicate"], args=[decode(a) for a in f["args"]])
            for f in closure
        ]
    return dict(
        available=True,
        scope="history",
        phase=None,
        eventId=event_id,
        edb=relations(binding, rows, "input"),
        idb=relations(binding, derived, "derived"),
        idbStatus="recomputed" if derive else "not_recorded",
        recordedPredicates=[],
        rules=source,
        limitations=contract["scope"],
    )
