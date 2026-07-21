"""Payment-schedule spreading — milestone 2. Interface only.

Some deals are paid in several installments across the year; their commission
must land in the months the money actually moves, not all at once. This module
will turn one deal plus its schedule into N monthly entries. The installments
must sum to the deal's gross — anything else is an error, never silently
normalised.
"""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from .schema import MonthlyEntry


class PaymentSchedule(BaseModel):
    """The agreed installments for one deal: (month, gross amount) pairs."""

    model_config = ConfigDict(frozen=True)

    installments: list[tuple[date, Decimal]]


def spread_deal(
    *,
    gross: Decimal,
    commission: Decimal,
    schedule: PaymentSchedule,
) -> list[MonthlyEntry]:
    """Split one deal's commission across its payment schedule. Milestone 2."""
    raise NotImplementedError("payment-schedule spreading is milestone 2")
