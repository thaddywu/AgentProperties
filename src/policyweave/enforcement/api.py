"""Small backend integration API. Applications supply facts, not runtime machinery."""

from contextlib import contextmanager
from contextvars import ContextVar
import asyncio
from concurrent.futures import Future
from copy import deepcopy
from datetime import datetime, timezone
from functools import partial, wraps
import inspect
from pathlib import Path
from types import MappingProxyType
import threading
import uuid

from policyweave.core.contracts import Applied, BridgeError, NotApplied
from .caller import current_caller
from policyweave.core.datalog import parse
from policyweave.core.policy import (
    CORE,
    CATALOG,
    FSM_INPUTS,
    compile_policy,
    policy_predicates,
    canonical,
)
from .runtime import PolicyRuntime
from policyweave.core.source import read_policy_document


class DataRegistry:
    """Opaque, version-specific handles. Contents and backend lookup remain app-owned."""

    def __init__(self):
        self._references = {}
        self._descriptions = {}

    def reference(self, kind, key, version=""):
        identity = (str(kind), str(key), str(version))
        if identity not in self._references:
            value = "data-" + str(uuid.uuid4())
            self._references[identity] = value
            self._descriptions[value] = {
                "kind": identity[0],
                "key": identity[1],
                "version": identity[2],
            }
        return self._references[identity]

    def describe(self, identity):
        return deepcopy(self._descriptions[identity])


def _parameters(values, prefix=""):
    result = {}
    for name, value in values.items():
        key = prefix + name
        if isinstance(value, dict):
            nested = _parameters(value, key + "_")
            if result.keys() & nested.keys():
                raise ValueError("Ambiguous parameter names.")
            result.update(nested)
        else:
            if value is None or isinstance(value, list):
                if key in result:
                    raise ValueError("Ambiguous parameter names.")
                result[key] = canonical(value)
                continue
            if not isinstance(value, (str, int, bool)):
                raise ValueError(
                    "Tool parameters must be JSON strings, integers, booleans, null, arrays or nested dictionaries."
                )
            if key in result:
                raise ValueError("Ambiguous parameter names.")
            result[key] = (
                ("true" if value else "false")
                if isinstance(value, bool)
                else str(value)
            )
    return result


def _context(context):
    request = context["request"]
    public = {
        "id": request["id"],
        "principal": request["actor"],
        "event": request["action"],
        "parameters": request["parameters"],
    }
    return MappingProxyType({**context, "request": MappingProxyType(public)})


