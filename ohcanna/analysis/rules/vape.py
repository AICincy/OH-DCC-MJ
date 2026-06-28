"""Vape-category consistency rules (F-001 .. F-005).

Ported from the POC analyzer.py. Each rule is conservative: a flag is an
observation, not an accusation (P2 §9). The publication layer surfaces
flags so consumers can verify against the COA.
"""
from __future__ import annotations

from dataclasses import asdict
from statistics import median
from typing import Optional

from ohcanna.analysis.cohort import compute_cohort_medians
from ohcanna.brands import legal_entity_for
from ohcanna.models import Flag

# F-006: a non-live-extraction vape running this far below the same brand +
# strain's live-resin/rosin median THC is the comparison the catalog exists
# to surface (a CO2 vape vs the same line's live resin).
F006_RATIO = 0.85

RULES = [
    {
        "id": "F-001",
        "name": "Live-extraction-claim-with-CBD-presence",
        "severity": "watch",
        "trigger": lambda p: (
            "live" in (p.get("product_format") or "").lower()
            and "CBD" in (p.get("secondary_cannabinoids") or [])
        ),
        "explain": (
            "Marketing claims live resin or live rosin extraction, but the "
            "cannabinoid profile shows measurable CBD. Real live-extraction "
            "products from typical high-THC cultivars rarely show CBD on "
            "the label unless the source strain has CBD genetics. Verify "
            "the source cultivar matches the cannabinoid mix."
        ),
    },
    {
        "id": "F-002",
        "name": "Full-spec-but-no-secondary-cannabinoids",
        "severity": "info",
        "trigger": lambda p: (
            "full spec" in (p.get("product_format") or "").lower()
            and not (p.get("secondary_cannabinoids") or [])
        ),
        "explain": (
            "Marketing claims full-spectrum extract, but the cannabinoid "
            "profile shows only THC. Full-spectrum products typically "
            "preserve minor cannabinoids; if only THC is listed, the "
            "spectrum may have been distilled."
        ),
    },
    {
        "id": "F-003",
        "name": "High-THC-with-CBD-in-non-CBD-cultivar",
        "severity": "watch",
        "trigger": lambda p: (
            (p.get("thc_percent") or 0) >= 70.0
            and "CBD" in (p.get("secondary_cannabinoids") or [])
        ),
        "explain": (
            "Cannabinoid profile shows >=70% THC alongside CBD. This is "
            "uncommon in single-source extracts and may indicate "
            "distillate blending with broad-spectrum input."
        ),
    },
    {
        "id": "F-004",
        "name": "Distillate-disposable-with-many-cannabinoids",
        "severity": "info",
        "trigger": lambda p: (
            "distillate" in (p.get("product_format") or "").lower()
            and len(p.get("secondary_cannabinoids") or []) >= 2
        ),
        "explain": (
            "Distillate format showing multiple minor cannabinoids may "
            "indicate distillate plus broad-spectrum blending. Not a "
            "labeling violation, but worth verification on the COA."
        ),
    },
    {
        "id": "F-005",
        "name": "Price-far-above-cohort-median-for-format",
        "severity": "info",
        "trigger": None,  # cohort-dependent, applied separately
        "explain": (
            "MSRP per gram is more than 1.5x the cohort median for this "
            "format. May reflect brand premium rather than production "
            "cost difference."
        ),
    },
    {
        "id": "F-006",
        "name": "Non-live-extraction-below-same-strain-live-resin-THC",
        "severity": "info",
        "trigger": None,  # cohort-dependent, applied separately
        "explain": (
            "A CO2 / full-spectrum / distillate vape testing well below the "
            "same producer and strain's live-resin THC. Extraction methods "
            "legitimately differ in potency, so this is context, not a "
            "labeling concern; compare the COAs side by side."
        ),
    },
]


def _extract_extra(product: dict, key: str):
    """Read a Klutch-style field from `extra`, tolerating a top-level copy."""
    extra = product.get("extra")
    if isinstance(extra, dict) and extra.get(key) is not None:
        return extra.get(key)
    return product.get(key)


