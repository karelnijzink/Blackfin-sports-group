"""Report/renderer robustness: edge-case series must render honestly, never crash."""

from datetime import date
from decimal import Decimal

import pytest

from commission_engine.forecast.engine import run_forecast
from commission_engine.ledger.csv_source import load_hubspot_csv
from commission_engine.reconcile.render import render_html, render_markdown
from commission_engine.reconcile.report import build_report
from commission_engine.rules.flat import FlatRate
from test_loader import row, write_csv

TEN_PERCENT = FlatRate(Decimal("0.10"))


def month_row(month: str, sales: str):
    commission = str(Decimal(sales) * Decimal("0.10"))
    return row(
        **{
            "Deal Name": f"Acme – {month}",
            "Period Start": f"{month}-01",
            "Period End": f"{month}-28",
            "Close Date": f"{month}-28",
            "Sales Amount": sales,
            "Commission Amount": commission,
        }
    )


def report_for(tmp_path, sales_by_month: dict[str, str], presented: str):
    csv_path = write_csv(
        tmp_path / "series.csv", [month_row(m, s) for m, s in sales_by_month.items()]
    )
    loaded = load_hubspot_csv(csv_path, TEN_PERCENT)
    result = run_forecast(loaded, as_of=date(2026, 7, 21), horizon=12)
    return build_report(
        client_name="Synthetic",
        result=result,
        presented_method=presented,
        presented_rationale="synthetic fixture",
    )


def test_all_zero_months_render_without_crashing(tmp_path):
    months = {f"2026-0{i}": "0" for i in range(1, 7)}
    report = report_for(tmp_path, months, presented="blend_3_6")
    html = render_html(report)
    assert "<svg" in html
    assert "$0.00" in html
    assert render_markdown(report)


def test_negative_projection_renders_with_negative_axis(tmp_path):
    # a declining book: linear trend legitimately projects below zero, and the
    # chart must show that, not clip it into the label strip
    months = {
        "2026-01": "6000",
        "2026-02": "5000",
        "2026-03": "4000",
        "2026-04": "3000",
        "2026-05": "2000",
        "2026-06": "1000",
    }
    report = report_for(tmp_path, months, presented="linear_trend")
    assert report.presented.monthly[-1] < 0
    html = render_html(report)
    assert "<svg" in html
    assert ">-1,000</text>" in html  # negative tick labels exist on the y axis


def test_missing_presented_rationale_is_rejected(tmp_path):
    months = {"2026-01": "1000", "2026-02": "2000"}
    csv_path = write_csv(tmp_path / "s.csv", [month_row(m, s) for m, s in months.items()])
    loaded = load_hubspot_csv(csv_path, TEN_PERCENT)
    result = run_forecast(loaded, as_of=date(2026, 7, 21), horizon=12)
    with pytest.raises(ValueError, match="rationale"):
        build_report(
            client_name="Synthetic",
            result=result,
            presented_method="blend_3_6",
            presented_rationale="",
        )


def test_client_supplied_strings_are_escaped_in_html(tmp_path):
    months = {f"2026-0{i}": "1000" for i in range(1, 7)}
    csv_path = write_csv(
        tmp_path / "s.csv",
        [month_row(m, s) for m, s in months.items()],
    )
    loaded = load_hubspot_csv(csv_path, TEN_PERCENT)
    result = run_forecast(loaded, as_of=date(2026, 7, 21), horizon=12)
    report = build_report(
        client_name="<script>alert(1)</script> & Co",
        result=result,
        presented_method="blend_3_6",
        presented_rationale="a & b <c>",
    )
    html = render_html(report)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
