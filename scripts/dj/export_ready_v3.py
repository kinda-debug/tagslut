#!/usr/bin/env python3
"""Export DJ-ready rows from v3 canonical + DJ profile joins."""

from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path
from urllib.parse import quote

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
        writer.writerows(rows)
    return resolved


def _fetch_rows(
    conn: sqlite3.Connection,
    *,
    min_rating: int | None,
    min_energy: int | None,
    set_roles: list[str],
    only_profiled: bool,
    limit: int | None,
) -> list[dict[str, object]]:
    where = [
        "ti.merged_into_id IS NULL",
        "ist.status = 'active'",
        "pa.asset_id IS NOT NULL",
    ]
    params: list[object] = []

    if min_rating is not None:
        where.append("dj.rating >= ?")
        params.append(int(min_rating))
    if min_energy is not None:
        where.append("dj.energy >= ?")
        params.append(int(min_energy))
    clean_roles = [role.strip().lower() for role in set_roles if role.strip()]
    if clean_roles:
        placeholders = ",".join("?" for _ in clean_roles)
        where.append(f"dj.set_role IN ({placeholders})")
        params.extend(clean_roles)
    if only_profiled:
        where.append("dj.identity_id IS NOT NULL")

    limit_sql = ""
    if limit is not None:
        limit_sql = " LIMIT ?"
        params.append(int(limit))

    query = f"""
        SELECT
            ti.id AS identity_id,
            ti.canonical_artist AS artist,
            ti.canonical_title AS title,
            ti.canonical_bpm AS bpm,
            ti.canonical_key AS key,
            ti.canonical_genre AS genre,
            ti.canonical_duration AS duration_s,
            af.path AS preferred_path,
            dj.rating AS rating,
            dj.energy AS energy,
            dj.set_role AS set_role,
            COALESCE(dj.dj_tags_json, '[]') AS dj_tags_json,
            COALESCE(dj.notes, '') AS notes,
            COALESCE(dj.last_played_at, '') AS last_played_at
        FROM track_identity ti
        JOIN identity_status ist ON ist.identity_id = ti.id
        JOIN preferred_asset pa ON pa.identity_id = ti.id
        JOIN asset_file af ON af.id = pa.asset_id
        LEFT JOIN dj_track_profile dj ON dj.identity_id = ti.id
        WHERE {' AND '.join(where)}
        ORDER BY LOWER(COALESCE(ti.canonical_artist, '')), LOWER(COALESCE(ti.canonical_title, '')), ti.id ASC
        {limit_sql}
    """

    rows = conn.execute(query, tuple(params)).fetchall()
    out: list[dict[str, object]] = []
    for row in rows:
        out.append(
            {
                "identity_id": int(row["identity_id"]),
                "artist": row["artist"] or "",
                "title": row["title"] or "",
                "bpm": "" if row["bpm"] is None else row["bpm"],
                "key": row["key"] or "",
                "genre": row["genre"] or "",
                "duration_s": "" if row["duration_s"] is None else row["duration_s"],
                "preferred_path": row["preferred_path"] or "",
                "rating": "" if row["rating"] is None else row["rating"],
                "energy": "" if row["energy"] is None else row["energy"],
                "set_role": row["set_role"] or "",
                "dj_tags_json": row["dj_tags_json"] or "[]",
                "notes": row["notes"] or "",
                "last_played_at": row["last_played_at"] or "",
            }
        )
    return out


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export DJ-ready v3 candidates")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--min-rating", type=int)
    parser.add_argument("--min-energy", type=int)
    parser.add_argument("--set-role", action="append", default=[])
    parser.add_argument("--only-profiled", action="store_true")
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
        rows = _fetch_rows(
            conn,
            min_rating=args.min_rating,
            min_energy=args.min_energy,
            set_roles=args.set_role,
            only_profiled=bool(args.only_profiled),
            limit=args.limit,
        )
        out_path = _write_csv(args.out, rows)
    finally:
        conn.close()

    print(f"v3 db: {args.db.expanduser().resolve()}")
    print(f"out: {out_path}")
    print(f"rows_exported: {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
