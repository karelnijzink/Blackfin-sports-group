"""Builds the reconciliation model: headline, method table, monthly view, flags.

This module arranges computed numbers next to the client's known numbers.
It computes variances and nothing else — every underlying figure arrives
from the engine already final.
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, ConfigDict

from commission_engine.forecast.engine import ForecastResult
from commission_engine.ledger.schema import TWO_DP, Flag, MonthlyEntry

PCT = Decimal("0.1")


class MethodRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    label: str
    total: Decimal | None  # None when the method could not run
    monthly: list[Decimal]
    variance_vs_midpoint_pct: Decimal | None  # None without a target or total
    in_range: bool | None
    presented: bool = False
    rationale: str | None = None
    error: str | None = None


class ReconciliationReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    client_name: str
    as_of: date
    horizon: int
    rule_description: str | None = None

    target_low: Decimal | None
    target_high: Decimal | None

    historical: list[MonthlyEntry]
    historical_total: Decimal

    methods: list[MethodRow]
    projected_months: list[date]

    flags: list[Flag]

    @property
    def presented(self) -> MethodRow:
        return next(m for m in self.methods if m.presented)

    @property
    def target_mid(self) -> Decimal | None:
        if self.target_low is None or self.target_high is None:
            return None
        return (self.target_low + self.target_high) / 2

    @property
    def headline_total(self) -> Decimal | None:
        return self.presented.total

    @property
    def headline_in_range(self) -> bool | None:
        return self.presented.in_range

    @property
    def headline_variance_pct(self) -> Decimal | None:
        """Signed % against the nearest range bound; 0 when inside the range."""
        total = self.presented.total
        if total is None or self.target_low is None or self.target_high is None:
            return None
        if total < self.target_low:
            bound = self.target_low
        elif total > self.target_high:
            bound = self.target_high
        else:
            return Decimal("0")
        return (total - bound) / bound * 100

    @property
    def projected(self) -> list[tuple[date, Decimal]]:
        """The presented method's projection, month by month."""
        return list(zip(self.projected_months, self.presented.monthly, strict=True))


def build_report(
    *,
    client_name: str,
    result: ForecastResult,
    target_low: Decimal | None = None,
    target_high: Decimal | None = None,
    presented_method: str,
    presented_rationale: str,
    rule_description: str | None = None,
) -> ReconciliationReport:
    if not result.stream:
        raise ValueError("no usable deal rows: nothing to reconcile or project")
    if not presented_rationale or not presented_rationale.strip():
        raise ValueError(
            "the presented method requires a stated rationale (set presented_rationale)"
        )
    method_keys = [m.key for m in result.methods]
    if presented_method not in method_keys:
        raise ValueError(
            f"presented method {presented_method!r} is not a computed method {method_keys}"
        )

    mid = None if target_low is None or target_high is None else (target_low + target_high) / 2

    rows: list[MethodRow] = []
    for m in result.methods:
        variance = None
        in_range = None
        if m.total is not None and mid is not None:
            variance = ((m.total - mid) / mid * 100).quantize(PCT, rounding=ROUND_HALF_UP)
            in_range = target_low <= m.total <= target_high
        is_presented = m.key == presented_method
        rows.append(
            MethodRow(
                key=m.key,
                label=m.label,
                total=m.total,
                monthly=m.monthly,
                variance_vs_midpoint_pct=variance,
                in_range=in_range,
                presented=is_presented,
                rationale=presented_rationale if is_presented else None,
                error=m.error,
            )
        )

    presented_row = next(r for r in rows if r.presented)
    if presented_row.error is not None:
        raise ValueError(
            f"presented method {presented_method!r} could not run: {presented_row.error}"
        )

    return ReconciliationReport(
        client_name=client_name,
        as_of=result.as_of,
        horizon=result.horizon,
        rule_description=rule_description,
        target_low=target_low,
        target_high=target_high,
        historical=result.stream,
        historical_total=result.historical_total.quantize(TWO_DP, rounding=ROUND_HALF_UP),
        methods=rows,
        projected_months=result.projected_months,
        flags=result.flags,
    )
