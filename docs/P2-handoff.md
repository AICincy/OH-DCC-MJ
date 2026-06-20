# OHCanna Project: Claude Code Handoff (P2, superseding)

**Project name:** OHCanna
**Repo:** github.com/AICincy/OH-DCC-MJ
**Status:** POC verified in Claude.ai; ready for production scaffolding in Claude Code
**Supersedes:** Original PRC-002 (vape-only Phase 1 scope is retired)
**Operating principal:** Krass (AICincy LLC), out-of-band during execution sessions

---

## 1. Mission

Build a public, batch-ID-searchable transparency layer for Ohio cannabis products, processors, cultivators, brands, and dispensaries. The site publishes structured data scraped from public dispensary menus, surfaces rule-based consistency observations between marketing claims and label data, and aggregates per-entity views. Data acquisition does not depend on Ohio DCC cooperation; it depends on data the operators have already chosen to publish.

The site answers the question current Ohio law makes operationally unanswerable: *what am I actually buying, and who really makes it?*

Legal framing: OAC 1301:18-6-15 requires dispensaries to make COAs available on request; in practice, they do not. OHCanna does not replace the COA. It surfaces algorithmically-derived observations from public label and menu data, indexed against the OAC's required label disclosures (3796:3-2-02(A)(2)), so consumers can verify processor claims without depending on a verification regime that does not function at the counter.

---

## 2. Decisions

| Tag | Decision | Rationale |
|---|---|---|
| D1 | Public name OHCanna; repo OH-DCC-MJ | Civic framing locates project alongside HCJC and MetroNow as transparency infrastructure |
| D2 | Phase 1 scrapes ALL product categories, not vape only | Original vape-only scope was reactive to P3 (OMC assessment). Scrapers handle full menus already. SEO and audience scale require breadth |
| D3 | Phase 1 publishes flags only where the rule set is mature (vape) | Other categories show structured data and price comparison; flags follow in Phase 2 |
| D4 | Primary acquisition: HTML scraping where SSR; Dutchie GraphQL where SPA | Bloom is custom Next.js SSR (verified). Dutchie-native dispensaries need GraphQL path. Both legitimate |
| D5 | Posture: neutral-publication, not adversarial | Mirrors HCJC stance. Surface data, let consumers conclude. Avoids defamation surface |
| D6 | Rate limit: 1 req per 2 sec, identify scraper in User-Agent | Respects WAF, mirrors HCJC operational discipline |
| D7 | Flag schema: severity tiers info/watch/warn, no accusations | Conservative. Each flag is an observation, not a claim of fraud |
| D8 | Storage: JSON snapshots per scrape cycle, indexed by scrape date | Simple, debuggable, deferrable to a proper DB later |
| D9 | Toolchain: Python 3.11+, requests + BeautifulSoup4 + lxml for scraping; SSG (Hugo or Astro) for publication; no SPA | Matches JCStream stack; rejects OMC's SPA failure mode (P3 finding) |
| D10 | Cadence: daily scrape, weekly snapshot | Matches Ohio DCC data publication cadence |
| D11 | Entity model: cultivator, processor, brand, dispensary, product, testing_lab | Five entity types form the graph. Processor is the analytical center (OAC license-number disclosure rule lands here) |
| D12 | Phase 3 adds DCC license registry as Tier 1 entity source | See P4 spec |

Decisions still routed back to Krass listed in section 7.

---

## 3. POC artifacts (Claude.ai work product)

Already built, verified live on 2026-06-20:

| File | Purpose | Status |
|---|---|---|
| `bloom_scraper.py` | Bloom Marijuana scraper for 7 Ohio locations, vape category | Verified, 420 products, 100% field coverage, 0 UNKNOWN brands |
| `analyzer.py` | Five rule-based consistency flags (F1-F5) | Verified, 108 of 420 products carry at least one flag |
| `bloom_all_vape_sample.json` | Sample dataset | 420 products |
| `bloom_all_vape_flagged_sample.json` | Same with flags applied | Same set, flag annotations added |
| `P3 OMC assessment` | Competitive recon of ohiomarijuanacommunity.com | Read before designing publication layer |
| `A1 Exa discovery agent` | Specification for Exa-equipped sessions doing entity discovery and verification | Use during Phase 2 and Phase 3 |
| `P4 DCC license registry` | Spec for Phase 3 license data integration | Read before Phase 3 |

Data model verified:

