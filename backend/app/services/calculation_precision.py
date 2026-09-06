"""Decimal output precision shared by cash-flow and reinvestment calculators.

Call only at existing result boundaries: intermediate amounts must retain
precision. Presentation rounding belongs to the frontend.
"""

from decimal import Decimal, ROUND_HALF_UP

MONEY_QUANTUM = Decimal("0.01")
PERCENT_QUANTUM = Decimal("0.000001")
UNIT_QUANTUM = Decimal("0.000001")


def round_money(value: Decimal) -> Decimal:
    """Round monetary results to cents, including negative half-way values."""
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def round_percentage(value: Decimal) -> Decimal:
    """Round percentage results to six decimal places."""
    return value.quantize(PERCENT_QUANTUM, rounding=ROUND_HALF_UP)


def round_units(value: Decimal) -> Decimal:
    """Round fractional-unit results without changing internal holdings."""
    return value.quantize(UNIT_QUANTUM, rounding=ROUND_HALF_UP)
