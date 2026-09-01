"""Executable value expressions and actual-operand identity resolvers."""

from __future__ import annotations

import hashlib
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from .errors import ModelError
from .selectors import select


def text(value: Any) -> str:
    if isinstance(value, Enum):
        value = value.value
    if not isinstance(value, str) or not value.strip():
        raise ModelError(f"expected a non-empty string, got {value!r}")
    return value.strip()


def evaluate_value(expression: dict[str, Any], environment: Mapping[str, Any]) -> Any:
    operator, operand = next(iter(expression.items()))
    if operator == "select":
        return select(operand, environment)
    if operator == "literal":
        return operand
    if operator in {"list", "tuple"}:
        return [evaluate_value(item, environment) for item in operand]
    if operator == "union":
        result: list[Any] = []
        for item in operand:
            value = evaluate_value(item, environment)
            if isinstance(value, (list, tuple)):
                result.extend(value)
            else:
                result.append(value)
        return result
    if operator == "coalesce":
        for item in operand:
            try:
                value = evaluate_value(item, environment)
            except ModelError:
                continue
            if value is not None and value != "":
                return value
        return None
    raise ModelError(f"unsupported value operator {operator!r}")


def resolve_identity(value: Any, resolver: str) -> Any:
    if resolver == "exact_string":
        return text(value)
    if resolver == "file_sha256":
        canonical = str(Path(text(value)).expanduser().resolve(strict=True))
        digest = hashlib.sha256()
        with open(canonical, "rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return {"canonical_path": canonical, "sha256": digest.hexdigest()}
    raise ModelError(f"unsupported identity resolver {resolver!r}")
