"""Interpreter for the intentionally small declarative SafeMA policy language."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .errors import ModelError
from .registry import MetadataRegistry, canonical_json
from .selectors import select
from .types import Decision, Effect


def _collection(value: Any, where: str) -> list[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ModelError(f"{where} expected a collection, got {type(value).__name__}")
    return list(value)


def evaluate_expression(expression: dict[str, Any], environment: Mapping[str, Any]) -> Any:
    operator, operand = next(iter(expression.items()))
    if operator == "select":
        return select(operand, environment)
    if operator == "literal":
        return operand
    if operator == "eq":
        left, right = operand
        return evaluate_expression(left, environment) == evaluate_expression(right, environment)
    if operator == "subset":
        left, right = operand
        actual = _collection(evaluate_expression(left, environment), "subset left operand")
        allowed = _collection(evaluate_expression(right, environment), "subset right operand")
        return {canonical_json(item) for item in actual}.issubset(
            {canonical_json(item) for item in allowed}
        )
    if operator in {"exists", "all", "any"} and isinstance(operand, dict):
        values = _collection(
            evaluate_expression(operand["in"], environment), f"{operator}.in"
        )
        outcomes = []
        for value in values:
            nested = dict(environment)
            nested[operand["as"]] = value
            outcomes.append(bool(evaluate_expression(operand["satisfies"], nested)))
        if operator == "exists" or operator == "any":
            return any(outcomes)
        return all(outcomes)
    if operator in {"all", "any"}:
        outcomes = [bool(evaluate_expression(item, environment)) for item in operand]
        return all(outcomes) if operator == "all" else any(outcomes)
    raise ModelError(f"unsupported policy operator {operator!r}")


class PolicyEvaluator:
    def __init__(
        self, policies: dict[str, dict[str, Any]], registry: MetadataRegistry
    ) -> None:
        self.policies = policies
        self.registry = registry

    def evaluate(self, effect: Effect) -> Decision:
        applicable = [
            declaration
            for declaration in self.policies.values()
            if declaration["effect_kind"] == effect.kind
        ]
        if not applicable:
            return Decision(False, "no policy applies to this effect kind", ())
        environment = {
            "effect": effect,
            "metadata": {
                "resources": self.registry.all_resources(),
                "contexts": self.registry.all_contexts(),
            },
        }
        evaluated = []
        for declaration in applicable:
            allowed = bool(evaluate_expression(declaration["allow"], environment))
            evaluated.append((declaration["id"], allowed))
        denied = [identifier for identifier, allowed in evaluated if not allowed]
        identifiers = tuple(identifier for identifier, _ in evaluated)
        if denied:
            return Decision(False, f"declarative policies denied: {denied}", identifiers)
        return Decision(True, f"declarative policies allowed: {list(identifiers)}", identifiers)
