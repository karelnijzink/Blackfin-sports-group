"""Orchestration: ledger -> monthly stream -> every projection method.

Every method always runs and is always reported. A method that cannot
honestly handle the series carries its error message instead of a number —
nothing is discarded silently and nothing is substituted.
"""

import statistics
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, ConfigDict

from commission_engine.ledger.csv_source import LoadResult
from commission_engine.ledger.schema import TWO_DP, Deal, Flag, FlagCode, MonthlyEntry

from . import methods

# a month more than 5x the median of its +-2 calendar neighbours is an outlier
OUTLIER_MULTIPLIER = 5
NEIGHBOUR_WINDOW = 2


def _month_add(month: date, count: int) -> date:
    total = month.year * 12 + (month.month - 1) + count
    return date(total // 12, total % 12 + 1, 1)


def _month_span(first: date, last: date) -> list[date]:
    """Every calendar month from first to last inclusive."""
    span = []
    current = first
    while current <= last:
        span.append(current)
        current = _month_add(current, 1)
    return span


def build_monthly_stream(deals: list[Deal]) -> list[MonthlyEntry]:
    """Bucket deals into calendar months by Period Start. Months with no deals
    are absent, not zero-filled — absence is a flag, zero is an invented value."""
    buckets: dict[date, list[Deal]] = {}
    for deal in deals:
        buckets.setdefault(deal.month, []).append(deal)
    return [
        MonthlyEntry(
            month=month,
            gross=sum((d.sales_amount for d in month_deals), Decimal("0")),
            commission=sum((d.computed_commission for d in month_deals), Decimal("0")),
            deal_count=len(month_deals),
        )
        for month, month_deals in sorted(buckets.items())
    ]


class MethodResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    label: str
    monthly: list[Decimal]  # projected months, 2dp; empty when errored
    total: Decimal | None  # 12-month total, 2dp; None when errored
    error: str | None = None


class ForecastResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    as_of: date
    horizon: int
    stream: list[MonthlyEntry]
    projected_months: list[date]  # calendar months the projections cover
    methods: list[MethodResult]
    flags: list[Flag]

    @property
    def historical_total(self) -> Decimal:
        return sum((e.commission for e in self.stream), Decimal("0")).quantize(
            TWO_DP, rounding=ROUND_HALF_UP
        )


def detect_stream_flags(stream: list[MonthlyEntry], *, as_of: date) -> list[Flag]:
    flags: list[Flag] = []
    if not stream:
        return flags
    by_month = {e.month: e for e in stream}
    first, last = stream[0].month, stream[-1].month
    current_month = as_of.replace(day=1)

    # months missing inside the recorded range
    for month in _month_span(first, last):
        if month not in by_month:
            flags.append(
                Flag(
                    code=FlagCode.MISSING_MONTH,
                    month=month,
                    question=(
                        f"There is no commission recorded for {month:%B %Y}, though the "
                        f"months around it are present — was there genuinely none, or is "
                        f"data missing from the export?"
                    ),
                )
            )

    # months missing between the end of the data and the month before as_of
    last_complete = _month_add(current_month, -1)
    if last < last_complete:
        for month in _month_span(_month_add(last, 1), last_complete):
            flags.append(
                Flag(
                    code=FlagCode.MISSING_MONTH,
                    month=month,
                    question=(
                        f"{month:%B %Y} is absent from an otherwise contiguous sequence "
                        f"ending {last:%B %Y} — is the export simply through {last:%B %Y}, "
                        f"or was there no commission that month?"
                    ),
                )
            )
    elif last == current_month:
        flags.append(
            Flag(
                code=FlagCode.PARTIAL_CURRENT_MONTH,
                month=last,
                question=(
                    f"{last:%B %Y} is the current month and likely incomplete — should it "
                    f"stay in the history the projections are built on, or be excluded "
                    f"until the month closes?"
                ),
            )
        )

    # outliers: a month far above its neighbours skews every trailing method
    for entry in stream:
        neighbours = [
            float(other.commission_2dp)
            for other in stream
            if other.month != entry.month
            and abs(
                (other.month.year * 12 + other.month.month)
                - (entry.month.year * 12 + entry.month.month)
            )
            <= NEIGHBOUR_WINDOW
        ]
        if not neighbours:
            continue
        median = statistics.median(neighbours)
        if float(entry.commission_2dp) > OUTLIER_MULTIPLIER * median:
            flags.append(
                Flag(
                    code=FlagCode.OUTLIER_MONTH,
                    month=entry.month,
                    question=(
                        f"{entry.month:%B %Y} commission ({entry.commission_2dp:,.2f}) is "
                        f"more than {OUTLIER_MULTIPLIER}x the median of its neighbouring "
                        f"months — is that a one-off, or volume to expect again?"
                    ),
                    detail=(
                        f"{entry.commission_2dp:,.2f} vs neighbour median {median:,.2f}; "
                        f"{entry.deal_count} deals in the month"
                    ),
                )
            )
    return flags


def _quantize(value: float) -> Decimal:
    return Decimal(str(value)).quantize(TWO_DP, rounding=ROUND_HALF_UP)


# every method, always computed, always reported, in presentation order
METHOD_SPECS: list[tuple[str, str, object]] = [
    ("run_rate_3", "Trailing 3-mo run-rate", lambda v, h: methods.run_rate(v, window=3, horizon=h)),
    ("run_rate_6", "Trailing 6-mo run-rate", lambda v, h: methods.run_rate(v, window=6, horizon=h)),
    ("blend_3_6", "3-mo/6-mo blend", lambda v, h: methods.blend(v, windows=(3, 6), horizon=h)),
    ("linear_trend", "Linear trend (least squares)", methods.linear_trend),
    ("geometric_growth", "Geometric MoM growth", methods.geometric_growth),
]


def run_forecast(loaded: LoadResult, *, as_of: date, horizon: int = 12) -> ForecastResult:
    stream = build_monthly_stream(loaded.deals)
    flags = list(loaded.flags) + detect_stream_flags(stream, as_of=as_of)

    # projections are computed from the monthly stream exactly as printed (2dp),
    # so every figure in the report can be recomputed by hand from the table
    values = [float(e.commission_2dp) for e in stream]
    last_month = stream[-1].month if stream else as_of.replace(day=1)
    projected_months = [_month_add(last_month, k) for k in range(1, horizon + 1)]

    results: list[MethodResult] = []
    for key, label, fn in METHOD_SPECS:
        try:
            projected = fn(values, horizon)
        except ValueError as exc:
            results.append(
                MethodResult(key=key, label=label, monthly=[], total=None, error=str(exc))
            )
            continue
        monthly = [_quantize(v) for v in projected]
        results.append(
            MethodResult(key=key, label=label, monthly=monthly, total=_quantize(sum(projected)))
        )

    return ForecastResult(
        as_of=as_of,
        horizon=horizon,
        stream=stream,
        projected_months=projected_months,
        methods=results,
        flags=flags,
    )
