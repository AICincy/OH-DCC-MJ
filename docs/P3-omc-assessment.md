# OhioMarijuanaCommunity.com Technical Assessment

**Matter ID:** PRC-003 (competitive reconnaissance)
**Source:** ohiomarijuanacommunity.com (OMC)
**Date:** 2026-06-20
**Method:** HTTP header inspection, HTML/JS bundle analysis, public API endpoint probing (one request per endpoint, rate-limited, identified User-Agent)
**Scope boundary:** No scraping of user-contributed content. No bulk extraction. Tech stack and feature surface characterization only.

---

## 1. Stack identification (verified)

| Layer | Technology | Evidence |
|---|---|---|
| Hosting | Windows Server, IIS 10.0 | `Server: Microsoft-IIS/10.0` response header |
| Backend | ASP.NET Core (5+) | `X-Powered-By: ASP.NET`, RFC 9110 ProblemDetails error format |
| Frontend | React + Vite | `<div id="root">` mount, hashed bundle name pattern `index-T0EpgC04.js`, 3 internal Vite signatures, 138 React mentions |
| Routing | React Router | Single React Router signature in bundle |
| Auth | Firebase Auth | 3 Firebase signatures, mixed with ASP.NET API (bolted-on pattern) |
| Maps | Leaflet (open source) | 1 Leaflet signature |
| Charts | d3 | 2 d3 signatures |
| Dates | Moment.js | 2 mentions (legacy library, deprecated 2020) |
| State management | None detected | No Redux, Zustand, Jotai, Recoil, MobX, TanStack Query, or SWR signatures |
| UI library | None detected | No MUI, Chakra, Ant Design, Radix, Bootstrap, Tailwind core signatures |
| Forms | Hand-rolled | No react-hook-form, formik, or zod signatures |
| Bundle size | 1.2 MB | Single ES module bundle |
| Component count | ~489 (rough) | Function-component pattern grep |

The HTML body is 476 bytes; everything renders client-side. There is no SSR, no SSG, and no sitemap.xml (returns 404).

---

## 2. Feature surface (from React Router route table)

The bundle contains a complete route table. Their intended feature surface:

**Dispensary features:**
- /dispensaries with sub-routes for browse, explore, maps, menus, specials, status
- /dispensary-deals, /dispensary-limits

**Brand and company directory:**
- /company-brands (public)
- Admin curation interface for brands, companies, company types

**Cannabis program:**
- /cannabis-program
- /program/medical-card, /program/state-links, /program/trends

**Community:**
- /chat, /community/chat, /discord, /reddit, /social
- /community/march-madness (bracket voting)
- /community/contribute, /community/yearly-highlights

**Knowledge base:**
- /wiki with revision workflow (admin reviews pending revisions)
- /strain-genetics, /tools/strain-genetics, /add-strain-genetics
- /growing with content, equipment, local, processing, seed-banks, seeds, tools
- /gear with concentrate, dryherbvape, glass, grinders, local

**Other:**
- /deals, /events, /add-event, /maps, /menu, /reservation, /trends
- /donate, /donations
- Full /admin panel with announcements, brands, companies, dispensaries, events, feedback, link-categories, map-categories, menu-search-analytics, social-platforms, strain-genetics, wiki revisions

**Auth and account:**
- /signin, /signout, /register, /banned
- /account/profile, /account/settings, /account/dispensary-exclusions

---

## 3. Operational state (verified)

**Findings from API probing (single request per endpoint, respectful rate limit):**

| Endpoint | Response | Interpretation |
|---|---|---|
| `/api/announcements` | `[]` (empty array, HTTP 200) | No announcements published |
| `/api/links?category=Dispensaries` | `[]` (HTTP 200) | No dispensary links in database |
| `/api/links?category=Brands` | `[]` (HTTP 200) | No brand links |
| `/api/links?category=Companies` | `[]` (HTTP 200) | No company links |
| `/api/links?category=Deals` | `[]` (HTTP 200) | No deals |
| `/api/links?category=Events` | `[]` (HTTP 200) | No events |
| `/api/links?category=Tools` | `[]` (HTTP 200) | No tools |
| `/api/links?category=Gear` | `[]` (HTTP 200) | No gear |
| `/api/links?category=Growing` | `[]` (HTTP 200) | No growing content |
| `/api/links?category=Wiki` | `[]` (HTTP 200) | No wiki content |
| `/api/links?category=Genetics` | `[]` (HTTP 200) | No genetics content |
| `/api/map-links?category=Dispensaries` | `[]` (HTTP 200) | No map markers |

Every public-facing data endpoint returns empty. Either the database genuinely is empty, or unauthenticated callers receive empty results across the board (and the site shows the same to anonymous visitors). Either way, the public experience is non-functional.

**robots.txt analysis:**
```
Disallow: /community/contribute
Disallow: /feedback
Disallow: /dispensaries/status
Disallow: /dispensaries/specials
Disallow: /dispensaries/menus
Disallow: /tools/strain-genetics
Disallow: /tools/strain-genetics/terpene
Disallow: /community/yearly-highlights
Disallow: /community/march-madness
```

These are the routes whose APIs return empty. The maintainer is hiding broken or incomplete features from search engines, which is the right defensive move, but it confirms these features are not functioning.

**Last-modified date:** 2026-06-11. The site is under active development as of nine days ago.

---

## 4. Implementation soundness (graded)

