"""Vape-category consistency rules (F-001 .. F-005).

Ported from the POC analyzer.py. Each rule is conservative: a flag is an
observation, not an accusation (P2 §9). The publication layer surfaces
flags so consumers can verify against the COA.
"""
from __future__ import annotations

from dataclasses import asdict

from ohcanna.analysis.cohort import compute_cohort_medians
from ohcanna.models import Flag

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
]


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


def evaluate_with_cohort(product: dict, cohort_medians: dict) -> list[Flag]:
    flags = evaluate_product(product)
    fmt = (product.get("product_format") or "").lower()
    size = product.get("cart_size_grams") or 0
    msrp = product.get("msrp") or 0
    if fmt and size and msrp:
        price_per_g = msrp / size
        median = cohort_medians.get(fmt)
        if median and price_per_g > median * 1.5:
            flags.append(
                Flag(
                    flag_id="F-005",
                    rule_name="Price-far-above-cohort-median-for-format",
                    severity="info",
                    explanation=(
                        f"MSRP ${price_per_g:.2f}/g vs cohort median "
                        f"${median:.2f}/g for {fmt}. Premium of "
                        f"{(price_per_g / median - 1) * 100:.0f}%."
                    ),
                )
            )
    return flags


def analyze_dataset(products: list[dict]) -> list[dict]:
    medians = compute_cohort_medians(products)
    results = []
    for p in products:
        flags = evaluate_with_cohort(p, medians)
        results.append({
            **p,
            "flags": [asdict(f) for f in flags],
            "flag_count": len(flags),
        })
    return results
