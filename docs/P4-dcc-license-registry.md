# P4: DCC License Registry as Phase 3 Data Source

**Designation:** P4
**Status:** Spec; verification work pending
**Sibling docs:** P2 (handoff), A1 (Exa agent)
**Scope:** Define the DCC license registry as a Tier 1 entity data source for OHCanna's Phase 3 entity graph

---

## 1. Why this document exists

P2 Phase 3 calls for entity pages keyed to DCC license numbers (cultivators, processors, dispensaries, testing labs). The dispensary menu data we scrape carries brand and product information, but not the license number that ties a brand to its operating processor. OAC 3796:3-2-02(A)(2)(a) requires the processor license number on every product label, which means the linkage exists in the regulatory record but is not exposed in menu data. The DCC license registry is the authoritative source for that linkage.

This spec describes what to ingest, where to get it, what schema to produce, and how to fail when the data is unavailable.

---

## 2. What DCC publishes

DCC publishes license information at com.ohio.gov under the Division of Cannabis Control section. The registry covers (verified from prior matter work and PRC-001):

| License class | Statutory basis | What's published |
|---|---|---|
| Level I cultivator (>25,000 sq ft) | ORC 3796.10, OAC 1301:18-2-02 | Legal name, license number, address, status, issue date |
| Level II cultivator (<25,000 sq ft) | ORC 3796.10, OAC 1301:18-2-02 | Same fields |
| Processor | ORC 3796.10, OAC 1301:18-3 | Legal name, license number, address, status |
| Dispensary | ORC 3796.10, OAC 1301:18-4 | Legal name, dispensary trade name, license number, address, hours (sometimes) |
| Testing lab | ORC 3796.10, OAC 1301:18-5 | Legal name, license number, lab director, address |

The registry is intermittently updated. License changes (new issuance, surrender, suspension) appear on DCC's enforcement actions page separately.

### Verification needed before Phase 3 starts (work item V1)
- Confirm current DCC license registry URL structure
- Confirm whether DCC publishes the registry as a downloadable file (CSV, PDF, Excel) or only as HTML tables
- Confirm whether the registry includes brand registrations (operating-as names) or only legal entity names
- Confirm refresh cadence

A1 in Mode A (Entity Discovery) is the recommended verification path. Kickoff query: `Ohio Division of Cannabis Control licensee list public registry`.

---

## 3. Data model

```python
@dataclass
class DCCLicense:
    license_number: str           # canonical primary key
    license_type: str             # cultivator_l1 | cultivator_l2 | processor | dispensary | testing_lab
    legal_name: str               # the LLC or corporation
    trade_names: list[str]        # operating-as names (e.g., "Klutch Cannabis" for AT-CPC of Ohio LLC)
    address: str
    city: str
    county: str
    zip: str
    status: str                   # active | provisional | surrendered | suspended | revoked
    issue_date: Optional[str]     # ISO8601
    status_date: Optional[str]    # ISO8601, last status change
    source_url: str
    fetched_at: str               # ISO8601
    notes: Optional[str]
```

The license_number is the primary key. Everything else can change; the number doesn't.

For relationships:

```python
@dataclass
class BrandProcessorLink:
    brand: str
    processor_license_number: str
    link_type: str                # in_house | exclusive_ohio_license | white_label | co_brand
    effective_date: Optional[str]
    verified_sources: list[dict]  # see A1 schema
    verification_status: str      # verified | unverified | disputed
```

Brand→processor links are inferred from a mix of:
- Product label data (the license number on the actual packaging)
- Processor company websites listing their brands
- Press releases announcing partnerships
- A1 Mode B output

The mapping is many-brands-to-one-processor in most cases. Klutch's AT-CPC of Ohio LLC operates Citizen, Cookies, Josh D, Habitat by Klutch, and the Klutch own-brand under one license. Standard Wellness operates The Standard and The Solid under one license. These should be encoded as the same processor_license_number across multiple brand records.

