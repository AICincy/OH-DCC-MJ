"""KlutchSource structure tests.

IMPORTANT: these validate the catalog+lab MERGE, dedup, fallback handling,
and request wiring against SYNTHETIC data, NOT a live Klutch site. The WP
field paths and the embedded ``data-page`` JointCommerce shape are modeled
from real captures (2026-06-27) and need one live-capture validation
(record a fixture via ``--record-fixtures``) before production use. No
network is touched: synthetic payloads are parsed directly and
``requests.get`` is mocked.
"""
from __future__ import annotations

import html
import json
from unittest.mock import MagicMock, patch

from ohcanna.models import (
    ConcentrateProduct,
    FlowerProduct,
    Product,
    VapeProduct,
)
from ohcanna.sources.base import Source
from ohcanna.sources.klutch import (
    KlutchSource,
    extract_data_page,
    select_lab_product,
)


def _jc_product(name, brand, strain_type, thc, terps, variants, cannabinoids=None, eid="x"):
    """Build a raw JointCommerce product record (the data-page `product`)."""
    return {
        "name": name,
        "brand": {"name": brand},
        "strainType": strain_type,
        "potencyThc": {"range": [thc]},
        "potencyCbd": {"range": []},
        "cannabinoids": cannabinoids or [],
        "terpenes": [
            {"terpene": {"name": n}, "value": v, "unit": "PERCENTAGE"} for n, v in terps
        ],
        "variants": variants,
        "enterpriseProductId": eid,
        "posMetaData": {"sku": "SKU-" + eid},
        "productBatchId": "BATCH-" + eid,
        "effects": ["HAPPY"],
        "tags": ["Klutch"],
    }


def _variant(option, rec, med=None, special_rec=None, qty=5):
    return {
        "option": option,
        "priceMed": med if med is not None else rec,
        "priceRec": rec,
        "specialPriceMed": None,
        "specialPriceRec": special_rec,
        "quantity": qty,
    }


# A vape Live Resin (Klutch) + the same strain as CO2 under the sibling brand
# Citizen by Klutch, plus a fallback duplicate of the CO2 that must lose the
# dedup to the real record.
VAPE_DOC = json.dumps({
    "source": "klutch", "location": "catalog", "category": "vape",
    "products": [
        {
            "catalog": {
                "title": "Jealousy Live Resin Disposable Vape", "strain": "Jealousy",
                "product_type": "Disposable Vape", "extraction_method": "Live Resin",
                "strain_type": "Hybrid", "brand": "Klutch",
                "url": "https://www.klutchcannabis.com/product/jealousy-live-resin/",
            },
            "lab": _jc_product(
                "Jealousy Live Resin", "Klutch", "HYBRID", 83.78,
                [("Beta Myrcene", 1.2), ("Limonene", 0.8)], [_variant("1g", 55)], eid="LR1",
            ),
            "fallback": False,
        },
        {
            "catalog": {
                "title": "Jealousy CO2 Cartridge", "strain": "Jealousy",
                "product_type": "Cartridge", "extraction_method": "CO2",
                "strain_type": "Hybrid", "brand": "Citizen by Klutch",
                "url": "https://www.klutchcannabis.com/product/jealousy-co2/",
            },
            "lab": _jc_product(
                "Jealousy CO2 Cart", "Citizen by Klutch", "HYBRID", 68.8,
                [("Beta Myrcene", 2.0)],
                [_variant("1g", 45, special_rec=40)],
                cannabinoids=[
                    {"cannabinoid": {"name": 'TAC" - Total Active Cannabinoids'}, "value": 80.0, "unit": "PERCENTAGE"},
                    {"cannabinoid": {"name": "CBD"}, "value": 0.3, "unit": "PERCENTAGE"},
                    {"cannabinoid": {"name": "THCA"}, "value": 60.0, "unit": "PERCENTAGE"},
                ],
                eid="CO2_1",
            ),
            "fallback": False,
        },
        {
            "catalog": {
                "title": "Jealousy CO2 Cartridge", "strain": "Jealousy",
                "product_type": "Cartridge", "extraction_method": "CO2",
                "strain_type": "Hybrid", "brand": "Citizen by Klutch",
                "url": "https://www.klutchcannabis.com/product/out-of-stock-location/",
            },
            "lab": _jc_product("Jealousy CO2 Cart", "Citizen by Klutch", "HYBRID", 68.8, [], [], eid="CO2_1"),
            "fallback": True,
        },
    ],
})


