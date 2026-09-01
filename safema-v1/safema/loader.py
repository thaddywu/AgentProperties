"""YAML loading and basic declaration validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .errors import ModelError


def load_yaml(path: str | Path, expected_schema: str) -> dict[str, Any]:
    source = Path(path)
    try:
        value = yaml.safe_load(source.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ModelError(f"cannot load {source}: {exc}") from exc
    if not isinstance(value, dict):
        raise ModelError(f"{source} must contain a YAML mapping")
    if value.get("schema") != expected_schema:
        raise ModelError(
            f"{source} has schema {value.get('schema')!r}, expected {expected_schema!r}"
        )
    return value


def indexed(items: Any, label: str) -> dict[str, dict[str, Any]]:
    if not isinstance(items, list):
        raise ModelError(f"{label} must be a list")
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ModelError(f"every {label} entry must have a string id")
        if item["id"] in result:
            raise ModelError(f"duplicate {label} id {item['id']!r}")
        result[item["id"]] = item
    return result
