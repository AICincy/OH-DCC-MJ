"""DCC license registry schema and local-file (Path B) ingestion.

Implements the offline-buildable part of the P4 spec
(docs/P4-dcc-license-registry.md): the data model (DCCLicense,
BrandProcessorLink), a "Path B" ingestion layer that reads license records
from a local JSON file, a registry diff/change-log helper, and the
brand->processor mapping loader/resolver.

Out of scope here (deferred to work item V1):
  - Path A (live DCC registry scrape) — requires a verified registry URL and
    network access. No HTTP/network code lives in this module.
  - Path C (ORC § 149.43 public-records request ingestion).

Per P4 §6 O5, unverified brand->processor mappings never surface to
user-facing callers: `resolve_processor` only returns links whose
verification_status == "verified".
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class DCCLicense:
    """A single DCC license record. `license_number` is the primary key."""

    license_number: str           # canonical primary key
    license_type: str             # cultivator_l1 | cultivator_l2 | processor | dispensary | testing_lab
    legal_name: str               # the LLC or corporation
    trade_names: list[str] = field(default_factory=list)  # operating-as names
    address: str = ""
    city: str = ""
    county: str = ""
    zip: str = ""
    status: str = ""              # active | provisional | surrendered | suspended | revoked
    issue_date: Optional[str] = None    # ISO8601
    status_date: Optional[str] = None   # ISO8601, last status change
    source_url: str = ""
    fetched_at: str = ""          # ISO8601
    notes: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BrandProcessorLink:
    """An inferred brand -> processor relationship (P4 §3, §5)."""

    brand: str
    processor_license_number: str
    link_type: str                # in_house | exclusive_ohio_license | white_label | co_brand
    effective_date: Optional[str] = None
    verified_sources: list[dict] = field(default_factory=list)  # see A1 schema
    verification_status: str = "unverified"  # verified | unverified | disputed

    def to_dict(self) -> dict:
        return asdict(self)


# Fields that DCCLicense considers required (no sensible default at ingest).
_REQUIRED_LICENSE_FIELDS = ("license_number", "license_type", "legal_name")

# Recognised DCCLicense fields, used to filter unknown JSON keys.
_LICENSE_FIELDS = set(DCCLicense.__dataclass_fields__.keys())
_LINK_FIELDS = set(BrandProcessorLink.__dataclass_fields__.keys())


def _coerce_license(record: dict) -> DCCLicense:
    """Build a DCCLicense from a JSON dict, tolerating missing optional fields."""
    for req in _REQUIRED_LICENSE_FIELDS:
        if not record.get(req):
            raise ValueError(
                f"license record missing required field {req!r}: {record!r}"
            )
    kwargs = {k: v for k, v in record.items() if k in _LICENSE_FIELDS}
    # Normalise trade_names to a list if it arrives as a scalar/None.
    tn = kwargs.get("trade_names")
    if tn is None:
        kwargs["trade_names"] = []
    elif isinstance(tn, str):
        kwargs["trade_names"] = [tn]
    return DCCLicense(**kwargs)


def load_registry(path: str) -> dict[str, DCCLicense]:
    """Path B ingestion: read a local JSON file of license records.

    The JSON may be either a top-level list of records, or an object with a
    "licenses" key holding that list (so a file can also carry a leading
    comment / metadata field, e.g. the sample fixture). Unknown keys on each
    record are ignored; missing optional fields fall back to defaults.

    Returns a dict keyed by license_number.
    """
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    if isinstance(data, dict):
        records = data.get("licenses", [])
    else:
        records = data

    registry: dict[str, DCCLicense] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        lic = _coerce_license(record)
        registry[lic.license_number] = lic
    return registry


def diff_registries(
    old: dict[str, DCCLicense], new: dict[str, DCCLicense]
) -> dict:
    """Diff two registries by license_number (P4 §4 step 3-4 change log).

    Returns a dict with three lists:
      - "added":   license_numbers present in `new` but not `old`
      - "removed": license_numbers present in `old` but not `new`
      - "status_changed": list of {license_number, old_status, new_status}
        for licenses present in both whose `status` differs.
    """
    old_keys = set(old)
    new_keys = set(new)

    added = sorted(new_keys - old_keys)
    removed = sorted(old_keys - new_keys)

    status_changed = []
    for ln in sorted(old_keys & new_keys):
        if old[ln].status != new[ln].status:
            status_changed.append(
                {
                    "license_number": ln,
                    "old_status": old[ln].status,
                    "new_status": new[ln].status,
                }
            )

    return {
        "added": added,
        "removed": removed,
        "status_changed": status_changed,
    }


def load_brand_processor_map(path: str) -> list[BrandProcessorLink]:
    """Load brand->processor links from a local JSON file.

    The JSON may be a top-level list of link records or an object with a
    "links" key. Unknown keys are ignored; missing fields fall back to
    BrandProcessorLink defaults.
    """
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    if isinstance(data, dict):
        records = data.get("links", [])
    else:
        records = data

    links: list[BrandProcessorLink] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        if not record.get("brand"):
            raise ValueError(f"link record missing required field 'brand': {record!r}")
        kwargs = {k: v for k, v in record.items() if k in _LINK_FIELDS}
        kwargs.setdefault("processor_license_number", "TBD")
        kwargs.setdefault("link_type", "")
        links.append(BrandProcessorLink(**kwargs))
    return links


def resolve_processor(
    brand: str, links: list[BrandProcessorLink]
) -> Optional[BrandProcessorLink]:
    """Return the verified processor link for `brand`, or None.

    Per P4 §6 O5, only links with verification_status == "verified" are
    returned; unverified/disputed mappings never surface. Matching on `brand`
    is case-insensitive. The first verified match wins.
    """
    needle = brand.strip().casefold()
    for link in links:
        if (
            link.brand.strip().casefold() == needle
            and link.verification_status == "verified"
        ):
            return link
    return None


def merge_brands_yaml(
    brand_yaml_entities: dict[str, Optional[str]],
    links: list[BrandProcessorLink],
    registry: Optional[dict[str, DCCLicense]] = None,
) -> list[dict]:
    """Cross-reference the existing brands.yaml legal_entity names with the
    brand->processor links (and, when available, the DCC registry).

    `brand_yaml_entities` is the {display_name: legal_entity_or_None} map that
    `ohcanna.brands` exposes. For each brand with a link, this best-effort
    matches the brand's brands.yaml legal_entity against the legal_name of the
    license referenced by the link (case-insensitive substring match), so a
    reviewer can see where the seed map agrees with the registry.

    Returns a list of report rows; this is a diagnostic helper, not a mutator —
    it does not edit brands.yaml or any input.
    """
    registry = registry or {}
    rows: list[dict] = []
    for link in links:
        yaml_entity = brand_yaml_entities.get(link.brand)
        lic = registry.get(link.processor_license_number)
        registry_legal_name = lic.legal_name if lic else None

        matches_registry = False
        if yaml_entity and registry_legal_name:
            a = yaml_entity.strip().casefold()
            b = registry_legal_name.strip().casefold()
            matches_registry = a in b or b in a

        rows.append(
            {
                "brand": link.brand,
                "yaml_legal_entity": yaml_entity,
                "processor_license_number": link.processor_license_number,
                "registry_legal_name": registry_legal_name,
                "verification_status": link.verification_status,
                "matches_registry": matches_registry,
            }
        )
    return rows
