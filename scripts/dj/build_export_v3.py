#!/usr/bin/env python3
"""Build deterministic DJ export tree from v3 preferred assets."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

SAFE_MAX_NAME = 160


@dataclass
class ExportRow:
    identity_id: int
    preferred_asset_id: int
    source_path: str
    dest_path: str
    action: str
    reason: str
    sha256: str
    mtime: str


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


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return row is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except sqlite3.OperationalError:
        return False
    return any(str(r[1]) == column for r in rows)


def _sanitize_component(value: str, fallback: str) -> str:
    text = (value or "").strip()
    if not text:
        text = fallback
    text = re.sub(r"[\\/:*?\"<>|]", " ", text)
    text = re.sub(r"\s+", " ", text).strip().strip(".")
    if not text:
        text = fallback
    if len(text) > SAFE_MAX_NAME:
        text = text[:SAFE_MAX_NAME].rstrip()
    return text


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _is_dangerous_out_dir(path: Path) -> bool:
    resolved = path.expanduser().resolve()
    if str(resolved) in {"/", ""}:
        return True
    return False


def _is_inside(parent: Path, child: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _select_rows(
    conn: sqlite3.Connection,
    *,
    scope: str,
    min_rating: int | None,
    set_roles: list[str],
    min_energy: int | None,
    limit: int | None,
) -> list[sqlite3.Row]:
    if not _table_exists(conn, "preferred_asset"):
        raise RuntimeError("missing required table: preferred_asset")
    if not _table_exists(conn, "identity_status"):
        raise RuntimeError("missing required table: identity_status")
    has_dj_profile = _table_exists(conn, "dj_track_profile")

    merged_where = "ti.merged_into_id IS NULL" if _column_exists(conn, "track_identity", "merged_into_id") else "1=1"
    status_values = ["active"] if scope == "active" else ["active", "orphan"]
    status_placeholders = ",".join("?" for _ in status_values)

    where = [
        merged_where,
        f"ist.status IN ({status_placeholders})",
        "pa.asset_id IS NOT NULL",
    ]
    params: list[object] = list(status_values)

    if min_rating is not None:
        if not has_dj_profile:
            return []
        where.append("dj.rating >= ?")
        params.append(int(min_rating))
    if min_energy is not None:
        if not has_dj_profile:
            return []
        where.append("dj.energy >= ?")
        params.append(int(min_energy))
    if set_roles:
        clean_roles = [role.strip().lower() for role in set_roles if role.strip()]
        if clean_roles:
            if not has_dj_profile:
                return []
            placeholders = ",".join("?" for _ in clean_roles)
            where.append(f"dj.set_role IN ({placeholders})")
            params.extend(clean_roles)

    limit_sql = ""
    if limit is not None:
        limit_sql = " LIMIT ?"
        params.append(int(limit))

    dj_join = "LEFT JOIN dj_track_profile dj ON dj.identity_id = ti.id" if has_dj_profile else ""
    dj_set_role_select = "dj.set_role AS set_role" if has_dj_profile else "NULL AS set_role"
    dj_rating_select = "dj.rating AS rating" if has_dj_profile else "NULL AS rating"
    dj_energy_select = "dj.energy AS energy" if has_dj_profile else "NULL AS energy"

    query = f"""
        SELECT
            ti.id AS identity_id,
            ti.canonical_artist AS artist,
            ti.canonical_title AS title,
            ti.canonical_genre AS genre,
            pa.asset_id AS preferred_asset_id,
            af.path AS source_path,
            af.content_sha256 AS source_sha256,
            af.mtime AS source_mtime,
            {dj_set_role_select},
            {dj_rating_select},
            {dj_energy_select}
        FROM track_identity ti
        JOIN identity_status ist ON ist.identity_id = ti.id
        JOIN preferred_asset pa ON pa.identity_id = ti.id
        JOIN asset_file af ON af.id = pa.asset_id
        {dj_join}
        WHERE {' AND '.join(where)}
        ORDER BY LOWER(COALESCE(ti.canonical_artist, '')), LOWER(COALESCE(ti.canonical_title, '')), ti.id ASC
        {limit_sql}
    """
    return conn.execute(query, tuple(params)).fetchall()


def _build_dest_path(out_dir: Path, row: sqlite3.Row, *, layout: str, fmt: str) -> Path:
    artist = _sanitize_component(str(row["artist"] or ""), "Unknown Artist")
    title = _sanitize_component(str(row["title"] or ""), "Unknown Title")
    role = _sanitize_component(str(row["set_role"] or ""), "unassigned")
    genre = _sanitize_component(str(row["genre"] or ""), "Unknown")
    identity_id = int(row["identity_id"])

    source_ext = Path(str(row["source_path"])).suffix.lower() or ".flac"
    ext = ".mp3" if fmt == "mp3" else source_ext
    file_name = _sanitize_component(f"{artist} - {title} [{identity_id}]", f"track-{identity_id}") + ext

    if layout == "by_role":
        return out_dir / role / file_name
    if layout == "by_genre":
        return out_dir / genre / file_name
    return out_dir / file_name


def _write_manifest(manifest_path: Path, rows: list[ExportRow]) -> Path:
    manifest_resolved = manifest_path.expanduser().resolve()
    manifest_resolved.parent.mkdir(parents=True, exist_ok=True)
    with manifest_resolved.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "identity_id",
                "preferred_asset_id",
                "source_path",
                "dest_path",
                "action",
                "reason",
                "sha256",
                "mtime",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)
    return manifest_resolved


def _append_receipt(receipts_path: Path, payload: dict[str, object]) -> None:
    receipts_path.parent.mkdir(parents=True, exist_ok=True)
    with receipts_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build deterministic DJ export tree from v3 preferred assets")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--source-mode", choices=["preferred"], default="preferred")
    parser.add_argument("--scope", choices=["active", "active+orphan"], default="active")
    parser.add_argument("--min-rating", type=int)
    parser.add_argument("--set-role", action="append", default=[])
    parser.add_argument("--min-energy", type=int)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--plan", dest="execute", action="store_false")
    parser.add_argument("--execute", dest="execute", action="store_true")
    parser.set_defaults(execute=False)
    parser.add_argument("--overwrite", choices=["never", "if_same_hash", "always"], default="if_same_hash")
    parser.add_argument("--layout", choices=["by_role", "by_genre", "flat"], default="by_role")
    parser.add_argument("--format", choices=["copy", "mp3"], default="copy")
    parser.add_argument("--mp3-bitrate", default="320k")
    parser.add_argument("--ffmpeg-path")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--strict", action=argparse.BooleanOptionalAction, default=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    out_dir = args.out_dir.expanduser().resolve()
    manifest_path = (args.manifest if args.manifest is not None else out_dir / "manifest.csv").expanduser().resolve()
    receipts_path = out_dir / "receipts.jsonl"

    if args.limit is not None and int(args.limit) <= 0:
        print("--limit must be > 0")
        return 2

    if args.execute:
        if _is_dangerous_out_dir(out_dir):
            print("refusing dangerous --out-dir")
            return 2
        lib_root = os.environ.get("LIBRARY_ROOT", "").strip()
        if lib_root:
            lib_path = Path(lib_root).expanduser().resolve()
            if _is_inside(lib_path, out_dir):
                print("refusing --out-dir inside LIBRARY_ROOT")
                return 2

    if args.format == "mp3" and args.execute:
        ffmpeg = args.ffmpeg_path or shutil.which("ffmpeg")
        if not ffmpeg:
            print("ffmpeg not found; set --ffmpeg-path or install ffmpeg")
            return 2
    else:
        ffmpeg = args.ffmpeg_path or shutil.which("ffmpeg")

    try:
        conn = _connect_ro(args.db)
    except FileNotFoundError as exc:
        print(str(exc))
        return 2

    try:
        rows = _select_rows(
            conn,
            scope=args.scope,
            min_rating=args.min_rating,
            set_roles=args.set_role,
            min_energy=args.min_energy,
            limit=args.limit,
        )
    except RuntimeError as exc:
        print(str(exc))
        conn.close()
        return 2
    finally:
        conn.close()

    selected_identities = len(rows)
    existing_files = 0
    would_copy = 0
    would_transcode = 0
    skipped_missing_profile = 0

    manifest_rows: list[ExportRow] = []
    for row in rows:
        source_path = Path(str(row["source_path"])).expanduser().resolve()
        dest_path = _build_dest_path(out_dir, row, layout=args.layout, fmt=args.format)

        if not source_path.exists():
            if args.strict:
                reason = "source_missing"
                action = "skip"
            else:
                reason = "source_missing_non_strict"
                action = "skip"
            manifest_rows.append(
                ExportRow(
                    identity_id=int(row["identity_id"]),
                    preferred_asset_id=int(row["preferred_asset_id"]),
                    source_path=str(source_path),
                    dest_path=str(dest_path),
                    action=action,
                    reason=reason,
                    sha256=str(row["source_sha256"] or ""),
                    mtime=str(row["source_mtime"] or ""),
                )
            )
            continue

        source_sha = str(row["source_sha256"] or "")
        action = "transcode" if args.format == "mp3" else "copy"
        reason = "selected"

        if dest_path.exists():
            existing_files += 1
            if args.overwrite == "never":
                action = "skip"
                reason = "exists_overwrite_never"
            elif args.overwrite == "if_same_hash":
                if source_sha:
                    dest_sha = _hash_file(dest_path)
                    if dest_sha == source_sha:
                        action = "skip"
                        reason = "exists_same_hash"
                    else:
                        reason = "exists_different_hash_overwrite"
                else:
                    reason = "exists_no_source_hash_overwrite"
            else:
                reason = "exists_overwrite_always"

        if action == "copy":
            would_copy += 1
        elif action == "transcode":
            would_transcode += 1

        manifest_rows.append(
            ExportRow(
                identity_id=int(row["identity_id"]),
                preferred_asset_id=int(row["preferred_asset_id"]),
                source_path=str(source_path),
                dest_path=str(dest_path),
                action=action,
                reason=reason,
                sha256=source_sha,
                mtime=str(row["source_mtime"] or ""),
            )
        )

    manifest_rows.sort(key=lambda item: (item.dest_path.casefold(), item.identity_id))
    manifest_written = _write_manifest(manifest_path, manifest_rows)

    if args.execute:
        for item in manifest_rows:
            if item.action == "skip":
                continue
            src = Path(item.source_path)
            dst = Path(item.dest_path)
            dst.parent.mkdir(parents=True, exist_ok=True)
            if args.format == "copy":
                shutil.copy2(src, dst)
            else:
                command = [
                    ffmpeg or "ffmpeg",
                    "-y",
                    "-i",
                    str(src),
                    "-vn",
                    "-c:a",
                    "libmp3lame",
                    "-b:a",
                    str(args.mp3_bitrate),
                    "-metadata",
                    f"artist={Path(src).stem}",
                    "-metadata",
                    f"title={Path(src).stem}",
                    str(dst),
                ]
                subprocess.check_call(command)
            _append_receipt(
                receipts_path,
                {
                    "identity_id": item.identity_id,
                    "source": item.source_path,
                    "dest": item.dest_path,
                    "action": item.action,
                    "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                    "tool_version": "dj_export_builder_v3",
                },
            )

    print(f"selected_identities: {selected_identities}")
    print(f"skipped_missing_profile: {skipped_missing_profile}")
    print(f"existing_files: {existing_files}")
    print(f"would_copy: {would_copy}")
    print(f"would_transcode: {would_transcode}")
    print(f"manifest: {manifest_written}")
    if args.execute:
        print(f"receipts: {receipts_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
