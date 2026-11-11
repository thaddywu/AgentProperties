"""Money representation at the original float-valued MCP boundary."""
from decimal import Decimal, InvalidOperation

def minor_units(value):
    if isinstance(value,bool):raise ValueError('A monetary amount is not a boolean.')
    try:
        cents=Decimal(str(value))*100
        if not cents.is_finite() or cents!=cents.to_integral_value() or abs(cents)>=2**63:
            raise ValueError('Use finite USD amounts with at most two decimal places.')
        return int(cents)
    except InvalidOperation:raise ValueError('Invalid monetary amount.') from None
