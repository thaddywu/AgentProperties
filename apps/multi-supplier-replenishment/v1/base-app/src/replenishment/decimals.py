"""Decimal helpers.

Every price, multiplier, and forecast value in this application is a
``decimal.Decimal``.  Binary floating point is never used for those values.
"""

from __future__ import annotations

import decimal
from decimal import Decimal

# Section 3 of the specification requires at least 28 significant digits for
# forecast arithmetic and forbids rounding intermediate values.
FORECAST_PRECISION = 28
FORECAST_CONTEXT = decimal.Context(
    prec=FORECAST_PRECISION, rounding=decimal.ROUND_HALF_EVEN
)

MONEY_EXPONENT = Decimal("0.01")


class DecimalFormatError(ValueError):
    """A string could not be read as the required kind of decimal value."""


def parse_decimal(raw: object, *, field: str) -> Decimal:
    """Read a decimal from a string or integer; floats are rejected."""
    if isinstance(raw, bool):
        raise DecimalFormatError(f"{field}: boolean is not a decimal value")
    if isinstance(raw, int):
        return Decimal(raw)
    if isinstance(raw, float):
        raise DecimalFormatError(
            f"{field}: binary floating point is not accepted; use a quoted string"
        )
    if isinstance(raw, str):
        try:
            value = Decimal(raw.strip())
        except decimal.InvalidOperation as exc:
            raise DecimalFormatError(f"{field}: {raw!r} is not a decimal") from exc
        if not value.is_finite():
            raise DecimalFormatError(f"{field}: {raw!r} is not finite")
        return value
    raise DecimalFormatError(f"{field}: expected a decimal string, got {type(raw).__name__}")


def parse_money(raw: object, *, field: str) -> Decimal:
    """Read a USD amount that must carry exactly two fractional digits."""
    value = parse_decimal(raw, field=field)
    exponent = value.as_tuple().exponent
    if not isinstance(exponent, int) or exponent != -2:
        raise DecimalFormatError(
            f"{field}: monetary values must have exactly two decimal places, got {raw!r}"
        )
    return value


def money_str(value: Decimal) -> str:
    """Render a USD amount with exactly two fractional digits."""
    return str(value.quantize(MONEY_EXPONENT, rounding=decimal.ROUND_HALF_EVEN))


def is_money(value: Decimal) -> bool:
    """True when the amount already carries exactly two fractional digits."""
    return value.is_finite() and value.as_tuple().exponent == -2


def ceil_to_int(value: Decimal) -> int:
    """Mathematical ceiling of a decimal, returned as a Python int."""
    return int(value.to_integral_value(rounding=decimal.ROUND_CEILING))
