"""Generic Dutchie-backend source (P2 D4 / T5).

Many dispensaries run their online menu on Dutchie, which exposes a
GraphQL endpoint (``https://dutchie.com/graphql``). A menu page issues a
POST with a ``filteredProducts`` query carrying the dispensary id (or
``cName``) plus a category filter, and receives a JSON document whose
``data.filteredProducts.products`` array holds one object per product.

The JSON shape parsed below is MODELED FROM PUBLIC DUTCHIE MENU
RESPONSES (the documented ``filteredProducts`` / menu shape: each product
carries ``name``, ``brand{name}``, ``strainType``, ``THC``/``THCContent``,
``Options``, ``Prices``, ``type``, ``id``). It has NOT been validated
against a live capture in this environment (no network access here).

LIVE VALIDATION REQUIRED before production use: record one real fixture
with ``--record-fixtures`` (which calls :meth:`fetch_raw` and writes the
raw JSON to ``ohcanna/data/fixtures/dutchie_<loc>_<cat>.json``), then
confirm the field paths in :func:`parse_products` still line up. Dutchie
periodically renames response fields; treat the selectors here as a
best-effort starting point, not a guarantee.

WAF discipline (P2 §9): one request per RATE_LIMIT_SECONDS, identified in
User-Agent, no parallel scraping against this domain.
"""
from __future__ import annotations

import json
import time
from typing import Optional

import requests

from ohcanna import USER_AGENT
from ohcanna.brands import MATCH_TABLE
from ohcanna.models import Product, VapeProduct
from ohcanna.sources.base import Source

GRAPHQL_URL = "https://dutchie.com/graphql"
RATE_LIMIT_SECONDS = 2.0
TIMEOUT = 20

# Dutchie menu categories (their ``filters.category`` enum values). The
# left key is our canonical category, the right value is the Dutchie enum.
DUTCHIE_CATEGORIES = {
    "vape": "Vaporizers",
    "flower": "Flower",
    "edibles": "Edible",
    "concentrates": "Concentrate",
    "pre-rolls": "Pre-Rolls",
    "tinctures": "Tincture",
    "topicals": "Topicals",
}

# The persisted-query-style document Dutchie's storefront posts. We send a
# plain (non-persisted) query string so the request is self-describing and
# easy to record/replay as a fixture.
FILTERED_PRODUCTS_QUERY = """
query FilteredProducts($productsFilter: ProductsFilterInput!, $page: Int, $perPage: Int) {
  filteredProducts(productsFilter: $productsFilter, page: $page, perPage: $perPage) {
    products {
      id
      name
      type
      strainType
      brand { name }
      brandName
      THC
      THCContent { range unit }
      cName
      Options
      Prices
      special
      measurements { CBD { value } THC { value } }
    }
    queryInfo { totalCount totalPages }
  }
}
""".strip()


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def build_graphql_payload(
    dispensary_id: str, dutchie_category: str, page: int = 0, per_page: int = 100
) -> dict:
    """Construct the GraphQL POST body for a menu category page.

    Pure function (no network) so tests can assert payload shape directly.
    """
    return {
        "operationName": "FilteredProducts",
        "query": FILTERED_PRODUCTS_QUERY,
        "variables": {
            "productsFilter": {
                "dispensaryId": dispensary_id,
                "types": [dutchie_category],
                "Status": "Active",
            },
            "page": page,
            "perPage": per_page,
        },
    }


