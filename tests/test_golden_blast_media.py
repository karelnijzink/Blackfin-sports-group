"""Golden acceptance suite for the Blast Media pilot.

These numbers are the answer key validated against the client's own expected
range. They are the regression net for the whole project: if any assertion
here fails after a refactor, the refactor is wrong — never the test.
"""

from datetime import date
from decimal import Decimal

from commission_engine.forecast.engine import build_monthly_stream, run_forecast
from commission_engine.ledger.csv_source import load_hubspot_csv
from commission_engine.ledger.schema import FlagCode
from commission_engine.reconcile.report import build_report
from commission_engine.rules.flat import FlatRate

AS_OF = date(2026, 7, 21)  # date of the client's export hand-off

GOLDEN_MONTHLY = {
    "2025-04": Decimal("1508.30"),
    "2025-05": Decimal("924.70"),
    "2025-06": Decimal("1254.40"),
    "2025-07": Decimal("267.20"),
    "2025-08": Decimal("484.58"),
    "2025-09": Decimal("11330.87"),
    "2025-10": Decimal("653.41"),
    "2025-11": Decimal("5911.50"),
    "2025-12": Decimal("3498.23"),
    "2026-01": Decimal("3594.19"),
    "2026-02": Decimal("1445.02"),
    "2026-03": Decimal("4258.45"),
    "2026-04": Decimal("9525.45"),
    "2026-05": Decimal("15530.96"),
}

GOLDEN_HISTORICAL_TOTAL = Decimal("60187.27")

# 12-month projection totals, tolerance ±$1 for float ordering.
GOLDEN_METHOD_TOTALS = {
    "run_rate_3": Decimal("117259"),
    "run_rate_6": Decimal("75705"),
    "blend_3_6": Decimal("96482"),
    "linear_trend": Decimal("157701"),
    "geometric_growth": Decimal("719407"),
}

TARGET_LOW = Decimal("97000")
TARGET_HIGH = Decimal("105000")


def _forecast(blast_media_csv):
    loaded = load_hubspot_csv(blast_media_csv, FlatRate(Decimal("0.10")))
    return run_forecast(loaded, as_of=AS_OF, horizon=12)


def test_monthly_commission_stream_verbatim(blast_media_csv):
    loaded = load_hubspot_csv(blast_media_csv, FlatRate(Decimal("0.10")))
    stream = build_monthly_stream(loaded.deals)
    got = {e.month.strftime("%Y-%m"): e.commission_2dp for e in stream}
    assert got == GOLDEN_MONTHLY
    # ordered, contiguous, 14 months
    assert [e.month.strftime("%Y-%m") for e in stream] == list(GOLDEN_MONTHLY)


def test_historical_total(blast_media_csv):
    loaded = load_hubspot_csv(blast_media_csv, FlatRate(Decimal("0.10")))
    stream = build_monthly_stream(loaded.deals)
    total = sum(e.commission for e in stream).quantize(Decimal("0.01"))
    assert total == GOLDEN_HISTORICAL_TOTAL


def test_every_projection_method_hits_golden_total(blast_media_csv):
    result = _forecast(blast_media_csv)
    totals = {m.key: m.total for m in result.methods}
    assert set(totals) == set(GOLDEN_METHOD_TOTALS)
    for key, golden in GOLDEN_METHOD_TOTALS.items():
        assert abs(totals[key] - golden) <= Decimal("1"), (key, totals[key], golden)


def test_blend_is_presented_and_within_half_percent_of_floor(blast_media_csv):
    result = _forecast(blast_media_csv)
    report = build_report(
        client_name="Blast Media",
        result=result,
        target_low=TARGET_LOW,
        target_high=TARGET_HIGH,
        presented_method="blend_3_6",
        presented_rationale="test rationale",
    )
    assert report.presented.key == "blend_3_6"
    # blend sits just under the range floor: -0.5% against 97,000
    assert report.headline_in_range is False
    assert round(report.headline_variance_pct, 1) == Decimal("-0.5")
    # every method is always reported, nothing discarded
    assert {m.key for m in report.methods} == set(GOLDEN_METHOD_TOTALS)
    # exactly one presented method, with a stated rationale
    presented = [m for m in report.methods if m.presented]
    assert len(presented) == 1 and presented[0].rationale


def test_june_2026_gap_flag(blast_media_csv):
    """June 2026 is absent from an otherwise contiguous sequence (as of July 2026)."""
    result = _forecast(blast_media_csv)
    missing = [f for f in result.flags if f.code == FlagCode.MISSING_MONTH]
    assert [f.month for f in missing] == [date(2026, 6, 1)]


def test_sep_2025_outlier_flag(blast_media_csv):
    """Sep 2025 (11,330.87) is >5x the median of its neighbouring months."""
    result = _forecast(blast_media_csv)
    outliers = [f for f in result.flags if f.code == FlagCode.OUTLIER_MONTH]
    assert [f.month for f in outliers] == [date(2025, 9, 1)]


def test_flags_render_as_questions(blast_media_csv):
    result = _forecast(blast_media_csv)
    for flag in result.flags:
        assert flag.question.strip().endswith("?")


def test_cli_end_to_end_reproduces_golden_numbers(blast_media_csv, tmp_path, capsys):
    """M1 definition of done: `forecast run --client blast_media` on the real CSV
    reproduces the golden numbers and emits the June-gap and Sep-outlier flags."""
    from commission_engine.cli import main

    exit_code = main(
        [
            "run",
            "--client", "blast_media",
            "--csv", str(blast_media_csv),
            "--target", "97000:105000",
            "--as-of", "2026-07-21",
            "--out", str(tmp_path),
        ]
    )
    assert exit_code == 0

    md = (tmp_path / "blast_media_reconciliation.md").read_text()
    html = (tmp_path / "blast_media_reconciliation.html").read_text()
    for output in (md, html):
        assert "96,482" in output          # presented blend total
        assert "117,259" in output         # 3-mo run-rate
        assert "75,70" in output           # 6-mo run-rate (75,704.60 -> 75,705 rounded)
        assert "157,70" in output          # linear trend
        assert "719,40" in output          # geometric growth
        assert "60,187.27" in output       # historical total
        assert "June 2026" in output       # gap flag
        assert "September 2025" in output  # outlier flag
        assert "Deterministic math. Every number computed by code from the deal export." in output

    console = capsys.readouterr().out
    assert "96,482" in console

