"""Loader behaviour: cross-check raise, month bucketing, no-fill on missing data."""

import csv
from datetime import date
from decimal import Decimal

import pytest

from commission_engine.forecast.engine import build_monthly_stream
from commission_engine.ledger.csv_source import load_hubspot_csv
from commission_engine.ledger.schema import CrossCheckError, FlagCode
from commission_engine.rules.flat import FlatRate

TEN_PERCENT = FlatRate(Decimal("0.10"))

HEADER = [
    "Deal Name",
    "Pipeline",
    "Deal Stage",
    "Amount",
    "Annual Payment Date",
    "Close Date",
    "Deal Owner",
    "Deal Type",
    "Priority",
    "Period Start",
    "Period End",
    "Sales Amount",
    "Commission Amount",
    "Revenue Source",
    "Invoice Reference",
    "Company Name (for association)",
    "Record ID",
]


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=HEADER)
        writer.writeheader()
        writer.writerows(rows)
    return path


def row(**overrides):
    base = {
        "Deal Name": "Acme – Blast Commission – Apr 2025",
        "Pipeline": "Blast Media Commission Revenue",
        "Deal Stage": "Recorded",
        "Amount": "100",
        "Close Date": "2025-04-30",
        "Period Start": "2025-04-01",
        "Period End": "2025-04-30",
        "Sales Amount": "1000",
        "Commission Amount": "100",
        "Invoice Reference": "11111",
        "Company Name (for association)": "Acme",
        "Record ID": "1",
    }
    base.update(overrides)
    return base


def test_loads_all_48_rows(blast_media_csv):
    loaded = load_hubspot_csv(blast_media_csv, TEN_PERCENT)
    assert len(loaded.deals) == 48
    # the real export is clean: no row-level flags
    assert loaded.flags == []


