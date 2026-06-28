"""Klutch Cannabis source — cultivator catalog + per-page lab data (T5-family).

Klutch publishes its catalog through a WordPress REST API
(``/wp-json/wp/v2/cp_product``) that carries product names, brand/category
taxonomy, and terpene *names* — but NOT THC, terpene values, or pricing.
Those live in a Dutchie/JointCommerce JSON record embedded in each product
page's ``<div id="root" data-page="...">`` attribute (HTML-entity encoded).

So a Klutch category scrape is two stages, both inside :meth:`fetch_raw`:

  1. Page the WP API for the Klutch-core brands and keep the products whose
     category maps to the requested canonical category, collecting each
     product's page URL plus catalog-derived fields (strain, product type,
     extraction method) that the lab record does not carry cleanly.
  2. Fetch each product page and pull out the embedded lab record (or, when
     the primary product is out of stock at the location encoded in the URL,
     the first related product that carries lab data — a *fallback*).

:func:`parse_raw` merges catalog + lab per product, deduplicates by
``enterpriseProductId``, marks fallback rows, and emits the category
``Product`` subclass. Because Klutch is a single statewide cultivator
catalog (no per-store menus), it exposes one pseudo-location, ``catalog``.

MODELED FROM REAL CAPTURES (2026-06-27) but NOT validated against a live
run in this environment (no outbound network here). LIVE VALIDATION
REQUIRED before production use: record fixtures with ``--record-fixtures``
and confirm the WP field paths and the ``data-page`` shape still line up.
The per-page fetch is N+1, so tune the inter-request delay with
``--delay`` (default :data:`RATE_LIMIT_SECONDS`).

WAF discipline (P2 §9): one request per ``self.delay`` seconds, identified
in the User-Agent, no parallel scraping against this domain.
"""
from __future__ import annotations

import html
import json
import re
import time
from typing import Optional

import requests

from ohcanna import USER_AGENT
from ohcanna.brands import MATCH_TABLE
from ohcanna.models import (
    ConcentrateProduct,
    EdibleProduct,
    FlowerProduct,
    PreRollProduct,
    Product,
    TinctureProduct,
    VapeProduct,
)
from ohcanna.sources.base import Source

WP_BASE = "https://www.klutchcannabis.com/wp-json/wp/v2"
RATE_LIMIT_SECONDS = 2.0
TIMEOUT = 20
WP_PER_PAGE = 100
LOCATION = "catalog"

# Klutch-core brand term ids (WP ``cp_product_brand``). Third-party brands
# sold in Klutch dispensaries are intentionally excluded — this source is the
# cultivator's own catalog.
KLUTCH_BRAND_IDS = {
    1274: "Klutch",
    1536: "Citizen by Klutch",
    1549: "Habitat by Klutch",
    1365: "The Citizen by Klutch",  # legacy; resolves to "Citizen by Klutch"
}

# WP ``cp_product_category`` term id -> canonical category. Accessories (1198)
# and Topicals (1158) are skipped: no flag rules and no lab data of interest.
KLUTCH_CATEGORY_IDS = {
    1266: "vape",          # Vaporizers
    1181: "concentrates",  # Concentrates
    1170: "flower",        # Flower
    1184: "pre-rolls",     # Pre-rolls
    1166: "edibles",       # Edibles
    1162: "tinctures",     # Tinctures
}
CATEGORY_NAMES = {
    1266: "Vaporizers",
    1181: "Concentrates",
    1170: "Flower",
    1184: "Pre-rolls",
    1166: "Edibles",
    1162: "Tinctures",
}
# canonical category -> the WP category term ids that map onto it
ENGINE_TO_KLUTCH_CAT_IDS: dict[str, set[int]] = {}
for _cid, _eng in KLUTCH_CATEGORY_IDS.items():
    ENGINE_TO_KLUTCH_CAT_IDS.setdefault(_eng, set()).add(_cid)
CATEGORIES = list(ENGINE_TO_KLUTCH_CAT_IDS.keys())

STRAIN_TYPE_NAMES = {
    1180: "Hybrid",
    1192: "Indica",
    1176: "Sativa",
    1234: "Indica Hybrid",
    1703: "Sativa Hybrid",
    1323: "High CBD",
    1519: "1:1",
    1204: "THC",
    1534: "20:1",
    1561: "2:1",
}

# Cannabinoid names that are THC itself / a roll-up, not a *secondary*
# (minor) cannabinoid. Compared against the cleaned, upper-cased name.
_NOT_SECONDARY = {"THC", "THCA", "THC-D9", "THCD9", "D9-THC", "DELTA 9 THC", "TAC"}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------------------------------------------------------------------------
# catalog-side helpers (ported from the standalone klutch_scraper.py)
# ---------------------------------------------------------------------------

