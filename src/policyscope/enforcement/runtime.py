"""Registered action port running locally in Python against native Soufflé."""

from copy import deepcopy
import threading
import json
from types import MappingProxyType
import uuid

from policyscope.core.contracts import (
    Applied,
    BridgeError,
    EffectNotAppliedError,
    NotApplied,
    Snapshot,
)
from policyscope.core.datalog import Souffle, encoded_fact, query_facts
from policyscope.core.policy import (
    CATALOG,
    FSM_INPUTS,
    canonical,
    compile_policy,
    decide,
    fact,
    fingerprint,
    installed_rules,
    validate_inputs,
    validate_intent,
    validate_state,
    text,
)


_query = query_facts  # Compatibility for existing applications; new analysis uses policy-query.


class AnalysisSnapshot:
    """A captured versioned view. It has no execute, source-write or registration authority."""

    def __init__(self, binding, rules, inputs, policy_hash, versions):
        self._binding, self._rules = deepcopy(binding), deepcopy(rules)
        self._inputs = deepcopy(inputs)
        self.policy_hash = policy_hash
        self.versions = MappingProxyType(dict(versions))
        self.input_hash = fingerprint(inputs)

    def facts(self):
        return deepcopy(self._inputs)

    def query(self, source):
        return _query(self._binding, self._rules, self._inputs, source)

    def check(self, intent):
        return decide(
            self._binding, self.policy_hash, self._rules, self._inputs, intent
        )

    def what_if(self, intent, inputs):
        captured = deepcopy(inputs)
        validate_state(self._binding, captured)
        return decide(self._binding, self.policy_hash, self._rules, captured, intent)


class _BoundPort:
    def __init__(self, runtime, principal):
        self._runtime, self._principal = runtime, principal

    def execute(self, action, resource=None, parameters=None):
        try:
            result = self._runtime.execute(
                {
                    "actor": self._principal,
                    "action": action,
                    **({"resource": resource} if resource is not None else {}),
                    "parameters": parameters or {},
                }
            )
        except BridgeError as error:
            raise BridgeError(
                error.code, "Protected operation did not complete.", error.attempt_id
            ) from None
        except Exception:
            raise BridgeError(
                "operation_failed", "Protected operation did not complete."
            ) from None
        public = {
            "allowed": result["allowed"],
            "attemptId": result["decision"]["request"]["id"],
        }
        if result["allowed"]:
            public["value"] = result["value"]
        return public


