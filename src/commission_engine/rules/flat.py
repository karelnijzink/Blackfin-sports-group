"""Flat-rate commission: one rate on every dollar of gross. Rule one (Blast Media)."""

from decimal import Decimal


class FlatRate:
    def __init__(self, rate: Decimal):
        rate = Decimal(rate)
        if not Decimal("0") <= rate <= Decimal("1"):
            raise ValueError(f"rate must be between 0 and 1, got {rate}")
        self.rate = rate

    def commission(self, gross: Decimal) -> Decimal:
        return gross * self.rate

    def describe(self) -> str:
        pct = (self.rate * 100).normalize()
        return f"flat {pct}% of gross"

    def __repr__(self) -> str:
        return f"FlatRate(rate={self.rate})"
