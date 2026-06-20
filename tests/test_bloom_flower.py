"""Bloom flower parser smoke test. Fixture-gated: skips if HTML fixture
hasn't been recorded yet (operator runs `python -m ohcanna scrape
--source bloom --location akron --category flower` to seed it). The
parser is wired through `_PARSERS["flower"]` and exercises the shared
label-split + price-pair helpers, so a green vape test gives us most of
the coverage already."""
from __future__ import annotations

import pytest

from ohcanna.sources.bloom import parse_cards


def test_flower_parser_fixture(fixtures_dir):
    fixture = fixtures_dir / "bloom_akron_flower.html"
    if not fixture.exists():
        pytest.skip("flower fixture not recorded yet; see README §Fixtures")
    products = parse_cards(fixture.read_text(), "akron", "flower")
    records = [p.to_dict() for p in products]
    assert len(records) >= 50
    assert all(r["brand"] for r in records)
    assert all(r["product_format"] for r in records)
    assert all(r["msrp"] is not None for r in records)
    unknown = [r for r in records if r["brand"] == "UNKNOWN"]
    assert not unknown, f"found {len(unknown)} UNKNOWN brands"
