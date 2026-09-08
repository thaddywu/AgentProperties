from __future__ import annotations

from decimal import Decimal

import pytest

from safema.errors import ModelError
from safema.policy import evaluate_expression


def test_exact_integer_aggregation_and_comparison():
    expression = {
        "lte": [
            {"add": [{"literal": 40}, {"literal": 20}, {"literal": 35}]},
            {"literal": 100},
        ]
    }
    assert evaluate_expression(expression, {}) is True


def test_exact_decimal_multiplication():
    expression = {
        "eq": [
            {"mul": [{"literal": 24}, {"literal": Decimal("0.29")}]},
            {"literal": Decimal("6.96")},
        ]
    }
    assert evaluate_expression(expression, {}) is True


def test_mod_requires_integer_operands():
    with pytest.raises(ModelError, match="left operand must be an integer"):
        evaluate_expression(
            {"mod": [{"literal": Decimal("10")}, {"literal": 5}]}, {}
        )


def test_numeric_operators_reject_strings_and_booleans():
    with pytest.raises(ModelError, match="exact integer or Decimal"):
        evaluate_expression(
            {"add": [{"literal": "40"}, {"literal": 2}]}, {}
        )
    with pytest.raises(ModelError, match="exact integer or Decimal"):
        evaluate_expression(
            {"lte": [{"literal": True}, {"literal": 2}]}, {}
        )