```python
VapeProduct:
    location: str
    product_id: str
    product_url: str
    name: str
    strain_type: Optional[str]   # indica | sativa | hybrid
    brand: str                    # resolved against registry
    product_format: str           # e.g. "live resin cart"
    cart_size_grams: Optional[float]
    thc_percent: Optional[float]
    secondary_cannabinoids: list[str]
    terpenes: list[str]
    sale_price: Optional[float]
    msrp: Optional[float]
    discount_percent: Optional[int]
    scraped_at: str

Flag:
    flag_id: str                  # F1, F2, F3, F4, F5
    rule_name: str
    severity: str                 # info | watch | warn
    explanation: str              # plain English, publication-ready
```

`VapeProduct` is the template for the generalized `Product` schema in Phase 1. Category-specific fields (flower THC, edible mg dosing, concentrate extraction-solvent disclosure) extend the base schema by category.

---

## 4. Phase 1 specification (revised)

### Scope
Scrape ALL product categories from Bloom Marijuana, 7 Ohio locations:
- Vape (verified working)
- Flower (next; standard menu category)
- Edibles
- Concentrates (rosin, badder, sauce, diamonds, hash)
- Pre-rolls
- Tinctures
- Topicals

Publish complete structured data for all categories. Apply flags only to vape until Phase 2 rule sets are designed.

