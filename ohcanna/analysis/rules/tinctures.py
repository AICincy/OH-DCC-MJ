"""Tincture-category consistency rules (TN-001, TN-002).

P2 §5 T11: "ratio claims." Two rules:

  TN-001  A CBD:THC ratio is claimed that is CBD-dominant (CBD share at
          least twice the THC share), yet the disclosed THC concentration
          (total_thc_mg / volume_ml) is high for a CBD-leaning product.
          A CBD-dominant ratio paired with a THC-heavy potency is a
          possible mismatch worth verifying against the COA.
  TN-002  Within a format cohort (same product_format, >=3 priced
          samples), price-per-mg of THC runs more than 1.5x the cohort
          median. May reflect brand premium rather than production cost.

Conservative by design (P2 §D7): a flag is an observation, not an
accusation. Severity tiers strictly info | watch | warn.
"""
from __future__ import annotations

from dataclasses import asdict
from statistics import median

from ohcanna.models import Flag

COHORT_RATIO = 1.5

# A ratio is treated as CBD-dominant when CBD share is at least this
# multiple of the THC share. mg/ml THC at or above this is "high" for a
# CBD-leaning tincture.
CBD_DOMINANT_FACTOR = 2.0
HIGH_THC_MG_PER_ML = 10.0

RULES = [
    {
        "id": "TN-001",
        "name": "CBD-dominant-ratio-with-high-THC-concentration",
        "severity": "watch",
        "trigger": lambda p: _cbd_dominant(p) and _thc_per_ml(p) is not None
        and _thc_per_ml(p) > HIGH_THC_MG_PER_ML,
        "explain": (
            "A CBD-dominant CBD:THC ratio is claimed, but the disclosed "
            "THC concentration per ml runs high for a CBD-leaning "
            "product. Verify the ratio and potency against the COA."
        ),
    },
    {
        "id": "TN-002",
        "name": "Price-per-mg-above-cohort-median-for-format",
        "severity": "info",
        "trigger": None,  # cohort-dependent, applied separately
        "explain": (
            "MSRP per mg of THC is more than 1.5x the cohort median for "
            "this format. May reflect brand premium rather than "
            "production cost difference."
        ),
    },
]


def parse_ratio(raw: str | None) -> tuple[float, float] | None:
    """Parse a "CBD:THC" ratio string into (cbd_share, thc_share).

    Returns None when the string is missing or unparseable. Accepts forms
    like "20:1", "1:1", "1 : 1".
    """
    if not raw:
        return None
    parts = raw.replace(" ", "").split(":")
    if len(parts) != 2:
        return None
    try:
        cbd = float(parts[0])
        thc = float(parts[1])
    except ValueError:
        return None
    if cbd <= 0 and thc <= 0:
        return None
    return cbd, thc


def _cbd_dominant(product: dict) -> bool:
    parsed = parse_ratio(product.get("cbd_thc_ratio"))
    if not parsed:
        return False
    cbd, thc = parsed
    if thc <= 0:
        return True  # pure-CBD claim
    return cbd >= thc * CBD_DOMINANT_FACTOR


def _thc_per_ml(product: dict) -> float | None:
    total = product.get("total_thc_mg") or 0
    volume = product.get("volume_ml") or 0
    if not total or not volume:
        return None
    return total / volume


def format_key(product: dict) -> str:
    return (product.get("product_format") or "").strip().lower()


def compute_cohort_medians(products: list[dict]) -> dict[str, float]:
    """Median $/mg THC per product format, for formats with >=3 samples.

    Mirrors the vape cohort threshold (P2 known-issue I3: <3 samples is
    noise).
    """
    by_format: dict[str, list[float]] = {}
    for p in products:
        fmt = format_key(p)
        total = p.get("total_thc_mg") or 0
        msrp = p.get("msrp") or 0
        if fmt and total and msrp:
            by_format.setdefault(fmt, []).append(msrp / total)
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
    total = product.get("total_thc_mg") or 0
    msrp = product.get("msrp") or 0
    if fmt and total and msrp:
        price_per_mg = msrp / total
        med = cohort_medians.get(fmt)
        if med and price_per_mg > med * COHORT_RATIO:
            flags.append(
                Flag(
                    flag_id="TN-002",
                    rule_name="Price-per-mg-above-cohort-median-for-format",
                    severity="info",
                    explanation=(
                        f"MSRP ${price_per_mg:.3f}/mg vs cohort median "
                        f"${med:.3f}/mg for {fmt}. Premium of "
                        f"{(price_per_mg / med - 1) * 100:.0f}%."
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
