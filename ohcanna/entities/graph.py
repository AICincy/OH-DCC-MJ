"""Entity-aggregation graph: rollups over loaded product dicts.

This is the Phase 2 data layer (T12 processor / T13 brand / T14 dispensary).
Pure functions in, dataclasses out. No I/O except the convenience
``load_and_rollup`` helper, and no HTML rendering — the publication
aesthetic is an unresolved operator decision, so this module only builds
the graph.

The analytical win is ``rollup_by_processor``: brands are surface labels,
but the *operating LLC* (``ohcanna.brands.legal_entity_for``) is the real
entity. Citizen by Klutch / Cookies / Josh D / Klutch all collapse into
"AT-CPC of Ohio LLC".
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from typing import Iterable, Optional

from ..brands import legal_entity_for
from ..storage import DEFAULT_DATA_ROOT

# Sentinel processor for brands with no verified legal entity.
UNKNOWN_PROCESSOR = "UNKNOWN PROCESSOR"


def slugify(name: str) -> str:
    """Lowercase, ASCII, hyphenated slug for canonical URLs.

    "AT-CPC of Ohio LLC" -> "at-cpc-of-ohio-llc"
    """
    if not name:
        return ""
    normalized = unicodedata.normalize("NFKD", name)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_only = ascii_only.lower()
    # Replace any run of non-alphanumeric chars with a single hyphen.
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_only)
    return slug.strip("-")


# ---------------------------------------------------------------------------
# Stats helpers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Stats:
    """min / median / max over a numeric field, plus the sample count.

    ``count`` is the number of non-null values that fed the stats, which
    can be smaller than a rollup's product count when some records lack
    the field.
    """

    min: Optional[float] = None
    median: Optional[float] = None
    max: Optional[float] = None
    count: int = 0


def _stats(values: Iterable[Optional[float]]) -> Stats:
    nums = [float(v) for v in values if v is not None]
    if not nums:
        return Stats()
    return Stats(min=min(nums), median=median(nums), max=max(nums), count=len(nums))


# ---------------------------------------------------------------------------
# Rollup dataclasses
# ---------------------------------------------------------------------------

@dataclass
class BrandRollup:
    brand: str
    legal_entity: Optional[str]
    product_count: int = 0
    categories: set[str] = field(default_factory=set)
    locations: set[str] = field(default_factory=set)
    price_stats: Stats = field(default_factory=Stats)
    thc_stats: Stats = field(default_factory=Stats)
    flag_distribution: dict[str, int] = field(default_factory=dict)

    @property
    def canonical_path(self) -> str:
        return f"/brand/{slugify(self.brand)}/"


@dataclass
class ProcessorRollup:
    legal_entity: str
    brands: set[str] = field(default_factory=set)
    product_count: int = 0
    categories: set[str] = field(default_factory=set)
    locations: set[str] = field(default_factory=set)
    price_stats: Stats = field(default_factory=Stats)
    thc_stats: Stats = field(default_factory=Stats)
    flag_distribution: dict[str, int] = field(default_factory=dict)

    @property
    def canonical_path(self) -> str:
        return f"/processor/{slugify(self.legal_entity)}/"


@dataclass
class DispensaryRollup:
    location: str
    product_count: int = 0
    brands: set[str] = field(default_factory=set)
    categories: set[str] = field(default_factory=set)
    # day (from scraped_at date) -> product count
    daily_count: dict[str, int] = field(default_factory=dict)

    @property
    def canonical_path(self) -> str:
        return f"/dispensary/{slugify(self.location)}/"


# ---------------------------------------------------------------------------
# Field accessors (tolerant of missing keys)
# ---------------------------------------------------------------------------

def _msrp(p: dict) -> Optional[float]:
    return p.get("msrp")


def _thc(p: dict) -> Optional[float]:
    return p.get("thc_percent")


def _flag_names(p: dict) -> list[str]:
    """Flag identifiers on a record, if any.

    Records may carry a ``flags`` list of dicts (Flag-shaped) or strings;
    real snapshots today have none. We key the distribution on
    ``rule_name`` when present, else ``flag_id``, else the raw string.
    """
    flags = p.get("flags")
    if not flags:
        return []
    out: list[str] = []
    for f in flags:
        if isinstance(f, dict):
            out.append(f.get("rule_name") or f.get("flag_id") or "unknown")
        else:
            out.append(str(f))
    return out


# ---------------------------------------------------------------------------
# Rollups
# ---------------------------------------------------------------------------

def rollup_by_brand(products: list[dict]) -> dict[str, BrandRollup]:
    """Group products by their display ``brand``.

    legal_entity is resolved per brand via ``legal_entity_for`` so callers
    can pivot to the processor view.
    """
    buckets: dict[str, list[dict]] = {}
    for p in products:
        buckets.setdefault(p.get("brand", ""), []).append(p)

    out: dict[str, BrandRollup] = {}
    for brand, group in buckets.items():
        flag_dist: Counter[str] = Counter()
        for p in group:
            flag_dist.update(_flag_names(p))
        out[brand] = BrandRollup(
            brand=brand,
            legal_entity=legal_entity_for(brand),
            product_count=len(group),
            categories={p.get("category") for p in group if p.get("category")},
            locations={p.get("location") for p in group if p.get("location")},
            price_stats=_stats(_msrp(p) for p in group),
            thc_stats=_stats(_thc(p) for p in group),
            flag_distribution=dict(flag_dist),
        )
    return out


def rollup_by_processor(products: list[dict]) -> dict[str, ProcessorRollup]:
    """Group products by operating legal entity (the processor LLC).

    Brands with no verified legal entity collapse under
    ``UNKNOWN_PROCESSOR``. Keyed on the legal-entity string.
    """
    buckets: dict[str, list[dict]] = {}
    for p in products:
        entity = legal_entity_for(p.get("brand", "")) or UNKNOWN_PROCESSOR
        buckets.setdefault(entity, []).append(p)

    out: dict[str, ProcessorRollup] = {}
    for entity, group in buckets.items():
        flag_dist: Counter[str] = Counter()
        for p in group:
            flag_dist.update(_flag_names(p))
        out[entity] = ProcessorRollup(
            legal_entity=entity,
            brands={p.get("brand") for p in group if p.get("brand")},
            product_count=len(group),
            categories={p.get("category") for p in group if p.get("category")},
            locations={p.get("location") for p in group if p.get("location")},
            price_stats=_stats(_msrp(p) for p in group),
            thc_stats=_stats(_thc(p) for p in group),
            flag_distribution=dict(flag_dist),
        )
    return out


def rollup_by_dispensary(products: list[dict]) -> dict[str, DispensaryRollup]:
    """Group products by ``location`` (the dispensary)."""
    buckets: dict[str, list[dict]] = {}
    for p in products:
        buckets.setdefault(p.get("location", ""), []).append(p)

    out: dict[str, DispensaryRollup] = {}
    for location, group in buckets.items():
        daily: Counter[str] = Counter()
        for p in group:
            scraped = p.get("scraped_at")
            if scraped:
                daily[str(scraped)[:10]] += 1
        out[location] = DispensaryRollup(
            location=location,
            product_count=len(group),
            brands={p.get("brand") for p in group if p.get("brand")},
            categories={p.get("category") for p in group if p.get("category")},
            daily_count=dict(daily),
        )
    return out


def build_all_rollups(products: list[dict]) -> dict[str, dict]:
    """All three rollups in one pass-friendly dict."""
    return {
        "brands": rollup_by_brand(products),
        "processors": rollup_by_processor(products),
        "dispensaries": rollup_by_dispensary(products),
    }


def load_and_rollup(data_root: Path = DEFAULT_DATA_ROOT) -> dict[str, dict]:
    """Read every ``<data_root>/latest/*.json`` snapshot and roll it up."""
    latest_dir = Path(data_root) / "latest"
    products: list[dict] = []
    for path in sorted(latest_dir.glob("*.json")):
        with open(path) as f:
            records = json.load(f)
        if isinstance(records, list):
            products.extend(records)
    return build_all_rollups(products)
