"""Bloom Marijuana source.

Bloom serves SSR HTML from a Next.js storefront. We fetch the rendered
HTML for `/oh/<dispensary>/recreational-menu/<category>`, parse product
cards, and emit category-specific Product subclasses.

WAF discipline (P2 §9): one request per RATE_LIMIT_SECONDS, identified
in User-Agent, no parallel scraping against this domain.
"""
from __future__ import annotations

import re
import time
from typing import Callable, Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from bs4.element import Tag

from ohcanna import USER_AGENT
from ohcanna.brands import MATCH_TABLE
from ohcanna.models import (
    ConcentrateProduct,
    EdibleProduct,
    FlowerProduct,
    PreRollProduct,
    Product,
    TinctureProduct,
    TopicalProduct,
    VapeProduct,
)
from ohcanna.sources.base import Source

RATE_LIMIT_SECONDS = 2.0
TIMEOUT = 20

BLOOM_LOCATIONS = {
    "akron": "akron-dispensary",
    "athens": "athens-dispensary",
    "columbus_west": "west-columbus-dispensary",
    "columbus": "columbus-dispensary",
    "massillon": "massillon-dispensary",
    "painesville": "painesville-dispensary",
    "seven_mile": "sevenmile-dispensary",
}

BLOOM_CATEGORIES = [
    "vape",
    "flower",
    "edibles",
    "concentrates",
    "pre-rolls",
    "tinctures",
    "topicals",
]


def _url(location_slug: str, category: str) -> str:
    return f"https://bloommarijuana.com/oh/{location_slug}/recreational-menu/{category}"


# ---------- shared helpers (ported from POC) ----------

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


def parse_product_url(href: str) -> tuple[str, Optional[float]]:
    """Bloom URLs: /product/<id>+<weight_slug>/<slug>"""
    path = urlparse(href).path
    m = re.search(r"/product/(\d+)\+([a-z_]+)/", path)
    if not m:
        return ("", None)
    product_id = m.group(1)
    weight_slug = m.group(2)
    weight_map = {
        "gram": 1.0,
        "half_gram": 0.5,
        "two_gram": 2.0,
        "three_gram": 3.0,
    }
    return (product_id, weight_map.get(weight_slug))


def extract_price_pair(
    card_text: str,
) -> tuple[Optional[float], Optional[float], Optional[int]]:
    prices = re.findall(r"\$\s*([\d,]+\.\d{2})", card_text)
    discount_m = re.search(r"(\d+)%\s*OFF", card_text)
    discount = int(discount_m.group(1)) if discount_m else None
    if len(prices) >= 2:
        sale = float(prices[0].replace(",", ""))
        msrp = float(prices[1].replace(",", ""))
        return (sale, msrp, discount)
    if len(prices) == 1:
        msrp = float(prices[0].replace(",", ""))
        return (None, msrp, None)
    return (None, None, None)


def extract_thc(card_text: str) -> Optional[float]:
    m = re.search(r"(\d+(?:\.\d+)?)\s*%\s*THC", card_text)
    return float(m.group(1)) if m else None


def extract_secondary_cannabinoids(card_text: str) -> list[str]:
    after_thc = re.search(
        r"%\s*THC\s*(.*?)(?:\$|Myrcene|Limonene|Caryo|Linalool|Terpinolene|Pinene|Humulene|Ocimene)",
        card_text,
    )
    if not after_thc:
        return []
    blob = after_thc.group(1)
    found = []
    for token in ("CBDA", "THCA", "CBD", "CBN", "CBG", "CBC"):
        if re.search(rf"\b{token}\b", blob):
            found.append(token)
    return sorted(set(found))


_TERPENE_IMG_MAP = {
    "betamyrcene": "Myrcene",
    "limonene": "Limonene",
    "betacaryophyllene": "Caryo",
    "linalool": "Linalool",
    "terpinolene": "Terpinolene",
    "alphapinene": "Pinene",
    "humulene": "Humulene",
    "ocimene": "Ocimene",
}


def extract_terpenes_from_imgs(card_tag: Tag) -> list[str]:
    terpenes: list[str] = []
    for img in card_tag.find_all("img", alt=True):
        alt = img["alt"].lower()
        canon = _TERPENE_IMG_MAP.get(alt)
        if canon and canon not in terpenes:
            terpenes.append(canon)
    return terpenes


