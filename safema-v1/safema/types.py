"""Small generic security-effect representation used by SafeMA."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Resource:
    identity: Any
    object_class: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Context:
    identity: Any
    object_class: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Effect:
    kind: str
    resources: tuple[Resource, ...]
    contexts: tuple[Context, ...]
    attributes: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str
    policy_ids: tuple[str, ...]