_STRAIN_SUFFIXES = [
    r"\s+Live\s+Resin.*$",
    r"\s+Live\s+Hash\s+Rosin.*$",
    r"\s+Live\s+Badder.*$",
    r"\s+Live\s+Diamonds.*$",
    r"\s+Cold\s+Cure.*$",
    r"\s+CO2\s+(?:Cartridge|Luster|Cart).*$",
    r"\s+Full\s+Spectrum.*$",
    r"\s+Distillate.*$",
    r"\s+Disposable\s+Vape.*$",
    r"\s+Luster\s+Pod.*$",
    r"\s+Cartridge.*$",
    r"\s+Cart\s*$",
    r"\s+Pre[\s-]?Roll.*$",
    r"\s+Small\s+Buds.*$",
    r"\s+Smalls.*$",
    r"\s+Gummies.*$",
    r"\s+Chocolates?.*$",
    r"\s+Capsules?.*$",
    r"\s+Mints?.*$",
    r"\s+Tincture.*$",
    r"\s+i?Krusher.*$",
    r"\s+AVD.*$",
    r"\s+\d+(?:\.\d+)?g\s*$",
    r"\s+\d+pk\s*$",
    r"\s+\d+pc\s*$",
    r"\s+\d{2,3}-\d{2,3}u\b.*$",  # rosin micron range, e.g. "90-159u"
]


def normalize_strain_name(title: str) -> str:
    """Strip product-type / format suffixes off a title to get the strain.

    ``'Apricot Gelato Live Resin Disposable Vape'`` -> ``'Apricot Gelato'``.
    """
    name = title or ""
    for pattern in _STRAIN_SUFFIXES:
        name = re.sub(pattern, "", name, flags=re.IGNORECASE)
    return name.strip()


def infer_product_type(title: str, category_name: str) -> str:
    """Infer a product type from the title and WP category name."""
    t = (title or "").lower()
    c = (category_name or "").lower()
    if "vaporizer" in c:
        if "luster" in t:
            return "Luster Pod"
        if "disposable" in t:
            return "Disposable Vape"
        if "cartridge" in t or "cart" in t:
            return "Cartridge"
        return "Vape"
    if "concentrate" in c:
        if "badder" in t:
            return "Live Badder"
        if "diamonds" in t:
            return "Live Diamonds & Sauce"
        if "rosin" in t:
            return "Live Hash Rosin"
        if "resin" in t:
            return "Live Resin"
        return "Concentrate"
    if "flower" in c:
        return "Small Buds" if "small" in t else "Flower"
    if "pre-roll" in c:
        return "Pre-roll"
    if "edible" in c:
        if "gumm" in t:
            return "Gummies"
        if "chocolate" in t:
            return "Chocolate"
        if "mint" in t:
            return "Mints"
        if "capsule" in t:
            return "Capsules"
        return "Edible"
    if "tincture" in c:
        return "Tincture"
    return "Other"


def infer_extraction_method(title: str) -> Optional[str]:
    """Infer the extraction method from a product title (None if n/a)."""
    t = (title or "").lower()
    if "live resin" in t:
        return "Live Resin"
    if "live hash rosin" in t or "live rosin" in t:
        return "Live Hash Rosin"
    if "live badder" in t or "live diamonds" in t:
        return "Live Resin"
    if "full spectrum" in t:
        return "Full Spectrum (CO2)"
    if "co2" in t:
        return "CO2"
    if "distillate" in t:
        return "Distillate"
    return None


def _is_live_method(method: Optional[str]) -> bool:
    return bool(method) and "live" in method.lower()


