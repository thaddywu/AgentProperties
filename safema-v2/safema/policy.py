"""Interpreter for the intentionally small declarative SafeMA policy language."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from .errors import ModelError
from .registry import MetadataRegistry, canonical_json
from .selectors import select
from .types import Decision, Effect


def _collection(value: Any, where: str) -> list[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ModelError(f"{where} expected a collection, got {type(value).__name__}")
    return list(value)


def _number(value: Any, where: str) -> int | Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise ModelError(
            f"{where} expected an exact integer or Decimal, got {type(value).__name__}"
        )
    return value


def _compatible_numbers(values: list[Any], where: str) -> list[int | Decimal]:
    numbers = [_number(value, where) for value in values]
    if any(isinstance(value, Decimal) for value in numbers):
        return [value if isinstance(value, Decimal) else Decimal(value) for value in numbers]
    return numbers


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
    if operator in {"add", "mul"}:
        values = _compatible_numbers(
            [evaluate_expression(item, environment) for item in operand], operator
        )
        result: int | Decimal = 0 if operator == "add" else 1
        if values and isinstance(values[0], Decimal):
            result = Decimal(result)
        for value in values:
            result = result + value if operator == "add" else result * value
        return result
    if operator == "mod":
        left, right = [evaluate_expression(item, environment) for item in operand]
        if isinstance(left, bool) or not isinstance(left, int):
            raise ModelError("mod left operand must be an integer")
        if isinstance(right, bool) or not isinstance(right, int) or right <= 0:
            raise ModelError("mod right operand must be a positive integer")
        return left % right
    if operator in {"gt", "gte", "lt", "lte"}:
        left, right = _compatible_numbers(
            [evaluate_expression(item, environment) for item in operand], operator
        )
        return {
            "gt": left > right,
            "gte": left >= right,
            "lt": left < right,
            "lte": left <= right,
        }[operator]
    if operator in {"exists", "all", "any"} and isinstance(operand, dict):
        values = _collection(
            evaluate_expression(operand["in"], environment), f"{operator}.in"
        )
        for value in values:
            nested = dict(environment)
            nested[operand["as"]] = value
            outcome = bool(evaluate_expression(operand["satisfies"], nested))
            if operator in {"exists", "any"} and outcome:
                return True
            if operator == "all" and not outcome:
                return False
        return operator == "all"
    if operator in {"all", "any"}:
        for item in operand:
            outcome = bool(evaluate_expression(item, environment))
            if operator == "all" and not outcome:
                return False
            if operator == "any" and outcome:
                return True
        return operator == "all"
    raise ModelError(f"unsupported policy operator {operator!r}")


class PolicyEvaluator:
    def __init__(
        self, policies: dict[str, dict[str, Any]], registry: MetadataRegistry
    ) -> None:
        self.policies = policies
        self.registry = registry

    def evaluate(
        self,
        effect: Effect,
        *,
        resources: Sequence[Any] = (),
        contexts: Sequence[Any] = (),
    ) -> Decision:
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
                "resources": self.registry.all_resources() + list(resources),
                "contexts": self.registry.all_contexts() + list(contexts),
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
