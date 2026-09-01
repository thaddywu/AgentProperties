"""Policy evaluation over normalized effects and SafeMA-owned metadata."""

from __future__ import annotations

from typing import Any

from .loader import indexed
from .registry import MetadataRegistry
from .types import Decision, NormalizedEffect


class PolicyEvaluator:
    """Evaluate the small generic policy vocabulary declared for v1."""

    def __init__(self, document: dict[str, Any], registry: MetadataRegistry) -> None:
        policies = indexed(document.get("policies"), "policies")
        if len(policies) != 1:
            raise ValueError("SafeMA v1 requires exactly one policy")
        self.declaration = next(iter(policies.values()))
        self.policy_id = self.declaration["id"]
        self.registry = registry

    def evaluate(self, effect: NormalizedEffect) -> Decision:
        applies = self.declaration["applies_to"]
        covered_classes = set(applies["resource_classes"])
        if effect.kind != applies["effect_kind"]:
            return Decision(True, "policy not applicable to effect kind", self.policy_id)

        covered = [item for item in effect.resources if item.resource_class in covered_classes]
        if not covered:
            return Decision(True, "no policy-covered resources", self.policy_id)

        actual = set(effect.destinations)
        if not actual:
            return Decision(False, "covered disclosure has no destination", self.policy_id)

        resolved = []
        for reference in covered:
            metadata, explanation = self.registry.resolve_resource(
                resolver_id=reference.resolver,
                resource_class=reference.resource_class,
                path=reference.value,
            )
            if metadata is None:
                return Decision(
                    False,
                    f"resource {reference.value!r} unresolved: {explanation}",
                    self.policy_id,
                )
            resolved.append(metadata)

        for metadata in resolved:
            contexts = self.registry.matching_contexts(
                principal=metadata.principal,
                channel=effect.channel,
                actual_destinations=actual,
            )
            if not contexts:
                return Decision(
                    False,
                    "no active trusted destination context authorizes "
                    f"principal={metadata.principal!r}, channel={effect.channel!r}, "
                    f"destinations={sorted(actual)!r}",
                    self.policy_id,
                )

        binding_ids = [item.binding_id for item in resolved]
        return Decision(
            True,
            f"all covered resources authorized; binding_ids={binding_ids}",
            self.policy_id,
        )
