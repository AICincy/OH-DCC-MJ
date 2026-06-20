"""Brand registry. Loaded from ohcanna/data/brands.yaml at import time.

Provides a list of `(match_string, canonical_display_name)` pairs ordered
by descending match-string length so that more-specific names win over
short prefixes (e.g. "Citizen by Klutch" matches before "Klutch").

`legal_entity_for(display_name)` returns the operating LLC where the
mapping has been verified (P2 §3, P4 §5); returns None otherwise. The
Phase 3 DCC registry integration (P4) is what fills in the remaining
nulls.
"""
from __future__ import annotations

from importlib import resources
from typing import Optional

import yaml


def _load() -> list[dict]:
    text = resources.files("ohcanna.data").joinpath("brands.yaml").read_text()
    data = yaml.safe_load(text)
    return data.get("brands", []) if data else []


_BRANDS = _load()

# (match_string, canonical_display_name), sorted long-first.
MATCH_TABLE: list[tuple[str, str]] = sorted(
    (
        (alias, b["display_name"])
        for b in _BRANDS
        for alias in [b["display_name"], *b.get("aliases", [])]
    ),
    key=lambda t: -len(t[0]),
)

KNOWN_BRANDS: list[str] = [b["display_name"] for b in _BRANDS]

_LEGAL_ENTITY: dict[str, Optional[str]] = {
    b["display_name"]: b.get("legal_entity") for b in _BRANDS
}


def legal_entity_for(display_name: str) -> Optional[str]:
    return _LEGAL_ENTITY.get(display_name)
