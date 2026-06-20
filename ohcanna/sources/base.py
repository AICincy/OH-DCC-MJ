"""Source abstraction.

Every dispensary or backend integration implements this. The orchestrator
iterates `scrape_all()` and persists per-(location, category) snapshots;
a failure in one sub-scrape must not abort the run (P2 §4 acceptance bar).
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Iterator

from ohcanna.models import Product

log = logging.getLogger(__name__)


class Source(ABC):
    name: str = ""

    @abstractmethod
    def list_locations(self) -> list[str]: ...

    @abstractmethod
    def list_categories(self) -> list[str]: ...

    @abstractmethod
    def scrape(self, location: str, category: str) -> list[Product]: ...

    def scrape_all(
        self,
        locations: list[str] | None = None,
        categories: list[str] | None = None,
    ) -> Iterator[tuple[str, str, list[Product], Exception | None]]:
        """Yield one tuple per (location, category) attempted.

        Catches per-sub-scrape exceptions so a single failure doesn't kill
        the run. Callers persist successful slices and log the failures.
        """
        locs = locations or self.list_locations()
        cats = categories or self.list_categories()
        for loc in locs:
            for cat in cats:
                try:
                    yield loc, cat, self.scrape(loc, cat), None
                except Exception as exc:  # noqa: BLE001 - acceptance bar requires it
                    log.warning("scrape failed: %s/%s/%s: %s", self.name, loc, cat, exc)
                    yield loc, cat, [], exc