_FORMAT_KEYWORDS = [
    "live rosin cart pks",
    "live rosin disposable",
    "live resin disposable",
    "live rosin cart",
    "live resin cart",
    "cured resin cart",
    "full spec luster pod",
    "full spec disposable",
    "full spec cart",
    "distillate disposable",
    "distillate cart",
    "CO2 cart",
    "live badder",
    "live resin",
    "live rosin",
    "rosin",
    "cart",
    "disposable",
    "pod",
]


def _split_label(label: str) -> tuple[str, str, str]:
    """name / brand / format from a Bloom label string."""
    cleaned = re.sub(r"\s*\d+(?:\.\d+)?\s*g\s*$", "", label).strip()
    for alias, canonical in MATCH_TABLE:
        m = re.search(rf"\b{re.escape(alias)}\b", cleaned, re.IGNORECASE)
        if m:
            name = cleaned[: m.start()].strip()
            after = cleaned[m.end() :].strip()
            return (name, canonical, after if after else "UNKNOWN")
    # Format-keyword fallback.
    for kw in _FORMAT_KEYWORDS:
        idx = cleaned.lower().find(kw.lower())
        if idx > 0:
            name_and_brand = cleaned[:idx].strip()
            product_format = cleaned[idx:].strip()
            tokens = name_and_brand.split()
            if len(tokens) >= 2:
                return (" ".join(tokens[:-1]), tokens[-1], product_format)
            return (name_and_brand, "UNKNOWN", product_format)
    return (cleaned, "UNKNOWN", "UNKNOWN")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _strain_type(card_text: str) -> Optional[str]:
    m = re.search(r"\b(indica|sativa|hybrid)\b", card_text, re.I)
    return m.group(1).lower() if m else None


def _best_label(card_tag: Tag) -> str:
    label_text = ""
    for a in card_tag.find_all("a", href=re.compile(r"/product/\d+")):
        t = a.get_text(" ", strip=True)
        t = re.sub(r"watermark$", "", t).strip()
        if len(t) > len(label_text):
            label_text = t
    return label_text


def _common_card_fields(card_tag: Tag, location: str, category: str):
    """Returns the shared (id, url, name, brand, format, strain, prices,
    thc, card_text, weight) tuple. Returns None if the card is not a real
    product card."""
    link = card_tag.find("a", href=re.compile(r"/product/\d+"))
    if not link:
        return None
    href = link["href"]
    product_id, weight = parse_product_url(href)
    if not product_id:
        return None
    product_url = (
        href if href.startswith("http") else f"https://bloommarijuana.com{href}"
    )
    card_text = card_tag.get_text(" ", strip=True)
    name, brand, product_format = _split_label(_best_label(card_tag))
    strain = _strain_type(card_text)
    sale, msrp, discount = extract_price_pair(card_text)
    thc = extract_thc(card_text)
    return dict(
        source="bloom",
        location=location,
        category=category,
        product_id=product_id,
        product_url=product_url,
        name=name,
        brand=brand,
        product_format=product_format,
        strain_type=strain,
        thc_percent=thc,
        sale_price=sale,
        msrp=msrp,
        discount_percent=discount,
        scraped_at=_now(),
        _card_text=card_text,
        _card_tag=card_tag,
        _weight=weight,
    )


# ---------- per-category parsers ----------

def _parse_vape_card(card_tag: Tag, location: str) -> Optional[VapeProduct]:
    base = _common_card_fields(card_tag, location, "vape")
    if base is None:
        return None
    card_text = base.pop("_card_text")
    tag = base.pop("_card_tag")
    weight = base.pop("_weight")
    return VapeProduct(
        **base,
        cart_size_grams=weight,
        secondary_cannabinoids=extract_secondary_cannabinoids(card_text),
        terpenes=extract_terpenes_from_imgs(tag),
    )


