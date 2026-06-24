"""Static-site build pipeline.

``build_site(products, rollups, out_dir, registry=None, links=None)`` is the
pure function: given already-loaded product dicts, the entity rollups from
``ohcanna.entities.graph.build_all_rollups`` and (optionally) a DCC registry
+ brand->processor links, it writes a complete static site under ``out_dir``
and returns the list of generated page URLs (the same set indexed by
``sitemap.xml``).

``main(out_dir="public", data_root="data")`` is the convenience entry that
loads the latest snapshots + rollups (+ registry/links fixtures when present)
and calls ``build_site``.

Everything is deterministic: rows are sorted, no timestamps leak into page
bodies, and the sitemap is emitted in sorted URL order.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from ..entities.graph import (
    BrandRollup,
    DispensaryRollup,
    ProcessorRollup,
    UNKNOWN_PROCESSOR,
    build_all_rollups,
    slugify,
)
from ..entities.dcc_registry import (
    DCCLicense,
    BrandProcessorLink,
    load_brand_processor_map,
    load_registry,
    resolve_processor,
)
from ..storage import DEFAULT_DATA_ROOT, read_snapshot
from .render import Page, esc

# License types that get their own entity page section.
_CULTIVATOR_TYPES = {"cultivator_l1", "cultivator_l2", "cultivator"}
_TESTING_LAB_TYPES = {"testing_lab", "testing-lab", "lab"}


# ---------------------------------------------------------------------------
# small formatting helpers
# ---------------------------------------------------------------------------

def _money(v: Optional[float]) -> str:
    return f"${v:,.2f}" if isinstance(v, (int, float)) else "—"


def _pct(v: Optional[float]) -> str:
    return f"{v:g}%" if isinstance(v, (int, float)) else "—"


def _stats_row(label: str, stats) -> str:
    if not stats or not stats.count:
        return ""
    return (
        f"<tr><th>{esc(label)}</th>"
        f"<td>{stats.min:g}</td><td>{stats.median:g}</td>"
        f"<td>{stats.max:g}</td><td>{stats.count}</td></tr>"
    )


def _sorted_unique(values) -> list[str]:
    return sorted({str(v) for v in values if v})


# ---------------------------------------------------------------------------
# write helper
# ---------------------------------------------------------------------------

def _write_page(out_dir: Path, url: str, html: str) -> None:
    """Write ``html`` for a site URL (e.g. ``/product/123/``) to disk."""
    rel = url.strip("/")
    if rel:
        path = out_dir / rel / "index.html"
    else:
        path = out_dir / "index.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


# ---------------------------------------------------------------------------
# entity registry indexing
# ---------------------------------------------------------------------------

def _registry_banner(registry: dict[str, DCCLicense]) -> Optional[str]:
    """Freshness banner from the most recent ``fetched_at`` in the registry."""
    if not registry:
        return None
    fetched = sorted(
        (lic.fetched_at for lic in registry.values() if lic.fetched_at)
    )
    latest = fetched[-1] if fetched else "unknown"
    n = len(registry)
    sample = any(
        (lic.notes or "").upper().find("SAMPLE") >= 0 for lic in registry.values()
    )
    note = " SAMPLE/non-authoritative data." if sample else ""
    return (
        f'<span class="stamp">DCC REGISTRY</span> {n} license record(s); '
        f"last fetched {esc(latest)}.{esc(note)}"
    )


# ---------------------------------------------------------------------------
# page builders
# ---------------------------------------------------------------------------

def _product_page(p: dict, brands: dict, processors: dict) -> str:
    pid = str(p.get("product_id"))
    name = p.get("name") or "(unnamed)"
    brand = p.get("brand") or ""
    brand_roll = brands.get(brand)
    legal_entity = brand_roll.legal_entity if brand_roll else None
    location = p.get("location") or ""
    category = p.get("category") or ""

    links_html = []
    if brand:
        links_html.append(
            f'<dt>Brand</dt><dd><a href="/brand/{slugify(brand)}/">'
            f"{esc(brand)}</a></dd>"
        )
    if legal_entity and legal_entity != UNKNOWN_PROCESSOR:
        links_html.append(
            f'<dt>Processor</dt><dd><a href="/processor/{slugify(legal_entity)}/">'
            f"{esc(legal_entity)}</a></dd>"
        )
    if location:
        links_html.append(
            f'<dt>Dispensary</dt><dd><a href="/dispensary/{slugify(location)}/">'
            f"{esc(location)}</a></dd>"
        )

    detail = [
        f"<dt>Category</dt><dd>{esc(category)}</dd>",
        f"<dt>Format</dt><dd>{esc(p.get('product_format'))}</dd>",
        f"<dt>Strain type</dt><dd>{esc(p.get('strain_type'))}</dd>",
        f"<dt>THC</dt><dd>{_pct(p.get('thc_percent'))}</dd>",
        f"<dt>MSRP</dt><dd>{_money(p.get('msrp'))}</dd>",
        f"<dt>Sale price</dt><dd>{_money(p.get('sale_price'))}</dd>",
    ]
    if p.get("discount_percent") is not None:
        detail.append(
            f"<dt>Discount</dt><dd>{esc(p.get('discount_percent'))}%</dd>"
        )
    # A few category-specific extras when present.
    for key, label in (
        ("cart_size_grams", "Cart size (g)"),
        ("package_size_grams", "Package size (g)"),
        ("weight_grams", "Weight (g)"),
        ("dose_mg", "Dose (mg)"),
        ("total_thc_mg", "Total THC (mg)"),
        ("volume_ml", "Volume (ml)"),
    ):
        if p.get(key) is not None:
            detail.append(f"<dt>{label}</dt><dd>{esc(p.get(key))}</dd>")

    terps = p.get("terpenes") or []
    cannas = p.get("secondary_cannabinoids") or []
    if terps:
        detail.append(f"<dt>Terpenes</dt><dd>{esc(', '.join(terps))}</dd>")
    if cannas:
        detail.append(
            f"<dt>Other cannabinoids</dt><dd>{esc(', '.join(cannas))}</dd>"
        )

    url = p.get("product_url")
    source_html = (
        f'<p class="muted">Source listing: '
        f'<a href="{esc(url)}" rel="nofollow">{esc(url)}</a></p>'
        if url
        else ""
    )

    body = (
        f'<span class="stamp">Product {esc(pid)}</span>'
        f"<h1>{esc(name)}</h1>"
        f'<p class="muted">{esc(brand)}</p>'
        "<h2>Attribution</h2>"
        f'<dl class="kv">{"".join(links_html)}</dl>'
        "<h2>Record</h2>"
        f'<dl class="kv">{"".join(detail)}</dl>'
        f"{source_html}"
    )
    return Page(
        f"{name} — Product {pid}",
        body,
        crumbs=[
            ("Index", "/"),
            (category or "products", f"/{slugify(category)}/" if category else "/"),
            (f"#{pid}", None),
        ],
    )


def _category_page(category: str, prods: list[dict]) -> str:
    rows = []
    for p in sorted(prods, key=lambda x: (x.get("brand") or "", str(x.get("name")))):
        pid = str(p.get("product_id"))
        rows.append(
            "<tr>"
            f'<td><a href="/product/{esc(pid)}/">{esc(p.get("name"))}</a></td>'
            f'<td><a href="/brand/{slugify(p.get("brand") or "")}/">'
            f'{esc(p.get("brand"))}</a></td>'
            f"<td>{esc(p.get('strain_type'))}</td>"
            f"<td>{_pct(p.get('thc_percent'))}</td>"
            f"<td>{_money(p.get('msrp'))}</td>"
            f"<td>{esc(p.get('location'))}</td>"
            "</tr>"
        )
    body = (
        f"<h1>{esc(category.title())} ({len(prods)})</h1>"
        "<table><thead><tr><th>Product</th><th>Brand</th><th>Strain</th>"
        "<th>THC</th><th>MSRP</th><th>Dispensary</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )
    return Page(
        f"{category.title()} — category index",
        body,
        crumbs=[("Index", "/"), (category, None)],
    )


def _brand_page(
    roll: BrandRollup, products_by_brand: dict, links: list[BrandProcessorLink]
) -> str:
    legal = roll.legal_entity
    attribution = ""
    if legal and legal != UNKNOWN_PROCESSOR:
        link = resolve_processor(roll.brand, links) if links else None
        verified = (
            ' <span class="stamp">verified</span>'
            if link and link.verification_status == "verified"
            else ""
        )
        attribution = (
            '<p class="banner">'
            f"<strong>{esc(roll.brand)}</strong> — operated in Ohio by "
            f'<a href="/processor/{slugify(legal)}/">{esc(legal)}</a>'
            f"{verified}</p>"
        )
    else:
        attribution = (
            '<p class="muted">Operating processor not yet verified.</p>'
        )

    stats = "".join(
        [
            "<table><thead><tr><th>Metric</th><th>Min</th><th>Median</th>"
            "<th>Max</th><th>n</th></tr></thead><tbody>",
            _stats_row("THC %", roll.thc_stats),
            _stats_row("MSRP $", roll.price_stats),
            "</tbody></table>",
        ]
    )

    prods = sorted(
        products_by_brand.get(roll.brand, []), key=lambda x: str(x.get("name"))
    )
    prod_rows = "".join(
        f'<tr><td><a href="/product/{esc(str(p.get("product_id")))}/">'
        f'{esc(p.get("name"))}</a></td>'
        f"<td>{esc(p.get('category'))}</td>"
        f"<td>{_pct(p.get('thc_percent'))}</td>"
        f"<td>{_money(p.get('msrp'))}</td></tr>"
        for p in prods
    )

    body = (
        f'<span class="stamp">Brand</span><h1>{esc(roll.brand)}</h1>'
        f"{attribution}"
        f'<dl class="kv">'
        f"<dt>SKUs</dt><dd>{roll.product_count}</dd>"
        f"<dt>Categories</dt><dd>{esc(', '.join(_sorted_unique(roll.categories)))}</dd>"
        f"<dt>Dispensaries</dt><dd>{esc(', '.join(_sorted_unique(roll.locations)))}</dd>"
        "</dl>"
        f"<h2>Pricing & potency</h2>{stats}"
        "<h2>Products</h2>"
        "<table><thead><tr><th>Product</th><th>Category</th><th>THC</th>"
        f"<th>MSRP</th></tr></thead><tbody>{prod_rows}</tbody></table>"
    )
    return Page(
        f"{roll.brand} — brand",
        body,
        crumbs=[("Index", "/"), ("Brands", "/brand/"), (roll.brand, None)],
    )


def _processor_page(
    roll: ProcessorRollup,
    products_by_processor: dict,
    registry: Optional[dict],
    banner: Optional[str],
) -> str:
    brand_list = "".join(
        f'<li><a href="/brand/{slugify(b)}/">{esc(b)}</a></li>'
        for b in sorted(roll.brands)
    )

    # Match the processor to a DCC license record, when one exists.
    lic_html = ""
    if registry:
        match = None
        target = roll.legal_entity.strip().casefold()
        for lic in registry.values():
            names = [lic.legal_name, *lic.trade_names]
            if any((n or "").strip().casefold() == target for n in names):
                match = lic
                break
            if (lic.legal_name or "").strip().casefold() == target:
                match = lic
                break
        if match:
            lic_html = (
                "<h2>DCC license</h2>"
                '<dl class="kv">'
                f"<dt>License #</dt><dd>{esc(match.license_number)}</dd>"
                f"<dt>Type</dt><dd>{esc(match.license_type)}</dd>"
                f"<dt>Status</dt><dd>{esc(match.status)}</dd>"
                f"<dt>City/County</dt><dd>{esc(match.city)} / {esc(match.county)}</dd>"
                f"<dt>Issued</dt><dd>{esc(match.issue_date)}</dd>"
                "</dl>"
            )

    stats = "".join(
        [
            "<table><thead><tr><th>Metric</th><th>Min</th><th>Median</th>"
            "<th>Max</th><th>n</th></tr></thead><tbody>",
            _stats_row("THC %", roll.thc_stats),
            _stats_row("MSRP $", roll.price_stats),
            "</tbody></table>",
        ]
    )

    prods = sorted(
        products_by_processor.get(roll.legal_entity, []),
        key=lambda x: (x.get("brand") or "", str(x.get("name"))),
    )
    prod_rows = "".join(
        f'<tr><td><a href="/product/{esc(str(p.get("product_id")))}/">'
        f'{esc(p.get("name"))}</a></td>'
        f'<td><a href="/brand/{slugify(p.get("brand") or "")}/">'
        f'{esc(p.get("brand"))}</a></td>'
        f"<td>{esc(p.get('category'))}</td>"
        f"<td>{_money(p.get('msrp'))}</td></tr>"
        for p in prods
    )

    body = (
        f'<span class="stamp">Processor</span><h1>{esc(roll.legal_entity)}</h1>'
        '<p class="muted">Operating legal entity. Brands below collapse to '
        "this processor in Ohio.</p>"
        f'<dl class="kv">'
        f"<dt>SKUs (all brands)</dt><dd>{roll.product_count}</dd>"
        f"<dt>Brand count</dt><dd>{len(roll.brands)}</dd>"
        f"<dt>Categories</dt><dd>{esc(', '.join(_sorted_unique(roll.categories)))}</dd>"
        "</dl>"
        f"{lic_html}"
        f"<h2>Brands operated</h2><ul>{brand_list}</ul>"
        f"<h2>Pricing & potency (rolled up)</h2>{stats}"
        "<h2>All SKUs</h2>"
        "<table><thead><tr><th>Product</th><th>Brand</th><th>Category</th>"
        f"<th>MSRP</th></tr></thead><tbody>{prod_rows}</tbody></table>"
    )
    return Page(
        f"{roll.legal_entity} — processor",
        body,
        banner=banner,
        crumbs=[
            ("Index", "/"),
            ("Processors", "/processor/"),
            (roll.legal_entity, None),
        ],
    )


def _dispensary_page(roll: DispensaryRollup, products_by_location: dict) -> str:
    brand_list = ", ".join(
        f'<a href="/brand/{slugify(b)}/">{esc(b)}</a>' for b in sorted(roll.brands)
    )
    prods = sorted(
        products_by_location.get(roll.location, []),
        key=lambda x: (x.get("category") or "", str(x.get("name"))),
    )
    prod_rows = "".join(
        f'<tr><td><a href="/product/{esc(str(p.get("product_id")))}/">'
        f'{esc(p.get("name"))}</a></td>'
        f'<td><a href="/brand/{slugify(p.get("brand") or "")}/">'
        f'{esc(p.get("brand"))}</a></td>'
        f"<td>{esc(p.get('category'))}</td>"
        f"<td>{_money(p.get('msrp'))}</td></tr>"
        for p in prods
    )
    body = (
        f'<span class="stamp">Dispensary</span><h1>{esc(roll.location)}</h1>'
        f'<dl class="kv">'
        f"<dt>SKUs</dt><dd>{roll.product_count}</dd>"
        f"<dt>Brands</dt><dd>{brand_list}</dd>"
        f"<dt>Categories</dt><dd>{esc(', '.join(_sorted_unique(roll.categories)))}</dd>"
        "</dl>"
        "<h2>Listings</h2>"
        "<table><thead><tr><th>Product</th><th>Brand</th><th>Category</th>"
        f"<th>MSRP</th></tr></thead><tbody>{prod_rows}</tbody></table>"
    )
    return Page(
        f"{roll.location} — dispensary",
        body,
        crumbs=[
            ("Index", "/"),
            ("Dispensaries", "/dispensary/"),
            (roll.location, None),
        ],
    )


def _license_page(lic: DCCLicense, kind: str, banner: Optional[str]) -> str:
    body = (
        f'<span class="stamp">{esc(kind)}</span>'
        f"<h1>{esc(lic.legal_name)}</h1>"
        f'<p class="muted">License {esc(lic.license_number)}</p>'
        f'<dl class="kv">'
        f"<dt>License type</dt><dd>{esc(lic.license_type)}</dd>"
        f"<dt>Status</dt><dd>{esc(lic.status)}</dd>"
        f"<dt>Trade names</dt><dd>{esc(', '.join(lic.trade_names) or '—')}</dd>"
        f"<dt>Address</dt><dd>{esc(lic.address)}</dd>"
        f"<dt>City</dt><dd>{esc(lic.city)}</dd>"
        f"<dt>County</dt><dd>{esc(lic.county)}</dd>"
        f"<dt>ZIP</dt><dd>{esc(lic.zip)}</dd>"
        f"<dt>Issued</dt><dd>{esc(lic.issue_date)}</dd>"
        f"<dt>Status date</dt><dd>{esc(lic.status_date)}</dd>"
        f"<dt>Source</dt><dd>{esc(lic.source_url)}</dd>"
        "</dl>"
    )
    crumb_root = "/cultivator/" if kind == "Cultivator" else "/testing-lab/"
    return Page(
        f"{lic.legal_name} — {kind.lower()}",
        body,
        banner=banner,
        crumbs=[
            ("Index", "/"),
            (kind + "s", crumb_root),
            (lic.license_number, None),
        ],
    )


def _index_page(
    products: list[dict],
    rollups: dict,
    categories: list[str],
    has_cultivators: bool,
    has_labs: bool,
    banner: Optional[str],
) -> str:
    cat_links = "".join(
        f'<li><a href="/{slugify(c)}/">{esc(c.title())}</a> '
        f'<span class="muted">({sum(1 for p in products if p.get("category") == c)})</span></li>'
        for c in categories
    )
    entity_links = [
        '<li><a href="/brand/">Brands</a> '
        f'<span class="muted">({len(rollups["brands"])})</span></li>',
        '<li><a href="/processor/">Processors (operating LLCs)</a> '
        f'<span class="muted">({len(rollups["processors"])})</span></li>',
        '<li><a href="/dispensary/">Dispensaries</a> '
        f'<span class="muted">({len(rollups["dispensaries"])})</span></li>',
    ]
    if has_cultivators:
        entity_links.append('<li><a href="/cultivator/">Cultivators</a></li>')
    if has_labs:
        entity_links.append('<li><a href="/testing-lab/">Testing labs</a></li>')

    body = (
        '<span class="stamp">Docket index</span>'
        "<h1>OHCanna transparency docket</h1>"
        f'<p class="muted">{len(products)} product record(s) indexed.</p>'
        "<h2>Browse by category</h2>"
        f"<ul>{cat_links}</ul>"
        "<h2>Entities</h2>"
        f"<ul>{''.join(entity_links)}</ul>"
        '<p class="muted"><a href="/sitemap.xml">sitemap.xml</a></p>'
    )
    return Page("OHCanna — docket index", body, banner=banner)


def _entity_index(title: str, root: str, items: list[tuple[str, str]]) -> str:
    rows = "".join(
        f'<li><a href="{esc(href)}">{esc(label)}</a></li>'
        for label, href in sorted(items)
    )
    body = f"<h1>{esc(title)}</h1><ul>{rows}</ul>"
    return Page(title, body, crumbs=[("Index", "/"), (title, None)])


def _sitemap(urls: list[str], base: str = "") -> str:
    entries = "".join(
        f"<url><loc>{esc(base + u)}</loc></url>" for u in sorted(set(urls))
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{entries}</urlset>\n"
    )


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------

def build_site(
    products: list[dict],
    rollups: dict,
    out_dir: str | Path,
    registry: Optional[dict[str, DCCLicense]] = None,
    links: Optional[list[BrandProcessorLink]] = None,
    base_url: str = "",
) -> list[str]:
    """Render the full static site under ``out_dir``; return generated URLs.

    ``rollups`` is the dict from ``build_all_rollups`` (keys ``brands``,
    ``processors``, ``dispensaries``). ``registry`` (optional) is a
    ``{license_number: DCCLicense}`` map — when provided, cultivator and
    testing-lab pages plus a registry-freshness banner are emitted; when
    absent those pages are skipped gracefully. ``links`` is the optional
    brand->processor seed map used for brand-page verification stamping.
    """
    out_dir = Path(out_dir)
    links = links or []
    urls: list[str] = []
    banner = _registry_banner(registry) if registry else None

    brands: dict[str, BrandRollup] = rollups["brands"]
    processors: dict[str, ProcessorRollup] = rollups["processors"]
    dispensaries: dict[str, DispensaryRollup] = rollups["dispensaries"]

    # Pre-bucket products for the entity pages (deterministic via sorts later).
    by_brand: dict[str, list[dict]] = {}
    by_processor: dict[str, list[dict]] = {}
    by_location: dict[str, list[dict]] = {}
    by_category: dict[str, list[dict]] = {}
    from ..brands import legal_entity_for

    for p in products:
        by_brand.setdefault(p.get("brand", ""), []).append(p)
        entity = legal_entity_for(p.get("brand", "")) or UNKNOWN_PROCESSOR
        by_processor.setdefault(entity, []).append(p)
        by_location.setdefault(p.get("location", ""), []).append(p)
        by_category.setdefault(p.get("category", ""), []).append(p)

    categories = sorted(c for c in by_category if c)

    # Registry-derived license groups.
    cultivators: list[DCCLicense] = []
    labs: list[DCCLicense] = []
    if registry:
        for lic in registry.values():
            if lic.license_type in _CULTIVATOR_TYPES:
                cultivators.append(lic)
            elif lic.license_type in _TESTING_LAB_TYPES:
                labs.append(lic)

    # --- index ---
    _write_page(
        out_dir,
        "/",
        _index_page(
            products,
            rollups,
            categories,
            bool(cultivators),
            bool(labs),
            banner,
        ),
    )
    urls.append("/")

    # --- category browse pages ---
    for cat in categories:
        url = f"/{slugify(cat)}/"
        _write_page(out_dir, url, _category_page(cat, by_category[cat]))
        urls.append(url)

    # --- product detail pages ---
    seen_pids: set[str] = set()
    for p in products:
        pid = str(p.get("product_id"))
        if not pid or pid in seen_pids:
            continue
        seen_pids.add(pid)
        url = f"/product/{pid}/"
        _write_page(out_dir, url, _product_page(p, brands, processors))
        urls.append(url)

    # --- brand pages + index ---
    brand_index_items: list[tuple[str, str]] = []
    for name, roll in brands.items():
        if not name:
            continue
        url = roll.canonical_path
        _write_page(out_dir, url, _brand_page(roll, by_brand, links))
        urls.append(url)
        brand_index_items.append((name, url))
    _write_page(
        out_dir, "/brand/", _entity_index("Brands", "/brand/", brand_index_items)
    )
    urls.append("/brand/")

    # --- processor pages + index ---
    proc_index_items: list[tuple[str, str]] = []
    for name, roll in processors.items():
        url = roll.canonical_path
        _write_page(
            out_dir, url, _processor_page(roll, by_processor, registry, banner)
        )
        urls.append(url)
        proc_index_items.append((name, url))
    _write_page(
        out_dir,
        "/processor/",
        _entity_index("Processors", "/processor/", proc_index_items),
    )
    urls.append("/processor/")

    # --- dispensary pages + index ---
    disp_index_items: list[tuple[str, str]] = []
    for name, roll in dispensaries.items():
        if not name:
            continue
        url = roll.canonical_path
        _write_page(out_dir, url, _dispensary_page(roll, by_location))
        urls.append(url)
        disp_index_items.append((name, url))
    _write_page(
        out_dir,
        "/dispensary/",
        _entity_index("Dispensaries", "/dispensary/", disp_index_items),
    )
    urls.append("/dispensary/")

    # --- registry-only pages: cultivators + testing labs ---
    if cultivators:
        items = []
        for lic in cultivators:
            url = f"/cultivator/{slugify(lic.license_number)}/"
            _write_page(out_dir, url, _license_page(lic, "Cultivator", banner))
            urls.append(url)
            items.append((f"{lic.legal_name} ({lic.license_number})", url))
        _write_page(
            out_dir,
            "/cultivator/",
            _entity_index("Cultivators", "/cultivator/", items),
        )
        urls.append("/cultivator/")

    if labs:
        items = []
        for lic in labs:
            url = f"/testing-lab/{slugify(lic.license_number)}/"
            _write_page(out_dir, url, _license_page(lic, "Testing lab", banner))
            urls.append(url)
            items.append((f"{lic.legal_name} ({lic.license_number})", url))
        _write_page(
            out_dir,
            "/testing-lab/",
            _entity_index("Testing labs", "/testing-lab/", items),
        )
        urls.append("/testing-lab/")

    # --- sitemap.xml (mandatory: every generated page) ---
    sitemap_xml = _sitemap(urls, base=base_url)
    (out_dir / "sitemap.xml").write_text(sitemap_xml, encoding="utf-8")

    return sorted(set(urls))


def main(
    out_dir: str | Path = "public",
    data_root: str | Path = DEFAULT_DATA_ROOT,
) -> list[str]:
    """Convenience entry: load latest snapshots + rollups + registry, build."""
    data_root = Path(data_root)
    products: list[dict] = []
    latest_dir = data_root / "latest"
    if latest_dir.is_dir():
        for path in sorted(latest_dir.glob("*.json")):
            records = read_snapshot(path)
            if isinstance(records, list):
                products.extend(records)

    rollups = build_all_rollups(products)

    registry = None
    links = None
    entities_dir = data_root / "entities"
    reg_path = entities_dir / "example_registry.json"
    map_path = entities_dir / "brand_processor_map.json"
    if reg_path.is_file():
        registry = load_registry(str(reg_path))
    if map_path.is_file():
        links = load_brand_processor_map(str(map_path))

    return build_site(
        products, rollups, out_dir, registry=registry, links=links
    )


if __name__ == "__main__":  # pragma: no cover
    import sys

    out = sys.argv[1] if len(sys.argv) > 1 else "public"
    generated = main(out)
    print(f"built {len(generated)} pages -> {out}")
