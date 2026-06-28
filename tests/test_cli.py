"""CLI smoke tests. --dry-run prints the matrix without touching the network."""
from __future__ import annotations

from ohcanna import cli
from ohcanna.cli import main
from ohcanna.sources.klutch import KlutchSource


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


def test_scrape_dry_run_klutch(capsys):
    rc = main(["scrape", "--source", "klutch", "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    # one statewide "catalog" location x the six mapped categories
    assert "matrix: 1 locations x 6 categories = 6 sub-scrapes" in out
    assert "- catalog / vape" in out


def test_scrape_delay_propagates_to_source(monkeypatch):
    """--delay must be set on a source that supports it before scraping."""
    seen = {}

    class FakeKlutch(KlutchSource):
        def scrape_all(self, *args, **kwargs):
            seen["delay"] = self.delay
            return iter(())

    monkeypatch.setitem(cli.REGISTRY, "klutch", FakeKlutch)
    rc = main(["scrape", "--source", "klutch", "--category", "vape", "--delay", "0.5"])
    assert rc == 0
    assert seen["delay"] == 0.5


def test_build_renders_site(capsys, tmp_path):
    out = tmp_path / "site"
    rc = main(["build", "--out-dir", str(out), "--data-root", "data"])
    assert rc == 0
    assert "built" in capsys.readouterr().out
    assert (out / "sitemap.xml").exists()
    assert (out / "index.html").exists()


def test_community_lists_queue(capsys, tmp_path):
    # Empty data root -> empty queue, exits cleanly.
    rc = main(["community", "--data-root", str(tmp_path)])
    assert rc == 0
    assert "submission(s)" in capsys.readouterr().out
