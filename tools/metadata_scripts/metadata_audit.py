#!/usr/bin/env python3
"""Audit canonical BPM/Key/Genre quality in tagslut DB.

Outputs:
  - summary JSON
  - flags CSV (missing/outliers/invalids)
  - ISRC conflicts CSV
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
import tomllib
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


_REPO = Path(__file__).resolve().parents[2]
DEFAULT_DB_FALLBACK = "/Users/georgeskhawam/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db"
CONFIG_TOML = _REPO / "config.toml"


def _load_config_db_path() -> str:
    if not CONFIG_TOML.exists():
        return ""
    try:
        data = tomllib.loads(CONFIG_TOML.read_text(encoding="utf-8"))
    except Exception:
        return ""
    path = data.get("db", {}).get("path")
    if not path:
        return ""
    return str(path)


def _resolve_default_db() -> str:
    env_value = os.environ.get("TAGSLUT_DB", "").strip()
    if env_value:
        env_path = Path(env_value).expanduser().resolve()
        if env_path.exists():
            return str(env_path)
    config_value = _load_config_db_path()
    if config_value:
        config_path = Path(config_value).expanduser().resolve()
        if config_path.exists():
            return str(config_path)
    return DEFAULT_DB_FALLBACK


DEFAULT_DB = _resolve_default_db()
DEFAULT_OUT_DIR = Path(__file__).resolve().parents[2] / "artifacts" / "audit"

CAM_KEY_RE = re.compile(r"^(1[0-2]|[1-9])[AB]$", re.IGNORECASE)
STD_KEY_RE = re.compile(r"^[A-G](#|b)?(m|min|maj)?$", re.IGNORECASE)


@dataclass
class Row:
    path: str
    bpm: float | None
    key: str
    genre: str
    isrc: str


def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _parse_bpm(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _split_values(value: str) -> list[str]:
    if not value:
        return []
    parts = re.split(r"[;,/|]+", value)
    return [part.strip() for part in parts if part.strip()]


def _key_valid(key: str) -> bool:
    if not key:
        return False
    if CAM_KEY_RE.match(key):
        return True
    if STD_KEY_RE.match(key):
        return True
    return False


def _iter_rows(conn: sqlite3.Connection) -> Iterable[Row]:
    cursor = conn.execute(
        """
        SELECT path, canonical_bpm, canonical_key, canonical_genre, canonical_isrc
        FROM files
        WHERE path IS NOT NULL AND trim(path) != ''
        """
    )
    for path, bpm, key, genre, isrc in cursor:
        yield Row(
            path=str(path),
            bpm=_parse_bpm(bpm),
            key=_normalize_text(key),
            genre=_normalize_text(genre),
            isrc=_normalize_text(isrc),
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit canonical BPM/Key/Genre quality.")
    parser.add_argument("--db", default=DEFAULT_DB, help="Path to tagslut SQLite DB.")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="Output directory.")
    parser.add_argument("--min-bpm", type=float, default=60.0, help="Minimum expected BPM.")
    parser.add_argument("--max-bpm", type=float, default=190.0, help="Maximum expected BPM.")
    parser.add_argument("--limit", type=int, default=0, help="Limit rows (0 = all).")
    args = parser.parse_args()

    db_path = Path(args.db).expanduser().resolve()
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = _now_stamp()
    flags_path = out_dir / f"metadata_audit_flags_{stamp}.csv"
    isrc_path = out_dir / f"metadata_audit_isrc_{stamp}.csv"
    summary_path = out_dir / f"metadata_audit_summary_{stamp}.json"

    total = 0
    missing_bpm = 0
    missing_key = 0
    missing_genre = 0
    bpm_outliers = 0
    key_invalid = 0

    isrc_map: dict[str, dict[str, set[str] | int | list[str]]] = defaultdict(
        lambda: {
            "count": 0,
            "bpms": set(),
            "keys": set(),
            "genres": set(),
            "paths": [],
        }
    )

    with sqlite3.connect(str(db_path)) as conn, flags_path.open("w", newline="", encoding="utf-8") as flags_csv:
        writer = csv.DictWriter(
            flags_csv,
            fieldnames=[
                "path",
                "canonical_bpm",
                "canonical_key",
                "canonical_genre",
                "canonical_isrc",
                "flags",
            ],
        )
        writer.writeheader()

        for row in _iter_rows(conn):
            total += 1
            if args.limit and total > args.limit:
                break

            flags: list[str] = []

            if row.bpm is None:
                missing_bpm += 1
                flags.append("missing_bpm")
            else:
                if row.bpm < args.min_bpm or row.bpm > args.max_bpm:
                    bpm_outliers += 1
                    flags.append("bpm_outlier")

            if not row.key:
                missing_key += 1
                flags.append("missing_key")
            else:
                key_parts = _split_values(row.key)
                if not any(_key_valid(k) for k in key_parts):
                    key_invalid += 1
                    flags.append("invalid_key")

            genre_lower = row.genre.lower()
            if not row.genre or genre_lower in {"unknown", "none", "n/a"}:
                missing_genre += 1
                flags.append("missing_genre")

            if flags:
                writer.writerow(
                    {
                        "path": row.path,
                        "canonical_bpm": "" if row.bpm is None else row.bpm,
                        "canonical_key": row.key,
                        "canonical_genre": row.genre,
                        "canonical_isrc": row.isrc,
                        "flags": ",".join(flags),
                    }
                )

            if row.isrc:
                info = isrc_map[row.isrc]
                info["count"] = int(info["count"]) + 1
                if row.bpm is not None:
                    info["bpms"].add(str(round(row.bpm, 1)))
                if row.key:
                    info["keys"].add(row.key.strip())
                if row.genre:
                    info["genres"].add(row.genre.strip())
                paths = info["paths"]
                if isinstance(paths, list) and len(paths) < 5:
                    paths.append(row.path)

    # ISRC conflicts
    with isrc_path.open("w", newline="", encoding="utf-8") as isrc_csv:
        writer = csv.DictWriter(
            isrc_csv,
            fieldnames=[
                "isrc",
                "count",
                "distinct_bpm",
                "distinct_key",
                "distinct_genre",
                "sample_paths",
            ],
        )
        writer.writeheader()
        for isrc, info in isrc_map.items():
            if int(info["count"]) < 2:
                continue
            bpms = sorted(info["bpms"])  # type: ignore[arg-type]
            keys = sorted(info["keys"])  # type: ignore[arg-type]
            genres = sorted(info["genres"])  # type: ignore[arg-type]
            if len(bpms) <= 1 and len(keys) <= 1 and len(genres) <= 1:
                continue
            writer.writerow(
                {
                    "isrc": isrc,
                    "count": info["count"],
                    "distinct_bpm": ";".join(bpms),
                    "distinct_key": ";".join(keys),
                    "distinct_genre": ";".join(genres),
                    "sample_paths": " | ".join(info["paths"]),  # type: ignore[arg-type]
                }
            )

    summary = {
        "db": str(db_path),
        "total_rows": total,
        "missing_bpm": missing_bpm,
        "missing_key": missing_key,
        "missing_genre": missing_genre,
        "bpm_outliers": bpm_outliers,
        "invalid_key": key_invalid,
        "flags_csv": str(flags_path),
        "isrc_conflicts_csv": str(isrc_path),
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