def _resolve_brand(raw_brand: str, name: str) -> str:
    """Map a Klutch brand string onto the canonical registry name.

    Mirrors :func:`ohcanna.sources.dutchie._resolve_brand`: alias-match the
    raw brand, else scan the product name, else ``UNKNOWN``.
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


def _option_to_grams(option) -> Optional[float]:
    """Parse a variant option label into grams.

    Handles explicit grams (``"1g"``, ``"2.83g"``) and the eighth/quarter/
    half/ounce labels dispensaries use (``"1/8oz"`` -> 3.5, ``"1oz"`` -> 28).
    """
    if not isinstance(option, str):
        return None
    s = option.strip().lower()
    m = re.search(r"([\d.]+)\s*g\b", s)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    oz_map = {"1/8": 3.5, "1/4": 7.0, "1/2": 14.0, "1": 28.0}
    m = re.search(r"(1/8|1/4|1/2|1)\s*oz", s)
    if m:
        return oz_map.get(m.group(1))
    return None


def _count_from_label(*texts: str) -> Optional[int]:
    """Pull a pack count from any of the given strings ('5pk', '10 pc')."""
    for text in texts:
        m = re.search(r"(\d+)\s*p[kc]\b", (text or "").lower())
        if m:
            return int(m.group(1))
    return None


# ---------------------------------------------------------------------------
# page-side helpers (ported from the standalone klutch_lab_extractor.py)
# ---------------------------------------------------------------------------

def extract_data_page(page_html: str) -> Optional[dict]:
    """Extract and parse the ``div#root data-page`` JSON from page HTML."""
    if not page_html:
        return None
    match = re.search(r'id="root"\s+data-page="([^"]+)"', page_html)
    if not match:
        return None
    try:
        return json.loads(html.unescape(match.group(1)))
    except json.JSONDecodeError:
        return None


def _has_thc(product: dict) -> bool:
    return bool(
        isinstance(product, dict)
        and (product.get("potencyThc") or {}).get("range")
    )


def select_lab_product(data_page: dict) -> tuple[Optional[dict], bool]:
    """Return ``(product_record, fallback)`` from a parsed data-page.

    The primary ``props.data.product`` is preferred. When it is ``None``
    (out of stock at the dispensary encoded in the URL) the first related
    product carrying THC is used and ``fallback`` is ``True``.
    """
    data = (data_page or {}).get("props", {}).get("data", {})
    product = data.get("product")
    if _has_thc(product):
        return product, False
    related = data.get("related_products", [])
    candidates = related if isinstance(related, list) else list(related.values()) if isinstance(related, dict) else []
    for rp in candidates:
        if _has_thc(rp):
            return rp, True
    return (product if isinstance(product, dict) else None), False


def _clean_name(name: str) -> str:
    """Normalize a cannabinoid/terpene label.

    Real captures carry a malformed total-cannabinoids key,
    ``TAC" - Total Active Cannabinoids``; cut at the first quote, paren, or
    " - " so it collapses to a clean ``TAC`` (which is then excluded as a
    roll-up, not a secondary cannabinoid).
    """
    return re.split(r'["(]| - ', name or "")[0].strip().strip('"').strip()


def _range_first(node) -> Optional[float]:
    rng = (node or {}).get("range") if isinstance(node, dict) else None
    if isinstance(rng, list) and rng:
        try:
            return float(rng[0])
        except (TypeError, ValueError):
            return None
    return None


def lab_to_fields(product: dict) -> dict:
    """Map a raw JointCommerce product record onto our flat lab fields."""
    out: dict = {}
    out["lab_name"] = (product.get("name") or "").strip("| ").strip()
    brand = product.get("brand")
    out["lab_brand"] = brand.get("name", "") if isinstance(brand, dict) else ""
    out["lab_strain_type"] = product.get("strainType") or ""
    out["thc_percent"] = _range_first(product.get("potencyThc"))
    out["cbd_pct"] = _range_first(product.get("potencyCbd"))
    out["effects"] = product.get("effects", [])
    out["tags"] = product.get("tags", [])
    out["enterprise_product_id"] = product.get("enterpriseProductId", "")
    out["pos_sku"] = (product.get("posMetaData") or {}).get("sku", "")
    out["product_batch_id"] = product.get("productBatchId", "")

    # Cannabinoid panel: full numeric dict + the secondary (minor) names.
    cannabinoids: dict[str, dict] = {}
    secondary: list[str] = []
    for c in product.get("cannabinoids", []) or []:
        name = _clean_name((c.get("cannabinoid") or {}).get("name", ""))
        value = c.get("value")
        if not name or value is None:
            continue
        cannabinoids[name] = {"value": value, "unit": c.get("unit", "PERCENTAGE")}
        if name.upper() not in _NOT_SECONDARY:
            secondary.append(name)
    out["cannabinoids"] = cannabinoids
    out["secondary_cannabinoids"] = secondary

    # Terpenes: numeric dict + total + the names.
    terpene_values: dict[str, float] = {}
    total = 0.0
    for t in product.get("terpenes", []) or []:
        terp = t.get("terpene") or {}
        name = terp.get("name") or t.get("name") or ""
        value = t.get("value")
        if not name or value is None:
            continue
        terpene_values[name] = value
        try:
            total += float(value)
        except (TypeError, ValueError):
            pass
    out["terpene_values"] = terpene_values
    out["terpene_names"] = list(terpene_values.keys())
    out["total_terpenes_pct"] = round(total, 2)

    # Variant pricing.
    pricing = []
    for v in product.get("variants", []) or []:
        pricing.append({
            "option": v.get("option", ""),
            "price_med": v.get("priceMed"),
            "price_rec": v.get("priceRec"),
            "special_price_med": v.get("specialPriceMed"),
            "special_price_rec": v.get("specialPriceRec"),
            "quantity_in_stock": v.get("quantity"),
        })
    out["pricing"] = pricing
    return out


