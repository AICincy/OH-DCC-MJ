"""Pre-roll rule tests (PR-001, PR-002).

Synthetic data only: the real pre-roll snapshot is vape-contaminated and
weight_grams is 0% populated. Mirrors flower.py's FL-002 synthetic
precedent.
"""
from __future__ import annotations

from ohcanna.analysis.rules import prerolls


def _base(**kw) -> dict:
    p = {
        "category": "prerolls",
        "name": "Test Pre-Roll",
        "brand": "Test",
        "product_format": "preroll",
        "weight_grams": 1.0,
        "count_per_package": 1,
        "msrp": 12.0,
    }
    p.update(kw)
    return p


def test_pr001_fires_on_missing_weight():
    flags = prerolls.evaluate_product(_base(weight_grams=None))
    assert any(f.flag_id == "PR-001" for f in flags)


def test_pr001_fires_on_zero_weight():
    flags = prerolls.evaluate_product(_base(weight_grams=0))
    assert any(f.flag_id == "PR-001" for f in flags)


def test_pr001_silent_when_weight_present():
    flags = prerolls.evaluate_product(_base(weight_grams=1.0))
    assert not any(f.flag_id == "PR-001" for f in flags)


def test_pr002_fires_on_price_outlier():
    cohort = [
        _base(weight_grams=1.0, count_per_package=1, msrp=12.0),
        _base(weight_grams=1.0, count_per_package=1, msrp=11.0),
        _base(weight_grams=1.0, count_per_package=1, msrp=13.0),
    ]
    outlier = _base(weight_grams=1.0, count_per_package=1, msrp=40.0)
    analyzed = prerolls.analyze_dataset(cohort + [outlier])
    assert any(f["flag_id"] == "PR-002" for f in analyzed[-1]["flags"])


def test_pr002_silent_within_cohort():
    cohort = [
        _base(weight_grams=1.0, count_per_package=1, msrp=12.0),
        _base(weight_grams=1.0, count_per_package=1, msrp=11.0),
        _base(weight_grams=1.0, count_per_package=1, msrp=13.0),
    ]
    analyzed = prerolls.analyze_dataset(cohort)
    for p in analyzed:
        assert not any(f["flag_id"] == "PR-002" for f in p["flags"])


def test_analyze_dataset_shape():
    out = prerolls.analyze_dataset([_base()])
    assert "flags" in out[0] and "flag_count" in out[0]
    assert out[0]["flag_count"] == len(out[0]["flags"])


def test_severity_taxonomy_is_constrained():
    allowed = {"info", "watch", "warn"}
    for rule in prerolls.RULES:
        assert rule["severity"] in allowed, rule
