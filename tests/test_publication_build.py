"""Tests for the static-site publication layer (Phase 2 SSG)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ohcanna.entities.graph import build_all_rollups, slugify
from ohcanna.entities.dcc_registry import load_registry
from ohcanna.publication.build import build_site

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_LATEST = REPO_ROOT / "data" / "latest"
REGISTRY_FIXTURE = REPO_ROOT / "data" / "entities" / "example_registry.json"


def _load_products() -> list[dict]:
    products: list[dict] = []
    for fname in ("bloom_vape.json", "bloom_flower.json"):
        with open(DATA_LATEST / fname) as f:
            products.extend(json.load(f))
    return products


@pytest.fixture
def products() -> list[dict]:
    return _load_products()


@pytest.fixture
def built(tmp_path, products):
    rollups = build_all_rollups(products)
    urls = build_site(products, rollups, tmp_path)
    return tmp_path, urls, products


def test_core_pages_exist(built):
    out, urls, products = built
    assert (out / "index.html").exists()
    assert (out / "sitemap.xml").exists()
    assert (out / "brand").is_dir()

    # At least one of each entity/detail page type exists.
    assert list(out.glob("product/*/index.html")), "no product pages"
    assert list(out.glob("brand/*/index.html")), "no brand pages"
    assert list(out.glob("processor/*/index.html")), "no processor pages"
    assert list(out.glob("dispensary/*/index.html")), "no dispensary pages"


def test_sitemap_lists_every_product_url(built):
    out, urls, products = built
    sitemap = (out / "sitemap.xml").read_text()

    product_ids = {str(p["product_id"]) for p in products}
    for pid in product_ids:
        assert f"/product/{pid}/" in sitemap, f"missing {pid} in sitemap"

    # Count match: number of <loc> product URLs == unique product count.
    sitemap_product_locs = sitemap.count("/product/")
    assert sitemap_product_locs == len(product_ids)


def test_product_pages_under_50kb(built):
    out, urls, products = built
    pages = list(out.glob("product/*/index.html"))
    assert pages
    largest = max(p.stat().st_size for p in pages)
    assert largest < 50_000, f"largest product page is {largest} bytes"


def test_processor_page_rolls_up_klutch_family(built):
    out, urls, products = built
    # AT-CPC of Ohio LLC is the Klutch-family operating processor.
    slug = slugify("AT-CPC of Ohio LLC")
    page = out / "processor" / slug / "index.html"
    assert page.exists(), f"missing processor page {page}"
    html = page.read_text()
    klutch_family = ["Klutch", "Cookies", "Citizen", "Josh D", "Habitat"]
    assert any(
        b in html for b in klutch_family
    ), "processor page mentions no Klutch-family brand"


def test_registry_pages_render_freshness_banner(tmp_path, products):
    rollups = build_all_rollups(products)
    registry = load_registry(str(REGISTRY_FIXTURE))
    urls = build_site(products, rollups, tmp_path, registry=registry)

    # A registry-driven page (cultivator or processor) carries the banner.
    candidates = list(tmp_path.glob("cultivator/*/index.html")) + list(
        tmp_path.glob("processor/*/index.html")
    )
    assert candidates, "no registry-driven pages generated"
    assert any(
        "DCC REGISTRY" in p.read_text() for p in candidates
    ), "no freshness banner rendered on registry-driven pages"

    # Cultivator page exists only because a registry was provided.
    assert list(tmp_path.glob("cultivator/*/index.html"))
