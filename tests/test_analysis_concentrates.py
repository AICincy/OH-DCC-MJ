"""Concentrate rule tests (CN-001, CN-002).

Synthetic data only: the real concentrate snapshot is vape-contaminated
and extraction_method is 0% populated. Mirrors flower.py's FL-002
synthetic precedent.
"""
from __future__ import annotations

from ohcanna.analysis.rules import concentrates


def _base(**kw) -> dict:
    p = {
        "category": "concentrates",
        "name": "Test Rosin",
        "brand": "Test",
        "product_format": "rosin",
        "weight_grams": 1.0,
        "extraction_method": "solventless press",
        "msrp": 50.0,
    }
    p.update(kw)
    return p


def test_cn001_fires_on_solventless_claim_with_solvent_method():
    flags = concentrates.evaluate_product(
        _base(name="Live Rosin", product_format="rosin", extraction_method="BHO")
    )
    assert any(f.flag_id == "CN-001" for f in flags)


def test_cn001_silent_when_method_matches_claim():
    flags = concentrates.evaluate_product(
        _base(name="Live Rosin", extraction_method="solventless press")
    )
    assert not any(f.flag_id == "CN-001" for f in flags)


def test_cn001_silent_when_no_solventless_claim():
    # Distillate product disclosing CO2 -- consistent, no claim mismatch.
    flags = concentrates.evaluate_product(
        _base(name="Distillate Cart", product_format="distillate", extraction_method="CO2")
    )
    assert not any(f.flag_id == "CN-001" for f in flags)


def test_cn002_fires_on_price_outlier():
    cohort = [
        _base(weight_grams=1.0, msrp=50.0),
        _base(weight_grams=1.0, msrp=48.0),
        _base(weight_grams=1.0, msrp=52.0),
    ]
    outlier = _base(weight_grams=1.0, msrp=150.0)
    analyzed = concentrates.analyze_dataset(cohort + [outlier])
    assert any(f["flag_id"] == "CN-002" for f in analyzed[-1]["flags"])


def test_cn002_silent_within_cohort():
    cohort = [
        _base(weight_grams=1.0, msrp=50.0),
        _base(weight_grams=1.0, msrp=48.0),
        _base(weight_grams=1.0, msrp=52.0),
    ]
    analyzed = concentrates.analyze_dataset(cohort)
    for p in analyzed:
        assert not any(f["flag_id"] == "CN-002" for f in p["flags"])


def test_analyze_dataset_shape():
    out = concentrates.analyze_dataset([_base()])
    assert "flags" in out[0] and "flag_count" in out[0]
    assert out[0]["flag_count"] == len(out[0]["flags"])


def test_severity_taxonomy_is_constrained():
    allowed = {"info", "watch", "warn"}
    for rule in concentrates.RULES:
        assert rule["severity"] in allowed, rule