Woodward Fine Cannabis is NOT a Klutch brand. Woodward is a separate vertically-integrated entity with its own cultivation, processing, and dispensaries (woodwardcannabis.com, locations in Delaware and Columbus, Ohio). The earlier draft of this document incorrectly grouped Woodward under Klutch based on the appearance of `klutchcannabis.com/brands/woodward-fine-cannabis/` URL; the correct read is that Klutch's dispensaries carry the Woodward brand the same way other dispensaries do. This correction is verified by the operator (Krass) directly.

---

## 4. Ingestion pipeline

### Path A: Direct scrape (preferred)

If DCC publishes the registry as structured HTML or downloadable file:

1. Daily fetch of the registry source URL
2. Parse into `DCCLicense` records
3. Diff against the previous day's snapshot
4. Emit a change log (`data/entities/registry_changes_<date>.json`)
5. Update `data/entities/{cultivators,processors,dispensaries,testing_labs}.json`

### Path B: Agent-assisted enrichment (fallback)

If the registry is fragmented or hard to scrape directly:

1. A1 Mode A executes a session per license class
2. Output JSON merged into the canonical registry
3. Manual review of A1's `verification_status: "unverified"` records before publication

### Path C: 149.43 request (last resort)

If neither A nor B yields complete data:

1. Krass files a public records request to DCC under ORC § 149.43 for the full licensee list
2. Wait period: 14 days for fulfillment, then enforcement options per HCJC playbook (certified mail, Court of Claims, AG/Auditor)
3. Once received, ingest as Path A

Path C is not on the critical path for Phase 3 launch. Phases 1 and 2 ship without DCC registry data.

---

## 5. Cross-reference with menu-scraped data

The P1 investigation established the brand-to-processor map for 17+ brands operating in Ohio. P4 Phase 3 work merges that knowledge with the DCC registry:

| Brand (from menu) | Processor (from P1, corrected) | Processor license (from DCC registry) | Status |
|---|---|---|---|
| Citizen by Klutch | AT-CPC of Ohio LLC | TBD via V1 | Confirmed; needs license number |
| Cookies | AT-CPC of Ohio LLC (Ohio license partnership) | TBD | Confirmed |
| Josh D | AT-CPC of Ohio LLC | TBD | Confirmed |
| Habitat by Klutch | AT-CPC of Ohio LLC | TBD | Confirmed by naming pattern |
| Klutch (own brand) | AT-CPC of Ohio LLC | TBD | Confirmed |
| Woodward Fine Cannabis | Woodward Fine Cannabis (own entity, separate from Klutch) | TBD | **Confirmed separate from Klutch.** Own cultivation, own processing, own dispensaries (woodwardcannabis.com) |
| Rythm | GTI Ohio LLC | TBD | Confirmed; verify exact entity name |
| Buckeye Relief | Buckeye Relief LLC | TBD | Confirmed |
| Butterfly Effect | Grow Ohio Pharmaceuticals LLC | TBD | Confirmed |
| The Standard | Standard Wellness Holdings LLC | TBD | Confirmed |
| The Solid | Standard Wellness Holdings LLC | TBD | Confirmed |
| Pure Ohio Wellness | Pure Ohio Wellness LLC | TBD | Confirmed |
| Hundred Percent Labs | Hundred Percent Labs LLC | TBD | Confirmed |
| King City Gardens | King City Gardens LLC | TBD | Confirmed |
| Edie Parker | TBD | TBD | Brand observed in Bloom Akron; processor unknown |
| Timeless | TBD | TBD | Brand observed; processor unknown |
| Ub Good | TBD | TBD | Brand observed; processor unknown |
| Riviera Creek | TBD | TBD | Brand observed; processor unknown |
| Airo | TBD | TBD | Brand observed; processor unknown |
| Ancient Roots | TBD | TBD | Brand observed; processor unknown |

A1 Mode B is the verification path for the TBD entries.

---

## 6. Operational concerns

