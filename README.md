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
  cli.py                 python -m ohcanna {scrape|analyze|build|community}
  models.py              Product (+ category subclasses), Flag
  storage.py             atomic snapshot writes, fixture recording
  brands.py              brand registry, legal-entity resolution
  sources/
    base.py              Source ABC (fetch_raw / parse_raw / scrape_all)
    bloom.py             Bloom Marijuana (production-verified)
    dutchie.py           generic Dutchie GraphQL (synthetic-validated)
    locals_cannabis.py   Locals scaffold (needs live validation)
  analysis/
    engine.py            category-dispatched analyzer
    cohort.py
    rules/               vape (F-001..F-005), flower (FL-001..FL-002),
                         edibles/concentrates/prerolls/tinctures (synthetic)
  entities/
    graph.py             processor / brand / dispensary rollups
    dcc_registry.py      DCC license schema + Path-B ingestion (P4)
  publication/
    render.py            federal-docket HTML helpers (no JS)
    build.py             static-site generator + entity pages + sitemap
  community/
    accounts.py          JSON-backed accounts (salted email hashes, no raw PII)
    moderation.py        COA submission state machine + moderation queue
    service.py           submit / moderate facade
  data/
    brands.yaml
    fixtures/            recorded HTML for offline tests (see below)
data/
  snapshots/<date>/      per-day, per-source, per-location, per-category JSON
  latest/                rolling per-category rollups
  entities/              DCC registry + brand→processor seed map
  community/             accounts / submissions / decisions (JSON)
docs/                    P2 / P3 / P4 / A1 specs, flag-rules catalog
tests/                   pytest, no network (94 passing)
```

## Build the site

```bash
python -m ohcanna build --out-dir public      # renders static HTML + sitemap.xml
python -m ohcanna community --status pending   # inspect the COA moderation queue
```

## Maturity / what still needs a live run

The swarm built every layer that is testable offline. These pieces are
structurally complete but **gated on network access this environment does
not have**, and must be validated against the live target before
production:

- **Dutchie / Locals sources** — GraphQL shape and CSS selectors are
  modeled, not captured live. Record one fixture per source via
  `--record-fixtures` and confirm the selectors before trusting output.
- **Non-vape flag rules (edibles/concentrates/pre-rolls/tinctures)** —
  validated against synthetic data only; the Bloom category URLs for
  these currently return vape-format content (a scraper bug), so there is
  no real category data to test against yet. See `docs/flag-rules.md`.
- **DCC registry** — schema + local-file (Path B) ingestion are built;
  the live registry fetch and URL verification are work item V1 (P4 §2).
- **Publication hosting & community deployment** — the SSG output and the
  community domain layer are complete, but choosing a host (P2 §7 DH) and
  standing up real auth / COA file upload are deployment concerns, not in
  this code.

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

## Phase coverage

All phases now have a built, offline-tested layer in this repo:

| Area | Status |
|------|--------|
| Phase 1 — Bloom scrape, all categories, vape flags | ✅ merged |
| Phase 2 — flower + edibles/concentrates/prerolls/tinctures flag rules | ✅ (non-vape synthetic-validated) |
| Phase 2 — processor / brand / dispensary rollups | ✅ data layer |
| Phase 2 — additional sources (Dutchie, Locals) | ⚠️ scaffold, needs live validation |
| Phase 2 — static-site publication + entity pages + sitemap | ✅ |
| Phase 3 — DCC license registry schema + ingestion | ✅ Path B (live fetch = V1) |
| Community — accounts / COA submission / moderation | ✅ JSON-backed domain layer |

See **Maturity / what still needs a live run** above for the
network-gated edges. The community layer was added at operator direction,
superseding the earlier P2 "not in OHCanna" stance; it is built
moderation-first per the P2 §7 DR decision (revisit with an explicit
moderation plan).

## License

Code MIT, data CC-BY-4.0 — pending operator confirmation (P2 §7 DL).
