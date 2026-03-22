#!/usr/bin/env python3
"""Plan remaining unresolved backfill identity conflicts for v3."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tagslut.storage.v3.backfill_identity import (  # noqa: E402
    _PROVIDER_COLUMNS,
    _choose_equivalent_identity,
    _extract_identity_payload,
    _find_fuzzy_candidates,
    _find_identity_by_asset_path,
    _find_identity_by_identity_key,
    _identity_key_for_payload,
    _load_file_columns,
    _load_library_track_sources,
    _load_library_tracks,
    _norm_text,
    _resolve_active_identity_row,
    _resolve_equivalent_fuzzy_candidates,
)
from tagslut.storage.v3.merge_identities import choose_winner_identity  # noqa: E402

DEFAULT_CSV = Path("output/backfill_identity_conflict_plan_v3.csv")
DEFAULT_JSON = Path("output/backfill_identity_conflict_plan_v3.json")

CSV_COLUMNS = [
    "file_id",
    "path",
    "issue_type",
    "match_field",
    "match_value",
    "identity_key",
    "suggested_action",
    "reason",
    "recommended_winner_id",
    "candidate_identity_ids_json",
    "candidate_identity_keys_json",
    "candidate_isrcs_json",
    "candidate_artists_json",
    "candidate_titles_json",
]


def _connect_ro(path: Path) -> sqlite3.Connection:
    db_path = path.expanduser().resolve()
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA query_only=ON")
    return conn


def _candidate_rows_for_exact_field(
    conn: sqlite3.Connection, field: str, value: str
) -> list[sqlite3.Row]:
    rows = conn.execute(
        f"SELECT * FROM track_identity WHERE {field} = ? ORDER BY id ASC",
        (value,),
    ).fetchall()
    canonical_rows: dict[int, sqlite3.Row] = {}
    for row in rows:
        canonical, _ = _resolve_active_identity_row(conn, row)
        canonical_rows[int(canonical["id"])] = canonical
    return list(canonical_rows.values())


def _candidate_rows_for_ids(conn: sqlite3.Connection, identity_ids: list[int]) -> list[sqlite3.Row]:
    if not identity_ids:
        return []
    placeholders = ",".join("?" for _ in identity_ids)
    rows = conn.execute(
        f"SELECT * FROM track_identity WHERE id IN ({placeholders}) ORDER BY id ASC",
        tuple(identity_ids),
    ).fetchall()
    return list(rows)


def _json_list(items: list[Any]) -> str:
    return json.dumps(items, ensure_ascii=False, sort_keys=True)


def _recommended_winner_id(conn: sqlite3.Connection, rows: list[sqlite3.Row]) -> int | None:
    if len(rows) < 2:
        return int(rows[0]["id"]) if rows else None
    try:
        selection = choose_winner_identity(conn, [int(row["id"]) for row in rows])
        return int(selection.winner_id)
    except sqlite3.OperationalError:
        return min(int(row["id"]) for row in rows)


def _classify_exact_conflict(rows: list[sqlite3.Row], field: str) -> tuple[str, str]:
    artists = {_norm_text(row["artist_norm"]) for row in rows if _norm_text(row["artist_norm"])}
    titles = {_norm_text(row["title_norm"]) for row in rows if _norm_text(row["title_norm"])}
    if len(artists) > 1 or len(titles) > 1:
        return (
            "manual_review_variant_metadata",
            "same exact key maps to identities with different normalized artist/title",
        )
    if field == "isrc":
        return (
            "manual_review_exact_isrc_duplicate",
            "same ISRC remains attached to multiple active identities",
        )
    return (
        "manual_review_exact_provider_duplicate",
        f"same {field} remains attached to multiple active identities",
    )


def _classify_fuzzy_collision(rows: list[sqlite3.Row]) -> tuple[str, str]:
    exact_values: set[tuple[str, str]] = set()
    for row in rows:
        for field_name in ("isrc", *(name for name, _ in _PROVIDER_COLUMNS)):
            value = _norm_text(row[field_name]) if field_name in row.keys() else None
            if value:
                exact_values.add((field_name, value))
    if len(exact_values) > 1:
        return (
            "manual_review_distinct_exact_ids",
            "fuzzy candidates carry different exact IDs and should stay manual",
        )
    return (
        "manual_review_fuzzy_collision",
        "multiple fuzzy candidates remain after equivalent-identity collapse",
    )


def _build_plan_row(
    conn: sqlite3.Connection,
    *,
    file_id: int,
    path: str,
    issue_type: str,
    match_field: str,
    match_value: str,
    identity_key: str,
    rows: list[sqlite3.Row],
    suggested_action: str,
    reason: str,
) -> dict[str, str]:
    return {
        "file_id": str(file_id),
        "path": path,
        "issue_type": issue_type,
        "match_field": match_field,
        "match_value": match_value,
        "identity_key": identity_key,
        "suggested_action": suggested_action,
        "reason": reason,
        "recommended_winner_id": str(_recommended_winner_id(conn, rows) or ""),
        "candidate_identity_ids_json": _json_list([int(row["id"]) for row in rows]),
        "candidate_identity_keys_json": _json_list([str(row["identity_key"] or "") for row in rows]),
        "candidate_isrcs_json": _json_list(sorted({str(row["isrc"]) for row in rows if _norm_text(row["isrc"])})),
        "candidate_artists_json": _json_list(
            sorted({str(row["artist_norm"]) for row in rows if _norm_text(row["artist_norm"])})
        ),
        "candidate_titles_json": _json_list(
            sorted({str(row["title_norm"]) for row in rows if _norm_text(row["title_norm"])})
        ),
    }


def _write_csv(path: Path, rows: list[dict[str, str]]) -> Path:
    resolved = path.expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    with resolved.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return resolved


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    resolved = path.expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    return resolved


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan unresolved backfill identity conflicts and fuzzy collisions for v3."
    )
    parser.add_argument("--db", required=True, type=Path, help="Path to SQLite DB")
    parser.add_argument("--out-csv", type=Path, default=DEFAULT_CSV, help=f"CSV output path (default: {DEFAULT_CSV})")
    parser.add_argument("--out-json", type=Path, default=DEFAULT_JSON, help=f"JSON summary path (default: {DEFAULT_JSON})")
    parser.add_argument("--resume-from-file-id", type=int, default=0, help="Start at files.rowid > this value")
    parser.add_argument("--limit", type=int, default=None, help="Optional max number of files rows to inspect")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    conn = _connect_ro(args.db)
    try:
        file_columns = _load_file_columns(conn)
        library_tracks = _load_library_tracks(conn)
        library_track_sources = _load_library_track_sources(conn)

        query = "SELECT rowid AS file_id, * FROM files WHERE rowid > ? ORDER BY rowid ASC"
        params: list[Any] = [max(int(args.resume_from_file_id), 0)]
        if args.limit is not None:
            query += " LIMIT ?"
            params.append(int(args.limit))
        rows = conn.execute(query, tuple(params)).fetchall()

        plan_rows: list[dict[str, str]] = []
        issue_counts: Counter[str] = Counter()
        action_counts: Counter[str] = Counter()

        for row in rows:
            file_id = int(row["file_id"])
            library_track_key = _norm_text(row["library_track_key"]) if "library_track_key" in file_columns else None
            payload = _extract_identity_payload(
                row,
                library_tracks.get(library_track_key) if library_track_key else None,
                library_track_sources.get(library_track_key, []) if library_track_key else [],
            )
            identity_key = _identity_key_for_payload(payload)
            if not identity_key:
                continue

            path = str(row["path"])
            asset_match_id, _ = _find_identity_by_asset_path(conn, path)
            if asset_match_id is not None:
                continue

            resolved = False
            for field_name, value in [("isrc", _norm_text(payload.get("isrc"))), *[
                (provider, _norm_text(payload.get(provider))) for provider, _ in _PROVIDER_COLUMNS
            ]]:
                if not value:
                    continue
                candidate_rows = _candidate_rows_for_exact_field(conn, field_name, value)
                if len(candidate_rows) <= 1:
                    if candidate_rows:
                        resolved = True
                        break
                    continue
                equivalent = _choose_equivalent_identity(candidate_rows)
                if equivalent is not None:
                    resolved = True
                    break
                suggested_action, reason = _classify_exact_conflict(candidate_rows, field_name)
                issue_type = "exact_conflict"
                plan_rows.append(
                    _build_plan_row(
                        conn,
                        file_id=file_id,
                        path=path,
                        issue_type=issue_type,
                        match_field=field_name,
                        match_value=value,
                        identity_key=identity_key,
                        rows=candidate_rows,
                        suggested_action=suggested_action,
                        reason=reason,
                    )
                )
                issue_counts[issue_type] += 1
                action_counts[suggested_action] += 1
                resolved = True
                break

            if resolved:
                continue

            identity_key_match_id, _ = _find_identity_by_identity_key(conn, identity_key)
            if identity_key_match_id is not None:
                continue

            fuzzy_candidates = _find_fuzzy_candidates(conn, payload)
            if not fuzzy_candidates:
                continue
            equivalent_fuzzy = _resolve_equivalent_fuzzy_candidates(conn, fuzzy_candidates)
            if equivalent_fuzzy is not None:
                continue
            candidate_rows = _candidate_rows_for_ids(conn, fuzzy_candidates)
            suggested_action, reason = _classify_fuzzy_collision(candidate_rows)
            issue_type = "fuzzy_collision"
            plan_rows.append(
                _build_plan_row(
                    conn,
                    file_id=file_id,
                    path=path,
                    issue_type=issue_type,
                    match_field="",
                    match_value="",
                    identity_key=identity_key,
                    rows=candidate_rows,
                    suggested_action=suggested_action,
                    reason=reason,
                )
            )
            issue_counts[issue_type] += 1
            action_counts[suggested_action] += 1
    finally:
        conn.close()

    csv_path = _write_csv(args.out_csv, plan_rows)
    json_path = _write_json(
        args.out_json,
        {
            "db_path": str(args.db.expanduser().resolve()),
            "resume_from_file_id": max(int(args.resume_from_file_id), 0),
            "limit": args.limit,
            "total_rows": len(plan_rows),
            "issue_counts": dict(sorted(issue_counts.items())),
            "action_counts": dict(sorted(action_counts.items())),
            "csv_path": str(csv_path),
        },
    )

    print(f"db: {args.db.expanduser().resolve()}")
    print(f"plan_rows: {len(plan_rows)}")
    print(f"issue_counts: {json.dumps(dict(sorted(issue_counts.items())), sort_keys=True)}")
    print(f"action_counts: {json.dumps(dict(sorted(action_counts.items())), sort_keys=True)}")
    print(f"csv: {csv_path}")
    print(f"json: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
