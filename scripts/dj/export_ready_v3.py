#!/usr/bin/env python3
"""Export DJ-ready rows by joining candidates with dj profile fields."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.dj.export_candidates_v3 import _build_rows, _parse_where_clause, _table_exists  # noqa: E402

CSV_COLUMNS = [
    "identity_id",
    "artist",
    "title",
    "bpm",
    "key",
    "genre",
    "duration_s",
    "preferred_path",
    "rating",
    "energy",
    "set_role",
    "dj_tags_json",
    "notes",
    "last_played_at",
]


def _connect_ro(path: Path) -> sqlite3.Connection:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"v3 DB not found: {resolved}")
    uri = f"file:{quote(str(resolved))}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA query_only=ON")
    return conn


def _write_csv(path: Path, rows: list[dict[str, object]]) -> Path:
    resolved = path.expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    with resolved.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return resolved


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export DJ-ready v3 candidates")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--min-rating", type=int)
    parser.add_argument("--set-role")
    parser.add_argument("--min-energy", type=int)
    parser.add_argument("--only-profiled", action="store_true")
    parser.add_argument("--include-orphans", action="store_true")
    parser.add_argument("--no-require-preferred", action="store_true")
    parser.add_argument("--limit", type=int)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        conn = _connect_ro(args.db)
    except FileNotFoundError as exc:
        print(str(exc))
        return 2

    try:
        where_predicates = _parse_where_clause(None)
        candidates, _ = _build_rows(
            conn,
            include_orphans=bool(args.include_orphans),
            require_preferred=not bool(args.no_require_preferred),
            min_bpm=None,
            max_bpm=None,
            min_duration=None,
            max_duration=None,
            where_predicates=where_predicates,
            strict=True,
        )

        profiles_by_id: dict[int, dict[str, object]] = {}
        if _table_exists(conn, "dj_track_profile"):
            for row in conn.execute(
                """
                SELECT identity_id, rating, energy, set_role, dj_tags_json, notes, last_played_at
                FROM dj_track_profile
                ORDER BY identity_id ASC
                """
            ).fetchall():
                profiles_by_id[int(row["identity_id"])] = {
                    "rating": row["rating"],
                    "energy": row["energy"],
                    "set_role": row["set_role"],
                    "dj_tags_json": row["dj_tags_json"] or "[]",
                    "notes": row["notes"] or "",
                    "last_played_at": row["last_played_at"] or "",
                }

        out_rows: list[dict[str, object]] = []
        for cand in candidates:
            identity_id = int(cand["identity_id"])
            profile = profiles_by_id.get(identity_id)
            if bool(args.only_profiled) and profile is None:
                continue

            rating = profile.get("rating") if profile else None
            energy = profile.get("energy") if profile else None
            set_role = (profile.get("set_role") if profile else "") or ""
            dj_tags_json = (profile.get("dj_tags_json") if profile else "[]") or "[]"
            notes = (profile.get("notes") if profile else "") or ""
            last_played_at = (profile.get("last_played_at") if profile else "") or ""

            if args.min_rating is not None and (rating is None or int(rating) < int(args.min_rating)):
                continue
            if args.min_energy is not None and (energy is None or int(energy) < int(args.min_energy)):
                continue
            if args.set_role and set_role != str(args.set_role).strip().lower():
                continue

            out_rows.append(
                {
                    "identity_id": identity_id,
                    "artist": cand["artist"],
                    "title": cand["title"],
                    "bpm": "" if cand["bpm"] is None else cand["bpm"],
                    "key": cand["key"],
                    "genre": cand["genre"],
                    "duration_s": "" if cand["duration_s"] is None else cand["duration_s"],
                    "preferred_path": cand["preferred_path"],
                    "rating": "" if rating is None else rating,
                    "energy": "" if energy is None else energy,
                    "set_role": set_role,
                    "dj_tags_json": dj_tags_json,
                    "notes": notes,
                    "last_played_at": last_played_at,
                }
            )

        out_rows.sort(key=lambda item: (str(item["artist"]).casefold(), str(item["title"]).casefold(), int(item["identity_id"])))
        if args.limit is not None:
            out_rows = out_rows[: int(args.limit)]

        out_path = _write_csv(args.out, out_rows)
    finally:
        conn.close()

    print(f"v3 db: {args.db.expanduser().resolve()}")
    print(f"out: {out_path}")
    print(f"rows_exported: {len(out_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
