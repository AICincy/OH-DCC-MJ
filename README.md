# OHCanna

Public transparency layer for Ohio cannabis products, processors, cultivators,
brands, and dispensaries. Built from public dispensary menu data under
one-source-publication principles inherited from HCJC.

**Repo:** github.com/AICincy/OH-DCC-MJ
**Operating principal:** AICincy LLC
**Status:** Phase 1 foundation. Publication layer, entity pages, and DCC
license registry integration are deferred to Phase 2 / Phase 3.

See [`docs/P2-handoff.md`](docs/P2-handoff.md) for the master spec,
[`docs/P3-omc-assessment.md`](docs/P3-omc-assessment.md) for competitive
recon, [`docs/P4-dcc-license-registry.md`](docs/P4-dcc-license-registry.md)
for the Phase 3 DCC registry spec, and
[`docs/A1-exa-discovery-agent.md`](docs/A1-exa-discovery-agent.md) for the
Exa-equipped entity discovery agent spec.

## Install

```bash
pip install -e .
# or with dev deps:
pip install -e ".[dev]"
```

## Run

```bash
# Print the planned (location, category) matrix without hitting the network:
python -m ohcanna scrape --source bloom --dry-run

# Full daily scrape across all 7 locations and 7 categories:
python -m ohcanna scrape --source bloom

# Narrow to one slice (good for iterating on a parser):
python -m ohcanna scrape --source bloom --location akron --category vape

# Apply F-001..F-005 consistency flags to a snapshot:
python -m ohcanna analyze data/snapshots/<YYYY-MM-DD>/bloom_akron_vape.json
```

Output lands at `data/snapshots/<YYYY-MM-DD>/bloom_<location>_<category>.json`,
with a per-category rollup mirrored to `data/latest/bloom_<category>.json`.

## Layout

```
ohcanna/                 package
  cli.py                 python -m ohcanna {scrape|analyze|build}
  models.py              Product (+ category subclasses), Flag
  storage.py             atomic snapshot writes
  brands.py              brand registry, legal-entity resolution
  sources/
    base.py              Source ABC
    bloom.py             Bloom Marijuana (7 locations, 7 categories)
  analysis/
    cohort.py
    rules/vape.py        F-001..F-005
  data/
    brands.yaml
    fixtures/            recorded HTML for offline tests (see below)
data/
  snapshots/<date>/      per-day, per-source, per-location, per-category JSON
  latest/                rolling per-category rollups
docs/                    P2 / P3 / P4 / A1 specs
tests/                   pytest, no network
```

## Fixtures

CI does not hit live Bloom (WAF discipline, P2 §9). Tests load HTML
fixtures from `ohcanna/data/fixtures/`. To seed them:

```bash
# From a workstation, scrape the slice you want to fixture:
python -m ohcanna scrape --source bloom --location akron --category vape
# Then save the raw HTML alongside the JSON snapshot (manual step today;
# automate in a follow-up).
```

If a fixture is missing, the corresponding parser smoke test falls back to
the POC sample (`data/snapshots/2026-06-20/bloom_all_vape.json`) so CI stays
green while still gating the analyzer rules and brand-registry mappings.

## Operational discipline (mandatory; from P2 §9)

- 1 request per 2 seconds against any one domain.
- Identify in `User-Agent: OhCannaTransparency/<version> (public-records research; aicincy.org)`.
- No authentication bypass. Respect `robots.txt`.
- 30-minute removal-request policy.
- Flags are observations, never accusations. Never use "fraud,"
  "deceptive," "misleading," or "false" in user-facing copy.
- No PII. Scrape only product and entity data.

## What's not in this phase

Per P2 §4 "Not in Phase 1":

- Static-site generator / publication layer
- Entity rollup pages (per-cultivator, per-processor, per-brand, per-dispensary)
- DCC license registry integration (Phase 3, see P4)
- Additional sources beyond Bloom (Phase 2)
- Category-specific flag rules beyond vape (Phase 2)
- User accounts, COA submission, moderation (not in OHCanna at all)

## License

Code MIT, data CC-BY-4.0 — pending operator confirmation (P2 §7 DL).
