"""Desktop launcher: the headless core the packaged app runs on."""

import shutil

import pytest

from commission_engine.app import main
from commission_engine.ledger.schema import CrossCheckError


def test_headless_run_writes_report_beside_the_export(tmp_path, blast_media_csv, capsys):
    export = tmp_path / "Blast_Media_Commission_Deals_Import.csv"
    shutil.copy(blast_media_csv, export)

    exit_code = main([str(export), "2026-07-21"])
    assert exit_code == 0

    html = tmp_path / "Forecast Reports" / "blast_media_reconciliation.html"
    assert html.exists()
    content = html.read_text()
    assert "96,482" in content  # golden presented total
    assert "June 2026" in content and "September 2025" in content
    # the app prints the report path so smoke tests can find it
    assert str(html) in capsys.readouterr().out


def test_headless_run_propagates_cross_check_refusal(tmp_path, blast_media_csv):
    import csv

    from test_loader import HEADER

    with open(blast_media_csv, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    rows[0]["Commission Amount"] = "999999"
    corrupt = tmp_path / "corrupt.csv"
    with open(corrupt, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=HEADER)
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(CrossCheckError):
        main([str(corrupt)])
    assert not (tmp_path / "Forecast Reports").exists()