def _is_live_extraction(method) -> bool:
    return bool(method) and "live" in str(method).lower()


def _producer_strain_key(product: dict) -> Optional[str]:
    """Group key for F-006: (producer, strain).

    Keyed on the legal entity so sibling brands of one processor compare
    together — Klutch sells the same strain as live resin under "Klutch" and
    as CO2 under "Citizen by Klutch", both AT-CPC of Ohio LLC, and that is
    exactly the pair the catalog exists to surface. Falls back to the brand
    label when no legal entity is registered.
    """
    brand = (product.get("brand") or "").strip()
    producer = (legal_entity_for(brand) or brand).lower()
    strain = (_extract_extra(product, "strain") or "").strip().lower()
    if producer and strain:
        return f"{producer}||{strain}"
    return None


def compute_brand_strain_liveresin_medians(products: list[dict]) -> dict[str, float]:
    """Median THC% per (producer, strain) over live-resin/rosin vapes only.

    These are the reference potencies F-006 compares non-live extractions
    against. Requires an `extraction_method` (in `extra`) to participate, so
    sources that don't carry one (e.g. Bloom) never seed or trip this rule.
    """
    by_key: dict[str, list[float]] = {}
    for p in products:
        if not _is_live_extraction(_extract_extra(p, "extraction_method")):
            continue
        key = _producer_strain_key(p)
        thc = p.get("thc_percent")
        if key and thc is not None:
            by_key.setdefault(key, []).append(thc)
    return {k: median(v) for k, v in by_key.items() if v}


def evaluate_product(product: dict) -> list[Flag]:
    flags = []
    for rule in RULES:
        if rule.get("trigger") and rule["trigger"](product):
            flags.append(
                Flag(
                    flag_id=rule["id"],
                    rule_name=rule["name"],
                    severity=rule["severity"],
                    explanation=rule["explain"],
                )
            )
    return flags


def evaluate_with_cohort(
    product: dict,
    cohort_medians: dict,
    liveresin_medians: Optional[dict] = None,
) -> list[Flag]:
    flags = evaluate_product(product)
    fmt = (product.get("product_format") or "").lower()
    size = product.get("cart_size_grams") or 0
    msrp = product.get("msrp") or 0
    if fmt and size and msrp:
        price_per_g = msrp / size
        median_price = cohort_medians.get(fmt)
        if median_price and price_per_g > median_price * 1.5:
            flags.append(
                Flag(
                    flag_id="F-005",
                    rule_name="Price-far-above-cohort-median-for-format",
                    severity="info",
                    explanation=(
                        f"MSRP ${price_per_g:.2f}/g vs cohort median "
                        f"${median_price:.2f}/g for {fmt}. Premium of "
                        f"{(price_per_g / median_price - 1) * 100:.0f}%."
                    ),
                )
            )

    # F-006: non-live extraction below the same brand+strain live-resin median.
    method = _extract_extra(product, "extraction_method")
    thc = product.get("thc_percent")
    if liveresin_medians and method and not _is_live_extraction(method) and thc is not None:
        key = _producer_strain_key(product)
        ref = liveresin_medians.get(key) if key else None
        if ref and thc < ref * F006_RATIO:
            flags.append(
                Flag(
                    flag_id="F-006",
                    rule_name="Non-live-extraction-below-same-strain-live-resin-THC",
                    severity="info",
                    explanation=(
                        f"{method} THC {thc:.1f}% vs the same producer's "
                        f"live-resin median {ref:.1f}% for this strain — "
                        f"{(1 - thc / ref) * 100:.0f}% lower."
                    ),
                )
            )
    return flags


def analyze_dataset(products: list[dict]) -> list[dict]:
    medians = compute_cohort_medians(products)
    liveresin_medians = compute_brand_strain_liveresin_medians(products)
    results = []
    for p in products:
        flags = evaluate_with_cohort(p, medians, liveresin_medians)
        results.append({
            **p,
            "flags": [asdict(f) for f in flags],
            "flag_count": len(flags),
        })
    return results