| Dimension | Grade | Notes |
|---|---|---|
| Security headers | A | Strong CSP, X-Frame-Options: DENY, nosniff, referrer-policy, x-permitted-cross-domain-policies. Someone competent configured these |
| Error format | A | RFC 9110 ProblemDetails, canonical .NET Core |
| HTTPS / HTTP/2 | A | Both present, modern |
| SEO architecture | F | SPA with no SSR means no content indexable by search engines. No sitemap.xml. Critical for a public information site |
| First-load performance | C- | 1.2 MB JS bundle, no SSR, blank shell until JS executes |
| Library currency | C | Moment.js (deprecated 2020) suggests upgrade debt |
| Architecture coherence | D | Firebase Auth + ASP.NET API is a bolted-on pattern. Two auth systems means double maintenance |
| State management | D | ~489 React components with no state management library is hard to maintain |
| Form handling | D | Hand-rolled forms at this scale invite validation drift |
| Database population | F | Every public endpoint returns empty. The site's value proposition is non-functional |
| Feature scope discipline | F | Sprawling feature surface (wiki, march madness, donations, gear shop, growing guide, strain genetics, events) for a small team |

**Headline:** the implementation is technically competent on security and API hygiene, but the architectural choices and scope ambition exceed what a small team can sustain. The empty database across every category is the killing problem. They built a Tesla and the gas tank is empty.

---

## 5. What this means for OhCanna

**Comparison to PRC-002 architecture:**

| Dimension | OMC | OhCanna (PRC-002) |
|---|---|---|
| Data source | User-contributed, admin-curated | Automated scraping of public dispensary menus |
| Day-one population | Requires users to show up | 420 products from 7 Bloom locations, real data |
| Feature scope | ~100 routes, sprawling | Vape category v1, narrow and deep |
| Rendering | SPA, no SSR, no SEO | SSG (Hugo/Astro), full SEO |
| Backend | ASP.NET Core + Firebase Auth | Python scrapers + static JSON snapshots |
| Operational burden | Continuous content moderation, wiki revision review, community management | Daily scrape, weekly snapshot, batch flag review |
| Failure mode | Empty database, ghost town | Stale data, but never empty |

**OMC's structural weakness is OhCanna's structural strength.** They depend on user contribution and have not reached critical mass. We depend on public data already on the web and ship a useful site on day one. The two models are not in direct competition; ours fills a gap their model cannot.

---

## 6. What we can leverage (legitimately)

| Item | How | Ethical posture |
|---|---|---|
| Their feature taxonomy | Reference for what features Ohio cannabis consumers want | Public route table, no IP issue |
| The gap they leave | Their empty database confirms unmet need for actual product data | Validates OhCanna's thesis |
| Their dispensary list (if we needed one) | Public DCC data is the source; we'd pull from DCC, not from them | DCC is the authoritative source |
| Their stack as a counter-example | We deliberately differ: SSG not SPA, automated not user-driven, narrow not sprawling | Pure architecture analysis |
| Map-based dispensary view | Leaflet works for us too if we add this feature in Phase 3 | Open-source library |
| Strain genetics differentiation | Don't replicate; differentiates them. Stay out of that lane | Avoids direct overlap |

---

## 7. What we should NOT do

- **Do not scrape their user-contributed content.** Their wiki entries, ratings, and community submissions are contributions to OMC, not to us. Even if their database were populated, those are not our records to take.
- **Do not replicate their feature surface.** They tried to be Yelp + Reddit + Wikipedia + Leafly for Ohio cannabis. They are none of those things because the scope was too broad. We should be one thing well: the consistency-flagged product transparency layer.
- **Do not adopt their SPA-without-SSR pattern.** It's the worst choice for a content-discovery site. SSG is the right answer.
- **Do not adopt Firebase Auth on a .NET backend.** If we ever need auth (we currently don't), single-system auth integrated with the chosen backend is cleaner.

---

## 8. Recommendations folded into PRC-002

Update the PRC-002 handoff with these specific additions:

| ID | Decision update | Source |
|---|---|---|
| DEC-007 (Toolchain) | Confirmed: Python + SSG (Hugo or Astro). Explicitly reject SPA-without-SSR | PRC-003 OMC failure mode |
| DEC-009 (NEW: Feature scope) | Phase 1: vape consistency flags only. No wiki, no community, no events, no strain genetics. Scope ambition kills small projects | PRC-003 OMC failure mode |
| DEC-010 (NEW: Map view) | Phase 3 optional: Leaflet-based dispensary map showing which dispensaries carry which flagged products. Skip Phase 1-2 | PRC-003 leverageable pattern |
| DEC-011 (NEW: SEO discipline) | Sitemap.xml mandatory. SSG mandatory. Every product gets an indexable URL. This is the inverse of OMC's choice | PRC-003 OMC failure mode |

---

## 9. Open questions for Krass

- **Krass mentioned the site has "broken features."** PRC-003 confirms the broken features are: empty database, missing announcements, robots-disallowed wiki/contribute/feedback/menus/specials/status/strain-genetics. Does Krass have additional broken-feature observations beyond what's visible to anonymous probing?
- **Krass mentioned "leveraging their model."** PRC-003 finds their model (community-driven curation) is the wrong model for OhCanna's goal (data-driven transparency). Recommend explicit reject of their model rather than incremental improvement. Confirm.

---

## 10. Coverage and limits of this assessment

- All findings are derived from publicly available HTTP responses to anonymous, rate-limited requests with an identifying User-Agent.
- No authenticated probing was performed.
- No bulk extraction of any kind was attempted.
- The "empty database" conclusion is based on 9 category probes plus announcements; it is possible authenticated users see populated content. The public experience is what matters for assessment.
- JS bundle analysis is signature-based and may miss libraries that don't leave obvious signatures.
- Component count estimate is rough.

End of PRC-003.
