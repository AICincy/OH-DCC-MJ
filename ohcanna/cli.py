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
from ohcanna.analysis.rules.vape import analyze_dataset
from ohcanna.sources import REGISTRY
from ohcanna.storage import update_latest, write_snapshot

log = logging.getLogger(__name__)


def _cmd_scrape(args: argparse.Namespace) -> int:
    src_cls = REGISTRY.get(args.source)
    if src_cls is None:
        print(f"unknown source: {args.source}. options: {sorted(REGISTRY)}", file=sys.stderr)
        return 2
    src = src_cls()

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


def _cmd_build(_: argparse.Namespace) -> int:
    print("publication layer not in this phase (P2 §4 'Not in Phase 1')")
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
    s.add_argument("--record-fixtures", action="store_true",
                   help="save raw HTML/JSON payloads under ohcanna/data/fixtures/ "
                        "for regression tests (see README §Fixtures). Also honors "
                        "OHCANNA_RECORD_FIXTURES=1.")
    s.set_defaults(func=_cmd_scrape)

    a = sub.add_parser("analyze", help="apply consistency rules to a snapshot JSON")
    a.add_argument("snapshot")
    a.set_defaults(func=_cmd_analyze)

    b = sub.add_parser("build", help="(stub) publication-layer build")
    b.set_defaults(func=_cmd_build)
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
