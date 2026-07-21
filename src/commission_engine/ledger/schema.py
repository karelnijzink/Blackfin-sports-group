"""Data models for the deal ledger.

Money is Decimal everywhere internally; rounding to 2dp happens only at the
reporting edge. Nothing in these models ever fills a missing value.
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

TWO_DP = Decimal("0.01")


def display_money(value: Decimal) -> str:
    """$ and 2dp with thousands separators — money is rendered the same way
    everywhere, including flag questions and error messages."""
    return f"${value.quantize(TWO_DP, rounding=ROUND_HALF_UP):,.2f}"


class Deal(BaseModel):
    """One row of the client's deal export. One deal, one revenue month."""

    model_config = ConfigDict(frozen=True)

    deal_name: str
    company: str | None = None
    record_id: str | None = None
    close_date: date | None = None
    period_start: date  # the revenue month; always bucket by this, never Close Date
    period_end: date | None = None
    sales_amount: Decimal  # gross
    computed_commission: Decimal  # our number: rule applied to gross, unrounded
    commission_amount: Decimal | None = None  # client's own figure, cross-check only
    invoice_refs: list[str] = []
    source_row: int  # 1-based data row in the export, for flag messages

    @property
    def month(self) -> date:
        return self.period_start.replace(day=1)


class MonthlyEntry(BaseModel):
    """One month of the commission stream."""

    model_config = ConfigDict(frozen=True)

    month: date  # first of month
    gross: Decimal
    commission: Decimal  # unrounded; quantize only when rendering
    deal_count: int

    @property
    def commission_2dp(self) -> Decimal:
        return self.commission.quantize(TWO_DP, rounding=ROUND_HALF_UP)


class FlagCode(StrEnum):
    MISSING_MONTH = "missing_month"
    OUTLIER_MONTH = "outlier_month"
    PARTIAL_CURRENT_MONTH = "partial_current_month"
    CROSS_CHECK_MISMATCH = "cross_check_mismatch"
    MISSING_CROSS_CHECK = "missing_cross_check"
    UNPARSEABLE_ROW = "unparseable_row"


class Flag(BaseModel):
    """A structured question for human review. First-class output, not a log line."""

    model_config = ConfigDict(frozen=True)

    code: FlagCode
    question: str  # phrased for the client, always ends in "?"
    month: date | None = None
    source_row: int | None = None
    detail: str | None = None


class CrossCheckError(ValueError):
    """A row's recorded commission disagrees with rule(gross) beyond tolerance."""

    def __init__(
        self,
        deal_name: str,
        source_row: int,
        computed: Decimal,
        recorded: Decimal,
        tolerance: Decimal,
    ):
        self.deal_name = deal_name
        self.source_row = source_row
        self.computed = computed
        self.recorded = recorded
        self.tolerance = tolerance
        super().__init__(
            f"Cross-check failed on row {source_row} ({deal_name!r}): "
            f"computed commission {display_money(computed)} vs recorded "
            f"{display_money(recorded)} (difference exceeds ${tolerance})"
        )
