"""Strict loaders for the complete SafeMA v1 executable configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .errors import ModelError
from .selectors import validate_selector

VALUE_OPERATORS = {"select", "literal", "list", "tuple", "union", "coalesce"}
POLICY_OPERATORS = {"select", "literal", "eq", "subset", "exists", "all", "any"}
IDENTITY_RESOLVERS = {"exact_string", "file_sha256"}


def _keys(value: Any, required: set[str], optional: set[str], where: str) -> None:
    if not isinstance(value, dict):
        raise ModelError(f"{where} must be a mapping")
    missing = required - set(value)
    unknown = set(value) - required - optional
    if missing:
        raise ModelError(f"{where} is missing {sorted(missing)}")
    if unknown:
        raise ModelError(f"{where} has unsupported fields {sorted(unknown)}")


def _read(path: str | Path, schema: str, collection: str) -> dict[str, Any]:
    source = Path(path)
    try:
        value = yaml.safe_load(source.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ModelError(f"cannot load {source}: {exc}") from exc
    _keys(value, {"schema", collection}, set(), "document")
    if value["schema"] != schema:
        raise ModelError(f"{source} has unsupported schema {value['schema']!r}")
    return value


def _identifier(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ModelError(f"{where} must be a non-empty string")
    return value


def _entries(value: Any, where: str) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list):
        raise ModelError(f"{where} must be a list")
    result = {}
    for index, item in enumerate(value):
        if not isinstance(item, dict) or "id" not in item:
            raise ModelError(f"{where}[{index}] must be a mapping with an id")
        identifier = _identifier(item["id"], f"{where}[{index}].id")
        if identifier in result:
            raise ModelError(f"duplicate {where} id {identifier!r}")
        result[identifier] = item
    return result


def validate_value(expression: Any, where: str) -> None:
    if not isinstance(expression, dict) or len(expression) != 1:
        raise ModelError(f"{where} must contain exactly one value operator")
    operator, operand = next(iter(expression.items()))
    if operator not in VALUE_OPERATORS:
        raise ModelError(f"{where} uses unsupported value operator {operator!r}")
    if operator == "select":
        try:
            validate_selector(operand)
        except ModelError as exc:
            raise ModelError(f"{where}.select is invalid: {exc}") from exc
    elif operator in {"list", "tuple", "union", "coalesce"}:
        if not isinstance(operand, list) or not operand:
            raise ModelError(f"{where}.{operator} must be a non-empty list")
        for index, item in enumerate(operand):
            validate_value(item, f"{where}.{operator}[{index}]")


def load_api_models(path: str | Path) -> dict[str, dict[str, Any]]:
    document = _read(path, "safema.api_effect_models/v1", "models")
    models = _entries(document["models"], "models")
    for identifier, model in models.items():
        _keys(model, {"id", "target", "effect"}, set(), f"model {identifier}")
        _keys(model["target"], {"callable"}, set(), f"model {identifier}.target")
        _identifier(model["target"]["callable"], f"model {identifier}.target.callable")
        effect = model["effect"]
        _keys(effect, {"kind", "resources", "contexts", "attributes"}, set(),
              f"model {identifier}.effect")
        _identifier(effect["kind"], f"model {identifier}.effect.kind")
        for field, allow_resolver in (("resources", True), ("contexts", False)):
            declaration = effect[field]
            required = {"from", "cardinality", "class"}
            optional = {"identity_resolver"} if allow_resolver else set()
            _keys(declaration, required, optional, f"model {identifier}.effect.{field}")
            validate_value(declaration["from"], f"model {identifier}.effect.{field}.from")
            if declaration["cardinality"] not in {"one", "many"}:
                raise ModelError(f"model {identifier}.{field}.cardinality is unsupported")
            _identifier(declaration["class"], f"model {identifier}.{field}.class")
            resolver = declaration.get("identity_resolver", "exact_string")
            if resolver not in IDENTITY_RESOLVERS:
                raise ModelError(f"model {identifier}.{field} has unsupported resolver")
        if not isinstance(effect["attributes"], dict):
            raise ModelError(f"model {identifier}.effect.attributes must be a mapping")
        for name, expression in effect["attributes"].items():
            _identifier(name, f"model {identifier}.effect.attributes key")
            validate_value(expression, f"model {identifier}.effect.attributes.{name}")
            if next(iter(expression)) != "literal":
                raise ModelError(
                    f"model {identifier}.effect.attributes.{name} must be a model literal; "
                    "application claims cannot become authorization attributes"
                )
    return models


def _validate_operation(operation: Any, where: str) -> None:
    if not isinstance(operation, dict) or len(operation) != 1:
        raise ModelError(f"{where} must contain exactly one operation")
    kind, declaration = next(iter(operation.items()))
    if kind == "put_context":
        _keys(declaration, {"identity", "class", "attributes"}, set(), where)
        validate_value(declaration["identity"], f"{where}.identity")
        _identifier(declaration["class"], f"{where}.class")
        if not isinstance(declaration["attributes"], dict):
            raise ModelError(f"{where}.attributes must be a mapping")
        for name, expression in declaration["attributes"].items():
            validate_value(expression, f"{where}.attributes.{name}")
    elif kind == "patch_context":
        _keys(declaration, {"identity", "set"}, set(), where)
        validate_value(declaration["identity"], f"{where}.identity")
        if not isinstance(declaration["set"], dict) or not declaration["set"]:
            raise ModelError(f"{where}.set must be a non-empty mapping")
        for name, expression in declaration["set"].items():
            validate_value(expression, f"{where}.set.{name}")
    elif kind == "transaction":
        if not isinstance(declaration, list) or not declaration:
            raise ModelError(f"{where}.transaction must be a non-empty list")
        for index, step in enumerate(declaration):
            _validate_operation(step, f"{where}.transaction[{index}]")
    else:
        raise ModelError(f"{where} uses unsupported operation {kind!r}")


def load_origin_models(path: str | Path) -> dict[str, dict[str, Any]]:
    document = _read(path, "safema.trusted_metadata_origins/v1", "origins")
    origins = _entries(document["origins"], "origins")
    for identifier, origin in origins.items():
        if "inherit_events" in origin:
            _keys(origin, {"id", "target", "inherit_events"}, set(), f"origin {identifier}")
        else:
            _keys(origin, {"id", "target", "events"}, set(), f"origin {identifier}")
        _keys(origin["target"], {"callable"}, set(), f"origin {identifier}.target")
        _identifier(origin["target"]["callable"], f"origin {identifier}.target.callable")
        if "events" not in origin:
            continue
        events = origin["events"]
        _keys(events, {"items", "id", "kind", "variants"}, set(), f"origin {identifier}.events")
        for name in ("items", "id", "kind"):
            validate_value(events[name], f"origin {identifier}.events.{name}")
        if not isinstance(events["variants"], dict) or not events["variants"]:
            raise ModelError(f"origin {identifier}.events.variants must be a mapping")
        for kind, operation in events["variants"].items():
            _identifier(kind, f"origin {identifier}.variant")
            _validate_operation(operation, f"origin {identifier}.variants.{kind}")
    for identifier, origin in origins.items():
        inherited = origin.get("inherit_events")
        if inherited is not None and inherited not in origins:
            raise ModelError(f"origin {identifier} inherits unknown origin {inherited!r}")
        if inherited is not None and "events" not in origins[inherited]:
            raise ModelError(
                f"origin {identifier} cannot inherit indirectly from {inherited!r}"
            )
    return origins


def validate_policy_expression(expression: Any, where: str) -> None:
    if not isinstance(expression, dict) or len(expression) != 1:
        raise ModelError(f"{where} must contain exactly one policy operator")
    operator, operand = next(iter(expression.items()))
    if operator not in POLICY_OPERATORS:
        raise ModelError(f"{where} uses unsupported policy operator {operator!r}")
    if operator == "select":
        try:
            validate_selector(operand)
        except ModelError as exc:
            raise ModelError(f"{where}.select is invalid: {exc}") from exc
    elif operator in {"eq", "subset"}:
        if not isinstance(operand, list) or len(operand) != 2:
            raise ModelError(f"{where}.{operator} must contain exactly two expressions")
        for index, item in enumerate(operand):
            validate_policy_expression(item, f"{where}.{operator}[{index}]")
    elif operator in {"exists", "all", "any"} and isinstance(operand, dict):
        _keys(operand, {"in", "as", "satisfies"}, set(), f"{where}.{operator}")
        validate_policy_expression(operand["in"], f"{where}.{operator}.in")
        _identifier(operand["as"], f"{where}.{operator}.as")
        validate_policy_expression(operand["satisfies"], f"{where}.{operator}.satisfies")
    elif operator in {"all", "any"}:
        if not isinstance(operand, list) or not operand:
            raise ModelError(f"{where}.{operator} must be a non-empty list or quantifier")
        for index, item in enumerate(operand):
            validate_policy_expression(item, f"{where}.{operator}[{index}]")
    elif operator == "exists":
        raise ModelError(f"{where}.exists must be a quantifier mapping")


def load_policies(path: str | Path) -> dict[str, dict[str, Any]]:
    document = _read(path, "safema.policies/v1", "policies")
    policies = _entries(document["policies"], "policies")
    for identifier, policy in policies.items():
        _keys(policy, {"id", "effect_kind", "allow"}, set(), f"policy {identifier}")
        _identifier(policy["effect_kind"], f"policy {identifier}.effect_kind")
        validate_policy_expression(policy["allow"], f"policy {identifier}.allow")
    return policies