def post_graphql(payload: dict, session: requests.Session | None = None) -> str:
    """POST the GraphQL body and return the raw JSON text.

    WAF discipline mirrors Bloom's ``fetch``: identified User-Agent and a
    rate-limit sleep after each request.
    """
    sess = session or requests
    resp = sess.post(
        GRAPHQL_URL,
        json=payload,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    time.sleep(RATE_LIMIT_SECONDS)
    return resp.text


# ---------- parsing helpers ----------

def _resolve_brand(raw_brand: str, name: str) -> str:
    """Map a Dutchie brand string onto the canonical registry name.

    Falls back to the registry alias table (as Bloom does) when the raw
    brand is empty/unknown, scanning the product name for a known alias.
    """
    if raw_brand:
        for alias, canonical in MATCH_TABLE:
            if alias.lower() == raw_brand.lower():
                return canonical
        return raw_brand
    haystack = name or ""
    for alias, canonical in MATCH_TABLE:
        if alias.lower() in haystack.lower():
            return canonical
    return "UNKNOWN"


def _first_price(prices) -> Optional[float]:
    if isinstance(prices, list) and prices:
        try:
            return float(prices[0])
        except (TypeError, ValueError):
            return None
    if isinstance(prices, (int, float)):
        return float(prices)
    return None


def _extract_thc(node: dict) -> Optional[float]:
    """Pull a THC percentage from the several shapes Dutchie has used."""
    thc = node.get("THC")
    if isinstance(thc, (int, float)):
        return float(thc)
    content = node.get("THCContent")
    if isinstance(content, dict):
        rng = content.get("range")
        if isinstance(rng, list) and rng:
            try:
                return float(rng[0])
            except (TypeError, ValueError):
                pass
        if isinstance(rng, (int, float)):
            return float(rng)
    meas = node.get("measurements")
    if isinstance(meas, dict):
        t = meas.get("THC")
        if isinstance(t, dict) and t.get("value") is not None:
            try:
                return float(t["value"])
            except (TypeError, ValueError):
                pass
    return None


def _option_to_grams(option) -> Optional[float]:
    """Dutchie Options look like ['1g', '0.5g', '3.5g']. Parse the first."""
    if isinstance(option, list) and option:
        option = option[0]
    if not isinstance(option, str):
        return None
    import re

    m = re.search(r"([\d.]+)\s*g", option, re.I)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def parse_products(
    raw: str, location: str, category: str
) -> list[Product]:
    """Parse a Dutchie ``filteredProducts`` JSON response into Products.

    Emits :class:`VapeProduct` for the vape category and base
    :class:`Product` otherwise (subclass coverage for other categories can
    follow once the live shape is confirmed). Robust to missing fields so a
    partial response yields whatever products it can.
    """
    doc = json.loads(raw)
    products_node = (
        doc.get("data", {}).get("filteredProducts", {}).get("products", [])
    )
    out: list[Product] = []
    for node in products_node:
        if not isinstance(node, dict):
            continue
        name = node.get("name") or ""
        raw_brand = ""
        brand_obj = node.get("brand")
        if isinstance(brand_obj, dict):
            raw_brand = brand_obj.get("name") or ""
        if not raw_brand:
            raw_brand = node.get("brandName") or ""
        brand = _resolve_brand(raw_brand, name)

        prices = node.get("Prices")
        msrp = _first_price(prices)
        sale = None
        special = node.get("special")
        # On special, Dutchie carries [sale, original]; surface both.
        if special and isinstance(prices, list) and len(prices) >= 2:
            sale = _first_price(prices[0:1])
            msrp = _first_price(prices[1:2])

        thc = _extract_thc(node)
        strain = node.get("strainType") or None
        if isinstance(strain, str):
            strain = strain.lower() or None
        product_id = str(node.get("id") or node.get("cName") or "")

        common = dict(
            source="dutchie",
            location=location,
            category=category,
            product_id=product_id,
            product_url="",
            name=name,
            brand=brand,
            product_format=node.get("type") or "UNKNOWN",
            strain_type=strain,
            thc_percent=thc,
            sale_price=sale,
            msrp=msrp,
            discount_percent=None,
            scraped_at=_now(),
        )
        if category == "vape":
            out.append(
                VapeProduct(
                    **common,
                    cart_size_grams=_option_to_grams(node.get("Options")),
                )
            )
        else:
            out.append(Product(**common))
    return out


class DutchieSource(Source):
    """Generic Dutchie GraphQL menu scraper.

    Configure with a Dutchie ``dispensary_id`` (or ``cName``) plus the
    categories to scrape. ``list_locations()`` returns the configured
    location keys mapping to dispensary ids.

    Abstract methods implemented: ``list_locations``, ``list_categories``,
    ``fetch_raw``, ``parse_raw``.
    """

    name = "dutchie"
    raw_ext = "json"

    def __init__(
        self,
        dispensaries: dict[str, str] | None = None,
        categories: list[str] | None = None,
        session: requests.Session | None = None,
    ) -> None:
        # location_key -> dispensary id/cName. A demo entry keeps the source
        # importable + ABC-conforming with no config; real deployments pass
        # verified ids.
        self.dispensaries = dispensaries or {"demo": "demo-dispensary-id"}
        self.categories = categories or list(DUTCHIE_CATEGORIES.keys())
        self.session = session

    def list_locations(self) -> list[str]:
        return list(self.dispensaries.keys())

    def list_categories(self) -> list[str]:
        return list(self.categories)

    def fetch_raw(self, location: str, category: str) -> str:
        if location not in self.dispensaries:
            raise ValueError(f"unknown dutchie location: {location}")
        if category not in DUTCHIE_CATEGORIES:
            raise ValueError(f"unknown dutchie category: {category}")
        payload = build_graphql_payload(
            self.dispensaries[location], DUTCHIE_CATEGORIES[category]
        )
        return post_graphql(payload, self.session)

    def parse_raw(self, raw: str, location: str, category: str) -> list[Product]:
        return parse_products(raw, location, category)
