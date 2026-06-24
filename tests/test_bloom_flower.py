"""Bloom flower parser smoke test. Fixture-gated: skips if HTML fixture
hasn't been recorded yet. Flower products don't always carry a THC%
reading on the card, so we relax that floor relative to vape but keep
the brand/format/price coverage bar."""
from __future__ import annotations

import pytest

from ohcanna.sources.bloom import parse_cards
from ohcanna.storage import fixture_path


def test_flower_parser_against_recorded_fixture():
    path = fixture_path("bloom", "akron", "flower")
    if not path.exists():
        pytest.skip(
            f"fixture not recorded yet at {path}; see README §Fixtures"
        )
    products = parse_cards(path.read_text(), "akron", "flower")
    records = [p.to_dict() for p in products]
    assert len(records) >= 50
    assert all(r["brand"] for r in records)
    assert all(r["product_format"] for r in records)
    assert all(r["msrp"] is not None for r in records)
    unknown = [r for r in records if r["brand"] == "UNKNOWN"]
    assert not unknown, f"found {len(unknown)} UNKNOWN brands"
