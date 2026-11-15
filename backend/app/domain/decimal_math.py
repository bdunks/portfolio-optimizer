from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal, localcontext


def _required_precision(values: tuple[Decimal, ...]) -> int:
    if not values:
        return 28
    exponents: list[int] = []
    for value in values:
        exponent = value.as_tuple().exponent
        if not isinstance(exponent, int):
            raise TypeError("Decimal exponent must be an integer")
        exponents.append(exponent)
    min_exponent = min(exponents)
    max_adjusted = max(value.adjusted() if value else 0 for value in values)
    return max(28, max_adjusted - min_exponent + len(str(len(values))) + 4)

def exact_sum(values: Iterable[Decimal]) -> Decimal:
    items = tuple(values)
    with localcontext() as context:
        context.prec = _required_precision(items)
        return sum(items, Decimal(0))


def exact_product(left: Decimal, right: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = max(28, len(left.as_tuple().digits) + len(right.as_tuple().digits) + 2)
        return left * right


def exact_difference(left: Decimal, right: Decimal) -> Decimal:
    return exact_sum((left, right.copy_negate()))


def percentage(value: Decimal, denominator: Decimal, *, places: int = 2) -> Decimal:
    if denominator == 0:
        return Decimal(0)
    quantum = Decimal(1).scaleb(-places)
    with localcontext() as context:
        context.prec = 80
        return (value / denominator * Decimal(100)).quantize(quantum)


def exact_percent_product(value: Decimal, percent: Decimal) -> Decimal:
    """Return value * percent / 100 without ambient-context division rounding."""
    return exact_product(exact_product(value, percent), Decimal("0.01"))


def whole_share_floor(amount: Decimal, unit_price: Decimal) -> Decimal:
    """Floor a nonnegative funding amount to whole shares using exact integer ratios."""
    if amount < 0 or unit_price <= 0:
        raise ValueError("amount must be nonnegative and unit_price must be positive")
    amount_numerator, amount_denominator = amount.as_integer_ratio()
    price_numerator, price_denominator = unit_price.as_integer_ratio()
    return Decimal((amount_numerator * price_denominator) // (amount_denominator * price_numerator))
