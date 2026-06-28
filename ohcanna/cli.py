"""`python -m ohcanna ...` entry point."""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

from ohcanna import __version__
from ohcanna.analysis.engine import analyze_dataset
from ohcanna.sources import REGISTRY
from ohcanna.storage import update_latest, write_snapshot

log = logging.getLogger(__name__)


def _cmd_scrape(args: argparse.Namespace) -> int:
    src_cls = REGISTRY.get(args.source)
    if src_cls is None:
        print(f"unknown source: {args.source}. options: {sorted(REGISTRY)}", file=sys.stderr)
        return 2
    src = src_cls()
    # --delay tunes the inter-request sleep for sources that support it
    # (e.g. Klutch's N+1 per-product page fetch). Sources without a `delay`
    # attribute keep their built-in rate limit.
    if args.delay is not None and hasattr(src, "delay"):
        src.delay = args.delay

    locations = [args.location] if args.location else src.list_locations()
    categories = [args.category] if args.category else src.list_categories()

    if args.dry_run:
        print(f"source={args.source} version={__version__}")
        print(f"matrix: {len(locations)} locations x {len(categories)} categories"
              f" = {len(locations) * len(categories)} sub-scrapes")
        for loc in locations:
            for cat in categories:
                print(f"  - {loc} / {cat}")
        return 0

    record_fixtures = args.record_fixtures or os.environ.get("OHCANNA_RECORD_FIXTURES") == "1"

    date = time.strftime("%Y-%m-%d", time.gmtime())
    by_category: dict[str, list] = {}
    failures: list[tuple[str, str, Exception]] = []
    total = 0
    for loc, cat, products, exc in src.scrape_all(
        locations, categories, record_fixtures=record_fixtures
    ):
        if exc is not None:
            failures.append((loc, cat, exc))
            continue
        if not products:
            log.warning("0 products: %s/%s", loc, cat)
        path = write_snapshot(args.source, loc, cat, products, date=date)
        log.info("wrote %d products to %s", len(products), path)
        by_category.setdefault(cat, []).extend(p.to_dict() for p in products)
        total += len(products)

    for cat, records in by_category.items():
        update_latest(args.source, cat, records)

    print(f"scraped {total} products across {len(by_category)} categories"
          f" ({len(failures)} sub-scrape failures)")
    for loc, cat, exc in failures:
        print(f"  FAIL {loc}/{cat}: {exc}", file=sys.stderr)
    return 0 if not failures else 1


def _cmd_analyze(args: argparse.Namespace) -> int:
    path = Path(args.snapshot)
    with open(path) as f:
        products = json.load(f)
    flagged = analyze_dataset(products)
    out_path = path.with_name(path.stem + "_flagged.json")
    with open(out_path, "w") as f:
        json.dump(flagged, f, indent=2)
    flagged_count = sum(1 for p in flagged if p["flag_count"] > 0)
    print(f"analyzed {len(flagged)} products, {flagged_count} carry at least one flag")
    print(f"output: {out_path}")
    return 0


def _cmd_build(args: argparse.Namespace) -> int:
    from ohcanna.publication.build import main as build_main

    urls = build_main(out_dir=args.out_dir, data_root=args.data_root)
    print(f"built {len(urls)} pages into {args.out_dir}/ (sitemap.xml lists all)")
    return 0


def _cmd_community(args: argparse.Namespace) -> int:
    from ohcanna.community.moderation import ModerationQueue

    queue = ModerationQueue(data_root=Path(args.data_root))
    records = (
        queue.list_by_status(args.status) if args.status else queue.list_pending()
    )
    label = args.status or "pending"
    print(f"{len(records)} submission(s) [{label}]")
    for sub in records:
        sub_id = getattr(sub, "submission_id", None) or sub.get("submission_id")
        brand = getattr(sub, "brand", None) or sub.get("brand", "?")
        batch = getattr(sub, "batch_id", None) or sub.get("batch_id", "?")
        print(f"  {sub_id}  {brand} / batch {batch}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ohcanna")
    p.add_argument("--version", action="version", version=f"ohcanna {__version__}")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scrape", help="run a source against locations and categories")
    s.add_argument("--source", required=True)
    s.add_argument("--location", help="restrict to one location")
    s.add_argument("--category", help="restrict to one category")
    s.add_argument("--dry-run", action="store_true",
                   help="print the (location, category) matrix and exit")
    s.add_argument("--delay", type=float, default=None,
                   help="seconds to sleep between requests, for sources that "
                        "support it (e.g. klutch). Default: the source's "
                        "built-in rate limit (2.0s, P2 §9).")
    s.add_argument("--record-fixtures", action="store_true",
                   help="save raw HTML/JSON payloads under ohcanna/data/fixtures/ "
                        "for regression tests (see README §Fixtures). Also honors "
                        "OHCANNA_RECORD_FIXTURES=1.")
    s.set_defaults(func=_cmd_scrape)

    a = sub.add_parser("analyze", help="apply consistency rules to a snapshot JSON")
    a.add_argument("snapshot")
    a.set_defaults(func=_cmd_analyze)

    b = sub.add_parser("build", help="render the static site from snapshots")
    b.add_argument("--out-dir", default="public", help="output directory (default: public)")
    b.add_argument("--data-root", default="data", help="snapshot data root (default: data)")
    b.set_defaults(func=_cmd_build)

    c = sub.add_parser("community", help="inspect the COA moderation queue")
    c.add_argument("--status", help="filter by submission status (default: pending)")
    c.add_argument("--data-root", default="data", help="community data root (default: data)")
    c.set_defaults(func=_cmd_community)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