def test_cross_check_raises_beyond_5_cents(tmp_path, blast_media_csv):
    """Corrupt one row's Commission Amount by more than $0.05 -> loader raises."""
    with open(blast_media_csv, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    rows[0]["Commission Amount"] = str(Decimal(rows[0]["Commission Amount"]) + Decimal("0.06"))
    corrupt = write_csv(tmp_path / "corrupt.csv", rows)
    with pytest.raises(CrossCheckError):
        load_hubspot_csv(corrupt, TEN_PERCENT)


def test_cross_check_tolerates_rounding_within_5_cents(tmp_path):
    # 894.75 * 0.10 = 89.475 computed vs 89.47 recorded: within tolerance
    p = write_csv(
        tmp_path / "ok.csv", [row(**{"Sales Amount": "894.75", "Commission Amount": "89.47"})]
    )
    loaded = load_hubspot_csv(p, TEN_PERCENT)
    assert len(loaded.deals) == 1


def test_buckets_by_period_start_never_close_date(tmp_path):
    """Close Date in June, Period Start in April: the commission lands in April."""
    p = write_csv(
        tmp_path / "bucket.csv",
        [
            row(
                **{
                    "Close Date": "2025-06-15",
                    "Period Start": "2025-04-01",
                    "Period End": "2025-04-30",
                }
            )
        ],
    )
    loaded = load_hubspot_csv(p, TEN_PERCENT)
    stream = build_monthly_stream(loaded.deals)
    assert [e.month for e in stream] == [date(2025, 4, 1)]
    assert stream[0].commission_2dp == Decimal("100.00")


def test_missing_sales_amount_is_flagged_never_filled(tmp_path):
    p = write_csv(
        tmp_path / "missing.csv",
        [row(), row(**{"Deal Name": "Broken", "Sales Amount": "", "Commission Amount": ""})],
    )
    loaded = load_hubspot_csv(p, TEN_PERCENT)
    # the broken row is excluded from the ledger, not guessed at
    assert len(loaded.deals) == 1
    assert [f.code for f in loaded.flags] == [FlagCode.UNPARSEABLE_ROW]
    assert "Broken" in loaded.flags[0].detail


def test_missing_period_start_is_flagged_never_filled(tmp_path):
    p = write_csv(tmp_path / "missing.csv", [row(**{"Period Start": ""})])
    loaded = load_hubspot_csv(p, TEN_PERCENT)
    assert loaded.deals == []
    assert [f.code for f in loaded.flags] == [FlagCode.UNPARSEABLE_ROW]


def test_missing_commission_column_flags_unverified(tmp_path):
    """A row we cannot cross-check is loaded but flagged for human review."""
    p = write_csv(tmp_path / "nocheck.csv", [row(**{"Commission Amount": ""})])
    loaded = load_hubspot_csv(p, TEN_PERCENT)
    assert len(loaded.deals) == 1
    assert [f.code for f in loaded.flags] == [FlagCode.MISSING_CROSS_CHECK]


def test_multi_invoice_rows_parse_reference_list(blast_media_csv):
    loaded = load_hubspot_csv(blast_media_csv, TEN_PERCENT)
    by_name = {d.deal_name: d for d in loaded.deals}
    deal = by_name["BC Lions – Blast Commission – May 2026"]
    assert deal.invoice_refs == ["25289", "25293", "25443", "25449", "25513"]


def test_blank_trailing_lines_are_ignored(blast_media_csv):
    # the real export ends with an empty line; it must not become a flag or a deal
    loaded = load_hubspot_csv(blast_media_csv, TEN_PERCENT)
    assert len(loaded.deals) == 48


def test_malformed_optional_date_is_flagged_never_crashes(tmp_path):
    # US-format Close Date is common in hand-edited exports; flag, don't die
    p = write_csv(tmp_path / "baddate.csv", [row(**{"Close Date": "07/15/2025"})])
    loaded = load_hubspot_csv(p, TEN_PERCENT)
    assert loaded.deals == []
    assert [f.code for f in loaded.flags] == [FlagCode.UNPARSEABLE_ROW]


def test_negative_gross_under_tiered_rule_is_flagged_never_crashes(tmp_path):
    from commission_engine.rules.tiered import Tier, Tiered

    tiered = Tiered(
        [Tier(up_to=Decimal("1000"), rate=Decimal("0.10")), Tier(None, Decimal("0.15"))]
    )
    p = write_csv(
        tmp_path / "refund.csv", [row(**{"Sales Amount": "-500", "Commission Amount": "-50"})]
    )
    loaded = load_hubspot_csv(p, tiered)
    assert loaded.deals == []
    assert [f.code for f in loaded.flags] == [FlagCode.UNPARSEABLE_ROW]


def test_row_numbers_are_physical_lines_despite_blank_lines(tmp_path):
    # a blank physical line must not shift the row numbers clients are told to fix
    path = tmp_path / "gaps.csv"
    good = row()
    broken = row(**{"Deal Name": "Broken", "Sales Amount": ""})
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=HEADER)
        writer.writeheader()  # line 1
        writer.writerow(good)  # line 2
        fh.write("\n")  # line 3: blank
        writer.writerow(broken)  # line 4
    loaded = load_hubspot_csv(path, TEN_PERCENT)
    assert len(loaded.deals) == 1
    assert loaded.flags[0].source_row == 4
    assert "Row 4" in loaded.flags[0].question


def test_extra_comma_junk_row_is_skipped_or_flagged_never_crashes(tmp_path):
    # DictReader parks surplus fields under key None as a list; the loader
    # must not call .strip() on it
    path = tmp_path / "junk.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=HEADER)
        writer.writeheader()
        writer.writerow(row())
        fh.write("," * len(HEADER) + "\n")  # all named fields empty + one surplus
        fh.write("," * len(HEADER) + "junk\n")  # surplus field with content
    loaded = load_hubspot_csv(path, TEN_PERCENT)
    assert len(loaded.deals) == 1
    assert [f.code for f in loaded.flags] == [FlagCode.UNPARSEABLE_ROW]
    assert loaded.flags[0].source_row == 4


def test_flag_text_renders_money_at_2dp(tmp_path):
    # 894.75 * 0.10 = 89.475 exactly; client-facing text must say 89.48
    p = write_csv(
        tmp_path / "nocheck.csv",
        [row(**{"Sales Amount": "894.75", "Commission Amount": ""})],
    )
    loaded = load_hubspot_csv(p, TEN_PERCENT)
    assert "89.48" in loaded.flags[0].question
    assert "89.475" not in loaded.flags[0].question


def test_cross_check_error_message_renders_money_at_2dp(tmp_path, blast_media_csv):
    p = write_csv(
        tmp_path / "bad.csv",
        [row(**{"Sales Amount": "894.75", "Commission Amount": "80"})],
    )
    with pytest.raises(CrossCheckError) as excinfo:
        load_hubspot_csv(p, TEN_PERCENT)
    assert "89.48" in str(excinfo.value)
    assert "89.475" not in str(excinfo.value)
