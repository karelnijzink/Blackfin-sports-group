"""CLI argument validation and failure modes."""

import pytest

from commission_engine.cli import main


def test_horizon_zero_is_rejected(blast_media_csv, tmp_path):
    with pytest.raises(SystemExit) as excinfo:
        main(
            [
                "run",
                "--client",
                "blast_media",
                "--csv",
                str(blast_media_csv),
                "--horizon",
                "0",
                "--out",
                str(tmp_path),
            ]
        )
    assert excinfo.value.code == 2  # argparse usage error
    assert not (tmp_path / "blast_media_reconciliation.md").exists()


def test_horizon_negative_is_rejected(blast_media_csv, tmp_path):
    with pytest.raises(SystemExit):
        main(
            [
                "run",
                "--client",
                "blast_media",
                "--csv",
                str(blast_media_csv),
                "--horizon",
                "-5",
                "--out",
                str(tmp_path),
            ]
        )
    assert not (tmp_path / "blast_media_reconciliation.md").exists()


def test_cross_check_failure_exits_nonzero_with_no_report(tmp_path, blast_media_csv, capsys):
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

    out_dir = tmp_path / "out"
    exit_code = main(
        [
            "run",
            "--client",
            "blast_media",
            "--csv",
            str(corrupt),
            "--out",
            str(out_dir),
        ]
    )
    assert exit_code == 1
    assert not out_dir.exists()
    assert "Cross-check failed" in capsys.readouterr().err