class Policy:
    """Load one reviewed .dl file; wrap existing business functions at the tool boundary."""

    def __init__(
        self,
        path,
        *,
        facts=None,
        transaction=None,
        target="resource",
        event=None,
        after=None,
        completed=None,
        refused=None,
        refusal=None,
        invariants=(),
        bundle=None,
        inputs=(),
        data=None,
        before=None,
        local_effects=False,
        mechanisms=(),
        observation_contract=None,
        call_contract=None,
        trace=False,
    ):
        if facts is not None and (data is not None or before is not None or inputs):
            raise ValueError(
                "Choose managed EDB or backend observation, not two state authorities."
            )
        requested = tuple(mechanisms)
        if len(set(requested)) != len(requested) or any(
            name not in CATALOG for name in requested
        ):
            raise ValueError("Select distinct supported mechanisms.")
        source = Path(path).read_text()
        _, rule_source, configuration = read_policy_document(source)
        clauses, _ = parse(rule_source)
        used = {
            atom["predicate"]
            for clause in clauses
            for atom in [clause["head"], *clause["body"]]
        }
        used.update(row["predicate"] for row in configuration)
        mechanisms = [
            name
            for name, module in CATALOG.items()
            if used.intersection(module["predicates"])
            or name in requested
            or (name == "observations" and observation_contract is not None)
        ]
        self.data = DataRegistry()
        self.events = []
        self._event, self._after = event, after
        self._effect_context = ContextVar("policy_effect", default=None)
        self._async_loop = self._async_lock = None
        self._completed = completed or (lambda _: True)
        self._refused = refused or (lambda _: {"ok": False, "code": "UNAVAILABLE"})
        self._refusal = refusal
        binding = {
            "version": 1,
            "id": "application-policy",
            "context": "Reviewed local application policy.",
            "predicates": policy_predicates(source, mechanisms=mechanisms),
            "decision": {
                "request": "Request",
                "parameters": "Parameter",
                "allow": "Allow",
                "deny": "Deny",
            },
            "tests": [],
            "configuration": configuration,
            "invariants": list(invariants),
        }
        if mechanisms:
            binding["mechanisms"] = mechanisms
        if observation_contract is not None:
            binding["observationContract"] = deepcopy(observation_contract)
        if call_contract is not None:
            binding["callContract"] = deepcopy(call_contract)
        if "fsm" in mechanisms:
            binding.update(
                fsmState="backend" if facts else "runtime",
                fsmTarget=target,
                fsmActions=sorted(
                    {
                        f["args"][1]
                        for f in configuration
                        if f["predicate"] == "AllowedTransition"
                    }
                ),
            )
        static = {f["predicate"] for f in configuration}
        observed = tuple(
            name
            for name, schema in binding["predicates"].items()
            if schema["kind"] == "input"
            and name not in CORE
            and name not in static
            and not (
                "fsm" in mechanisms
                and name in FSM_INPUTS
                and not (facts and name in ("ResourceType", "ResourceState"))
            )
        )
        from policyweave.core.contracts import ObservationSource, Snapshot
        from policyweave.core.policy import fingerprint

        def observe(context):
            rows = list(facts(_context(context), self.data))
            return Snapshot(fingerprint(rows), True, rows)

        self.runtime = PolicyRuntime(
            binding=binding,
            bundle=compile_policy(binding, source) if bundle is None else bundle,
            inputs=[*configuration, *inputs],
            observations=[ObservationSource("backend", observed, observe)]
            if facts
            else (),
            transaction=transaction,
            managed=facts is None,
            persist=data,
            local_effects=local_effects,
            prepare=(lambda context: before(_context(context))) if before else None,
            trace=trace,
        )

    def trajectory(self):
        """Private operator export of recorded policy inputs and outcomes."""
        return self.runtime.trajectory()

    def update(self, function):
        """Trusted host writes input facts atomically; never export this as an agent tool."""
        return self.runtime.update(function)

    @contextmanager
    def _scope(self, context):
        token = self._effect_context.set(context)
        try:
            yield
        finally:
            self._effect_context.reset(token)

    def _facts(self):
        context = self._effect_context.get()
        if context is None or "facts" not in context:
            raise RuntimeError(
                "This operation requires a guarded managed-EDB tool body."
            )
        return context["facts"]

    def put(self, name, *values):
        """Insert/upsert in the current tool batch, or ingest one trusted host fact."""
        if self._effect_context.get() is not None:
            return self._facts().put(name, *values)
        result = []
        self.update(lambda facts: result.append(facts.put(name, *values)))
        return result[0]

    def delete(self, name, *key):
        """Remove a keyed row (or an unkeyed tuple), in the tool batch or host update."""
        if self._effect_context.get() is not None:
            return self._facts().delete(name, *key)
        return self.update(lambda facts: facts.delete(name, *key))

    def rows(self, name):
        """Read staged input rows inside the guarded body; query IDB separately."""
        return self._facts().rows(name)

    @property
    def transition(self):
        """The immutable selected FSM move, or None; available only in a tool body."""
        self._facts()
        return self._effect_context.get()["transition"]

    def __call__(self, function=None, *, name=None, arguments=None):
        """Guard a sync or async entry; adapters explicitly supply fact updates.

        Ordinary functions supply their own name/arguments. Existing dispatchers
        with fn(event_id) callbacks may supply the actual tool name/arguments.
        """

        def decorate(body):
            signature = inspect.signature(body)
            captured = deepcopy(arguments) if arguments is not None else None

            if inspect.iscoroutinefunction(body):
                @wraps(body)
                async def checked(*args, **kwargs):
                    principal = current_caller()
                    bound = signature.bind(*args, **kwargs)
                    bound.apply_defaults()
                    values = captured if captured is not None else dict(bound.arguments)
                    return await self.acall(
                        principal, name or body.__name__, values, partial(body, *args, **kwargs)
                    )
                return checked

            @wraps(body)
            def checked(*args, **kwargs):
                principal = current_caller()
                bound = signature.bind(*args, **kwargs)
                bound.apply_defaults()
                values = captured if captured is not None else dict(bound.arguments)
                event_id = (
                    next(iter(bound.arguments.values()), None)
                    if captured is not None
                    else None
                )
                return self.wrap(
                    principal,
                    name or body.__name__,
                    values,
                    lambda _: body(*args, **kwargs),
                )(event_id)

            return checked

        return decorate(function) if function is not None else decorate

    def wrap(self, principal, name, arguments, function):
        """Return an upstream-compatible callback; its business body remains unchanged."""
        captured = deepcopy(arguments)
        kind = self._event(name, captured) if self._event else name

        def run(upstream_event_id=None):
            parameters = _parameters(captured)
            result_value = []
            declined = False

            def effect(context):
                nonlocal declined
                with self._scope(context):
                    value = function(upstream_event_id)
                    result_value.append(value)
                    if not self._completed(value):
                        declined = True
                        return NotApplied("The backend reported no applied operation.")
                    if self._after:
                        value = self._after(_context(context), value)
                    return Applied(value)

            result = None
            try:
                result = self.runtime.execute(
                    {"actor": principal, "action": kind, "parameters": parameters},
                    effect=effect,
                )
            except BridgeError as error:
                if error.code == "not_applied" and declined:
                    self.events.append(
                        {
                            "id": error.attempt_id,
                            "upstreamEvent": upstream_event_id,
                            "principal": principal,
                            "event": kind,
                            "allowed": True,
                            "applied": False,
                            "finishedAt": datetime.now(timezone.utc).isoformat(),
                            "policyHash": self.runtime.policy_hash,
                        }
                    )
                    return result_value[0]
                raise
            self.events.append(
                {
                    "id": result["decision"]["request"]["id"],
                    "upstreamEvent": upstream_event_id,
                    "principal": principal,
                    "event": kind,
                    "allowed": result["allowed"],
                    "applied": result["allowed"],
                    "finishedAt": datetime.now(timezone.utc).isoformat(),
                    "policyHash": self.runtime.policy_hash,
                }
            )
            return (
                result["value"]
                if result["allowed"]
                else self._reject(name, result["decision"])
            )

        def invoke(upstream_event_id=None):
            return self._observe_call(
                principal, name, captured, lambda: run(upstream_event_id)
            )

        return invoke

    def _observe_call(self, principal, name, arguments, callback):
        from .telemetry import observe_operation

        if self._effect_context.get() is not None:
            raise BridgeError("reentrant_call", "A callback cannot re-enter its policy session.")
        with observe_operation(principal, name, arguments) as observation:
            value = callback()
            if observation is not None:
                event = self.events[-1]
                observation.update(
                    value=value,
                    outcome=(
                        "blocked"
                        if not event["allowed"]
                        else "applied"
                        if event["applied"]
                        else "not_applied"
                    ),
                )
            return value

    def execute(self, principal, name, arguments, function):
        """Guard an effect that receives private, transactional facts and evaluated rows."""
        return self._observe_call(
            principal,
            name,
            arguments,
            lambda: self._execute(principal, name, arguments, function),
        )

    def _execute(self, principal, name, arguments, function):
        captured, values = deepcopy(arguments), []
        kind = self._event(name, captured) if self._event else name

        def effect(context):
            with self._scope(context):
                value = function(_context(context))
                values.append(value)
                if not self._completed(value):
                    return NotApplied("Backend reported no applied operation.")
                if self._after:
                    value = self._after(_context(context), value)
                return Applied(value)

        try:
            result = self.runtime.execute(
                {
                    "actor": principal,
                    "action": kind,
                    "parameters": _parameters(captured),
                },
                effect=effect,
            )
        except BridgeError as error:
            if (
                error.code == "not_applied"
                and values
                and not self._completed(values[0])
            ):
                self.events.append(
                    {
                        "id": error.attempt_id,
                        "principal": principal,
                        "event": kind,
                        "allowed": True,
                        "applied": False,
                        "finishedAt": datetime.now(timezone.utc).isoformat(),
                        "policyHash": self.runtime.policy_hash,
                    }
                )
                return values[0]
            raise
        self.events.append(
            {
                "id": result["decision"]["request"]["id"],
                "principal": principal,
                "event": kind,
                "allowed": result["allowed"],
                "applied": result["allowed"],
                "finishedAt": datetime.now(timezone.utc).isoformat(),
                "policyHash": self.runtime.policy_hash,
            }
        )
        return (
            result["value"]
            if result["allowed"]
            else self._reject(name, result["decision"])
        )

    def _reject(self, name, decision):
        """The trusted app adapter projects refusal evidence into its tool protocol."""
        if self._refusal is None:
            return self._refused(name)
        return self._refusal(
            name,
            {
                "requestId": decision["request"]["id"],
                "decision": "blocked",
                "reasonType": decision["reasonType"],
                "reasonCodes": list(decision["reasons"]),
            },
        )

    def call(self, principal, name, arguments, function):
        """Guard a normal business callback when the host has no callback/event protocol."""
        return self.wrap(principal, name, arguments, lambda _: function())()

    async def acall(self, principal, name, arguments, function):
        """Await an original async effect on its caller loop under the native gate.

        Native evaluation and synchronous hooks run in a worker. The effect runs
        on this event loop with the guarded fact context. Cancellation waits for
        actual coroutine completion; unconfirmed effects retain unknown status.
        """
        if self._effect_context.get() is not None:
            raise RuntimeError("A policy cannot re-enter its own active effect.")
        loop = asyncio.get_running_loop()
        if self._async_loop is None:
            self._async_loop, self._async_lock = loop, asyncio.Lock()
        if self._async_loop is not loop:
            raise ValueError("Use an async policy on its original event loop.")
        captured = deepcopy(arguments)
        async with self._async_lock:
            response = Future()
            cancelled = threading.Event()
            running = []

            async def run_body():
                running.append(asyncio.current_task())
                try:
                    if cancelled.is_set():
                        raise asyncio.CancelledError()
                    value = await function()
                except BaseException as error:
                    response.set_exception(error)
                else:
                    response.set_result(value)

            def invoke():
                # Scheduling from inside the guarded effect transfers its
                # ContextVars, including the staged facts and caller identity.
                loop.call_soon_threadsafe(lambda: loop.create_task(run_body()))
                return response.result()

            def checked():
                body = function.func if isinstance(function, partial) else function
                if not inspect.iscoroutinefunction(body):
                    raise ValueError("acall requires an async callback or its bound partial.")
                return self.call(principal, name, captured, invoke)

            worker = asyncio.create_task(asyncio.to_thread(checked))
            try:
                return await asyncio.shield(worker)
            except asyncio.CancelledError:
                cancelled.set()
                if running:
                    running[0].cancel()
                # Repeated caller cancellation must not abandon an effect or
                # interrupt its cleanup a second time.
                while not worker.done():
                    try:
                        await asyncio.shield(worker)
                    except asyncio.CancelledError:
                        continue
                    except BaseException:
                        break
                if worker.done() and not worker.cancelled():
                    worker.exception()
                raise
