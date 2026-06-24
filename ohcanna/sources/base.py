"""Source abstraction.

Every dispensary or backend integration implements this. The orchestrator
iterates `scrape_all()` and persists per-(location, category) snapshots;
a failure in one sub-scrape must not abort the run (P2 §4 acceptance bar).

`scrape()` is split into `fetch_raw()` + `parse_raw()` so the raw payload
(HTML for an SSR storefront, JSON for a GraphQL backend) can be recorded
to disk as a regression-test fixture before parsing. See
`tests/test_recorder.py`.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterator

from ohcanna.models import Product
from ohcanna.storage import write_fixture

log = logging.getLogger(__name__)


class Source(ABC):
    name: str = ""
    raw_ext: str = "html"  # override for sources returning JSON, etc.

    @abstractmethod
    def list_locations(self) -> list[str]: ...

    @abstractmethod
    def list_categories(self) -> list[str]: ...

    @abstractmethod
    def fetch_raw(self, location: str, category: str) -> str: ...

    @abstractmethod
    def parse_raw(self, raw: str, location: str, category: str) -> list[Product]: ...

    def scrape(self, location: str, category: str) -> list[Product]:
        raw = self.fetch_raw(location, category)
        return self.parse_raw(raw, location, category)

    def scrape_all(
        self,
        locations: list[str] | None = None,
        categories: list[str] | None = None,
        record_fixtures: bool = False,
    ) -> Iterator[tuple[str, str, list[Product], Exception | None]]:
        """Yield one tuple per (location, category) attempted.

        Catches per-sub-scrape exceptions so a single failure doesn't kill
        the run. Callers persist successful slices and log the failures.
        When `record_fixtures` is true, the raw payload is written to
        `storage.fixture_path(...)` between fetch and parse.
        """
        locs = locations or self.list_locations()
        cats = categories or self.list_categories()
        for loc in locs:
            for cat in cats:
                try:
                    raw = self.fetch_raw(loc, cat)
                    if record_fixtures:
                        path = write_fixture(self.name, loc, cat, raw, ext=self.raw_ext)
                        log.info("recorded fixture: %s", path)
                    yield loc, cat, self.parse_raw(raw, loc, cat), None
                except Exception as exc:  # noqa: BLE001 - acceptance bar requires it
                    log.warning("scrape failed: %s/%s/%s: %s", self.name, loc, cat, exc)
                    yield loc, cat, [], exc
