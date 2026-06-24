"""Edible rule tests (ED-001 .. ED-003).

Validated against synthetic product dicts only. The real edible snapshot
is vape-contaminated and the category fields (dose_mg, count_per_package,
total_thc_mg) are 0% populated, so synthetic data is the honest way to
prove the rules fire. This mirrors flower.py's FL-002 synthetic test.
"""
from __future__ import annotations

from ohcanna.analysis.rules import edibles


def _base(**kw) -> dict:
    p = {
        "category": "edibles",
        "name": "Test Gummies",
        "brand": "Test",
        "product_format": "gummies",
        "dose_mg": 10.0,
        "count_per_package": 10,
        "total_thc_mg": 100.0,
        "msrp": 25.0,
    }
    p.update(kw)
    return p


def test_ed001_fires_on_total_mismatch():
    # 10mg x 10 = 100 expected, labeled 130 -> 30% gap > 10%.
    flags = edibles.evaluate_product(_base(total_thc_mg=130.0))
    assert any(f.flag_id == "ED-001" for f in flags)


def test_ed001_silent_when_consistent():
    # 10mg x 10 = 100, labeled 100 -> 0% gap.
    flags = edibles.evaluate_product(_base(total_thc_mg=100.0))
    assert not any(f.flag_id == "ED-001" for f in flags)


def test_ed001_silent_when_field_missing():
    flags = edibles.evaluate_product(_base(total_thc_mg=None))
    assert not any(f.flag_id == "ED-001" for f in flags)


def test_ed002_fires_on_implausible_dose():
    flags = edibles.evaluate_product(_base(dose_mg=250.0, total_thc_mg=2500.0))
    assert any(f.flag_id == "ED-002" for f in flags)


def test_ed002_silent_on_normal_dose():
    flags = edibles.evaluate_product(_base(dose_mg=10.0))
    assert not any(f.flag_id == "ED-002" for f in flags)


def test_ed003_fires_on_price_outlier():
    # Cohort of 3 normal gummies at ~$0.25/mg, plus one priced 3x.
    cohort = [
        _base(total_thc_mg=100.0, msrp=25.0),
        _base(total_thc_mg=100.0, msrp=24.0),
        _base(total_thc_mg=100.0, msrp=26.0),
    ]
    outlier = _base(total_thc_mg=100.0, msrp=80.0)
    dataset = cohort + [outlier]
    analyzed = edibles.analyze_dataset(dataset)
    outlier_out = analyzed[-1]
    assert any(f["flag_id"] == "ED-003" for f in outlier_out["flags"])


def test_ed003_silent_within_cohort():
    cohort = [
        _base(total_thc_mg=100.0, msrp=25.0),
        _base(total_thc_mg=100.0, msrp=24.0),
        _base(total_thc_mg=100.0, msrp=26.0),
    ]
    analyzed = edibles.analyze_dataset(cohort)
    for p in analyzed:
        assert not any(f["flag_id"] == "ED-003" for f in p["flags"])


def test_analyze_dataset_shape():
    out = edibles.analyze_dataset([_base()])
    assert "flags" in out[0] and "flag_count" in out[0]
    assert out[0]["flag_count"] == len(out[0]["flags"])


def test_severity_taxonomy_is_constrained():
    allowed = {"info", "watch", "warn"}
    for rule in edibles.RULES:
        assert rule["severity"] in allowed, rule
