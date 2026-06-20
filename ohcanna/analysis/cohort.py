"""Cohort-relative price helpers for the analyzer's F-005 rule."""
from __future__ import annotations

from statistics import median


def compute_cohort_medians(products: list[dict]) -> dict[str, float]:
    """Median $/g per product format, across all products in the dataset.

    A format is only included if it has at least 3 priced samples (P2
    known-issue I3: low-count formats produce noise).
    """
    by_format: dict[str, list[float]] = {}
    for p in products:
        fmt = (p.get("product_format") or "").lower()
        size = (
            p.get("cart_size_grams")
            or p.get("package_size_grams")
            or p.get("weight_grams")
            or 0
        )
        msrp = p.get("msrp") or 0
        if fmt and size and msrp:
            by_format.setdefault(fmt, []).append(msrp / size)
    return {fmt: median(vals) for fmt, vals in by_format.items() if len(vals) >= 3}