def _representative_variant(pricing: list[dict]) -> Optional[dict]:
    """Pick the variant whose price/size feed the base model (first priced)."""
    for v in pricing:
        if v.get("price_rec") is not None:
            return v
    return pricing[0] if pricing else None


# ---------------------------------------------------------------------------
# merge: catalog + lab -> Product subclass
# ---------------------------------------------------------------------------

def _build_product(entry: dict, category: str, location: str) -> Optional[Product]:
    catalog = entry.get("catalog") or {}
    lab_raw = entry.get("lab")
    fallback = bool(entry.get("fallback"))
    if not isinstance(lab_raw, dict):
        return None
    lab = lab_to_fields(lab_raw)

    strain = catalog.get("strain") or normalize_strain_name(lab["lab_name"])
    product_name = catalog.get("title") or lab["lab_name"]
    product_type = catalog.get("product_type") or "Other"
    extraction = catalog.get("extraction_method") or infer_extraction_method(product_name)
    brand = _resolve_brand(catalog.get("brand") or lab["lab_brand"], product_name)
    strain_type = (catalog.get("strain_type") or lab["lab_strain_type"] or "").lower() or None

    # Fold the extraction method into product_format so the existing vape
    # rules (which scan product_format for "live"/"full spec"/"distillate")
    # see Klutch's extraction signal, which otherwise lives only in metadata.
    product_format = f"{extraction} {product_type}".strip() if extraction else product_type

    rep = _representative_variant(lab["pricing"])
    msrp = rep.get("price_rec") if rep else None
    sale = rep.get("special_price_rec") if rep else None
    discount = None
    if msrp and sale and msrp > sale:
        discount = round((1 - sale / msrp) * 100)
    size = _option_to_grams(rep.get("option")) if rep else None

    extra = {
        "strain": strain,
        "product_name": product_name,
        "product_type": product_type,
        "extraction_method": extraction,
        "cbd_pct": lab["cbd_pct"],
        "cannabinoids": lab["cannabinoids"],
        "terpene_values": lab["terpene_values"],
        "total_terpenes_pct": lab["total_terpenes_pct"],
        "effects": lab["effects"],
        "tags": lab["tags"],
        "pricing": lab["pricing"],
        "pos_sku": lab["pos_sku"],
        "product_batch_id": lab["product_batch_id"],
        "enterprise_product_id": lab["enterprise_product_id"],
        "fallback": fallback,
    }

    common = dict(
        source="klutch",
        location=location,
        category=category,
        product_id=str(lab["enterprise_product_id"] or catalog.get("url") or product_name),
        product_url=catalog.get("url") or "",
        name=strain,
        brand=brand,
        product_format=product_format,
        strain_type=strain_type,
        thc_percent=lab["thc_percent"],
        sale_price=sale,
        msrp=msrp,
        discount_percent=discount,
        scraped_at=_now(),
        extra=extra,
    )

    terps = lab["terpene_names"] or catalog.get("terpenes") or []
    if category == "vape":
        return VapeProduct(
            **common,
            cart_size_grams=size,
            secondary_cannabinoids=lab["secondary_cannabinoids"],
            terpenes=terps,
        )
    if category == "concentrates":
        return ConcentrateProduct(
            **common,
            weight_grams=size,
            extraction_method=extraction,
            terpenes=terps,
        )
    if category == "flower":
        return FlowerProduct(**common, package_size_grams=size, terpenes=terps)
    if category == "pre-rolls":
        count = _count_from_label(product_name, (rep or {}).get("option", ""))
        return PreRollProduct(**common, weight_grams=size, count_per_package=count)
    if category == "edibles":
        count = _count_from_label(product_name, (rep or {}).get("option", ""))
        return EdibleProduct(**common, count_per_package=count)
    if category == "tinctures":
        return TinctureProduct(**common)
    return Product(**common)


