"""Model-driven Python interception, normalization, and effect mediation."""

from __future__ import annotations

import functools
import importlib
import inspect
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable

from .errors import ModelError, OriginError, SafeMADenied
from .loader import (
    load_api_models,
    load_origin_models,
    load_policies,
    load_resolver_models,
)
from .policy import PolicyEvaluator, evaluate_expression
from .registry import MetadataRegistry
from .types import Context, Effect, ResolvedMetadata, Resource
from .values import evaluate_value, resolve_identity, text


def _resolve_owner(callable_name: str) -> tuple[Any, str, Callable[..., Any]]:
    parts = callable_name.split(".")
    module = None
    split = 0
    for index in range(len(parts), 0, -1):
        try:
            module = importlib.import_module(".".join(parts[:index]))
        except ModuleNotFoundError:
            continue
        split = index
        break
    if module is None or split == len(parts):
        raise ModelError(f"cannot resolve callable {callable_name!r}")
    owner: Any = module
    for name in parts[split:-1]:
        try:
            owner = getattr(owner, name)
        except AttributeError:
            raise ModelError(f"cannot resolve callable {callable_name!r}") from None
    attribute = parts[-1]
    original = getattr(owner, attribute, None)
    if not callable(original):
        raise ModelError(f"target {callable_name!r} is not callable")
    return owner, attribute, original


def _call_environment(
    original: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]
) -> dict[str, Any]:
    signature = inspect.signature(original)
    bound = signature.bind(*args, **kwargs)
    bound.apply_defaults()
    arguments = dict(bound.arguments)
    first_parameter = next(iter(signature.parameters), None)
    receiver = arguments.pop(first_parameter, None) if first_parameter else None
    return {"receiver": receiver, "call": {"args": arguments}}


def _cardinality(value: Any, cardinality: str) -> list[Any]:
    if cardinality == "one":
        return [value]
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise ModelError(f"cardinality many expected a sequence, got {type(value).__name__}")
    return list(value)


