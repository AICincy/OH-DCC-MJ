"""CLI smoke tests. --dry-run prints the matrix without touching the network."""
from __future__ import annotations

from ohcanna.cli import main


def test_scrape_dry_run_lists_full_matrix(capsys):
    rc = main(["scrape", "--source", "bloom", "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "matrix: 7 locations x 7 categories = 49 sub-scrapes" in out
    assert "- akron / vape" in out
    assert "- seven_mile / topicals" in out


def test_scrape_dry_run_narrowed(capsys):
    rc = main(["scrape", "--source", "bloom", "--dry-run",
               "--location", "akron", "--category", "vape"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "matrix: 1 locations x 1 categories = 1 sub-scrapes" in out


def test_build_is_stub(capsys):
    rc = main(["build"])
    assert rc == 0
    assert "not in this phase" in capsys.readouterr().out
