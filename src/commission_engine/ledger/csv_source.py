"""HubSpot export CSV adapter — the v1 deal source.

Read-only: this module reads an export file and returns models. Every row's
recorded commission is cross-checked against the client's rule; a disagreement
beyond tolerance is an error, not a warning, because it means either the rule
or the export is wrong and no forecast should be built on it.

Rows with missing critical fields are excluded and flagged — never filled.
"""

import csv
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from commission_engine.rules.base import CommissionRule

from .schema import CrossCheckError, Deal, Flag, FlagCode

DEFAULT_TOLERANCE = Decimal("0.05")

# HubSpot export header -> internal field
COLUMNS = {
    "deal_name": "Deal Name",
    "close_date": "Close Date",
    "period_start": "Period Start",
    "period_end": "Period End",
    "sales_amount": "Sales Amount",
    "commission_amount": "Commission Amount",
    "invoice_refs": "Invoice Reference",
    "company": "Company Name (for association)",
    "record_id": "Record ID",
}


@dataclass
class LoadResult:
    deals: list[Deal] = field(default_factory=list)
    flags: list[Flag] = field(default_factory=list)


def _parse_money(raw: str | None) -> Decimal | None:
    if raw is None:
        return None
    cleaned = raw.replace("$", "").replace(",", "").strip()
    if not cleaned:
        return None
    return Decimal(cleaned)


def _parse_date(raw: str | None) -> date | None:
    if raw is None or not raw.strip():
        return None
    return date.fromisoformat(raw.strip())


def load_hubspot_csv(
    path: str | Path,
    rule: CommissionRule,
    *,
    tolerance: Decimal = DEFAULT_TOLERANCE,
    strict: bool = True,
) -> LoadResult:
    """Load a HubSpot deal export.

    strict=True (the default) raises CrossCheckError on the first row whose
    recorded commission disagrees with rule(gross) by more than `tolerance`.
    strict=False records the disagreement as a flag instead, for exploratory
    runs; the CLI always runs strict.
    """
    result = LoadResult()
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for line_no, raw in enumerate(reader, start=2):  # line 1 is the header
            if not any((v or "").strip() for v in raw.values()):
                continue  # trailing blank line in the export

            deal_name = (raw.get(COLUMNS["deal_name"]) or "").strip()
            try:
                sales_amount = _parse_money(raw.get(COLUMNS["sales_amount"]))
                commission_amount = _parse_money(raw.get(COLUMNS["commission_amount"]))
                period_start = _parse_date(raw.get(COLUMNS["period_start"]))
            except (InvalidOperation, ValueError) as exc:
                result.flags.append(
                    Flag(
                        code=FlagCode.UNPARSEABLE_ROW,
                        source_row=line_no,
                        question=(
                            f"Row {line_no} ({deal_name or 'unnamed'}) could not be parsed "
                            f"({exc}) and was left out — can you correct the export?"
                        ),
                        detail=f"{deal_name}: {exc}",
                    )
                )
                continue

            missing = [
                label
                for label, value in (
                    ("Sales Amount", sales_amount),
                    ("Period Start", period_start),
                )
                if value is None
            ]
            if missing:
                result.flags.append(
                    Flag(
                        code=FlagCode.UNPARSEABLE_ROW,
                        source_row=line_no,
                        question=(
                            f"Row {line_no} ({deal_name or 'unnamed'}) is missing "
                            f"{' and '.join(missing)} and was left out — what should it be?"
                        ),
                        detail=f"{deal_name}: missing {', '.join(missing)}",
                    )
                )
                continue

            computed = rule.commission(sales_amount)
            if commission_amount is None:
                result.flags.append(
                    Flag(
                        code=FlagCode.MISSING_CROSS_CHECK,
                        source_row=line_no,
                        question=(
                            f"Row {line_no} ({deal_name or 'unnamed'}) has no recorded "
                            f"commission to check our {computed} against — can you confirm it?"
                        ),
                        detail=f"{deal_name}: no Commission Amount",
                    )
                )
            elif abs(computed - commission_amount) > tolerance:
                if strict:
                    raise CrossCheckError(
                        deal_name=deal_name,
                        source_row=line_no,
                        computed=computed,
                        recorded=commission_amount,
                        tolerance=tolerance,
                    )
                result.flags.append(
                    Flag(
                        code=FlagCode.CROSS_CHECK_MISMATCH,
                        source_row=line_no,
                        question=(
                            f"Row {line_no} ({deal_name or 'unnamed'}): we compute "
                            f"{computed} but the export records {commission_amount} — "
                            f"which is right?"
                        ),
                        detail=f"{deal_name}: computed {computed} vs recorded {commission_amount}",
                    )
                )

            invoice_raw = (raw.get(COLUMNS["invoice_refs"]) or "").strip()
            result.deals.append(
                Deal(
                    deal_name=deal_name or f"row {line_no}",
                    company=(raw.get(COLUMNS["company"]) or "").strip() or None,
                    record_id=(raw.get(COLUMNS["record_id"]) or "").strip() or None,
                    close_date=_parse_date(raw.get(COLUMNS["close_date"])),
                    period_start=period_start,
                    period_end=_parse_date(raw.get(COLUMNS["period_end"])),
                    sales_amount=sales_amount,
                    computed_commission=computed,
                    commission_amount=commission_amount,
                    invoice_refs=[p.strip() for p in invoice_raw.split(",") if p.strip()],
                    source_row=line_no,
                )
            )
    return result
