"""Bloom vape parser smoke tests.

If a recorded HTML fixture exists at
`ohcanna/data/fixtures/bloom_akron_vape.html` (record from a workstation
via `python -m ohcanna scrape --source bloom --location akron --category
vape --record-fixtures`), the parser runs over real HTML and the full
P2 §4 acceptance bar applies. Otherwise the parser-over-real-HTML test
skips and we still gate the brand-registry mapping below.
"""
from __future__ import annotations

import pytest

from ohcanna.sources.bloom import parse_cards
from ohcanna.storage import fixture_path


def _assert_vape_invariants(records: list[dict]) -> None:
    assert len(records) >= 50, f"expected >=50 vape products, got {len(records)}"
    assert all(r["brand"] for r in records)
    assert all(r["product_format"] for r in records)
    assert all(r["msrp"] is not None for r in records)
    assert all(r["scraped_at"] for r in records)
    unknown = [r for r in records if r["brand"] == "UNKNOWN"]
    assert not unknown, f"found {len(unknown)} UNKNOWN brands"
    with_thc = [r for r in records if r["thc_percent"] is not None]
    assert len(with_thc) / len(records) >= 0.95, "<95% THC coverage"


def test_vape_parser_against_recorded_fixture():
    path = fixture_path("bloom", "akron", "vape")
    if not path.exists():
        pytest.skip(
            f"fixture not recorded yet at {path}; see README §Fixtures"
        )
    products = parse_cards(path.read_text(), "akron", "vape")
    records = [p.to_dict() for p in products]
    _assert_vape_invariants(records)


def test_brand_registry_resolves_klutch_family():
    """Verified consolidation per P2 §3 / P4 §5: Citizen, Cookies, Josh D,
    Habitat by Klutch, and Klutch all map to AT-CPC of Ohio LLC."""
    from ohcanna.brands import legal_entity_for

    for brand in ("Citizen by Klutch", "Cookies", "Josh D",
                  "Habitat by Klutch", "Klutch"):
        assert legal_entity_for(brand) == "AT-CPC of Ohio LLC", (
            f"{brand} should map to AT-CPC of Ohio LLC"
        )
    assert legal_entity_for("Woodward Fine Cannabis") == "Woodward Fine Cannabis"
    for brand in ("The Standard", "The Solid"):
        assert legal_entity_for(brand) == "Standard Wellness Holdings LLC"
