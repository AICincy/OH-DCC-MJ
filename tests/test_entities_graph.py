"""Tests for the entity-aggregation data layer.

Real assertions run against the committed snapshots
``data/latest/bloom_vape.json`` and ``data/latest/bloom_flower.json``.
A synthetic test exercises the UNKNOWN-processor sentinel path.
"""
from __future__ import annotations

import json
from pathlib import Path

from ohcanna.brands import legal_entity_for
from ohcanna.entities.graph import (
    UNKNOWN_PROCESSOR,
    rollup_by_brand,
    rollup_by_processor,
    rollup_by_dispensary,
    slugify,
    build_all_rollups,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
LATEST = REPO_ROOT / "data" / "latest"

KLUTCH_FAMILY = {"Citizen by Klutch", "Cookies", "Josh D", "Klutch", "Habitat by Klutch"}
AT_CPC = "AT-CPC of Ohio LLC"


def _load_real() -> list[dict]:
    products: list[dict] = []
    for name in ("bloom_vape.json", "bloom_flower.json"):
        with open(LATEST / name) as f:
            products.extend(json.load(f))
    return products


def test_processor_groups_klutch_family_under_at_cpc():
    products = _load_real()
    family_count = sum(1 for p in products if p["brand"] in KLUTCH_FAMILY)

    processors = rollup_by_processor(products)

    if family_count == 0:
        return  # no klutch-family brand present; nothing to assert

    assert AT_CPC in processors
    rollup = processors[AT_CPC]
    assert rollup.product_count == family_count
    # Every brand bucketed here really maps to AT-CPC.
    for brand in rollup.brands:
        assert legal_entity_for(brand) == AT_CPC
    assert rollup.canonical_path == "/processor/at-cpc-of-ohio-llc/"


def test_brand_rollup_legal_entity_matches_registry():
    products = _load_real()
    brands = rollup_by_brand(products)

    assert brands  # non-empty
    total = sum(r.product_count for r in brands.values())
    assert total == len(products)
    for brand, rollup in brands.items():
        assert rollup.legal_entity == legal_entity_for(brand)
        assert rollup.canonical_path == f"/brand/{slugify(brand)}/"


def test_dispensary_one_entry_per_location():
    products = _load_real()
    distinct_locations = {p["location"] for p in products}

    dispensaries = rollup_by_dispensary(products)

    assert set(dispensaries) == distinct_locations
    assert len(dispensaries) == len(distinct_locations)
    total = sum(r.product_count for r in dispensaries.values())
    assert total == len(products)


def test_slugify_round_trips():
    assert slugify("AT-CPC of Ohio LLC") == "at-cpc-of-ohio-llc"
    assert slugify("Standard Wellness Holdings LLC") == "standard-wellness-holdings-llc"
    assert slugify("columbus_west") == "columbus-west"
    assert slugify("Eden's Trees") == "eden-s-trees"


def test_build_all_rollups_keys():
    products = _load_real()
    rollups = build_all_rollups(products)
    assert set(rollups) == {"brands", "processors", "dispensaries"}


def test_unknown_processor_sentinel_and_flags():
    synthetic = [
        {
            "brand": "Totally Made Up Brand",
            "category": "vape",
            "location": "nowhere",
            "msrp": 40.0,
            "thc_percent": 80.0,
            "scraped_at": "2026-06-24T00:00:00Z",
            "flags": [{"rule_name": "price_outlier", "flag_id": "f1"}],
        },
        {
            "brand": "Klutch",
            "category": "flower",
            "location": "akron",
            "msrp": 30.0,
            "thc_percent": 25.0,
            "scraped_at": "2026-06-24T00:00:00Z",
        },
    ]
    processors = rollup_by_processor(synthetic)

    assert UNKNOWN_PROCESSOR in processors
    unknown = processors[UNKNOWN_PROCESSOR]
    assert unknown.product_count == 1
    assert unknown.brands == {"Totally Made Up Brand"}
    assert unknown.flag_distribution == {"price_outlier": 1}

    assert AT_CPC in processors
    assert processors[AT_CPC].product_count == 1

    # Brand rollup surfaces the same flag distribution.
    brands = rollup_by_brand(synthetic)
    assert brands["Totally Made Up Brand"].flag_distribution == {"price_outlier": 1}
    assert brands["Totally Made Up Brand"].legal_entity is None
