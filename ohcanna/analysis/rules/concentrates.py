"""Concentrate-category consistency rules (CN-001, CN-002).

P2 §5 T9: "solventless claim vs solvent disclosure." Two rules:

  CN-001  Name or format claims a solventless process (rosin, hash,
          "solventless") but the disclosed extraction_method names a
          solvent (BHO, CO2, distillate, etc.). A solventless claim
          paired with a solvent disclosure is a possible mismatch worth
          verifying against the COA.
  CN-002  Within a format cohort (same product_format, >=3 priced
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

# Terms in a product name/format that claim a solventless process, and
# extraction methods that involve a solvent. Both compared lowercased.
SOLVENTLESS_TERMS = ("rosin", "hash", "solventless", "ice water", "bubble")
SOLVENT_METHODS = ("bho", "butane", "co2", "co₂", "distillate", "propane", "ethanol", "hydrocarbon")

RULES = [
    {
        "id": "CN-001",
        "name": "Solventless-claim-with-solvent-extraction",
        "severity": "watch",
        "trigger": lambda p: _claims_solventless(p) and _method_is_solvent(p),
        "explain": (
            "Product name or format suggests a solventless process "
            "(rosin/hash/solventless) but the disclosed extraction method "
            "names a solvent. Verify the process against the COA and "
            "manufacturer disclosure."
        ),
    },
    {
        "id": "CN-002",
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


def _claims_solventless(product: dict) -> bool:
    text = f"{product.get('name') or ''} {product.get('product_format') or ''}".lower()
    return any(term in text for term in SOLVENTLESS_TERMS)


def _method_is_solvent(product: dict) -> bool:
    method = (product.get("extraction_method") or "").lower()
    return any(s in method for s in SOLVENT_METHODS)


def format_key(product: dict) -> str:
    return (product.get("product_format") or "").strip().lower()


def compute_cohort_medians(products: list[dict]) -> dict[str, float]:
    """Median $/g per product format, for formats with >=3 priced samples.

    Mirrors the vape cohort threshold (P2 known-issue I3: <3 samples is
    noise).
    """
    by_format: dict[str, list[float]] = {}
    for p in products:
        fmt = format_key(p)
        weight = p.get("weight_grams") or 0
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
    weight = product.get("weight_grams") or 0
    msrp = product.get("msrp") or 0
    if fmt and weight and msrp:
        price_per_g = msrp / weight
        med = cohort_medians.get(fmt)
        if med and price_per_g > med * COHORT_RATIO:
            flags.append(
                Flag(
                    flag_id="CN-002",
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
