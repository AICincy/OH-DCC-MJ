"""Fixture-recording smoke tests.

The CLI's `--record-fixtures` flag should write the raw HTML to
`storage.fixture_path(source, location, category)`. Tests override the
fixture root via `OHCANNA_FIXTURE_DIR` so the real
`ohcanna/data/fixtures/` directory is never touched.

`requests.get` is mocked so these tests are offline-safe.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from ohcanna.cli import main
from ohcanna.storage import fixture_path

# Minimal HTML that survives the parser: one product-card div with a
# product link, a brand from the registry, a format keyword, and a price.
# The parser-over-fixture vape test in `test_bloom_vape.py` runs against
# a real recording; this one only asserts the *recording* path, so we
# don't care if 0 products parse out.
CANNED_HTML = """\
<html><body>
<div class="product-card">
  <a href="/product/9999+half_gram/test">Test Strain Klutch live resin cart 0.5g</a>
  76 % THC $ 24.85 $ 35.50 30% OFF
</div>
</body></html>
"""


@pytest.fixture
def fake_fixture_root(tmp_path, monkeypatch):
    """Redirect both fixtures and JSON snapshots away from the real repo."""
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    monkeypatch.setenv("OHCANNA_FIXTURE_DIR", str(fixtures))
    monkeypatch.chdir(tmp_path)  # JSON snapshots land in tmp_path/data/...
    return fixtures


@pytest.fixture
def mock_get(monkeypatch):
    """Patch requests.get inside ohcanna.sources.bloom to return CANNED_HTML."""
    resp = MagicMock()
    resp.text = CANNED_HTML
    resp.raise_for_status = MagicMock()
    with patch("ohcanna.sources.bloom.requests.get", return_value=resp) as m:
        # Skip the 2-second rate-limit sleep so the test runs instantly.
        with patch("ohcanna.sources.bloom.time.sleep"):
            yield m


def test_record_fixtures_flag_writes_html(fake_fixture_root, mock_get, capsys):
    rc = main([
        "scrape", "--source", "bloom",
        "--location", "akron", "--category", "vape",
        "--record-fixtures",
    ])
    assert rc == 0
    path = fixture_path("bloom", "akron", "vape")
    assert path.exists(), f"expected fixture at {path}"
    assert path.read_text() == CANNED_HTML
    assert mock_get.call_count == 1


def test_no_record_flag_does_not_write_html(fake_fixture_root, mock_get):
    path = fixture_path("bloom", "akron", "vape")
    assert not path.exists()
    rc = main([
        "scrape", "--source", "bloom",
        "--location", "akron", "--category", "vape",
    ])
    assert rc == 0
    assert not path.exists(), "fixture should not be written without --record-fixtures"


def test_env_var_opts_in(fake_fixture_root, mock_get, monkeypatch):
    monkeypatch.setenv("OHCANNA_RECORD_FIXTURES", "1")
    rc = main([
        "scrape", "--source", "bloom",
        "--location", "akron", "--category", "flower",
    ])
    assert rc == 0
    path = fixture_path("bloom", "akron", "flower")
    assert path.exists()
    assert path.read_text() == CANNED_HTML
