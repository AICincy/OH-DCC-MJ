"""Tincture rule tests (TN-001, TN-002).

Synthetic data only: the real tincture snapshot is vape-contaminated and
cbd_thc_ratio is 0% populated. Mirrors flower.py's FL-002 synthetic
precedent.
"""
from __future__ import annotations

from ohcanna.analysis.rules import tinctures


def _base(**kw) -> dict:
    p = {
        "category": "tinctures",
        "name": "Test Tincture",
        "brand": "Test",
        "product_format": "tincture",
        "volume_ml": 30.0,
        "total_thc_mg": 100.0,
        "cbd_thc_ratio": "1:1",
        "msrp": 40.0,
    }
    p.update(kw)
    return p


def test_tn001_fires_on_cbd_dominant_with_high_thc():
    # 20:1 CBD-dominant claim, but 600mg THC / 30ml = 20mg/ml -> high.
    flags = tinctures.evaluate_product(
        _base(cbd_thc_ratio="20:1", total_thc_mg=600.0, volume_ml=30.0)
    )
    assert any(f.flag_id == "TN-001" for f in flags)


def test_tn001_silent_when_thc_concentration_low():
    # 20:1 claim with 30mg / 30ml = 1mg/ml -> consistent with CBD-leaning.
    flags = tinctures.evaluate_product(
        _base(cbd_thc_ratio="20:1", total_thc_mg=30.0, volume_ml=30.0)
    )
    assert not any(f.flag_id == "TN-001" for f in flags)


def test_tn001_silent_when_ratio_not_cbd_dominant():
    # 1:1 is balanced, not CBD-dominant -> rule does not apply.
    flags = tinctures.evaluate_product(
        _base(cbd_thc_ratio="1:1", total_thc_mg=600.0, volume_ml=30.0)
    )
    assert not any(f.flag_id == "TN-001" for f in flags)


def test_tn001_silent_when_ratio_missing():
    flags = tinctures.evaluate_product(
        _base(cbd_thc_ratio=None, total_thc_mg=600.0, volume_ml=30.0)
    )
    assert not any(f.flag_id == "TN-001" for f in flags)


def test_parse_ratio_handles_garbage():
    assert tinctures.parse_ratio("not a ratio") is None
    assert tinctures.parse_ratio(None) is None
    assert tinctures.parse_ratio("20:1") == (20.0, 1.0)


def test_tn002_fires_on_price_outlier():
    cohort = [
        _base(total_thc_mg=100.0, msrp=40.0),
        _base(total_thc_mg=100.0, msrp=38.0),
        _base(total_thc_mg=100.0, msrp=42.0),
    ]
    outlier = _base(total_thc_mg=100.0, msrp=120.0)
    analyzed = tinctures.analyze_dataset(cohort + [outlier])
    assert any(f["flag_id"] == "TN-002" for f in analyzed[-1]["flags"])


def test_tn002_silent_within_cohort():
    cohort = [
        _base(total_thc_mg=100.0, msrp=40.0),
        _base(total_thc_mg=100.0, msrp=38.0),
        _base(total_thc_mg=100.0, msrp=42.0),
    ]
    analyzed = tinctures.analyze_dataset(cohort)
    for p in analyzed:
        assert not any(f["flag_id"] == "TN-002" for f in p["flags"])


def test_analyze_dataset_shape():
    out = tinctures.analyze_dataset([_base()])
    assert "flags" in out[0] and "flag_count" in out[0]
    assert out[0]["flag_count"] == len(out[0]["flags"])


def test_severity_taxonomy_is_constrained():
    allowed = {"info", "watch", "warn"}
    for rule in tinctures.RULES:
        assert rule["severity"] in allowed, rule
