"""Normalized values exchanged by the generic SafeMA core."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ResourceRef:
    value: str
    resource_class: str
    resolver: str
    metadata_required: bool


@dataclass(frozen=True)
class NormalizedEffect:
    model_id: str
    target: str
    kind: str
    channel: str
    correlation: str
    resources: tuple[ResourceRef, ...]
    destinations: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ResourceMetadata:
    binding_id: int
    resolver_id: str
    resource_class: str
    canonical_path: str
    fingerprint: str
    principal: str
    attributes: dict[str, Any]


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str
    policy_id: str
