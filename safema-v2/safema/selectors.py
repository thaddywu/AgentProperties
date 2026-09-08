"""Small read-only selector language used by SafeMA YAML declarations."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from .errors import ModelError

_TOKEN = re.compile(r"^([^\[\]]+)(\[\*\])?$")


def validate_selector(expression: Any) -> None:
    if not isinstance(expression, str) or not expression.startswith("$"):
        raise ModelError(f"invalid selector {expression!r}")
    for token in expression[1:].split("."):
        if not _TOKEN.match(token):
            raise ModelError(f"invalid selector token {token!r} in {expression!r}")


def member(value: Any, name: str) -> Any:
    """Read one mapping key or object attribute without invoking application code."""
    if isinstance(value, Mapping):
        if name not in value:
            raise ModelError(f"mapping has no key {name!r}")
        return value[name]
    try:
        return getattr(value, name)
    except AttributeError:
        raise ModelError(f"{type(value).__name__} has no attribute {name!r}") from None


def select(expression: str, environment: Mapping[str, Any]) -> Any:
    """Evaluate `$root.path[*]` against an explicit environment."""
    validate_selector(expression)
    parts = expression[1:].split(".")
    root_token = parts.pop(0)
    root_match = _TOKEN.match(root_token)
    if not root_match:
        raise ModelError(f"invalid selector root {root_token!r}")
    root, root_star = root_match.groups()
    if root not in environment:
        raise ModelError(f"unknown selector root ${root}")
    root_value = environment[root]
    if root_star:
        if isinstance(root_value, (str, bytes)) or not isinstance(root_value, Sequence):
            raise ModelError(f"selector {expression!r} expected a sequence at root")
        values = list(root_value)
        expanded = True
    else:
        values = [root_value]
        expanded = False
    for raw in parts:
        match = _TOKEN.match(raw)
        if not match:
            raise ModelError(f"invalid selector token {raw!r}")
        name, star = match.groups()
        next_values: list[Any] = []
        for value in values:
            child = member(value, name)
            if star:
                if isinstance(child, (str, bytes)) or not isinstance(child, Sequence):
                    raise ModelError(f"selector {expression!r} expected a sequence at {name}")
                next_values.extend(child)
                expanded = True
            else:
                next_values.append(child)
        values = next_values
    if expanded:
        return values
    if len(values) != 1:
        raise ModelError(f"selector {expression!r} produced {len(values)} values")
    return values[0]


def many(value: Any, cardinality: str) -> list[Any]:
    if cardinality == "one":
        return [value]
    if cardinality == "many":
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
        raise ModelError(f"expected many values, got {type(value).__name__}")
    raise ModelError(f"unsupported cardinality {cardinality!r}")
