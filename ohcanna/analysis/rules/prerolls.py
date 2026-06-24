"""Pre-roll-category consistency rules (PR-001, PR-002).

P2 §5 T10: "weight accuracy." Two rules:

  PR-001  weight_grams is missing or zero. A pre-roll listing without a
          disclosed weight can't be checked for weight accuracy or
          compared on price per gram; flag the gap so it's visible.
  PR-002  Within a format cohort (same product_format, >=3 priced
          samples), price-per-gram runs more than 1.5x the cohort
          median. May reflect brand premium rather than production cost.

Conservative by design (P2 §D7): a flag is an observation, not an
accusation. Severity tiers strictly info | watch | warn.
"""
from __future__ import annotations

from dataclasses import asdict
from statistics import median

from ohcanna.models import Flag

COHORT_RATIO = 1.5

RULES = [
    {
        "id": "PR-001",
        "name": "Missing-or-zero-weight",
        "severity": "info",
        "trigger": lambda p: not (p.get("weight_grams") or 0),
        "explain": (
            "No pack weight is disclosed for this pre-roll. Without a "
            "weight, weight accuracy and price-per-gram can't be checked. "
            "Verify the gram figure on the package or COA."
        ),
    },
    {
        "id": "PR-002",
        "name": "Price-per-gram-above-cohort-median-for-format",
        "severity": "info",
        "trigger": None,  # cohort-dependent, applied separately
        "explain": (
            "MSRP per gram is more than 1.5x the cohort median for this "
            "format. May reflect brand premium rather than production "
            "cost difference."
        ),
    },
]


def format_key(product: dict) -> str:
    return (product.get("product_format") or "").strip().lower()


def _total_weight(product: dict) -> float:
    """Pack weight: per-unit weight times count if both present, else the
    bare weight_grams (treated as the pack total)."""
    weight = product.get("weight_grams") or 0
    count = product.get("count_per_package") or 0
    if weight and count:
        return weight * count
    return weight


def compute_cohort_medians(products: list[dict]) -> dict[str, float]:
    """Median $/g per product format, for formats with >=3 priced samples.

    Mirrors the vape cohort threshold (P2 known-issue I3: <3 samples is
    noise).
    """
    by_format: dict[str, list[float]] = {}
    for p in products:
        fmt = format_key(p)
        weight = _total_weight(p)
        msrp = p.get("msrp") or 0
        if fmt and weight and msrp:
            by_format.setdefault(fmt, []).append(msrp / weight)
    return {fmt: median(vals) for fmt, vals in by_format.items() if len(vals) >= 3}


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
    fmt = format_key(product)
    weight = _total_weight(product)
    msrp = product.get("msrp") or 0
    if fmt and weight and msrp:
        price_per_g = msrp / weight
        med = cohort_medians.get(fmt)
        if med and price_per_g > med * COHORT_RATIO:
            flags.append(
                Flag(
                    flag_id="PR-002",
                    rule_name="Price-per-gram-above-cohort-median-for-format",
                    severity="info",
                    explanation=(
                        f"MSRP ${price_per_g:.2f}/g vs cohort median "
                        f"${med:.2f}/g for {fmt}. Premium of "
                        f"{(price_per_g / med - 1) * 100:.0f}%."
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
