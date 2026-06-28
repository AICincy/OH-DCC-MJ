"""F-006 (Klutch extraction-method mismatch) analysis tests.

F-006 flags a non-live extraction (CO2 / full-spectrum / distillate) vape
whose THC runs below 0.85x the same PRODUCER's live-resin/rosin median THC
for the same strain. The producer key groups sibling brands of one processor
(Klutch + Citizen by Klutch, both AT-CPC of Ohio LLC), which is exactly the
comparison the catalog exists to surface. SYNTHETIC product dicts only.
"""
from __future__ import annotations

from ohcanna.analysis.engine import analyze_dataset
from ohcanna.analysis.rules.vape import RULES


def _vape(brand, strain, method, thc, *, extra_method=True):
    """A vape product dict as it lands in a snapshot (extra carries Klutch
    fields). `extra_method=False` simulates a source (e.g. Bloom) that does
    not capture an extraction method."""
    extra = {"strain": strain}
    if extra_method:
        extra["extraction_method"] = method
    return {
        "source": "klutch", "category": "vape", "brand": brand,
        "name": strain, "product_format": f"{method} Cartridge",
        "thc_percent": thc, "cart_size_grams": 1.0, "msrp": 45,
        "extra": extra,
    }


def _flag_ids(record):
    return {f["flag_id"] for f in record["flags"]}


def test_f006_fires_on_co2_below_sibling_live_resin():
    products = [
        _vape("Klutch", "Jealousy", "Live Resin", 83.78),
        _vape("Citizen by Klutch", "Jealousy", "CO2", 68.8),  # 0.82x -> fires
    ]
    flagged = analyze_dataset(products)
    by_brand = {p["brand"]: p for p in flagged}
    assert "F-006" in _flag_ids(by_brand["Citizen by Klutch"])
    # The live-resin reference product itself is never flagged by F-006.
    assert "F-006" not in _flag_ids(by_brand["Klutch"])


def test_f006_silent_when_within_threshold():
    products = [
        _vape("Klutch", "Gelato", "Live Resin", 80.0),
        _vape("Klutch", "Gelato", "CO2", 72.0),  # 0.90x -> above 0.85, silent
    ]
    flagged = analyze_dataset(products)
    co2 = next(p for p in flagged if p["product_format"].startswith("CO2"))
    assert "F-006" not in _flag_ids(co2)


def test_f006_silent_without_extraction_method():
    # Bloom-style vapes with no extraction_method in extra must never seed or
    # trip F-006, even with a large THC gap for the same name.
    products = [
        _vape("SomeBrand", "Mintz", "Live Resin", 85.0, extra_method=False),
        _vape("SomeBrand", "Mintz", "CO2", 60.0, extra_method=False),
    ]
    flagged = analyze_dataset(products)
    assert all("F-006" not in _flag_ids(p) for p in flagged)


def test_f006_requires_same_strain_reference():
    # Different strains never compare, even within one producer.
    products = [
        _vape("Klutch", "StrainA", "Live Resin", 85.0),
        _vape("Citizen by Klutch", "StrainB", "CO2", 60.0),
    ]
    flagged = analyze_dataset(products)
    assert all("F-006" not in _flag_ids(p) for p in flagged)


def test_all_vape_rule_severities_valid():
    for rule in RULES:
        assert rule["severity"] in {"info", "watch", "warn"}, rule
