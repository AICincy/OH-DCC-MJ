"""LocalsCannabisSource structure tests.

IMPORTANT: these validate the HTML parser + request STRUCTURE against
SYNTHETIC HTML, NOT against the live Locals Cannabis site. The CSS
selectors, URL shape, location slugs, and any Dutchie dispensary ids in
the source are UNVERIFIED placeholders and need one live-capture
validation before production use. No network is touched: synthetic HTML
is parsed directly and ``requests.get`` is mocked.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from ohcanna.models import Product
from ohcanna.sources.base import Source
from ohcanna.sources.dutchie import DutchieSource
from ohcanna.sources.locals_cannabis import (
    LocalsCannabisSource,
    build_dutchie_delegate,
)

# Synthetic Locals-style HTML: 2 product cards using the guessed selector
# (div.product-card) with a registry brand, a price pair, THC, and strain.
SYNTHETIC_HTML = """\
<html><body>
<div class="product-card">
  <a href="/product/111"><h3 class="product-title">Sunset Sherbet Klutch</h3></a>
  Hybrid 78.5% THC $29.99 $40.00
</div>
<div class="product-card">
  <a href="/product/222"><h3 class="product-title">Wedding Cake Butterfly Effect</h3></a>
  Indica 71.0% THC $45.00
</div>
</body></html>
"""


def test_parse_raw_returns_populated_products():
    products = LocalsCannabisSource().parse_raw(
        SYNTHETIC_HTML, "cincinnati", "flower"
    )
    assert len(products) == 2
    assert all(isinstance(p, Product) for p in products)

    by_brand = {p.brand: p for p in products}
    assert "Klutch" in by_brand
    assert "Butterfly Effect" in by_brand

    klutch = by_brand["Klutch"]
    assert klutch.name == "Sunset Sherbet"
    assert klutch.sale_price == 29.99
    assert klutch.msrp == 40.00
    assert klutch.thc_percent == 78.5
    assert klutch.strain_type == "hybrid"
    assert klutch.source == "locals_cannabis"
    assert klutch.product_url == "https://localscannabis.com/product/111"

    be = by_brand["Butterfly Effect"]
    assert be.msrp == 45.00
    assert be.sale_price is None
    assert be.thc_percent == 71.0
    assert be.strain_type == "indica"


def test_fetch_raw_builds_request_without_network():
    """fetch_raw must GET the menu URL and NEVER hit the network
    (requests.get mocked, rate-limit sleep patched)."""
    resp = MagicMock()
    resp.text = SYNTHETIC_HTML
    resp.raise_for_status = MagicMock()
    with patch("ohcanna.sources.locals_cannabis.requests.get", return_value=resp) as m_get, \
            patch("ohcanna.sources.locals_cannabis.time.sleep") as m_sleep:
        src = LocalsCannabisSource()
        raw = src.fetch_raw("cincinnati", "flower")

    assert raw == SYNTHETIC_HTML
    assert m_get.call_count == 1
    args, kwargs = m_get.call_args
    assert args[0].startswith("https://localscannabis.com/")
    assert "cincinnati" in args[0]
    assert "User-Agent" in kwargs["headers"]
    assert m_sleep.called


def test_fetch_raw_rejects_unknown_location_and_category():
    src = LocalsCannabisSource()
    for bad in [("nope", "flower"), ("cincinnati", "nope")]:
        try:
            src.fetch_raw(*bad)
        except ValueError:
            continue
        raise AssertionError(f"expected ValueError for {bad}")


def test_satisfies_source_interface():
    src = LocalsCannabisSource()
    assert isinstance(src, Source)
    assert src.name == "locals_cannabis"
    assert src.list_locations()
    assert src.list_categories()


def test_dutchie_delegate_is_configured_dutchie_source():
    """If Locals turns out to be Dutchie-backed, the delegate builder
    returns a ready DutchieSource carrying Locals' (placeholder) ids."""
    delegate = build_dutchie_delegate()
    assert isinstance(delegate, DutchieSource)
    assert set(delegate.list_locations()) == {
        "cincinnati", "dayton", "columbus", "monroe",
    }
    assert delegate.list_categories()
