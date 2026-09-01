"""Model-driven Python interception, normalization, and effect mediation."""

from __future__ import annotations

import functools
import importlib
import inspect
from pathlib import Path
from typing import Any, Callable

from .errors import ModelError, OriginError, SafeMADenied
from .loader import load_api_models, load_origin_models, load_policies
from .policy import PolicyEvaluator
from .registry import MetadataRegistry
from .types import Context, Effect, Resource
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
        policy_path: str | Path,
        metadata_db: str | Path,
    ) -> None:
        self.effect_models = load_api_models(effect_models_path)
        self.origins = load_origin_models(origins_path)
        policies = load_policies(policy_path)
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
        self._installed = False

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
                try:
                    environment = _call_environment(original, args, kwargs)
                    effect = self._normalize_effect(declaration["effect"], environment)
                    decision = self.evaluator.evaluate(effect)
                except Exception as exc:
                    if isinstance(exc, SafeMADenied):
                        raise
                    reason = f"effect interpretation failed closed: {type(exc).__name__}: {exc}"
                    decision_id = self.registry.record_decision(
                        effect,
                        model_id=declaration["id"],
                        target=callable_name,
                        observability={},
                        allowed=False,
                        reason=reason,
                    )
                    raise SafeMADenied(decision_id, reason) from exc
                decision_id = self.registry.record_decision(
                    effect,
                    model_id=declaration["id"],
                    target=callable_name,
                    observability={},
                    allowed=decision.allowed,
                    reason=decision.reason,
                )
                if not decision.allowed:
                    raise SafeMADenied(decision_id, decision.reason)
                try:
                    result = original(*args, **kwargs)
                except BaseException as exc:
                    self.registry.mark_raw_invoked(
                        decision_id, f"RAISED:{type(exc).__name__}"
                    )
                    raise
                self.registry.mark_raw_invoked(decision_id, "RETURNED")
                return result

            return intercepted

        self._set_wrapper(callable_name, factory)

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
            attributes = {
                name: evaluate_value(expression, environment)
                for name, expression in declaration["set"].items()
            }
            self.registry.patch_context(
                evaluate_value(declaration["identity"], environment), attributes
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
    policy_path: str | Path,
    metadata_db: str | Path,
) -> SafeMARuntime:
    return SafeMARuntime(
        effect_models_path=effect_models_path,
        origins_path=origins_path,
        policy_path=policy_path,
        metadata_db=metadata_db,
    ).install()
