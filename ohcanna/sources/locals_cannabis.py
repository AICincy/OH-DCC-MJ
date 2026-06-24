"""Locals Cannabis source (P2 §5 T1 - highest priority).

Locals Cannabis operates retail dispensaries in Ohio. This is a SCAFFOLD:
the menu backend has NOT been confirmed in this (offline, no-network)
environment.

Two delivery paths are anticipated, gated by what a live capture reveals:

1. Dutchie backend (common for Ohio dispensaries). If a live check shows
   Locals serves its menu from Dutchie, prefer delegating to
   :class:`ohcanna.sources.dutchie.DutchieSource` with Locals' verified
   dispensary ids. :func:`build_dutchie_delegate` returns a preconfigured
   DutchieSource for that path; its dispensary ids are PLACEHOLDERS.

2. Custom / SSR HTML storefront. If Locals does NOT use Dutchie, the
   HTML ``parse_raw`` below mirrors Bloom's card-parsing approach. The CSS
   selectors and URL/price regexes are UNVERIFIED guesses and MUST be
   corrected against a recorded fixture.

LIVE VALIDATION REQUIRED before production use:
  * Confirm the backend (Dutchie vs custom HTML).
  * Verify each location slug / dispensary id below (placeholders).
  * If HTML: record a fixture via ``--record-fixtures`` and fix the
    selectors in :func:`parse_cards`.

WAF discipline (P2 §9): one request per RATE_LIMIT_SECONDS, identified in
User-Agent, no parallel scraping.
"""
from __future__ import annotations

import re
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup

from ohcanna import USER_AGENT
from ohcanna.brands import MATCH_TABLE
from ohcanna.models import Product
from ohcanna.sources.base import Source
from ohcanna.sources.dutchie import DUTCHIE_CATEGORIES, DutchieSource

RATE_LIMIT_SECONDS = 2.0
TIMEOUT = 20

# Known Locals Cannabis Ohio retail locations. PLACEHOLDER slugs/ids - the
# location keys are real city markets, but the menu slugs and any Dutchie
# dispensary ids MUST be verified against the live site before use.
LOCALS_LOCATIONS = {
    "cincinnati": "cincinnati",  # TODO: verify menu slug / dispensary id
    "dayton": "dayton",          # TODO: verify
    "columbus": "columbus",      # TODO: verify
    "monroe": "monroe",          # TODO: verify
}

LOCALS_CATEGORIES = list(DUTCHIE_CATEGORIES.keys())

# PLACEHOLDER. If Locals is on Dutchie, map each location to its real
# Dutchie dispensary id here (capture from the live menu's GraphQL POST).
LOCALS_DUTCHIE_DISPENSARY_IDS: dict[str, str] = {
    "cincinnati": "TODO-locals-cincinnati-dispensary-id",
    "dayton": "TODO-locals-dayton-dispensary-id",
    "columbus": "TODO-locals-columbus-dispensary-id",
    "monroe": "TODO-locals-monroe-dispensary-id",
}


def build_dutchie_delegate(
    categories: list[str] | None = None,
    session: requests.Session | None = None,
) -> DutchieSource:
    """Return a DutchieSource preconfigured with Locals' (placeholder) ids.

    Use this once a live check confirms Locals serves its menu via Dutchie.
    The dispensary ids in :data:`LOCALS_DUTCHIE_DISPENSARY_IDS` are
    placeholders and must be replaced with verified values first.
    """
    return DutchieSource(
        dispensaries=dict(LOCALS_DUTCHIE_DISPENSARY_IDS),
        categories=categories or LOCALS_CATEGORIES,
        session=session,
    )


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _url(location_slug: str, category: str) -> str:
    # PLACEHOLDER URL shape - verify the real menu path against the site.
    return f"https://localscannabis.com/menu/{location_slug}/{category}"


def fetch(url: str, session: requests.Session | None = None) -> str:
    sess = session or requests
    resp = sess.get(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        },
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    time.sleep(RATE_LIMIT_SECONDS)
    return resp.text


