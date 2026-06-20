"""Snapshot persistence.

Layout:
    data/snapshots/<YYYY-MM-DD>/<source>_<location>_<category>.json
    data/latest/<source>_<category>.json   (overwritten each run)

Writes are atomic: write to a temp file in the same directory, then rename.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Iterable

DEFAULT_DATA_ROOT = Path("data")


def _serialize(records: Iterable) -> list[dict]:
    out = []
    for r in records:
        if is_dataclass(r):
            out.append(asdict(r))
        elif isinstance(r, dict):
            out.append(r)
        else:
            raise TypeError(f"cannot serialize {type(r).__name__}")
    return out


def _atomic_write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def snapshot_path(
    source: str,
    location: str,
    category: str,
    date: str | None = None,
    data_root: Path = DEFAULT_DATA_ROOT,
) -> Path:
    date = date or time.strftime("%Y-%m-%d", time.gmtime())
    return data_root / "snapshots" / date / f"{source}_{location}_{category}.json"


def latest_path(
    source: str, category: str, data_root: Path = DEFAULT_DATA_ROOT
) -> Path:
    return data_root / "latest" / f"{source}_{category}.json"


def write_snapshot(
    source: str,
    location: str,
    category: str,
    records: Iterable,
    date: str | None = None,
    data_root: Path = DEFAULT_DATA_ROOT,
) -> Path:
    p = snapshot_path(source, location, category, date=date, data_root=data_root)
    _atomic_write_json(p, _serialize(records))
    return p


def update_latest(
    source: str,
    category: str,
    records: Iterable,
    data_root: Path = DEFAULT_DATA_ROOT,
) -> Path:
    p = latest_path(source, category, data_root=data_root)
    _atomic_write_json(p, _serialize(records))
    return p


def read_snapshot(path: Path) -> list[dict]:
    with open(path) as f:
        return json.load(f)
