"""Tests for the Phase 3 DCC license registry schema + Path-B ingestion.

Offline-only. Exercises load_registry / diff_registries against the sample
registry fixture, and the brand->processor seed map loader/resolver against
data/entities/brand_processor_map.json. See docs/P4-dcc-license-registry.md.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ohcanna.entities.dcc_registry import (
    DCCLicense,
    BrandProcessorLink,
    load_registry,
    diff_registries,
    load_brand_processor_map,
    resolve_processor,
)

DATA = Path(__file__).parent.parent / "data" / "entities"
EXAMPLE_REGISTRY = DATA / "example_registry.json"
BRAND_MAP = DATA / "brand_processor_map.json"


def test_load_registry_parses_fixture():
    reg = load_registry(str(EXAMPLE_REGISTRY))
    # Keyed by license_number, one entry per record.
    assert set(reg) == {
        "MMCPP000123",
        "MMCPC000456",
        "MMCPD000789",
        "MMCPT000321",
    }
    proc = reg["MMCPP000123"]
    assert isinstance(proc, DCCLicense)
    assert proc.legal_name == "AT-CPC of Ohio LLC"
    assert proc.license_type == "processor"
    assert "Klutch Cannabis" in proc.trade_names
    # One of each class present.
    types = {lic.license_type for lic in reg.values()}
    assert types == {"processor", "cultivator_l1", "dispensary", "testing_lab"}


def test_load_registry_tolerates_missing_optional_fields():
    import json
    import tempfile

    minimal = [
        {
            "license_number": "MIN001",
            "license_type": "processor",
            "legal_name": "Minimal LLC",
        }
    ]
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(minimal, fh)
        path = fh.name
    reg = load_registry(path)
    lic = reg["MIN001"]
    assert lic.trade_names == []
    assert lic.issue_date is None
    assert lic.status == ""


def test_diff_registries_detects_add_remove_status_change():
    old = {
        "A": DCCLicense("A", "processor", "Alpha LLC", status="active"),
        "B": DCCLicense("B", "processor", "Beta LLC", status="active"),
    }
    new = {
        "A": DCCLicense("A", "processor", "Alpha LLC", status="surrendered"),
        "C": DCCLicense("C", "processor", "Gamma LLC", status="active"),
    }
    diff = diff_registries(old, new)
    assert diff["added"] == ["C"]
    assert diff["removed"] == ["B"]
    assert diff["status_changed"] == [
        {"license_number": "A", "old_status": "active", "new_status": "surrendered"}
    ]


def test_load_brand_processor_map_klutch_verified():
    links = load_brand_processor_map(str(BRAND_MAP))
    by_brand = {l.brand: l for l in links}

    # Klutch family brands are verified.
    for brand in ["Citizen by Klutch", "Cookies", "Josh D", "Habitat by Klutch", "Klutch"]:
        assert by_brand[brand].verification_status == "verified", brand

    # Edie Parker and Timeless are unverified (processor unknown).
    assert by_brand["Edie Parker"].verification_status == "unverified"
    assert by_brand["Timeless"].verification_status == "unverified"


def test_resolve_processor_only_returns_verified():
    links = load_brand_processor_map(str(BRAND_MAP))
    # Unverified brand -> None (P4 §6 O5: never surfaces).
    assert resolve_processor("Edie Parker", links) is None
    assert resolve_processor("Timeless", links) is None
    # Verified brand -> a link.
    klutch = resolve_processor("Klutch", links)
    assert isinstance(klutch, BrandProcessorLink)
    assert klutch.verification_status == "verified"
    # Unknown brand -> None.
    assert resolve_processor("Nonexistent Brand", links) is None


def test_verified_links_have_at_least_two_sources():
    # P4 §6 O5: mapping records carry at least two source citations before
    # publication (i.e. before verification_status == "verified").
    links = load_brand_processor_map(str(BRAND_MAP))
    for link in links:
        if link.verification_status == "verified":
            assert len(link.verified_sources) >= 2, link.brand
