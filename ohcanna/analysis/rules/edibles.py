"""Edible-category consistency rules (ED-001 .. ED-003).

P2 §5 T8: "dosage accuracy by mg, ratio claims." Three rules:

  ED-001  Labeled total_thc_mg is inconsistent with dose_mg ×
          count_per_package by more than 10%. A package's total should
          reconcile with its per-piece dose and piece count; a large gap
          is a possible labeling discrepancy worth verifying on the COA.
  ED-002  Implausible single dose: dose_mg above 100mg per piece. Ohio
          edibles are dosed in small increments (commonly 5-10mg); a
          three-digit single dose is uncommon and worth a look.
  ED-003  Within a format cohort (same product_format, >=3 priced
          samples), price-per-mg of THC runs more than 1.5x the cohort
          median. May reflect brand premium rather than production cost.

Conservative by design (P2 §D7): a flag is an observation, not an
accusation. Severity tiers strictly info | watch | warn.
"""
from __future__ import annotations

from dataclasses import asdict
from statistics import median

from ohcanna.models import Flag

# Tolerance on the total-vs-(dose×count) reconciliation, and the
# absolute single-dose ceiling for the OH market.
TOTAL_TOLERANCE = 0.10
IMPLAUSIBLE_DOSE_MG = 100.0
COHORT_RATIO = 1.5

RULES = [
    {
        "id": "ED-001",
        "name": "Total-THC-inconsistent-with-dose-times-count",
        "severity": "watch",
        "trigger": lambda p: _total_mismatch(p) is not None
        and _total_mismatch(p) > TOTAL_TOLERANCE,
        "explain": (
            "Labeled total THC differs from per-piece dose times piece "
            "count by more than 10%. A package total should reconcile "
            "with its dosing; verify the figures against the COA."
        ),
    },
    {
        "id": "ED-002",
        "name": "Implausibly-high-single-dose",
        "severity": "info",
        "trigger": lambda p: (p.get("dose_mg") or 0) > IMPLAUSIBLE_DOSE_MG,
        "explain": (
            "Per-piece dose above 100mg THC. Ohio edibles are typically "
            "dosed in small increments; a three-digit single dose is "
            "uncommon and may indicate a total-vs-per-piece labeling mixup."
        ),
    },
    {
        "id": "ED-003",
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


def _total_mismatch(product: dict) -> float | None:
    """Relative gap between labeled total and dose×count, or None.

    Returns None when any input is missing/zero so the rule stays silent
    rather than dividing by zero.
    """
    dose = product.get("dose_mg") or 0
    count = product.get("count_per_package") or 0
    total = product.get("total_thc_mg") or 0
    if not dose or not count or not total:
        return None
    expected = dose * count
    return abs(total - expected) / expected


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
                    flag_id="ED-003",
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