def test_parse_raw_merges_catalog_and_lab():
    products = KlutchSource().parse_raw(VAPE_DOC, "catalog", "vape")
    # 3 entries dedup to 2 (the fallback CO2 collapses into the real one).
    assert len(products) == 2
    assert all(isinstance(p, VapeProduct) for p in products)

    by_brand = {p.brand: p for p in products}
    lr = by_brand["Klutch"]
    co2 = by_brand["Citizen by Klutch"]

    assert lr.name == "Jealousy"
    assert lr.thc_percent == 83.78
    assert lr.msrp == 55
    assert lr.cart_size_grams == 1.0
    assert lr.strain_type == "hybrid"
    assert lr.source == "klutch" and lr.category == "vape"
    # extraction method is folded into product_format so the vape rules see it
    assert "live resin" in lr.product_format.lower()

    # On special, sale + original both surface.
    assert co2.sale_price == 40 and co2.msrp == 45
    # The malformed TAC roll-up and THC itself are NOT secondary cannabinoids.
    assert co2.secondary_cannabinoids == ["CBD"]
    assert "co2" in co2.product_format.lower()
    assert co2.extra["extraction_method"] == "CO2"


def test_dedup_prefers_real_record_over_fallback():
    products = KlutchSource().parse_raw(VAPE_DOC, "catalog", "vape")
    co2 = next(p for p in products if p.brand == "Citizen by Klutch")
    # The surviving CO2 is the in-stock one (real url, fallback False), not
    # the out-of-stock-location fallback duplicate.
    assert co2.extra["fallback"] is False
    assert "out-of-stock-location" not in co2.product_url


def test_concentrate_and_flower_subclasses_and_sizes():
    doc = json.dumps({
        "source": "klutch", "location": "catalog", "category": "concentrates",
        "products": [{
            "catalog": {
                "title": "Lemon Granita Live Hash Rosin", "strain": "Lemon Granita",
                "product_type": "Live Hash Rosin", "extraction_method": "Live Hash Rosin",
                "strain_type": "Sativa", "brand": "Klutch",
                "url": "https://www.klutchcannabis.com/product/lemon-granita-rosin/",
            },
            "lab": _jc_product(
                "Lemon Granita Rosin", "Klutch", "SATIVA", 72.7,
                [("Beta Myrcene", 3.0)], [_variant("1g", 60)], eid="C1",
            ),
            "fallback": False,
        }],
    })
    (conc,) = KlutchSource().parse_raw(doc, "catalog", "concentrates")
    assert isinstance(conc, ConcentrateProduct)
    assert conc.weight_grams == 1.0
    assert conc.extraction_method == "Live Hash Rosin"
    assert conc.thc_percent == 72.7

    flower_doc = json.dumps({
        "source": "klutch", "location": "catalog", "category": "flower",
        "products": [{
            "catalog": {
                "title": "Big Head", "strain": "Big Head", "product_type": "Flower",
                "extraction_method": None, "strain_type": "Indica", "brand": "Klutch",
                "url": "https://www.klutchcannabis.com/product/big-head/",
            },
            "lab": _jc_product(
                "Big Head", "Klutch", "INDICA", 21.52, [("Limonene", 0.5)],
                [_variant("1/8oz", 45)], eid="F1",
            ),
            "fallback": False,
        }],
    })
    (flower,) = KlutchSource().parse_raw(flower_doc, "catalog", "flower")
    assert isinstance(flower, FlowerProduct)
    assert flower.package_size_grams == 3.5  # "1/8oz" -> 3.5g
    assert flower.product_format == "Flower"  # no extraction method to fold in


def test_legacy_citizen_brand_resolves_to_canonical():
    doc = json.dumps({
        "source": "klutch", "location": "catalog", "category": "vape",
        "products": [{
            "catalog": {
                "title": "GMO Cartridge", "strain": "GMO", "product_type": "Cartridge",
                "extraction_method": "CO2", "strain_type": "Indica",
                "brand": "The Citizen by Klutch",  # legacy label
                "url": "https://www.klutchcannabis.com/product/gmo/",
            },
            "lab": _jc_product("GMO Cart", "The Citizen by Klutch", "INDICA", 70.0, [], [_variant("1g", 45)], eid="L1"),
            "fallback": False,
        }],
    })
    (p,) = KlutchSource().parse_raw(doc, "catalog", "vape")
    assert p.brand == "Citizen by Klutch"


