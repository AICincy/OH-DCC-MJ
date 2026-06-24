"""Category-dispatched analyzer.

Routes each product to the rule module for its category. Vape and flower
have rule sets today (F-001..F-005, FL-001..FL-002); the remaining
categories pass through with no flags until their rule sets land
(P2 §5 T8-T11) and their scrapers emit real category data.

Cohorts are computed per category over the products passed in, so a
single-category snapshot and a mixed snapshot both analyze correctly.
"""
from __future__ import annotations

from ohcanna.analysis.rules import flower, vape

# category -> module exposing analyze_dataset(list[dict]) -> list[dict]
RULE_MODULES = {
    "vape": vape,
    "flower": flower,
}


def _passthrough(products: list[dict]) -> list[dict]:
    return [{**p, "flags": [], "flag_count": 0} for p in products]


def analyze_dataset(products: list[dict]) -> list[dict]:
    # Partition by category, preserving original order on the way out.
    buckets: dict[str, list[tuple[int, dict]]] = {}
    for i, p in enumerate(products):
        buckets.setdefault(p.get("category") or "", []).append((i, p))

    results: list[dict | None] = [None] * len(products)
    for category, items in buckets.items():
        group = [p for _, p in items]
        module = RULE_MODULES.get(category)
        analyzed = module.analyze_dataset(group) if module else _passthrough(group)
        for (idx, _), record in zip(items, analyzed):
            results[idx] = record
    return results  # type: ignore[return-value]
