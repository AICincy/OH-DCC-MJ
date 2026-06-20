"""Dataclasses for products and analyzer flags.

`Product` is the base shape every scraped record carries. Category-specific
subclasses extend with fields that only make sense for that category
(cart_size_grams for vape, dose_mg for edibles, etc.). Category-agnostic
consumers (storage, analyzer rollups) read the base fields; category-aware
rules read the subclass.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Product:
    source: str
    location: str
    category: str
    product_id: str
    product_url: str
    name: str
    brand: str
    product_format: str
    strain_type: Optional[str]
    thc_percent: Optional[float]
    sale_price: Optional[float]
    msrp: Optional[float]
    discount_percent: Optional[int]
    scraped_at: str
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class VapeProduct(Product):
    cart_size_grams: Optional[float] = None
    secondary_cannabinoids: list[str] = field(default_factory=list)
    terpenes: list[str] = field(default_factory=list)


@dataclass
class FlowerProduct(Product):
    package_size_grams: Optional[float] = None
    terpenes: list[str] = field(default_factory=list)


@dataclass
class EdibleProduct(Product):
    dose_mg: Optional[float] = None
    count_per_package: Optional[int] = None
    total_thc_mg: Optional[float] = None


@dataclass
class ConcentrateProduct(Product):
    weight_grams: Optional[float] = None
    extraction_method: Optional[str] = None
    terpenes: list[str] = field(default_factory=list)


@dataclass
class PreRollProduct(Product):
    weight_grams: Optional[float] = None
    count_per_package: Optional[int] = None


@dataclass
class TinctureProduct(Product):
    volume_ml: Optional[float] = None
    total_thc_mg: Optional[float] = None
    cbd_thc_ratio: Optional[str] = None


@dataclass
class TopicalProduct(Product):
    volume_ml: Optional[float] = None
    total_thc_mg: Optional[float] = None


@dataclass
class Flag:
    flag_id: str
    rule_name: str
    severity: str  # info | watch | warn
    explanation: str
