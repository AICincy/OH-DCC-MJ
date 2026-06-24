# Flag rule catalog

Human-readable companion to the rule modules in
`ohcanna/analysis/rules/`. Every flag is an **observation, not an
accusation** (P2 §D7, §9). User-facing copy never uses "fraud,"
"deceptive," "misleading," or "false." Severity tiers are `info` |
`watch` | `warn`.

The analyzer is category-dispatched (`ohcanna/analysis/engine.py`): each
product is routed to the rule set for its `category`. Categories without
a rule set yet pass through with no flags.

## Vape — `rules/vape.py` (F-001 … F-005)

| ID | Rule | Severity | Fires when |
|----|------|----------|------------|
| F-001 | Live-extraction-claim-with-CBD-presence | watch | format mentions "live" **and** profile lists CBD |
| F-002 | Full-spec-but-no-secondary-cannabinoids | info | format mentions "full spec" **and** no minor cannabinoids listed |
| F-003 | High-THC-with-CBD-in-non-CBD-cultivar | watch | THC ≥ 70% **and** CBD present |
| F-004 | Distillate-disposable-with-many-cannabinoids | info | format mentions "distillate" **and** ≥2 minor cannabinoids |
| F-005 | Price-far-above-cohort-median-for-format | info | MSRP/g > 1.5× the median for that format (cohort needs ≥3 priced samples) |

Verified distribution: 108 of 420 POC vape products carry ≥1 flag.

## Flower — `rules/flower.py` (FL-001 … FL-002)

| ID | Rule | Severity | Fires when |
|----|------|----------|------------|
| FL-001 | THC-above-cultivar-cohort-median | watch | labeled THC > 1.15× the median for other batches of the same cultivar (cohort needs ≥3 THC samples) |
| FL-002 | Implausibly-high-flower-THC | watch | labeled THC ≥ 35% by mass |

P2 §5 T7 ("THC inflation across batches of same cultivar") lands as
FL-001. The cultivar cohort key is the lowercased product name — a coarse
proxy; brand/descriptor noise can split a cohort, but the rule only ever
compares a batch *within* a matched group, so it never produces a
cross-strain false positive.

Calibration against the committed Akron flower snapshot (420 products):
FL-001 fires on 5 batches; FL-002 fires on 0 (Bloom's Akron flower THC
tops out at 34%, within the plausible range). FL-002 stands as a guard
and is exercised in tests with a synthetic 38% product.

## Categories without rule sets yet

Edibles (T8), concentrates (T9), pre-rolls (T10), and tinctures (T11)
are specified in P2 §5 but not implemented. They are blocked on the
scraper emitting real category data: the current Bloom category URLs for
these return vape-format content rather than the category's own menu, so
the category-specific fields (`dose_mg`, `extraction_method`,
`cbd_thc_ratio`, …) are unpopulated. Once those scrapers are fixed and a
fixture is recorded, each rule module drops into `engine.RULE_MODULES`
with no other change.
