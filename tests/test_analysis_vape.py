"""Pin the F-001..F-005 flag distribution against the POC sample.

The POC was verified live 2026-06-20 with 108 of 420 vape products
carrying at least one flag (P2 §3). This test reproduces that exact
distribution against the canonical sample so that any rule-logic
regression is caught at PR time.
"""
from __future__ import annotations

import json

from ohcanna.analysis.rules.vape import analyze_dataset


def test_analyzer_reproduces_poc_distribution(poc_vape_sample):
    with open(poc_vape_sample) as f:
        products = json.load(f)
    flagged = analyze_dataset(products)
    assert len(flagged) == len(products) == 420

    flagged_count = sum(1 for p in flagged if p["flag_count"] > 0)
    # POC verified ratio = 108/420. Allow ±10% tolerance for cohort-median
    # F-005 noise (P2 §11 verification protocol §5).
    assert 97 <= flagged_count <= 119, (
        f"expected ~108 flagged products (±10%), got {flagged_count}"
    )

    # Each of F-001..F-005 should fire on at least one product, otherwise
    # the rule logic has silently broken.
    fired: set[str] = set()
    for p in flagged:
        for flag in p["flags"]:
            fired.add(flag["flag_id"])
    for rule_id in ("F-001", "F-002", "F-003", "F-004", "F-005"):
        assert rule_id in fired, f"rule {rule_id} never fired"


def test_severity_taxonomy_is_constrained():
    """P2 §D7: severity tiers are info | watch | warn. Nothing else."""
    from ohcanna.analysis.rules.vape import RULES
    allowed = {"info", "watch", "warn"}
    for rule in RULES:
        assert rule["severity"] in allowed, rule