def _resolve_brand(label: str) -> tuple[str, str]:
    """(name, brand) from a label, reusing the brand alias table."""
    cleaned = label.strip()
    for alias, canonical in MATCH_TABLE:
        m = re.search(rf"\b{re.escape(alias)}\b", cleaned, re.IGNORECASE)
        if m:
            name = cleaned[: m.start()].strip() or cleaned
            return (name, canonical)
    return (cleaned, "UNKNOWN")


def parse_cards(html: str, location: str, category: str) -> list[Product]:
    """Parse Locals product cards from rendered HTML.

    TODO (LIVE VALIDATION): every selector and regex here is an
    UNVERIFIED guess. Record a fixture and correct:
      * the card container selector (``div.product-card`` below)
      * the title/label selector
      * price / THC extraction
    Robust to missing fields so it never raises on an unexpected shape.
    """
    soup = BeautifulSoup(html, "lxml")
    out: list[Product] = []
    # TODO: confirm the real card selector.
    for card in soup.select("div.product-card, li.product, article.product"):
        text = card.get_text(" ", strip=True)
        # TODO: confirm the label/title element.
        title_el = card.select_one(
            ".product-title, .product-name, h3, h2, a"
        )
        label = title_el.get_text(" ", strip=True) if title_el else text
        if not label:
            continue
        name, brand = _resolve_brand(label)

        prices = re.findall(r"\$\s*([\d,]+\.\d{2})", text)
        msrp = float(prices[0].replace(",", "")) if prices else None
        sale = float(prices[1].replace(",", "")) if len(prices) >= 2 else None
        if sale is not None and msrp is not None and sale > msrp:
            sale, msrp = msrp, sale  # normalize: sale <= msrp

        thc_m = re.search(r"(\d+(?:\.\d+)?)\s*%\s*THC", text, re.I)
        thc = float(thc_m.group(1)) if thc_m else None
        strain_m = re.search(r"\b(indica|sativa|hybrid)\b", text, re.I)
        strain = strain_m.group(1).lower() if strain_m else None

        link = card.select_one("a[href]")
        href = link["href"] if link and link.has_attr("href") else ""
        product_url = (
            href
            if href.startswith("http")
            else (f"https://localscannabis.com{href}" if href else "")
        )

        out.append(
            Product(
                source="locals_cannabis",
                location=location,
                category=category,
                product_id=href or label,  # TODO: stable id from live data
                product_url=product_url,
                name=name,
                brand=brand,
                product_format="UNKNOWN",  # TODO: derive from live data
                strain_type=strain,
                thc_percent=thc,
                sale_price=sale,
                msrp=msrp,
                discount_percent=None,
                scraped_at=_now(),
            )
        )
    return out


class LocalsCannabisSource(Source):
    """Locals Cannabis (Ohio) menu scraper - HTML-parse scaffold.

    Abstract methods implemented: ``list_locations``, ``list_categories``,
    ``fetch_raw``, ``parse_raw``.

    If a live check confirms a Dutchie backend, switch to the delegate via
    :func:`build_dutchie_delegate` instead of this HTML path.
    """

    name = "locals_cannabis"
    raw_ext = "html"

    def __init__(self, session: requests.Session | None = None) -> None:
        self.session = session

    def list_locations(self) -> list[str]:
        return list(LOCALS_LOCATIONS.keys())

    def list_categories(self) -> list[str]:
        return list(LOCALS_CATEGORIES)

    def fetch_raw(self, location: str, category: str) -> str:
        if location not in LOCALS_LOCATIONS:
            raise ValueError(f"unknown locals location: {location}")
        if category not in LOCALS_CATEGORIES:
            raise ValueError(f"unknown locals category: {category}")
        return fetch(_url(LOCALS_LOCATIONS[location], category), self.session)

    def parse_raw(self, raw: str, location: str, category: str) -> list[Product]:
        return parse_cards(raw, location, category)
