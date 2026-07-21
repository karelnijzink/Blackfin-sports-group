"""Payment-schedule spreading is milestone 2: interface ships now, marked skip."""

from datetime import date
from decimal import Decimal

import pytest

from commission_engine.ledger.spread import PaymentSchedule, spread_deal

pytestmark = pytest.mark.skip(reason="milestone 2: payment-schedule spreading not yet implemented")


def test_even_split_across_months():
    schedule = PaymentSchedule(
        installments=[
            (date(2026, 1, 1), Decimal("5000")),
            (date(2026, 4, 1), Decimal("5000")),
        ]
    )
    entries = spread_deal(gross=Decimal("10000"), commission=Decimal("1000"), schedule=schedule)
    assert [(e.month, e.commission) for e in entries] == [
        (date(2026, 1, 1), Decimal("500")),
        (date(2026, 4, 1), Decimal("500")),
    ]


def test_installments_must_sum_to_gross():
    schedule = PaymentSchedule(installments=[(date(2026, 1, 1), Decimal("4000"))])
    with pytest.raises(ValueError):
        spread_deal(gross=Decimal("10000"), commission=Decimal("1000"), schedule=schedule)
