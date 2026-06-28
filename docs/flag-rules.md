# Flag rule catalog

Human-readable companion to the rule modules in
`ohcanna/analysis/rules/`. Every flag is an **observation, not an
accusation** (P2 §D7, §9). User-facing copy never uses "fraud,"
"deceptive," "misleading," or "false." Severity tiers are `info` |
`watch` | `warn`.

The analyzer is category-dispatched (`ohcanna/analysis/engine.py`): each
product is routed to the rule set for its `category`. Categories without
a rule set yet pass through with no flags.

## Vape — `rules/vape.py` (F-001 … F-006)

| ID | Rule | Severity | Fires when |
|----|------|----------|------------|
| F-001 | Live-extraction-claim-with-CBD-presence | watch | format mentions "live" **and** profile lists CBD |
| F-002 | Full-spec-but-no-secondary-cannabinoids | info | format mentions "full spec" **and** no minor cannabinoids listed |
| F-003 | High-THC-with-CBD-in-non-CBD-cultivar | watch | THC ≥ 70% **and** CBD present |
| F-004 | Distillate-disposable-with-many-cannabinoids | info | format mentions "distillate" **and** ≥2 minor cannabinoids |
| F-005 | Price-far-above-cohort-median-for-format | info | MSRP/g > 1.5× the median for that format (cohort needs ≥3 priced samples) |
| F-006 | Non-live-extraction-below-same-strain-live-resin-THC | info | a non-live extraction (CO2 / full-spectrum / distillate) tests below 0.85× the same brand + strain's live-resin/rosin median THC |

Verified distribution: 108 of 420 POC vape products carry ≥1 flag (F-001…F-005).

F-006 is the cross-extraction comparison the cultivator catalog exists to
surface — e.g. a Citizen CO2 vape against the same line's live resin (P2 §9:
context, not an accusation). It needs an `extraction_method` in the product's
`extra` to participate, so it only applies to sources that capture one
(Klutch today); Bloom vapes neither seed nor trip it. **Synthetic-validated
only** — calibrate the 0.85 ratio against a live Klutch capture before
trusting the real distribution.

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

## Edibles — `rules/edibles.py` (ED-001 … ED-003)

P2 §5 T8: "dosage accuracy by mg, ratio claims."

| ID | Rule | Severity | Fires when |
|----|------|----------|------------|
| ED-001 | Total-THC-inconsistent-with-dose-times-count | watch | labeled `total_thc_mg` differs from `dose_mg` × `count_per_package` by > 10% |
| ED-002 | Implausibly-high-single-dose | info | `dose_mg` > 100mg per piece |
| ED-003 | Price-per-mg-above-cohort-median-for-format | info | MSRP per mg THC > 1.5× the median for that format (cohort needs ≥3 priced samples) |

## Concentrates — `rules/concentrates.py` (CN-001, CN-002)

P2 §5 T9: "solventless claim vs solvent disclosure."

| ID | Rule | Severity | Fires when |
|----|------|----------|------------|
| CN-001 | Solventless-claim-with-solvent-extraction | watch | name/format claims solventless (rosin/hash/solventless/ice water/bubble) **and** `extraction_method` names a solvent (BHO/butane/CO2/distillate/propane/ethanol/hydrocarbon) |
| CN-002 | Price-per-gram-above-cohort-median-for-format | info | MSRP/g > 1.5× the median for that format (cohort needs ≥3 priced samples) |

## Pre-rolls — `rules/prerolls.py` (PR-001, PR-002)

P2 §5 T10: "weight accuracy."

| ID | Rule | Severity | Fires when |
|----|------|----------|------------|
| PR-001 | Missing-or-zero-weight | info | `weight_grams` missing or zero (weight accuracy can't be checked) |
| PR-002 | Price-per-gram-above-cohort-median-for-format | info | MSRP/g > 1.5× the median for that format (pack weight = `weight_grams` × `count_per_package` when both present; cohort needs ≥3 priced samples) |

## Tinctures — `rules/tinctures.py` (TN-001, TN-002)

P2 §5 T11: "ratio claims."

| ID | Rule | Severity | Fires when |
|----|------|----------|------------|
| TN-001 | CBD-dominant-ratio-with-high-THC-concentration | watch | `cbd_thc_ratio` is CBD-dominant (CBD share ≥ 2× THC share) **and** `total_thc_mg` / `volume_ml` > 10 mg/ml |
| TN-002 | Price-per-mg-above-cohort-median-for-format | info | MSRP per mg THC > 1.5× the median for that format (cohort needs ≥3 priced samples) |

### Validation status (T8–T11)

These four rule sets are validated **only against synthetic product
dicts**, pending a scraper fix. The current Bloom category URLs for
edibles, concentrates, pre-rolls, and tinctures return vape-format
content rather than the category's own menu, so the category-specific
fields (`dose_mg`, `extraction_method`, `cbd_thc_ratio`, …) are
unpopulated (0%) in real snapshots. Each rule is exercised with a crafted
positive case (fires) and a crafted negative case (silent) in
`tests/test_analysis_{edibles,concentrates,prerolls,tinctures}.py`. Once
the scrapers emit real category data and a fixture is recorded, each
module drops into `engine.RULE_MODULES` with no other change.
