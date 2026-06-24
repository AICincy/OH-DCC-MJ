"""Static-site publication layer (Phase 2 SSG).

Pure static HTML generation from already-scraped product dicts and the
entity rollups (``ohcanna.entities.graph``). No server, no SPA, no JS
framework — every page is a plain ``index.html`` written to disk, plus a
mandatory ``sitemap.xml`` indexing every generated URL.

Aesthetic: "federal docket" — IBM Plex Mono (with a system-monospace
fallback), cream ``#fafafa`` background, federal-red ``#b30000`` accents.
CSS is inlined and tiny so first-load HTML for any product page stays well
under the 50 KB P2 acceptance bar.
"""
from __future__ import annotations

from .render import Page, esc  # noqa: F401
from .build import build_site, main  # noqa: F401
