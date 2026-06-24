"""Flower rule tests (FL-001, FL-002) and the category-dispatch engine.

FL-001 is validated against the committed flower snapshot (real Bloom
data: 420 products, 56 cultivar cohorts with >=3 batches). FL-002's
absolute ceiling sits above anything in the current data — Bloom's
Akron flower THC tops out at 34% — so it's exercised with a synthetic
product, which is the honest way to prove the guard works.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ohcanna.analysis import engine
from ohcanna.analysis.rules import flower

FLOWER_SNAPSHOT = Path(__file__).parent.parent / "data" / "latest" / "bloom_flower.json"


@pytest.fixture
def flower_products() -> list[dict]:
    if not FLOWER_SNAPSHOT.exists():
        pytest.skip(f"flower snapshot not present at {FLOWER_SNAPSHOT}")
    return json.load(open(FLOWER_SNAPSHOT))


def test_fl001_fires_on_real_cohort_outliers(flower_products):
    analyzed = flower.analyze_dataset(flower_products)
    fl001 = [
        p for p in analyzed
        if any(f["flag_id"] == "FL-001" for f in p["flags"])
    ]
    # Calibrated against the committed snapshot: 5 batches run >15% above
    # their cultivar-cohort median. Allow a small band for snapshot drift.
    assert 1 <= len(fl001) <= 25, f"FL-001 fired on {len(fl001)} products"
    # Every FL-001 hit must genuinely exceed its cohort median.
    cohorts = flower.compute_cultivar_cohorts(flower_products)
    for p in fl001:
        med = cohorts[flower.cultivar_key(p)]
        assert p["thc_percent"] > med * flower.COHORT_RATIO


def test_fl002_fires_on_implausible_thc():
    synthetic = {
        "category": "flower",
        "name": "Test Cultivar",
        "thc_percent": 38.0,
        "brand": "Test",
        "product_format": "whole buds",
        "msrp": 40.0,
    }
    flags = flower.evaluate_product(synthetic)
    assert any(f.flag_id == "FL-002" for f in flags)


def test_fl002_silent_on_plausible_thc(flower_products):
    """No product in the real Akron snapshot trips the 35% ceiling."""
    analyzed = flower.analyze_dataset(flower_products)
    fl002 = [p for p in analyzed if any(f["flag_id"] == "FL-002" for f in p["flags"])]
    assert fl002 == []


def test_severity_taxonomy_is_constrained():
    allowed = {"info", "watch", "warn"}
    for rule in flower.RULES:
        assert rule["severity"] in allowed, rule


def test_engine_routes_by_category(flower_products):
    """The engine sends flower products to flower rules and leaves
    unhandled categories flag-free, preserving input order."""
    vape_like = {"category": "vape", "product_format": "live resin cart",
                 "secondary_cannabinoids": ["CBD"], "thc_percent": 80.0}
    topical = {"category": "topicals", "name": "Balm", "thc_percent": None}
    mixed = [flower_products[0], vape_like, topical]
    out = engine.analyze_dataset(mixed)

    assert len(out) == 3
    # order preserved
    assert out[0]["category"] == "flower"
    assert out[1]["category"] == "vape"
    assert out[2]["category"] == "topicals"
    # vape rule F-001 (live + CBD) fired via dispatch
    assert any(f["flag_id"] == "F-001" for f in out[1]["flags"])
    # unhandled category passes through with no flags
    assert out[2]["flags"] == []
    assert out[2]["flag_count"] == 0
