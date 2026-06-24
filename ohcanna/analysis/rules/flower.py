"""Flower-category consistency rules (FL-001, FL-002).

P2 §5 T7: "THC inflation across batches of same cultivar." Two rules:

  FL-001  Within a cultivar cohort (same strain, >=3 batches), flag a
          batch whose THC% runs more than 15% above the cohort median.
          Same genetics should not vary that widely batch-to-batch;
          a high outlier is a possible label-inflation signal.
  FL-002  Absolute implausibility: flower above ~35% THC by mass is
          essentially never real. A standing guard regardless of cohort.

Conservative by design (P2 §D7): a flag is an observation, not an
accusation. The cohort key is the lowercased product name — a coarse
cultivar proxy (known limitation: brand/descriptor noise in the name can
split a cohort; the rule still only ever flags *within* a matched group).
"""
from __future__ import annotations

from dataclasses import asdict
from statistics import median

from ohcanna.models import Flag

# Cohort outlier threshold and absolute implausibility ceiling.
COHORT_RATIO = 1.15
IMPLAUSIBLE_THC = 35.0

RULES = [
    {
        "id": "FL-001",
        "name": "THC-above-cultivar-cohort-median",
        "severity": "watch",
        "trigger": None,  # cohort-dependent, applied separately
        "explain": (
            "Labeled THC runs more than 15% above the median for other "
            "batches of the same cultivar. Identical genetics rarely vary "
            "that much batch-to-batch; verify the high reading against "
            "the COA."
        ),
    },
    {
        "id": "FL-002",
        "name": "Implausibly-high-flower-THC",
        "severity": "watch",
        "trigger": lambda p: (p.get("thc_percent") or 0) >= IMPLAUSIBLE_THC,
        "explain": (
            "Labeled THC at or above 35% by mass. Dried cannabis flower "
            "rarely tests this high; values in this range commonly reflect "
            "sampling or reporting inflation rather than measured potency."
        ),
    },
]


def cultivar_key(product: dict) -> str:
    return (product.get("name") or "").strip().lower()


def compute_cultivar_cohorts(products: list[dict]) -> dict[str, float]:
    """Median THC% per cultivar, for cultivars with >=3 THC samples.

    Mirrors the vape cohort threshold (P2 known-issue I3: <3 samples is
    noise).
    """
    by_cultivar: dict[str, list[float]] = {}
    for p in products:
        key = cultivar_key(p)
        thc = p.get("thc_percent")
        if key and thc is not None:
            by_cultivar.setdefault(key, []).append(thc)
    return {k: median(v) for k, v in by_cultivar.items() if len(v) >= 3}


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
    key = cultivar_key(product)
    thc = product.get("thc_percent")
    median_thc = cohort_medians.get(key)
    if thc is not None and median_thc and thc > median_thc * COHORT_RATIO:
        flags.append(
            Flag(
                flag_id="FL-001",
                rule_name="THC-above-cultivar-cohort-median",
                severity="watch",
                explanation=(
                    f"Labeled THC {thc:.0f}% vs cultivar-cohort median "
                    f"{median_thc:.0f}% for this strain. "
                    f"{(thc / median_thc - 1) * 100:.0f}% above the cohort."
                ),
            )
        )
    return flags


def analyze_dataset(products: list[dict]) -> list[dict]:
    cohorts = compute_cultivar_cohorts(products)
    results = []
    for p in products:
        flags = evaluate_with_cohort(p, cohorts)
        results.append({
            **p,
            "flags": [asdict(f) for f in flags],
            "flag_count": len(flags),
        })
    return results