| Tag | Concern | Mitigation |
|---|---|---|
| O1 | DCC registry may be hosted behind anti-scraping protections similar to HCSO | Use the HCJC enforcement playbook: GitHub Actions runner IPs blocked = constructive denial under ORC § 149.43 |
| O2 | Registry data may be stale at any given moment | Mark each `DCCLicense` record with `fetched_at`; surface staleness on entity pages ("Registry last refreshed YYYY-MM-DD") |
| O3 | License surrenders and revocations are sensitive; entity pages should reflect status accurately and immediately | Status field is required on every record; status changes trigger entity page regeneration on next build |
| O4 | DCC may publish individual officer or owner names in license records; some of these may be sensitive | Officer names appearing in DCC public records are in-scope. Personal addresses or family members are not. Filter at ingestion |
| O5 | Brand-to-processor mapping has legal sensitivity: claiming Brand X is operated by Processor Y when it isn't could be defamatory | All mapping records require `verification_status: "verified"` and at least two source citations before publication. Unverified mappings stay in the database but do not surface to user-facing pages |

---

## 7. Integration with A1

A1 (the Exa discovery agent) is the primary tool for Phase 3 entity work that the direct-scrape path cannot resolve.

| A1 Mode | Phase 3 task |
|---|---|
| Mode A (Discovery) | Identify cultivators and processors not yet in the registry; identify trade names operating under license-holder legal names |
| Mode B (Relationship Mapping) | Map the TBD brand-to-processor links in section 5; verify processor consolidation patterns |
| Mode C (Regulatory Surveillance) | Track license status changes (issuances, surrenders, suspensions) for live updates between DCC registry refreshes |
| Mode D (Claim Verification) | Verify specific brand-to-processor claims surfaced by user feedback or press reports |

Each A1 session feeds the canonical entity registry. The operator (Krass or a designated reviewer) merges A1 output between sessions.

---

## 8. Acceptance bar for Phase 3 launch

Phase 3 is shippable when:

| Metric | Bar |
|---|---|
| Processor license registry coverage | 100% of active Ohio processors represented |
| Cultivator registry coverage | 100% of active Ohio cultivators (L1 and L2) represented |
| Dispensary registry coverage | 100% of active Ohio dispensaries represented |
| Testing lab registry coverage | 100% of active Ohio testing labs represented |
| Brand-to-processor mapping verification | ≥90% of brands appearing in scraped menu data linked to a verified processor license |
| Entity page completeness | Every entity has a canonical URL, an indexable summary, and (where applicable) a product portfolio rollup |
| Source citation discipline | Every entity record carries at least one Tier 1 source citation; mapping records carry at least two |
| Registry freshness banner | Visible on every entity page, showing last refresh date |

Phase 3 is NOT launched if:
- The DCC license registry coverage is below 100% on any class
- More than 10% of brands are mapped to processors with `verification_status: "unverified"`
- A pending removal request from any processor is unresolved

---

## 9. Decisions routed to Krass

These cannot be made unilaterally:

| Tag | Decision | Default |
|---|---|---|
| DRA | When DCC blocks our scraper (likely), do we pursue 149.43 enforcement (HCJC playbook) or accept agent-assisted enrichment as canonical? | Pursue 149.43 in parallel; do not block Phase 3 on it |
| DRB | When a brand-to-processor mapping is disputed by a processor, what is the resolution workflow? | Pause the mapping, require Krass review, downgrade to `verification_status: "disputed"` until resolved |
| DRC | Do we publish license surrender or suspension as a flag on the entity page, or only as a status field? | Status field on entity page; flag if and only if the surrender is publicly notable (recall, enforcement action) |
| DRD | Display officer names on entity pages where DCC publishes them? | Yes if in public DCC record; never linked to non-business personal information |

---

## 10. Out of scope for P4

- Federal Cole Memorandum analysis
- Cross-state licensing analysis (Ohio operators with licenses in MI, MA, etc.)
- Lobbying disclosure cross-reference
- Campaign finance cross-reference
- Hemp / Delta-8 regulatory framework
- Smokable hemp distinctions under HB 523 vs. Issue 2

All of these are interesting and possibly future work. None of them are required for the consumer transparency mission OHCanna serves.

---

End of P4.