class PolicyRuntime:
    """One serialized policy scope. Authentication and storage are backend-owned. Uncertain execution stops this session.

    Give agents only bind(authenticated_identity). The runtime/admin object must remain private.
    A transaction context must enclose the complete source-read/gate/effect/commit sequence.
    Raise EffectNotAppliedError only after certified absence or rollback of *all* relevant effects.
    """

    def __init__(
        self,
        *,
        binding,
        bundle,
        observations=(),
        operations=(),
        inputs=None,
        transaction=None,
        managed=False,
        persist=None,
        prepare=None,
        local_effects=False,
    ):
        if bundle.get("version") != 2:
            raise ValueError(
                "Unsupported policy bundle; recompile with the trusted binding."
            )
        compiled = compile_policy(binding, bundle["source"])
        if compiled["hash"] != bundle.get("hash") or canonical(
            compiled["binding"]
        ) != canonical(bundle.get("binding")):
            raise ValueError("Policy bundle hash or binding mismatch.")
        self.binding, self.policy_hash = compiled["binding"], compiled["hash"]
        self.rules = installed_rules(self.binding, bundle["source"])
        if persist:
            from pathlib import Path

            persist = Path(persist).resolve()
        self._managed, self._persist, self._prepare = managed, persist, prepare
        self._local_effects = local_effects
        if local_effects and not managed:
            raise ValueError("Local EDB effects require managed facts.")
        if managed and observations:
            raise ValueError("Managed EDB does not mirror observation sources.")
        self._data_lock = None
        if persist:
            if not managed:
                raise ValueError("Persistence requires managed EDB.")
            from .edb import lock_facts

            self._data_lock = lock_facts(persist)
        try:
            if persist:
                from pathlib import Path
                from .edb import load_facts

                if Path(persist).exists():
                    inputs = load_facts(persist, self.policy_hash)
            self._inputs = self._checked(inputs or [])
            self._validate_fixed(self._inputs)
        except BaseException:
            if self._data_lock:
                self._data_lock.close()
            raise
        self._failed, self._operations = False, {}
        self.effect_calls = 0
        self._transaction = transaction
        self._lock, self._active = threading.Lock(), None
        self._sources, owned, identities = [], set(), set()
        for source in observations:
            text(source.id)
            if (
                source.id in identities
                or not source.predicates
                or not callable(source.read)
            ):
                raise ValueError("Distinct source identities and inputs are required.")
            identities.add(source.id)
            for name in source.predicates:
                if not self._admitted(name) or name in owned:
                    raise ValueError("Sources must own distinct admitted inputs.")
                owned.add(name)
            self._sources.append((source.id, tuple(source.predicates), source.read))
        for operation in operations:
            text(operation.action)
            outputs = tuple(operation.observations)
            if (
                operation.action in self._operations
                or not callable(operation.execute)
                or len(set(outputs)) != len(outputs)
                or any(
                    not self._admitted(n)
                    or n in owned
                    or ("fsm" in self.binding.get("mechanisms", []) and n in FSM_INPUTS)
                    for n in outputs
                )
            ):
                raise ValueError("Invalid operation or successful event ownership.")
            reads = tuple(operation.reads)
            if len(set(reads)) != len(reads) or any(
                self.binding["predicates"].get(n, {}).get("kind") != "derived"
                for n in reads
            ):
                raise ValueError(
                    "Operation reads must name distinct declared derived relations."
                )
            self._operations[operation.action] = (operation.execute, outputs, reads)
        if self.binding.get("fsmState") == "backend" and not {
            "ResourceType",
            "ResourceState",
        }.issubset(owned):
            raise ValueError(
                "Backend FSM requires authoritative ResourceType and ResourceState sources."
            )
        runtime_inputs = {
            self.binding["decision"]["request"],
            self.binding["decision"].get("parameters"),
        }
        event_inputs = {
            name for _, outputs, _ in self._operations.values() for name in outputs
        }
        unbound = (
            {
                name
                for name, schema in self.binding["predicates"].items()
                if schema["kind"] == "input"
            }
            - owned
            - runtime_inputs
            - event_inputs
        )
        if unbound and inputs is None:
            raise ValueError(
                "Register input producers or provide an explicit complete startup configuration: "
                + ", ".join(sorted(unbound))
            )

    def _validate_fixed(self, rows):
        if not self._managed:
            return
        from .edb import BUILTIN_KEYS

        fixed = {
            f["predicate"]
            for f in self.binding.get("configuration", [])
            if "key" not in self.binding["predicates"][f["predicate"]]
            and f["predicate"] not in BUILTIN_KEYS
        }
        expected = [
            f for f in self.binding.get("configuration", []) if f["predicate"] in fixed
        ]
        actual = [f for f in rows if f["predicate"] in fixed]
        if sorted(map(canonical, expected)) != sorted(map(canonical, actual)):
            raise ValueError("Reviewed static facts cannot be replaced.")

    def update(self, function):
        """Trusted host ingestion, never an agent assertion endpoint."""
        if not self._managed:
            raise ValueError("Direct updates require managed EDB.")
        from .edb import FactUpdates, save_facts

        self._enter()
        try:
            if self._failed:
                raise BridgeError("session_failed", "This session is stopped.")
            updates = FactUpdates(self.binding, self._inputs)
            try:
                function(updates)
            finally:
                rows = updates._finish()
            rows = self._checked(rows)
            self._validate_fixed(rows)
            if self._persist:
                try:
                    save_facts(self._persist, self.policy_hash, rows)
                except BaseException:
                    self._failed = True
                    raise BridgeError(
                        "execution_uncertain",
                        "Fact persistence was not confirmed; this session is stopped.",
                    ) from None
            self._inputs = rows
        finally:
            self._leave()

    def _admitted(self, name):
        gate = self.binding["decision"]
        return (
            name in self.binding["predicates"]
            and self.binding["predicates"][name]["kind"] == "input"
            and name not in (gate["request"], gate.get("parameters"))
            and not (
                "fsm" in self.binding.get("mechanisms", [])
                and name in FSM_INPUTS
                and not (
                    self.binding.get("fsmState") == "backend"
                    and name in ("ResourceType", "ResourceState")
                )
            )
        )

    def _checked(self, facts):
        validate_state(self.binding, facts)
        result = deepcopy(facts)
        closure = Souffle().evaluate([encoded_fact(f) for f in result], self.rules)
        if any(f["predicate"] in self.binding.get("invariants", []) for f in closure):
            raise ValueError("An application invariant was violated.")
        return result

    def _enter(self):
        if self._active == threading.get_ident():
            raise BridgeError(
                "reentrant_call", "A callback cannot re-enter its policy session."
            )
        self._lock.acquire()
        self._active = threading.get_ident()

    def _leave(self):
        self._active = None
        self._lock.release()

    def bind(self, authenticated_principal):
        text(authenticated_principal)
        return _BoundPort(self, authenticated_principal)

    def describe_predicates(self):
        """Explain actual startup registrations. This is an administrator API, never an agent tool."""
        selected = {
            name
            for mechanism in self.binding.get("mechanisms", [])
            for name in CATALOG[mechanism]["predicates"]
        }
        descriptions = []
        for name, schema in self.binding["predicates"].items():
            category = (
                "runtime"
                if name in self.binding["decision"].values()
                else "foundation"
                if name in selected
                else "application"
            )
            writers = [
                identity for identity, names, _ in self._sources if name in names
            ]
            events = [
                action
                for action, (_, outputs, _) in self._operations.items()
                if name in outputs
            ]
            if name in (
                self.binding["decision"]["request"],
                self.binding["decision"].get("parameters"),
            ):
                registration, writers = (
                    "runtime-request",
                    ["immutable operation intent"],
                )
            elif schema["kind"] == "derived":
                writers = [
                    r["id"] for r in self.rules if r["head"]["predicate"] == name
                ]
                application = any(writer.startswith("user_") for writer in writers)
                gates = any(not writer.startswith("user_") for writer in writers)
                registration = (
                    "foundation"
                    if name in selected
                    else "rules+gate"
                    if application and gates
                    else "gate"
                    if gates
                    else "rules"
                )
            elif writers:
                registration = "source"
            elif events:
                registration, writers = "effect-events", events
            elif (
                "fsm" in self.binding.get("mechanisms", []) and name == "ResourceState"
            ):
                registration, writers = "runtime-state", ["FSM executor"]
            elif self._managed and (
                "key" in schema
                or not any(
                    f["predicate"] == name
                    for f in self.binding.get("configuration", [])
                )
            ):
                registration, writers = (
                    "tool-input",
                    ["trusted tool result or host ingestion"],
                )
            else:
                registration, writers = (
                    "configuration",
                    ["trusted startup inputs (including explicitly empty relations)"],
                )
            descriptions.append(
                {
                    "predicate": name,
                    "kind": schema["kind"],
                    "args": list(schema["args"]),
                    "builtin": category != "application",
                    "category": category,
                    "key": schema.get(
                        "key",
                        ["Resource"]
                        if name in ("ResourceType", "ResourceState")
                        else None,
                    ),
                    "registration": registration,
                    "writers": writers,
                    "declaredAt": "reviewed policy schema",
                    "factProduction": {
                        "source": "automatically before gate, after confirmed effect, or during admin capture",
                        "rules": "Datalog evaluation",
                        "foundation": "fixed Datalog evaluation",
                        "gate": "mandatory gate evaluation",
                        "rules+gate": "application and mandatory gate evaluation",
                        "effect-events": "registered effect result, published after commit",
                        "runtime-state": "confirmed FSM execution",
                        "runtime-request": "bound business tool invocation",
                        "configuration": "reviewed .dl initial facts",
                        "tool-input": "atomic managed EDB update",
                    }[registration],
                    "agentCanAssert": False,
                }
            )
        return descriptions

    def capture(self, intent):
        """Admin-only source capture under the backend transaction; invokes no operation effect."""
        validate_intent(intent)
        request = {**deepcopy(intent), "id": str(uuid.uuid4())}
        request["parameters"] = MappingProxyType(dict(request.get("parameters", {})))
        context = MappingProxyType(
            {"request": MappingProxyType(request), "policyHash": self.policy_hash}
        )
        self._enter()
        try:

            def read_current():
                current, versions = self._refresh(context)
                if self._managed and self._prepare:
                    from .edb import FactUpdates

                    updates = FactUpdates(self.binding, current)
                    try:
                        self._prepare(MappingProxyType({**context, "facts": updates}))
                    finally:
                        current = updates._finish()
                    current = self._checked(current)
                return current, versions

            if self._transaction:
                with self._transaction(context):
                    current, versions = read_current()
            else:
                current, versions = read_current()
            self._inputs = current
            return AnalysisSnapshot(
                self.binding, self.rules, current, self.policy_hash, versions
            )
        finally:
            self._leave()

    def _refresh(self, context, current=None):
        replaced, facts, versions = set(), [], {}
        for identity, names, read in self._sources:
            snapshot = read(context)
            if not isinstance(snapshot, Snapshot) or snapshot.complete is not True:
                raise ValueError("A source must return a complete versioned Snapshot.")
            text(snapshot.version)
            if not snapshot.version.strip():
                raise ValueError("Empty snapshot version.")
            captured = deepcopy(snapshot.facts)
            validate_inputs(self.binding, captured)
            if any(f["predicate"] not in names for f in captured):
                raise ValueError("Source wrote an undeclared relation.")
            replaced.update(names)
            facts += captured
            versions[identity] = snapshot.version
        return self._checked(
            [
                f
                for f in (self._inputs if current is None else current)
                if f["predicate"] not in replaced
            ]
            + facts
        ), versions

    def _next(self, current, transition, observations, *, confirmed=False):
        if not transition:
            return self._checked([*current, *observations])
        resource = transition["resource"]
        if self.binding.get("fsmState") == "backend":
            if (
                confirmed
                and fact("ResourceState", resource, transition["to"]) not in current
            ):
                raise ValueError("Backend did not confirm the expected transition.")
            return self._checked([*current, *observations])
        if fact("ResourceState", resource, transition["from"]) not in current:
            raise ValueError("State changed before transition commit.")
        return self._checked(
            [
                f
                for f in current
                if not (f["predicate"] == "ResourceState" and f["args"][0] == resource)
            ]
            + observations
            + [fact("ResourceState", resource, transition["to"])]
        )

    def execute(self, intent, *, effect=None):
        validate_intent(intent)
        captured = deepcopy(intent)
        operation = (
            (
                effect,
                (),
                tuple(
                    name
                    for name, schema in self.binding["predicates"].items()
                    if schema["kind"] == "derived"
                ),
            )
            if effect is not None
            else self._operations.get(captured["action"])
        )
        if operation is None:
            raise ValueError("Unknown protected operation.")
        self._enter()
        request = {**captured, "id": str(uuid.uuid4())}
        frozen = {
            **request,
            "parameters": MappingProxyType(dict(request.get("parameters", {}))),
        }
        context = MappingProxyType(
            {"request": MappingProxyType(frozen), "policyHash": self.policy_hash}
        )
        effect_started, persist_started, transition, observations, edits = (
            False,
            False,
            None,
            [],
            None,
        )
        try:
            if self._failed:
                raise BridgeError(
                    "session_failed",
                    "An earlier execution was not confirmed; this session is stopped.",
                )

            def run():
                nonlocal effect_started, transition, observations, edits
                current, versions = self._refresh(context)
                if self._managed:
                    from .edb import FactUpdates

                    edits = FactUpdates(self.binding, current)
                    if self._prepare:
                        self._prepare(MappingProxyType({**context, "facts": edits}))
                    current = self._checked(edits._rows)
                decision = decide(
                    self.binding,
                    self.policy_hash,
                    self.rules,
                    current,
                    captured,
                    request["id"],
                    operation[2],
                )
                if versions:
                    decision["observationVersions"] = versions
                if not decision["allowed"]:
                    return {"allowed": False, "decision": decision}, current
                transition = decision.get("transition")
                if not self._managed:
                    self._next(current, transition, [])
                callback, outputs, _ = operation
                effect_started = True
                effect_context = MappingProxyType(
                    {
                        **context,
                        "observationVersions": MappingProxyType(dict(versions)),
                        "inputHash": fingerprint(current),
                        **(
                            {
                                "facts": edits,
                                "transition": MappingProxyType(dict(transition))
                                if transition
                                else None,
                            }
                            if self._managed
                            else {}
                        ),
                        "derived": MappingProxyType(
                            {
                                name: tuple(tuple(row) for row in rows)
                                for name, rows in decision.get("derived", {}).items()
                            }
                        ),
                    }
                )
                self.effect_calls += 1
                outcome = callback(effect_context)
                if isinstance(outcome, NotApplied):
                    raise EffectNotAppliedError(outcome.reason)
                if not isinstance(outcome, Applied):
                    raise RuntimeError("External outcome is uncertain.")
                committed = deepcopy(outcome.observations)
                validate_inputs(self.binding, committed)
                if any(f["predicate"] not in outputs for f in committed):
                    raise ValueError("Operation wrote an undeclared successful event.")
                # Keep pipe-compatible size bounds even without a pipe.
                if (
                    len(
                        canonical(
                            {"value": outcome.value, "observations": committed}
                        ).encode()
                    )
                    > 524_288
                ):
                    raise ValueError("Effect result exceeds contract limits.")
                observations = committed
                base = edits._finish() if edits else current
                if edits:
                    # Existing lifecycle rows are changed by the confirmed FSM commit, not by a handler.
                    before = {
                        f["args"][0]: f["args"][1]
                        for f in current
                        if f["predicate"] == "ResourceState"
                    }
                    after = {
                        f["args"][0]: f["args"][1]
                        for f in base
                        if f["predicate"] == "ResourceState"
                    }
                    types_before = {
                        tuple(f["args"])
                        for f in current
                        if f["predicate"] == "ResourceType"
                    }
                    types_after = {
                        tuple(f["args"])
                        for f in base
                        if f["predicate"] == "ResourceType"
                    }
                    if not types_before.issubset(types_after) or any(
                        after.get(r) != state for r, state in before.items()
                    ):
                        raise ValueError(
                            "Handlers cannot bypass the managed lifecycle transition."
                        )
                    # New tool-created resources must start in their configured initial state.
                    initials = {
                        f["args"][0]: f["args"][1]
                        for f in base
                        if f["predicate"] == "InitialState"
                    }
                    for resource, kind in types_after - types_before:
                        if (
                            kind not in initials
                            or after.get(resource) != initials[kind]
                        ):
                            raise ValueError(
                                "New resources must match their configured InitialState."
                            )
                base = self._next(base, transition, observations)
                staged, committed_versions = self._refresh(context, base)
                if self.binding.get("fsmState") == "backend":
                    if transition:
                        staged = self._next(staged, transition, [], confirmed=True)
                    else:
                        before = [
                            f
                            for f in current
                            if f["predicate"] == "ResourceState"
                            and f["args"][0]
                            == request.get(
                                "resource",
                                request["parameters"].get(
                                    self.binding.get("fsmTarget", "resource")
                                ),
                            )
                        ]
                        after = [
                            f
                            for f in staged
                            if f["predicate"] == "ResourceState"
                            and f["args"][0]
                            == request.get(
                                "resource",
                                request["parameters"].get(
                                    self.binding.get("fsmTarget", "resource")
                                ),
                            )
                        ]
                        if before and before != after:
                            raise ValueError(
                                "An unselected operation changed its managed resource state."
                            )
                decision["committedObservationVersions"] = committed_versions
                result = {"allowed": True, "decision": decision, "value": outcome.value}
                if (
                    len(json.dumps(result, ensure_ascii=True, allow_nan=False).encode())
                    > 1_047_552
                ):
                    raise ValueError("Execution reply exceeds adapter frame limit.")
                return result, staged

            if self._transaction:
                with self._transaction(context):
                    result, staged = run()
            else:
                result, staged = run()
            if self._persist:
                from .edb import save_facts

                persist_started = True
                save_facts(self._persist, self.policy_hash, staged)
            self._inputs = staged  # Publish only after successful backend commit.
            return result
        except EffectNotAppliedError:
            raise BridgeError(
                "not_applied", "Operation was confirmed not applied.", request["id"]
            ) from None
        except BaseException as error:
            if effect_started and self._local_effects and not persist_started:
                raise BridgeError(
                    "not_applied", "Local fact edits were discarded.", request["id"]
                ) from None
            if effect_started or persist_started:
                self._failed = True
                raise BridgeError(
                    "execution_uncertain",
                    "Execution was not confirmed; this session is stopped.",
                    request["id"],
                ) from None
            raise error
        finally:
            if edits and not edits._closed:
                edits._finish()
            self._leave()

    def snapshot(self):
        self._enter()
        try:
            return deepcopy(self._inputs)
        finally:
            self._leave()

    def check(self, intent):
        self._enter()
        try:
            return decide(
                self.binding, self.policy_hash, self.rules, self._inputs, intent
            )
        finally:
            self._leave()

    def what_if(self, intent, hypothetical_inputs):
        """A read-only preview over a complete hypothetical snapshot, never an authorization."""
        self._enter()
        try:
            hypothetical = self._checked(hypothetical_inputs)
            return decide(
                self.binding, self.policy_hash, self.rules, hypothetical, intent
            )
        finally:
            self._leave()

    def replace_inputs(self, facts):
        captured = deepcopy(facts)
        self._enter()
        try:
            if "fsm" in self.binding.get("mechanisms", []):
                protected = lambda items: sorted(
                    {
                        canonical(f)
                        for f in items
                        if f["predicate"] in FSM_INPUTS
                        and not (
                            self.binding.get("fsmState") == "backend"
                            and f["predicate"] in ("ResourceType", "ResourceState")
                        )
                    }
                )
                if protected(captured) != protected(self._inputs):
                    raise ValueError(
                        "FSM configuration and runtime-owned state cannot be replaced."
                    )
            self._inputs = self._checked(captured)
        finally:
            self._leave()

    def query(self, source):
        self._enter()
        try:
            return _query(self.binding, self.rules, self._inputs, source)
        finally:
            self._leave()

    def close(self):
        self._enter()
        try:
            if self._data_lock:
                self._data_lock.close()
                self._data_lock = None
            self._failed = True
        finally:
            self._leave()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
