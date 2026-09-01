"""Runtime patching, effect normalization, metadata capture, and mediation."""

from __future__ import annotations

import functools
import importlib
import inspect
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from .errors import ModelError, OriginError, SafeMADenied
from .loader import indexed, load_yaml
from .policy import PolicyEvaluator
from .registry import MetadataRegistry
from .selectors import many, member, select
from .types import NormalizedEffect, ResourceRef


def _text(value: Any) -> str:
    if isinstance(value, Enum):
        value = value.value
    if not isinstance(value, str) or not value.strip():
        raise ModelError(f"expected a non-empty string, got {value!r}")
    return value.strip()


def _resolve_owner(callable_name: str) -> tuple[Any, str, Callable[..., Any]]:
    """Resolve ``package.module.Class.method`` without importing application code early."""
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
        owner = getattr(owner, name)
    attribute = parts[-1]
    original = getattr(owner, attribute)
    if not callable(original):
        raise ModelError(f"target {callable_name!r} is not callable")
    return owner, attribute, original


def _call_environment(original: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    bound = inspect.signature(original).bind(*args, **kwargs)
    bound.apply_defaults()
    arguments = dict(bound.arguments)
    receiver = arguments.pop(next(iter(inspect.signature(original).parameters)), None)
    return {"receiver": receiver, "call": {"args": arguments}}


class SafeMARuntime:
    """One installed set of method interceptors and a persistent sidecar registry."""

    def __init__(
        self,
        *,
        effect_models_path: str | Path,
        origins_path: str | Path,
        policy_path: str | Path,
        metadata_db: str | Path,
    ) -> None:
        self.effect_document = load_yaml(
            effect_models_path, "safema.api_effect_models/v1alpha1"
        )
        self.origin_document = load_yaml(
            origins_path, "safema.trusted_metadata_origins/v1alpha1"
        )
        policy_document = load_yaml(policy_path, "safema.policies/v1alpha1")
        self.registry = MetadataRegistry(metadata_db)
        self.evaluator = PolicyEvaluator(policy_document, self.registry)
        self._restorations: list[tuple[Any, str, Callable[..., Any]]] = []
        self._installed = False

    def install(self) -> "SafeMARuntime":
        if self._installed:
            return self
        origins = indexed(self.origin_document.get("origins"), "origins")
        for declaration in origins.values():
            self._patch_origin(declaration, origins)
        for declaration in indexed(self.effect_document.get("models"), "models").values():
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

    def _set_wrapper(self, callable_name: str, factory: Callable[[Callable[..., Any]], Callable[..., Any]]) -> None:
        owner, attribute, current = _resolve_owner(callable_name)
        wrapped = factory(current)
        setattr(owner, attribute, wrapped)
        self._restorations.append((owner, attribute, current))

    def _patch_effect(self, declaration: dict[str, Any]) -> None:
        callable_name = declaration["target"]["callable"]

        def factory(original: Callable[..., Any]) -> Callable[..., Any]:
            @functools.wraps(original)
            def intercepted(*args: Any, **kwargs: Any) -> Any:
                effect = None
                try:
                    environment = _call_environment(original, args, kwargs)
                    effect = self._normalize_effect(declaration, environment)
                    decision = self.evaluator.evaluate(effect)
                except Exception as exc:
                    if isinstance(exc, SafeMADenied):
                        raise
                    reason = f"effect interpretation failed closed: {type(exc).__name__}: {exc}"
                    decision_id = self.registry.record_decision(
                        effect, model_id=declaration["id"], target=callable_name,
                        allowed=False, reason=reason,
                    )
                    raise SafeMADenied(decision_id, reason) from exc

                decision_id = self.registry.record_decision(
                    effect, model_id=declaration["id"], target=callable_name,
                    allowed=decision.allowed, reason=decision.reason,
                )
                if not decision.allowed:
                    raise SafeMADenied(decision_id, decision.reason)
                try:
                    result = original(*args, **kwargs)
                except BaseException as exc:
                    self.registry.mark_raw_invoked(decision_id, f"RAISED:{type(exc).__name__}")
                    raise
                self.registry.mark_raw_invoked(decision_id, "RETURNED")
                return result

            return intercepted

        self._set_wrapper(callable_name, factory)

    def _normalize_effect(
        self, declaration: dict[str, Any], environment: dict[str, Any]
    ) -> NormalizedEffect:
        spec = declaration["effect"]
        resources_spec = spec["resources"]
        raw_resources = many(
            select(resources_spec["select"], environment), resources_spec["cardinality"]
        )
        resources = tuple(
            ResourceRef(
                value=_text(value),
                resource_class=resources_spec["resource_class"],
                resolver=resources_spec["resolver"],
                metadata_required=bool(resources_spec["metadata_required"]),
            )
            for value in raw_resources
        )
        destination_spec = spec["destinations"]
        raw_destinations: list[Any] = []
        if "union" in destination_spec:
            for branch in destination_spec["union"]:
                raw_destinations.extend(many(select(branch["select"], environment), "many"))
        else:
            raw_destinations = many(
                select(destination_spec["select"], environment),
                destination_spec["cardinality"],
            )
        return NormalizedEffect(
            model_id=declaration["id"],
            target=declaration["target"]["callable"],
            kind=_text(spec["kind"]["constant"]),
            channel=_text(spec["channel"]["constant"]),
            correlation=_text(select(spec["correlation"]["select"], environment)),
            resources=resources,
            destinations=tuple(_text(value) for value in raw_destinations),
        )

    def _patch_origin(
        self, declaration: dict[str, Any], origins: dict[str, dict[str, Any]]
    ) -> None:
        callable_name = declaration["target"]["callable"]

        def factory(original: Callable[..., Any]) -> Callable[..., Any]:
            @functools.wraps(original)
            def observed(*args: Any, **kwargs: Any) -> Any:
                environment = _call_environment(original, args, kwargs)
                result = original(*args, **kwargs)
                environment["return"] = result
                try:
                    if "emits" in declaration:
                        self._observe_resource(declaration, environment)
                    else:
                        stream = declaration.get("event_stream")
                        if stream is None:
                            inherited = declaration.get("inherits_event_stream")
                            stream = origins[inherited]["event_stream"]
                        self._observe_events(declaration, stream, environment)
                except Exception as exc:
                    raise OriginError(
                        f"trusted origin {declaration['id']} produced unusable metadata: {exc}"
                    ) from exc
                return result

            return observed

        self._set_wrapper(callable_name, factory)

    def _observe_resource(self, declaration: dict[str, Any], environment: dict[str, Any]) -> None:
        emits = declaration["emits"]
        resource = emits["resource"]
        attributes = {
            key: _text(select(value["select"], environment))
            for key, value in emits.get("attributes", {}).items()
        }
        self.registry.bind_resource(
            resolver_id=resource["resolver_id"],
            resource_class=resource["resource_class"],
            path=_text(select(resource["select"], environment)),
            principal=_text(select(emits["principal"]["select"], environment)),
            attributes=attributes,
            origin_id=declaration["id"],
            application_resource_id=attributes.get("application_letter_id"),
        )

    def _observe_events(
        self,
        declaration: dict[str, Any],
        stream: dict[str, Any],
        environment: dict[str, Any],
    ) -> None:
        items = select(stream["items"], environment)
        source_kind = _text(select(stream["source_kind"]["select"], environment))
        # One scan is one trusted observation: do not retain a prefix if a
        # later event in the same returned batch cannot be interpreted.
        with self.registry.transaction():
            for item in items:
                item_environment = dict(environment, item=item)
                event_id = _text(select(stream["event_id"]["select"], item_environment))
                if self.registry.origin_event_seen(declaration["id"], source_kind, event_id):
                    continue
                discriminator = _text(
                    select(stream["discriminator"]["select"], item_environment)
                )
                variant = stream["variants"].get(discriminator)
                if variant is None:
                    raise OriginError(f"unsupported trusted event variant {discriminator!r}")
                operation = variant["operation"]
                if operation == "ACTIVATE_DESTINATION_CONTEXT":
                    self._activate_context(declaration["id"], variant, item_environment, source_kind)
                elif operation == "DEACTIVATE_DESTINATION_CONTEXT":
                    self.registry.deactivate_context(
                        self._context_key(variant["context_key"], item_environment, source_kind)
                    )
                elif operation == "REPLACE_DESTINATION_CONTEXT":
                    self.registry.deactivate_context(
                        self._context_key(
                            variant["deactivate_context_key"], item_environment, source_kind
                        )
                    )
                    self._activate_context(
                        declaration["id"],
                        {**variant, "context_key": variant["activate_context_key"]},
                        item_environment,
                        source_kind,
                    )
                else:
                    raise OriginError(f"unsupported metadata operation {operation!r}")
                self.registry.record_origin_event(declaration["id"], source_kind, event_id)

    def _context_key(
        self, declaration: dict[str, Any], environment: dict[str, Any], source_kind: str
    ) -> str:
        values = []
        for expression in declaration["tuple"]:
            if expression == "$receiver.source_kind":
                values.append(source_kind)
            elif expression.startswith("coalesce("):
                inner = expression[len("coalesce("):-1].split(",")
                first = select(inner[0].strip(), environment)
                values.append(_text(first) if first else source_kind)
            else:
                values.append(_text(select(expression, environment)))
        if len(values) != 2:
            raise OriginError("v1 destination context keys must contain two values")
        return self.registry.context_key(values[0], values[1])

    def _activate_context(
        self,
        origin_id: str,
        variant: dict[str, Any],
        environment: dict[str, Any],
        source_kind: str,
    ) -> None:
        claims = variant["claims"]
        principal = _text(select(claims["principal"]["select"], environment))
        channel = _text(select(claims["channel"]["select"], environment))
        allowed_expression = claims["allowed_destinations"]["singleton"]
        allowed = [_text(select(allowed_expression, environment))]
        attributes = {
            key: _text(select(value["select"], environment))
            for key, value in claims.items()
            if key not in {"principal", "channel", "allowed_destinations"}
        }
        self.registry.activate_context(
            context_key=self._context_key(
                variant["context_key"], environment, source_kind
            ),
            principal=principal,
            channel=channel,
            allowed_destinations=allowed,
            attributes=attributes,
            origin_id=origin_id,
        )


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
