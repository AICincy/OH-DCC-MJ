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

CI does not hit live Bloom (WAF discipline, P2 §9). Parser smoke tests
in `tests/test_bloom_vape.py` and `tests/test_bloom_flower.py` load HTML
fixtures from `ohcanna/data/fixtures/` and skip cleanly when a fixture
is missing. To seed them from a workstation with network access:

```bash
python -m ohcanna scrape --source bloom --location akron --category vape   --record-fixtures
python -m ohcanna scrape --source bloom --location akron --category flower --record-fixtures
git add ohcanna/data/fixtures/bloom_akron_vape.html ohcanna/data/fixtures/bloom_akron_flower.html
git commit -m "fixtures: bloom akron vape + flower"
```

Re-record on a quarterly cadence (or after a Bloom template change is
observed). The daily cron does NOT record fixtures — drifting fixtures
would create noisy diffs and force endless test-baseline updates. Set
`OHCANNA_RECORD_FIXTURES=1` to opt in from an environment where adding
the CLI flag is awkward.

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
- Flag rules for edibles / concentrates / pre-rolls / tinctures (Phase 2
  T8–T11; blocked on those scrapers emitting real category data — see
  `docs/flag-rules.md`). Vape (F-001–F-005) and flower (FL-001–FL-002)
  rule sets are implemented.
- User accounts, COA submission, moderation (not in OHCanna at all)

## License

Code MIT, data CC-BY-4.0 — pending operator confirmation (P2 §7 DL).