class SafeMARuntime:
    def __init__(
        self,
        *,
        effect_models_path: str | Path,
        origins_path: str | Path,
        resolver_models_path: str | Path,
        policy_path: str | Path,
        metadata_db: str | Path,
        trusted_resolvers: Mapping[str, Callable[[Effect], ResolvedMetadata]],
        denial_handler: Callable[[int, str, Effect | None], Any] | None = None,
    ) -> None:
        self.effect_models = load_api_models(effect_models_path)
        self.origins = load_origin_models(origins_path)
        policies = load_policies(policy_path)
        self.resolver_models = load_resolver_models(resolver_models_path)
        supplied = set(trusted_resolvers)
        declared = set(self.resolver_models)
        if supplied != declared:
            raise ModelError(
                "trusted resolver implementations do not match declarations: "
                f"missing={sorted(declared - supplied)} extra={sorted(supplied - declared)}"
            )
        self.trusted_resolvers = dict(trusted_resolvers)
        self.denial_handler = denial_handler
        effect_kinds = {
            declaration["effect"]["kind"] for declaration in self.effect_models.values()
        }
        policy_kinds = {declaration["effect_kind"] for declaration in policies.values()}
        uncovered = effect_kinds - policy_kinds
        if uncovered:
            raise ModelError(
                f"modeled effect kinds have no policy and would be unmediated: {sorted(uncovered)}"
            )
        self.registry = MetadataRegistry(metadata_db)
        self.evaluator = PolicyEvaluator(policies, self.registry)
        self._restorations: list[tuple[Any, str, Callable[..., Any]]] = []
        self._receiver_bindings: dict[int, tuple[Any, dict[str, Any]]] = {}
        self._installed = False

    def bind_receiver(self, receiver: Any, attributes: Mapping[str, Any]) -> None:
        """Bind one concrete endpoint instance to deployment-trusted attributes."""

        if not attributes:
            raise ModelError("receiver binding attributes must not be empty")
        key = id(receiver)
        current = self._receiver_bindings.get(key)
        if current is not None and current[0] is not receiver:
            raise ModelError("receiver identity collision")
        if current is not None and current[1] != dict(attributes):
            raise ModelError("receiver is already bound to different attributes")
        self._receiver_bindings[key] = (receiver, dict(attributes))

    def _receiver_binding(self, receiver: Any) -> dict[str, Any]:
        registered = self._receiver_bindings.get(id(receiver))
        if registered is None or registered[0] is not receiver:
            raise ModelError("effect receiver is not registered by deployment")
        return dict(registered[1])

    def install(self) -> "SafeMARuntime":
        if self._installed:
            return self
        for declaration in self.origins.values():
            self._patch_origin(declaration)
        for declaration in self.effect_models.values():
            self._patch_effect(declaration)
        self._installed = True
        return self

    def uninstall(self) -> None:
        while self._restorations:
            owner, attribute, original = self._restorations.pop()
            setattr(owner, attribute, original)
        self._installed = False

    def close(self) -> None:
        self.uninstall()
        self._receiver_bindings.clear()
        self.registry.close()

    def __enter__(self) -> "SafeMARuntime":
        return self.install()

    def __exit__(self, *exc_info: Any) -> None:
        self.close()

    def _set_wrapper(
        self,
        callable_name: str,
        factory: Callable[[Callable[..., Any]], Callable[..., Any]],
    ) -> None:
        owner, attribute, current = _resolve_owner(callable_name)
        setattr(owner, attribute, factory(current))
        self._restorations.append((owner, attribute, current))

    def _patch_effect(self, declaration: dict[str, Any]) -> None:
        callable_name = declaration["target"]["callable"]

        def factory(original: Callable[..., Any]) -> Callable[..., Any]:
            @functools.wraps(original)
            def intercepted(*args: Any, **kwargs: Any) -> Any:
                effect = None
                observability: dict[str, Any] = {}
                try:
                    environment = _call_environment(original, args, kwargs)
                    if declaration["target"].get("receiver_binding") == "registered_instance":
                        environment["target"] = {
                            "binding": self._receiver_binding(environment["receiver"])
                        }
                    effect = self._normalize_effect(declaration["effect"], environment)
                    resolved = self._resolve_trusted_metadata(effect)
                    observability = resolved.observability
                    decision = self.evaluator.evaluate(
                        effect,
                        resources=resolved.resources,
                        contexts=resolved.contexts,
                    )
                    prepared_updates = self._prepare_after_return_updates(
                        declaration["effect"].get("after_return", []), effect
                    ) if decision.allowed else []
                except Exception as exc:
                    if isinstance(exc, SafeMADenied):
                        raise
                    reason = f"effect interpretation failed closed: {type(exc).__name__}: {exc}"
                    decision_id = self.registry.record_decision(
                        effect,
                        model_id=declaration["id"],
                        target=callable_name,
                        observability=observability,
                        allowed=False,
                        reason=reason,
                    )
                    if self.denial_handler is not None:
                        return self.denial_handler(decision_id, reason, effect)
                    raise SafeMADenied(decision_id, reason) from exc
                decision_id = self.registry.record_decision(
                    effect,
                    model_id=declaration["id"],
                    target=callable_name,
                    observability=observability,
                    allowed=decision.allowed,
                    reason=decision.reason,
                )
                if not decision.allowed:
                    if self.denial_handler is not None:
                        return self.denial_handler(decision_id, decision.reason, effect)
                    raise SafeMADenied(decision_id, decision.reason)
                try:
                    result = original(*args, **kwargs)
                except BaseException as exc:
                    self.registry.mark_raw_invoked(
                        decision_id, f"RAISED:{type(exc).__name__}"
                    )
                    raise
                self.registry.mark_raw_invoked(decision_id, "RETURNED")
                self._apply_after_return_updates(prepared_updates, effect, result)
                return result

            return intercepted

        self._set_wrapper(callable_name, factory)

    def _resolve_trusted_metadata(self, effect: Effect) -> ResolvedMetadata:
        resources: list[Resource] = []
        contexts: list[Context] = []
        observability: dict[str, Any] = {}
        for identifier, declaration in self.resolver_models.items():
            if declaration["effect_kind"] != effect.kind:
                continue
            resolved = self.trusted_resolvers[identifier](effect)
            if not isinstance(resolved, ResolvedMetadata):
                raise ModelError(
                    f"trusted resolver {identifier!r} returned "
                    f"{type(resolved).__name__}, expected ResolvedMetadata"
                )
            resources.extend(resolved.resources)
            contexts.extend(resolved.contexts)
            observability[identifier] = resolved.observability
        return ResolvedMetadata(
            resources=tuple(resources),
            contexts=tuple(contexts),
            observability=observability,
        )

    def _effect_environment(self, effect: Effect) -> dict[str, Any]:
        return {
            "effect": effect,
            "metadata": {
                "resources": self.registry.all_resources(),
                "contexts": self.registry.all_contexts(),
            },
        }

    def _prepare_after_return_updates(
        self, declarations: list[dict[str, Any]], effect: Effect
    ) -> list[tuple[dict[str, Any], Context, dict[str, Any]]]:
        environment = self._effect_environment(effect)
        prepared = []
        for declaration in declarations:
            if not bool(evaluate_expression(declaration["applies_when"], environment)):
                continue
            update = declaration["update_context"]
            candidates = evaluate_expression(update["in"], environment)
            if isinstance(candidates, (str, bytes)) or not isinstance(
                candidates, (list, tuple)
            ):
                raise ModelError(
                    f"after-return update {declaration['id']!r} expected a context collection"
                )
            matches = []
            for candidate in candidates:
                if not isinstance(candidate, Context):
                    raise ModelError(
                        f"after-return update {declaration['id']!r} selected a "
                        f"{type(candidate).__name__}, expected Context"
                    )
                nested = dict(environment)
                nested[update["as"]] = candidate
                if bool(evaluate_expression(update["where"], nested)):
                    matches.append((candidate, nested))
            if len(matches) != 1:
                raise ModelError(
                    f"after-return update {declaration['id']!r} matched "
                    f"{len(matches)} contexts; expected one"
                )
            context, nested = matches[0]
            required = {
                name: evaluate_value(expression, nested)
                for name, expression in update["require"].items()
            }
            prepared.append((declaration, context, required))
        return prepared

    def _apply_after_return_updates(
        self,
        prepared: list[tuple[dict[str, Any], Context, dict[str, Any]]],
        effect: Effect,
        result: Any,
    ) -> None:
        for declaration, context, required in prepared:
            environment = self._effect_environment(effect)
            environment["return"] = result
            update = declaration["update_context"]
            environment[update["as"]] = context
            if not bool(evaluate_expression(declaration["when"], environment)):
                continue
            attributes = {
                name: evaluate_value(expression, environment)
                for name, expression in update["set"].items()
            }
            self.registry.patch_context(
                context.identity,
                attributes,
                object_class=context.object_class,
                require=required,
            )

    def _normalize_effect(
        self, declaration: dict[str, Any], environment: dict[str, Any]
    ) -> Effect:
        resource_model = declaration["resources"]
        resource_values = _cardinality(
            evaluate_value(resource_model["from"], environment),
            resource_model["cardinality"],
        )
        resources = tuple(
            Resource(
                identity=resolve_identity(
                    value, resource_model.get("identity_resolver", "exact_string")
                ),
                object_class=resource_model["class"],
            )
            for value in resource_values
        )
        context_model = declaration["contexts"]
        context_values = _cardinality(
            evaluate_value(context_model["from"], environment),
            context_model["cardinality"],
        )
        contexts = tuple(
            Context(
                identity=resolve_identity(value, "exact_string"),
                object_class=context_model["class"],
            )
            for value in context_values
        )
        attributes = {
            name: evaluate_value(expression, environment)
            for name, expression in declaration["attributes"].items()
        }
        return Effect(
            kind=declaration["kind"],
            resources=resources,
            contexts=contexts,
            attributes=attributes,
        )

    def _patch_origin(self, declaration: dict[str, Any]) -> None:
        callable_name = declaration["target"]["callable"]
        events = declaration.get("events")
        if events is None:
            events = self.origins[declaration["inherit_events"]]["events"]

        def factory(original: Callable[..., Any]) -> Callable[..., Any]:
            @functools.wraps(original)
            def observed(*args: Any, **kwargs: Any) -> Any:
                environment = _call_environment(original, args, kwargs)
                result = original(*args, **kwargs)
                environment["return"] = result
                try:
                    self._observe_events(declaration["id"], events, environment)
                except Exception as exc:
                    raise OriginError(
                        f"trusted origin {declaration['id']} returned invalid metadata: {exc}"
                    ) from exc
                return result

            return observed

        self._set_wrapper(callable_name, factory)

    def _observe_events(
        self,
        origin_id: str,
        declaration: dict[str, Any],
        environment: dict[str, Any],
    ) -> None:
        items = evaluate_value(declaration["items"], environment)
        if isinstance(items, (str, bytes)) or not isinstance(items, (list, tuple)):
            raise OriginError("events.items must evaluate to a sequence")
        with self.registry.transaction():
            for item in items:
                item_environment = dict(environment, item=item)
                event_identity = evaluate_value(declaration["id"], item_environment)
                if self.registry.origin_event_seen(origin_id, event_identity):
                    continue
                kind = text(evaluate_value(declaration["kind"], item_environment))
                operation = declaration["variants"].get(kind)
                if operation is None:
                    raise OriginError(f"unsupported trusted event kind {kind!r}")
                self._execute_origin_operation(operation, item_environment, origin_id)
                self.registry.record_origin_event(origin_id, event_identity)

    def _execute_origin_operation(
        self,
        operation: dict[str, Any],
        environment: dict[str, Any],
        origin_id: str,
    ) -> None:
        kind, declaration = next(iter(operation.items()))
        if kind == "put_context":
            attributes = {
                name: evaluate_value(expression, environment)
                for name, expression in declaration["attributes"].items()
            }
            self.registry.put_context(
                Context(
                    identity=evaluate_value(declaration["identity"], environment),
                    object_class=declaration["class"],
                    attributes=attributes,
                ),
                origin_id=origin_id,
            )
            return
        if kind == "patch_context":
            required = {
                name: evaluate_value(expression, environment)
                for name, expression in declaration.get("require", {}).items()
            }
            attributes = {
                name: evaluate_value(expression, environment)
                for name, expression in declaration["set"].items()
            }
            self.registry.patch_context(
                evaluate_value(declaration["identity"], environment),
                attributes,
                require=required,
            )
            return
        if kind == "transaction":
            for step in declaration:
                self._execute_origin_operation(step, environment, origin_id)
            return
        raise OriginError(f"unsupported origin operation {kind!r}")


def install(
    *,
    effect_models_path: str | Path,
    origins_path: str | Path,
    resolver_models_path: str | Path,
    policy_path: str | Path,
    metadata_db: str | Path,
    trusted_resolvers: Mapping[str, Callable[[Effect], ResolvedMetadata]],
    denial_handler: Callable[[int, str, Effect | None], Any] | None = None,
) -> SafeMARuntime:
    return SafeMARuntime(
        effect_models_path=effect_models_path,
        origins_path=origins_path,
        resolver_models_path=resolver_models_path,
        policy_path=policy_path,
        metadata_db=metadata_db,
        trusted_resolvers=trusted_resolvers,
        denial_handler=denial_handler,
    ).install()
