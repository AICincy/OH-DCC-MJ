"""Dependency-free HTML rendering helpers (no Jinja).

Everything here is plain Python string assembly. The single entry point is
``Page(title, body, ...)`` which wraps a body fragment in a full HTML
document carrying the inlined "federal docket" stylesheet.

Design constraints (P2 §4):
  - First-load HTML for any product page must stay under 50 KB. The CSS is
    a few hundred bytes inlined; no external JS, no web-font payload is
    *required* (the Google Fonts <link> is progressive — pages render fine
    on the monospace fallback if it never loads).
  - Output must be deterministic: no timestamps, no dict-order surprises.
    Callers are responsible for sorting their rows.
"""
from __future__ import annotations

from typing import Iterable, Optional


def esc(value: object) -> str:
    """Minimal HTML-escape for text/attribute content."""
    if value is None:
        return ""
    s = str(value)
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


# The federal-docket stylesheet. Kept deliberately small (well under 1 KB)
# so it can be inlined on every page without bloating first-load HTML.
_STYLE = (
    ":root{--cream:#fafafa;--ink:#1a1a1a;--red:#b30000;--rule:#d8d2c4;"
    "--muted:#6b6b6b}"
    "*{box-sizing:border-box}"
    "body{background:var(--cream);color:var(--ink);"
    "font-family:'IBM Plex Mono',ui-monospace,SFMono-Regular,Menlo,"
    "Consolas,monospace;font-size:14px;line-height:1.5;margin:0;"
    "padding:0 16px}"
    ".wrap{max-width:880px;margin:0 auto;padding:24px 0 64px}"
    "header.masthead{border-bottom:3px double var(--red);padding-bottom:8px;"
    "margin-bottom:20px}"
    "header.masthead .org{color:var(--red);font-weight:700;"
    "letter-spacing:1px;text-transform:uppercase}"
    "header.masthead .sub{color:var(--muted);font-size:12px}"
    "nav.crumbs{font-size:12px;color:var(--muted);margin-bottom:16px}"
    "nav.crumbs a{color:var(--red)}"
    "h1{font-size:20px;border-left:4px solid var(--red);padding-left:8px;"
    "margin:0 0 4px}"
    "h2{font-size:15px;text-transform:uppercase;letter-spacing:.5px;"
    "border-bottom:1px solid var(--rule);padding-bottom:4px;margin:28px 0 8px}"
    "a{color:var(--red)}"
    "table{border-collapse:collapse;width:100%;font-size:13px}"
    "th,td{text-align:left;padding:4px 8px;border-bottom:1px solid var(--rule);"
    "vertical-align:top}"
    "th{text-transform:uppercase;font-size:11px;color:var(--muted);"
    "letter-spacing:.5px}"
    "dl.kv{display:grid;grid-template-columns:max-content 1fr;gap:2px 16px;"
    "margin:0}"
    "dl.kv dt{color:var(--muted);text-transform:uppercase;font-size:11px;"
    "letter-spacing:.5px}"
    "dl.kv dd{margin:0}"
    ".banner{border:1px solid var(--red);background:#fff4f4;color:#7a0000;"
    "padding:8px 12px;font-size:12px;margin-bottom:20px}"
    ".stamp{display:inline-block;border:1px solid var(--red);color:var(--red);"
    "padding:1px 6px;font-size:11px;text-transform:uppercase;"
    "letter-spacing:1px}"
    ".muted{color:var(--muted)}"
    "footer{margin-top:48px;border-top:1px solid var(--rule);"
    "padding-top:12px;font-size:11px;color:var(--muted)}"
)

_FONT_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link rel="stylesheet" '
    'href="https://fonts.googleapis.com/css2?'
    'family=IBM+Plex+Mono:wght@400;600;700&display=swap">'
)


def Page(
    title: str,
    body: str,
    *,
    crumbs: Optional[Iterable[tuple[str, Optional[str]]]] = None,
    banner: Optional[str] = None,
    subtitle: str = "Ohio cannabis product & entity transparency docket",
) -> str:
    """Wrap a body fragment in a full HTML document.

    ``crumbs`` is a sequence of ``(label, href_or_None)`` breadcrumb items;
    items with ``href=None`` render as plain text (the current page).
    ``banner`` is optional pre-escaped HTML rendered in the red notice box
    (used for the registry-freshness banner). ``title`` and ``subtitle`` are
    escaped here; ``body``/``banner`` are inserted verbatim (callers escape).
    """
    crumb_html = ""
    if crumbs:
        parts = []
        for label, href in crumbs:
            if href:
                parts.append(f'<a href="{esc(href)}">{esc(label)}</a>')
            else:
                parts.append(esc(label))
        crumb_html = '<nav class="crumbs">' + " / ".join(parts) + "</nav>"

    banner_html = f'<div class="banner">{banner}</div>' if banner else ""

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f"<title>{esc(title)}</title>\n"
        f"{_FONT_LINK}\n"
        f"<style>{_STYLE}</style>\n"
        "</head>\n<body>\n"
        '<div class="wrap">\n'
        '<header class="masthead">'
        '<div class="org">OHCanna</div>'
        f'<div class="sub">{esc(subtitle)}</div>'
        "</header>\n"
        f"{crumb_html}\n"
        f"{banner_html}\n"
        f"{body}\n"
        "<footer>OHCanna &mdash; structured from public dispensary menus. "
        "Not affiliated with the Ohio DCC. Sample/registry data is labeled "
        "as such.</footer>\n"
        "</div>\n</body>\n</html>\n"
    )