### Deliverables
- Refactored `ohcanna/sources/bloom.py` with per-category scrapers behind a single `BloomSource` class
- Generalized `Product` dataclass with category-specific subclasses
- Persistence layer (JSON snapshots per category per location per day)
- Scrape orchestrator CLI: `python -m ohcanna scrape --source bloom`
- GitHub Actions daily scrape with output committed to `data/snapshots/`
- Static site generator (Hugo or Astro, builder's choice) producing per-product pages
- Index page listing all categories
- Per-category browse page with filter and sort
- Per-product detail page (canonical URL: `/product/<product_id>/`)
- Sitemap.xml mandatory (every product gets an indexable URL)
- Federal docket aesthetic (IBM Plex Mono, cream `#fafafa`, federal red `#b30000`) unless DA decision changes it

### Acceptance bar
- Scraping 7 locations across 7 categories yields between 2,000 and 4,000 products per scrape cycle
- 100% of products have brand, format, price, scrape timestamp
- 95% of products have THC % (some categories like topicals may legitimately omit)
- Zero UNKNOWN brands (extend the registry as new brands appear)
- All vape products have at least the F1-F5 rule set applied
- Sitemap.xml lists every product URL
- First-load HTML for any product page is under 50 KB (SSG produces lean output)

### Not in Phase 1
- Multi-source scraping (Locals, Pure Ohio Wellness, etc.)
- Category-specific flag rules beyond vape
- Entity aggregation pages (per-cultivator, per-processor, per-brand)
- DCC license registry integration
- User accounts, submissions, or community features (none of these belong in OHCanna at all)

---

## 5. Phase 2 specification

### Scope
Expand data sources beyond Bloom, develop category-specific flag rules, surface processor-level aggregation.

### Tracks
| Track | Work | Priority |
|---|---|---|
| T1 | Add Locals Cannabis scraper | Highest (broadest indie Ohio chain) |
| T2 | Add Pure Ohio Wellness scraper (own retail) | High |
| T3 | Add Saphyre / Zips scraper | High |
| T4 | Add Story Cannabis scraper (iHeartJane backend) | Medium |
| T5 | Add Dutchie-native dispensary scraper (Greenlight Marietta, Supergood Ravenna) | Medium |
| T6 | Add MSO chains (Curaleaf, Sunnyside, Rise) | Lower; anti-scraping likely |
| T7 | Flower flag rules (THC inflation across batches of same cultivar) | High |
| T8 | Edibles flag rules (dosage accuracy by mg, ratio claims) | High |
| T9 | Concentrate flag rules (solventless claim vs. solvent disclosure) | High |
| T10 | Pre-roll flag rules (weight accuracy) | Medium |
| T11 | Tincture flag rules (ratio claims) | Medium |
| T12 | Processor-level rollup pages (`/processor/<license_number>/`) | High (this is the SEO and analytical win) |
| T13 | Brand rollup pages (`/brand/<slug>/`) | High |
| T14 | Dispensary rollup pages (`/dispensary/<slug>/`) | Medium |

Each track lands as its own PR. The orchestrator must handle per-source failures without aborting the run.

### Acceptance bar (cumulative)
- 5+ active data sources by end of Phase 2
- All 7 product categories have at least one category-specific flag rule
- Processor pages aggregate all SKUs across all dispensaries showing that processor's product
- Brand pages surface processor attribution prominently (e.g., "Cookies (operated in Ohio by AT-CPC of Ohio LLC, Klutch)")

---

## 6. Phase 3 specification

### Scope
Integrate DCC license registry as Tier 1 entity source. Build the entity graph. Per-entity pages become canonical references.

### Reference: P4 (sibling spec) covers DCC license registry data sources, schema, and ingestion. Read P4 before starting Phase 3.

### Entity model
```
Cultivator    --grows-->    Plant Material   --supplies-->    Processor
Processor     --produces--> Product           --sold_at-->     Dispensary
Brand         --owned_by--> Processor         (license-level relationship)
Brand         --licensed_to_processor (when applicable, e.g. Cookies-by-Klutch)
TestingLab    --tested-->   Product (via batch_id, when COA data is available)
```

### Page types added
- `/cultivator/<license_number>/` - flower cultivars produced, processors supplied (where verifiable), license history
- `/processor/<license_number>/` - brands operated, products produced (rolled up across all SKUs scraped), license history
- `/brand/<slug>/` - operating processor, full product portfolio, format and price distribution, flag distribution
- `/dispensary/<license_number>/` - location, hours, brands carried, daily product count
- `/testing-lab/<license_number>/` - labs licensed under OAC 1301:18-5

### Cross-references that become visible
- Klutch consolidation (Cookies, Citizen, Josh D, Habitat by Klutch, and Klutch own-brand under one processor license) becomes a publishable graph. Woodward Fine Cannabis is a SEPARATE entity: own cultivation, own processing, own dispensaries (woodwardcannabis.com), own brand. Not part of Klutch
- Standard Wellness's value-tier (The Solid) vs. premium-tier (The Standard) brand spread becomes visible
- Any MSO operating Ohio brands behind a local-sounding name surfaces in cross-reference

### Acceptance bar
- All DCC-licensed cultivators, processors, dispensaries, and testing labs are represented as entity pages
- Every product page links to its processor, brand, and dispensary entity pages
- The brand-to-processor map is verified for at least 90% of brands appearing in scraped data
- A1 (Exa discovery agent) is used to fill verification gaps

---

## 7. Decisions routed to Krass

These should NOT be made by Claude Code or A1 unilaterally. Open as GitHub issues tagged `decision-needed` and pause that track until resolved.

| Tag | Decision | Default if no answer |
|---|---|---|
| DA | Federal docket aesthetic (HCJC) or distinct OHCanna aesthetic? | Federal docket; distinguishing brand token TBD |
| DH | Hosting (GitHub Pages, Cloudflare Pages, self-hosted)? | GitHub Pages |
| DL | Code license (MIT, AGPL, other)? Data license? | MIT for code, CC-BY-4.0 for data |
| DD | Disclose DCC's operational failure to enforce OAC 1301:18-6-15 on the About page? | Yes |
| DB | Workflow when a processor pushes back on a flag? | Pause flag, route to Krass, resume only with review |
| DP | Response to defamation threats from a processor? | Halt publication of disputed product, route to Krass, do not engage on legal substance |
| DM | Migrate to Postgres or keep JSON snapshots indefinitely? | JSON until performance forces migration |
| DR | Should the site support COA submission by users (per OMC's failed pattern)? | No in Phase 1-2; revisit Phase 3 with explicit moderation plan |

---

## 8. Repository structure (proposed)

```
OH-DCC-MJ/
  ohcanna/
    __init__.py
    cli.py                # python -m ohcanna {scrape|analyze|build}
    storage.py            # snapshot read/write, atomic writes
    models.py             # Product (+ subclasses), Flag, Entity dataclasses
    sources/
      __init__.py
      base.py             # Source abstract class
      bloom.py            # Bloom Marijuana (all categories)
      locals_cannabis.py  # Phase 2
      pure_ohio_wellness.py
      saphyre.py
      story.py
      dutchie.py          # generic Dutchie GraphQL
    analysis/
      __init__.py
      rules/
        vape.py           # F1-F5 (already designed)
        flower.py         # Phase 2
        edibles.py
        concentrates.py
        prerolls.py
        tinctures.py
      cohort.py
      processor_resolver.py
    entities/             # Phase 3
      __init__.py
      dcc_registry.py     # license registry ingestion (see P4)
      graph.py            # entity relationship resolution
    publication/
      templates/
      build.py            # SSG build pipeline
  data/
    snapshots/
      2026-06-20/
        bloom_akron_vape.json
        bloom_akron_flower.json
        ...
    latest/
      bloom_vape.json
      bloom_flower.json
      ...
    runs/
      <run_id>.json
    entities/             # Phase 3
      cultivators.json
      processors.json
      brands.json
      dispensaries.json
      testing_labs.json
  docs/
    P1-investigation.md         # vape oil pricing investigation
    P2-handoff.md               # this document
    P3-omc-assessment.md        # competitive recon
    P4-dcc-license-registry.md  # Phase 3 spec
    A1-exa-discovery-agent.md   # Exa session spec
    flag-rules.md               # human-readable rule catalog
    brand-processor-map.md      # P1 finding: 9 processors operate 17+ brands
  .github/
    workflows/
      scrape-daily.yml          # daily scrape cron
      deploy.yml                # publish to GitHub Pages or Cloudflare Pages
  pyproject.toml
  README.md
  LICENSE
```

---

## 9. Operational discipline (mandatory, inherited from HCJC)

- **WAF respect**: 1 req per 2 sec minimum delay. No parallel scraping against one domain. User-Agent: `OhCannaTransparency/<version> (public-records research; aicincy.org)`
- **No authentication bypass**: scrape only public surfaces. If a page requires age verification, follow the same flow a normal browser would
- **30-minute removal policy**: processor or dispensary removal requests honored within 30 min pending review
- **One-source publication**: never republish a third-party COA without permission
- **No accusations**: flags are observations. The site never uses "fraud," "deceptive," "misleading," or "false" in user-facing copy. Flag explanations describe the inconsistency
- **Robots.txt**: respect it. If a source blocks scraping in robots.txt, that source is removed from queue
- **No PII**: scrape only product and entity data. Individual customers, employees not in their corporate capacity, and license-holders' personal details outside the business filing are out-of-scope

---

## 10. Known issues

| Tag | Issue | Mitigation |
|---|---|---|
| I1 | `_KNOWN_BRANDS` registry incomplete | Treat UNKNOWN as a queue, weekly review to expand |
| I2 | Bloom format keyword list will drift | Track UNKNOWN format counts; alert when >5% of products show UNKNOWN |
| I3 | F5 cohort median needs ≥3 samples per format | Acceptable; niche formats are not the high-value targets |
| I4 | THC %, terpenes, secondary cannabinoids are dispensary-published values, not COA-verified | This is the entire reason the project exists. Surface what we have; label provenance; note gap |
| I5 | No way to verify dispensary menu data against actual COA without manual review | Partial: A1 + future submission widget. Full resolution requires DCC enforcement, which is structural |
| I6 | Processor-license-to-brand mapping not yet implemented | Phase 2 work; A1 supports |
| I7 | Some Bloom products may be priced differently across locations; we currently treat each location as canonical | Surface intentionally; price variance across the same processor's product is its own analytical signal |
| I8 | DCC license registry URL structure not yet verified | P4 spec includes verification work as first task; A1 supports |

---

## 11. Verification protocol per session

Before opening a PR:

1. Run `python -m ohcanna scrape --source bloom --dry-run`. Expect 7 locations × 7 categories = 49 sub-scrapes, totals between 2,000 and 4,000 products per cycle once flower and edibles are added
2. Run `pytest`. If no tests exist for the changes, the session is incomplete
3. Diff the run summary against the previous day's. Flag if total product count changes by >20% (likely scraper drift)
4. Spot-check 3 random product entries against the live menu by hand. Any field mismatch fails the run
5. Confirm no PII or non-public data has been ingested

---

## 12. First Claude Code session: suggested scope

> Stand up the OH-DCC-MJ repository per the structure in section 8. Move `bloom_scraper.py` to `ohcanna/sources/bloom.py` with a clean `Source` base class abstraction. Generalize the scraper to handle all Bloom product categories, not just vape. Add a CLI entry point. Add smoke tests for at least vape and flower asserting >=50 products per category with full field coverage. Set up GitHub Actions for daily scraping with output committed to `data/snapshots/`. Open a PR with these changes. Do not deploy publication layer yet.

That session is roughly 3-5 hours of Claude Code work and produces a deployable foundation that already exceeds Phase 1 of the original PRC-002.

---

End of P2 (superseding).
