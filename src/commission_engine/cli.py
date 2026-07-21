"""Command-line surface: `forecast run --client blast_media --csv path`.

Reads the client's entry in clients.yaml, loads the export, runs every
projection method, and writes the reconciliation as markdown and HTML.
Read-only throughout: the only thing written is the report.
"""

import argparse
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

from commission_engine.forecast.engine import run_forecast
from commission_engine.ledger.csv_source import load_hubspot_csv
from commission_engine.ledger.schema import CrossCheckError
from commission_engine.reconcile.render import render_html, render_markdown
from commission_engine.reconcile.report import ReconciliationReport, build_report
from commission_engine.rules.registry import build_rule, get_client


def _positive_int(raw: str) -> int:
    value = int(raw)
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be a positive number of months, got {raw}")
    return value


def _parse_target(raw: str) -> tuple[Decimal, Decimal]:
    try:
        low, high = raw.split(":")
        low, high = Decimal(low), Decimal(high)
    except (ValueError, ArithmeticError):
        raise argparse.ArgumentTypeError(
            f"target must look like 97000:105000, got {raw!r}"
        ) from None
    if low > high:
        raise argparse.ArgumentTypeError(f"target low must not exceed high, got {raw!r}")
    return low, high


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="forecast",
        description="Deterministic commission forecast with reconciliation.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run the forecast for one client")
    run.add_argument("--client", required=True, help="client id from clients.yaml")
    run.add_argument("--csv", required=True, type=Path, help="path to the deal export CSV")
    run.add_argument(
        "--target",
        type=_parse_target,
        default=None,
        help="expected 12-mo range LOW:HIGH; defaults to the client's clients.yaml entry",
    )
    run.add_argument(
        "--as-of",
        type=date.fromisoformat,
        default=None,
        help="reference date for gap/partial-month flags (default: today)",
    )
    run.add_argument(
        "--horizon", type=_positive_int, default=12, help="months to project (default 12)"
    )
    run.add_argument("--out", type=Path, default=Path("out"), help="output directory")
    run.add_argument(
        "--clients-file", type=Path, default=None, help="path to clients.yaml (default: repo root)"
    )
    return parser


def _print_summary(report: ReconciliationReport) -> None:
    print(f"{report.client_name} — commission forecast reconciliation")
    print(f"As of {report.as_of:%d %b %Y}")
    print()
    presented = report.presented
    print(f"  Presented: {presented.label} -> ${presented.total:,.2f} over {report.horizon} months")
    if report.target_low is not None and report.target_high is not None:
        print(f"  Client's expected range: ${report.target_low:,.2f} - ${report.target_high:,.2f}")
        variance = report.headline_variance_pct
        if report.headline_in_range:
            print("  Inside the expected range.")
        else:
            side = "below the range floor" if variance < 0 else "above the range ceiling"
            print(f"  Variance: {variance:+.1f}% {side}")
    print()
    print(f"  {'Method':<32}{'12-mo total':>14}  in range")
    for row in report.methods:
        if row.error is not None:
            print(f"  {row.label:<32}{'—':>14}  could not run: {row.error}")
            continue
        in_range = "—"
        if row.in_range is not None:
            in_range = "yes" if row.in_range else "no"
        mark = "  <- presented" if row.presented else ""
        print(f"  {row.label:<32}{f'${row.total:,.2f}':>14}  {in_range}{mark}")
    print()
    if report.flags:
        print("  Confirm with client:")
        for flag in report.flags:
            print(f"  - {flag.question}")
    else:
        print("  No flags raised by this run.")
    print()


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    client = get_client(args.client, args.clients_file)
    rule = build_rule(client.rule)

    try:
        loaded = load_hubspot_csv(args.csv, rule)
    except CrossCheckError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print(
            "The export and the configured rule disagree; no forecast was produced. "
            "Check the rule in clients.yaml or the export row above.",
            file=sys.stderr,
        )
        return 1

    as_of = args.as_of or date.today()
    result = run_forecast(loaded, as_of=as_of, horizon=args.horizon)

    target_low, target_high = (
        args.target if args.target is not None else (client.target_low, client.target_high)
    )
    report = build_report(
        client_name=client.display_name,
        result=result,
        target_low=target_low,
        target_high=target_high,
        presented_method=client.presented_method,
        presented_rationale=client.presented_rationale,
        rule_description=rule.describe(),
    )

    args.out.mkdir(parents=True, exist_ok=True)
    md_path = args.out / f"{args.client}_reconciliation.md"
    html_path = args.out / f"{args.client}_reconciliation.html"
    md_path.write_text(render_markdown(report))
    html_path.write_text(render_html(report))

    _print_summary(report)
    print(f"  Wrote {md_path}")
    print(f"  Wrote {html_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
