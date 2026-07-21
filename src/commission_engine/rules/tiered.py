"""Tiered commission with marginal bands.

Each band's rate applies only to the slice of gross inside that band, the way
marginal tax brackets work: with 10% up to 100k and 15% above, a 150k deal
earns 100k x 10% + 50k x 15%, not 150k x 15%.
"""

from decimal import Decimal
from typing import NamedTuple


class Tier(NamedTuple):
    up_to: Decimal | None  # band's upper gross bound; None = open-ended top band
    rate: Decimal


class Tiered:
    def __init__(self, tiers: list[Tier]):
        if not tiers:
            raise ValueError("at least one tier is required")
        if tiers[-1].up_to is not None:
            raise ValueError("the last tier must be open-ended (up_to=None)")
        bounds = [t.up_to for t in tiers[:-1]]
        if any(b is None for b in bounds):
            raise ValueError("only the last tier may be open-ended")
        if any(b <= 0 for b in bounds):
            raise ValueError("tier bounds must be positive")
        if any(later <= earlier for earlier, later in zip(bounds, bounds[1:])):
            raise ValueError(f"tier bounds must strictly ascend, got {bounds}")
        if any(not Decimal("0") <= t.rate <= Decimal("1") for t in tiers):
            raise ValueError("every rate must be between 0 and 1")
        self.tiers = [Tier(None if t.up_to is None else Decimal(t.up_to), Decimal(t.rate)) for t in tiers]

    def commission(self, gross: Decimal) -> Decimal:
        if gross < 0:
            raise ValueError(f"marginal bands are undefined for negative gross ({gross})")
        total = Decimal("0")
        band_floor = Decimal("0")
        for tier in self.tiers:
            band_ceiling = gross if tier.up_to is None else min(gross, tier.up_to)
            if band_ceiling > band_floor:
                total += (band_ceiling - band_floor) * tier.rate
            band_floor = tier.up_to if tier.up_to is not None else gross
            if band_floor >= gross:
                break
        return total

    def describe(self) -> str:
        parts = []
        for tier in self.tiers:
            pct = (tier.rate * 100).normalize()
            if tier.up_to is None:
                parts.append(f"{pct}% above that")
            else:
                parts.append(f"{pct}% up to {tier.up_to:,.0f}")
        return "marginal bands: " + ", ".join(parts)

    def __repr__(self) -> str:
        return f"Tiered(tiers={self.tiers})"