def parse_products(raw: str, location: str, category: str) -> list[Product]:
    """Merge the combined catalog+lab document into deduplicated Products.

    Dedup key is ``enterpriseProductId`` (falling back to the product URL).
    A non-fallback record wins over a fallback one for the same key.
    """
    doc = json.loads(raw)
    entries = doc.get("products", []) if isinstance(doc, dict) else []
    by_key: dict[str, Product] = {}
    order: list[str] = []
    for entry in entries:
        product = _build_product(entry, category, location)
        if product is None:
            continue
        key = product.extra.get("enterprise_product_id") or product.product_url or product.name
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = product
            order.append(key)
        elif existing.extra.get("fallback") and not product.extra.get("fallback"):
            by_key[key] = product  # prefer the real (non-fallback) record
    return [by_key[k] for k in order]


# ---------------------------------------------------------------------------
# network
# ---------------------------------------------------------------------------

def _wp_get(endpoint: str, params: dict, session: requests.Session | None, delay: float):
    """GET a WP REST endpoint, return parsed JSON (list). Rate-limit after."""
    sess = session or requests
    query = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{WP_BASE}/{endpoint}?{query}"
    resp = sess.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    time.sleep(delay)
    return json.loads(resp.text)


def _fetch_page(url: str, session: requests.Session | None, delay: float) -> Optional[str]:
    sess = session or requests
    resp = sess.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    time.sleep(delay)
    return resp.text


def discover_catalog(category: str, session, delay: float) -> list[dict]:
    """Page the WP API for Klutch brands; return catalog dicts in `category`."""
    want_cats = ENGINE_TO_KLUTCH_CAT_IDS[category]
    seen_urls: set[str] = set()
    catalog: list[dict] = []
    for brand_id, brand_name in KLUTCH_BRAND_IDS.items():
        page = 1
        while True:
            data = _wp_get(
                "cp_product",
                {"cp_product_brand": brand_id, "per_page": WP_PER_PAGE, "page": page},
                session,
                delay,
            )
            if not data:
                break
            for p in data:
                cat_ids = set(p.get("cp_product_category", []) or [])
                if not (cat_ids & want_cats):
                    continue
                url = p.get("link", "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                raw_title = html.unescape(p.get("title", {}).get("rendered", "")).strip()
                title = re.sub(r"\s*\|.*$", "", re.sub(r"^\|?\s*", "", raw_title)).strip()
                cat_name = next(
                    (CATEGORY_NAMES[c] for c in p.get("cp_product_category", []) if c in CATEGORY_NAMES),
                    "",
                )
                strain_ids = p.get("cp_product_strain_type", []) or []
                strain_type = next(
                    (STRAIN_TYPE_NAMES[s] for s in strain_ids if s in STRAIN_TYPE_NAMES), ""
                )
                catalog.append({
                    "title": title,
                    "strain": normalize_strain_name(title),
                    "product_type": infer_product_type(title, cat_name),
                    "extraction_method": infer_extraction_method(title),
                    "strain_type": strain_type,
                    "brand": brand_name,
                    "url": url,
                })
            if len(data) < WP_PER_PAGE:
                break
            page += 1
    return catalog


class KlutchSource(Source):
    """Klutch cultivator catalog + per-product lab/pricing scraper.

    Abstract methods implemented: ``list_locations``, ``list_categories``,
    ``fetch_raw``, ``parse_raw``. The per-page fetch is N+1; ``delay``
    (settable via the CLI ``--delay`` flag) controls the inter-request sleep.
    """

    name = "klutch"
    raw_ext = "json"

    def __init__(
        self,
        session: requests.Session | None = None,
        delay: float = RATE_LIMIT_SECONDS,
    ) -> None:
        self.session = session
        self.delay = delay

    def list_locations(self) -> list[str]:
        return [LOCATION]

    def list_categories(self) -> list[str]:
        return list(CATEGORIES)

    def fetch_raw(self, location: str, category: str) -> str:
        if location != LOCATION:
            raise ValueError(f"unknown klutch location: {location}")
        if category not in ENGINE_TO_KLUTCH_CAT_IDS:
            raise ValueError(f"unknown klutch category: {category}")

        catalog = discover_catalog(category, self.session, self.delay)
        products = []
        for item in catalog:
            page = _fetch_page(item["url"], self.session, self.delay)
            data_page = extract_data_page(page) if page else None
            lab, fallback = select_lab_product(data_page) if data_page else (None, False)
            products.append({"catalog": item, "lab": lab, "fallback": fallback})

        return json.dumps({
            "source": "klutch",
            "location": location,
            "category": category,
            "scraped_at": _now(),
            "products": products,
        })

    def parse_raw(self, raw: str, location: str, category: str) -> list[Product]:
        return parse_products(raw, location, category)