def _parse_flower_card(card_tag: Tag, location: str) -> Optional[FlowerProduct]:
    base = _common_card_fields(card_tag, location, "flower")
    if base is None:
        return None
    card_text = base.pop("_card_text")
    tag = base.pop("_card_tag")
    weight = base.pop("_weight")
    # Flower commonly comes in 3.5g / 7g / 14g / 28g packages, encoded in
    # the URL weight slug or the trailing size token. We reuse the
    # URL-encoded weight when available, but also widen the weight_map
    # below for flower-specific slugs not seen in vape.
    flower_weight_map = {
        "eighth": 3.5,
        "quarter": 7.0,
        "half_ounce": 14.0,
        "ounce": 28.0,
    }
    if weight is None:
        m = re.search(r"/product/\d+\+([a-z_]+)/", urlparse(base["product_url"]).path)
        if m:
            weight = flower_weight_map.get(m.group(1))
    return FlowerProduct(
        **base,
        package_size_grams=weight,
        terpenes=extract_terpenes_from_imgs(tag),
    )


def _parse_edible_card(card_tag: Tag, location: str) -> Optional[EdibleProduct]:
    base = _common_card_fields(card_tag, location, "edibles")
    if base is None:
        return None
    base.pop("_card_text"); base.pop("_card_tag"); base.pop("_weight")
    return EdibleProduct(**base)


def _parse_concentrate_card(card_tag: Tag, location: str) -> Optional[ConcentrateProduct]:
    base = _common_card_fields(card_tag, location, "concentrates")
    if base is None:
        return None
    tag = base.pop("_card_tag"); base.pop("_card_text")
    weight = base.pop("_weight")
    return ConcentrateProduct(
        **base,
        weight_grams=weight,
        terpenes=extract_terpenes_from_imgs(tag),
    )


def _parse_preroll_card(card_tag: Tag, location: str) -> Optional[PreRollProduct]:
    base = _common_card_fields(card_tag, location, "pre-rolls")
    if base is None:
        return None
    base.pop("_card_text"); base.pop("_card_tag")
    weight = base.pop("_weight")
    return PreRollProduct(**base, weight_grams=weight)


def _parse_tincture_card(card_tag: Tag, location: str) -> Optional[TinctureProduct]:
    base = _common_card_fields(card_tag, location, "tinctures")
    if base is None:
        return None
    base.pop("_card_text"); base.pop("_card_tag"); base.pop("_weight")
    return TinctureProduct(**base)


def _parse_topical_card(card_tag: Tag, location: str) -> Optional[TopicalProduct]:
    base = _common_card_fields(card_tag, location, "topicals")
    if base is None:
        return None
    base.pop("_card_text"); base.pop("_card_tag"); base.pop("_weight")
    return TopicalProduct(**base)


_PARSERS: dict[str, Callable[[Tag, str], Optional[Product]]] = {
    "vape": _parse_vape_card,
    "flower": _parse_flower_card,
    "edibles": _parse_edible_card,
    "concentrates": _parse_concentrate_card,
    "pre-rolls": _parse_preroll_card,
    "tinctures": _parse_tincture_card,
    "topicals": _parse_topical_card,
}


# ---------- public scrape interface ----------

def parse_cards(html: str, location: str, category: str) -> list[Product]:
    """Parse all product cards in the rendered HTML."""
    parser = _PARSERS.get(category)
    if parser is None:
        raise ValueError(f"unknown bloom category: {category}")
    soup = BeautifulSoup(html, "lxml")
    out: list[Product] = []
    for card in soup.select("div.product-card"):
        p = parser(card, location)
        if p:
            out.append(p)
    return out


class BloomSource(Source):
    name = "bloom"

    def __init__(self, session: requests.Session | None = None) -> None:
        self.session = session

    def list_locations(self) -> list[str]:
        return list(BLOOM_LOCATIONS.keys())

    def list_categories(self) -> list[str]:
        return list(BLOOM_CATEGORIES)

    def fetch_raw(self, location: str, category: str) -> str:
        if location not in BLOOM_LOCATIONS:
            raise ValueError(f"unknown bloom location: {location}")
        if category not in BLOOM_CATEGORIES:
            raise ValueError(f"unknown bloom category: {category}")
        return fetch(_url(BLOOM_LOCATIONS[location], category), self.session)

    def parse_raw(self, raw: str, location: str, category: str) -> list[Product]:
        return parse_cards(raw, location, category)