def test_unknown_category_falls_back_to_base_product():
    doc = json.dumps({
        "products": [{
            "catalog": {"title": "Mystery", "strain": "Mystery", "product_type": "Other",
                        "extraction_method": None, "strain_type": "", "brand": "Klutch", "url": "u"},
            "lab": _jc_product("Mystery", "Klutch", "", 50.0, [], [], eid="M1"),
            "fallback": False,
        }],
    })
    (p,) = KlutchSource().parse_raw(doc, "catalog", "topicals")
    assert type(p) is Product


def test_extract_data_page_and_fallback_selection():
    # Primary product null (out of stock) -> first related with THC, fallback.
    data_page = {"props": {"data": {
        "product": None,
        "related_products": [_jc_product("Rel", "Klutch", "HYBRID", 70.1, [], [], eid="R1")],
    }}}
    page_html = '<html><div id="root" data-page="' + html.escape(json.dumps(data_page)) + '"></div></html>'

    parsed = extract_data_page(page_html)
    assert parsed is not None
    product, fallback = select_lab_product(parsed)
    assert fallback is True
    assert product["enterpriseProductId"] == "R1"

    # No data-page element -> None.
    assert extract_data_page("<html>no root here</html>") is None


def test_fetch_raw_wiring_without_network():
    """fetch_raw must page the WP API + fetch product pages, sleep at the
    configured delay, and never hit the network (requests.get mocked)."""
    wp_products = [{
        "id": 1,
        "title": {"rendered": "Jealousy Live Resin Disposable Vape"},
        "link": "https://www.klutchcannabis.com/product/jealousy-live-resin/",
        "cp_product_category": [1266],  # Vaporizers -> vape
        "cp_product_strain_type": [1180],  # Hybrid
    }]
    data_page = {"props": {"data": {
        "product": _jc_product("Jealousy Live Resin", "Klutch", "HYBRID", 83.78, [], [_variant("1g", 55)], eid="LR1"),
        "related_products": [],
    }}}
    page_html = '<div id="root" data-page="' + html.escape(json.dumps(data_page)) + '"></div>'

    def fake_get(url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if "/wp-json/" in url:
            # Only the Klutch brand (1274) returns products; others are empty.
            resp.text = json.dumps(wp_products if "cp_product_brand=1274" in url else [])
        else:
            resp.text = page_html
        return resp

    with patch("ohcanna.sources.klutch.requests.get", side_effect=fake_get) as m_get, \
            patch("ohcanna.sources.klutch.time.sleep") as m_sleep:
        src = KlutchSource(delay=0.05)
        raw = src.fetch_raw("catalog", "vape")

    doc = json.loads(raw)
    assert doc["category"] == "vape"
    assert len(doc["products"]) == 1
    assert doc["products"][0]["lab"]["enterpriseProductId"] == "LR1"
    assert m_get.called
    # rate-limit sleep observed, at the configured delay
    assert m_sleep.called
    assert all(call.args == (0.05,) for call in m_sleep.call_args_list)

    # And the recorded payload round-trips through parse_raw.
    products = src.parse_raw(raw, "catalog", "vape")
    assert len(products) == 1 and products[0].thc_percent == 83.78


def test_fetch_raw_rejects_unknown_location_and_category():
    src = KlutchSource()
    for bad in [("nope", "vape"), ("catalog", "nope")]:
        try:
            src.fetch_raw(*bad)
        except ValueError:
            continue
        raise AssertionError(f"expected ValueError for {bad}")


def test_satisfies_source_interface():
    src = KlutchSource()
    assert isinstance(src, Source)
    assert src.name == "klutch"
    assert src.raw_ext == "json"
    assert src.list_locations() == ["catalog"]
    cats = src.list_categories()
    assert "vape" in cats and "concentrates" in cats
    assert "topicals" not in cats  # no lab data of interest; intentionally dropped
