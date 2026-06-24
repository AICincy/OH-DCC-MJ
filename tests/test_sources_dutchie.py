"""DutchieSource structure tests.

IMPORTANT: these validate the parser + request-builder STRUCTURE against
SYNTHETIC Dutchie GraphQL JSON, NOT against a live Dutchie site. The JSON
shape is hand-modeled from public Dutchie ``filteredProducts`` responses
and needs one live-capture validation (record a fixture via
``--record-fixtures``) before production use. No network is touched: the
synthetic JSON is parsed directly and ``requests.post`` is mocked.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from ohcanna.models import Product, VapeProduct
from ohcanna.sources.base import Source
from ohcanna.sources.dutchie import (
    DutchieSource,
    GRAPHQL_URL,
    build_graphql_payload,
)

# Synthetic Dutchie filteredProducts response: 3 vape products. Brand names
# (Klutch, Butterfly Effect) are drawn from the registry so brand
# resolution is exercised; the third uses a brand only findable via the
# product name (alias fallback).
SYNTHETIC_VAPE_JSON = json.dumps(
    {
        "data": {
            "filteredProducts": {
                "products": [
                    {
                        "id": "abc123",
                        "name": "Blue Dream Cart",
                        "type": "Cartridge",
                        "strainType": "Sativa",
                        "brand": {"name": "Klutch"},
                        "THC": 81.5,
                        "Options": ["0.5g"],
                        "Prices": [35.00],
                        "special": False,
                    },
                    {
                        "id": "def456",
                        "name": "Gelato Disposable",
                        "type": "Disposable",
                        "strainType": "Hybrid",
                        "brand": {"name": "Butterfly Effect"},
                        "THCContent": {"range": [88.2], "unit": "%"},
                        "Options": ["1g"],
                        "Prices": [29.99, 45.00],
                        "special": True,
                    },
                    {
                        "id": "ghi789",
                        "name": "Cookies Live Resin Cart",
                        "type": "Cartridge",
                        "strainType": "Indica",
                        "brand": {"name": ""},
                        "measurements": {"THC": {"value": 76.0}},
                        "Options": ["0.3g"],
                        "Prices": [40.00],
                    },
                ],
                "queryInfo": {"totalCount": 3, "totalPages": 1},
            }
        }
    }
)


def test_parse_raw_returns_populated_products():
    products = DutchieSource().parse_raw(SYNTHETIC_VAPE_JSON, "demo", "vape")
    assert len(products) == 3
    assert all(isinstance(p, VapeProduct) for p in products)

    by_name = {p.name: p for p in products}

    blue = by_name["Blue Dream Cart"]
    assert blue.brand == "Klutch"
    assert blue.thc_percent == 81.5
    assert blue.msrp == 35.00
    assert blue.sale_price is None
    assert blue.strain_type == "sativa"
    assert blue.cart_size_grams == 0.5
    assert blue.source == "dutchie"
    assert blue.category == "vape"

    # On special, sale + original msrp both surfaced.
    gelato = by_name["Gelato Disposable"]
    assert gelato.brand == "Butterfly Effect"
    assert gelato.thc_percent == 88.2  # parsed from THCContent.range
    assert gelato.sale_price == 29.99
    assert gelato.msrp == 45.00
    assert gelato.cart_size_grams == 1.0

    # Brand resolved via alias fallback on the name (empty brand object).
    cookies = by_name["Cookies Live Resin Cart"]
    assert cookies.brand == "Cookies"
    assert cookies.thc_percent == 76.0  # parsed from measurements.THC.value


def test_non_vape_category_yields_base_product():
    products = DutchieSource().parse_raw(SYNTHETIC_VAPE_JSON, "demo", "flower")
    assert products
    assert all(type(p) is Product for p in products)


def test_build_graphql_payload_shape():
    payload = build_graphql_payload("disp-1", "Vaporizers")
    assert payload["operationName"] == "FilteredProducts"
    assert "filteredProducts" in payload["query"]
    variables = payload["variables"]
    assert variables["productsFilter"]["dispensaryId"] == "disp-1"
    assert variables["productsFilter"]["types"] == ["Vaporizers"]
    assert "page" in variables and "perPage" in variables


def test_fetch_raw_builds_request_without_network():
    """fetch_raw must POST to the GraphQL URL with the right payload and
    NEVER hit the network (requests.post mocked, rate-limit sleep patched)."""
    resp = MagicMock()
    resp.text = SYNTHETIC_VAPE_JSON
    resp.raise_for_status = MagicMock()
    with patch("ohcanna.sources.dutchie.requests.post", return_value=resp) as m_post, \
            patch("ohcanna.sources.dutchie.time.sleep") as m_sleep:
        src = DutchieSource(dispensaries={"demo": "demo-id"})
        raw = src.fetch_raw("demo", "vape")

    assert raw == SYNTHETIC_VAPE_JSON
    assert m_post.call_count == 1
    args, kwargs = m_post.call_args
    assert args[0] == GRAPHQL_URL
    body = kwargs["json"]
    assert body["variables"]["productsFilter"]["dispensaryId"] == "demo-id"
    # Dutchie vape category enum, identified UA, rate-limit observed.
    assert body["variables"]["productsFilter"]["types"] == ["Vaporizers"]
    assert "User-Agent" in kwargs["headers"]
    assert m_sleep.called


def test_fetch_raw_rejects_unknown_location_and_category():
    src = DutchieSource(dispensaries={"demo": "demo-id"})
    for bad in [("nope", "vape"), ("demo", "nope")]:
        try:
            src.fetch_raw(*bad)
        except ValueError:
            continue
        raise AssertionError(f"expected ValueError for {bad}")


def test_satisfies_source_interface():
    src = DutchieSource()
    assert isinstance(src, Source)
    assert src.name == "dutchie"
    assert src.raw_ext == "json"
    assert src.list_locations()
    assert src.list_categories()
