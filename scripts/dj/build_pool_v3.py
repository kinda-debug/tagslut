#!/usr/bin/env python3
"""Build deterministic downstream DJ pool export tree from v3 policy view."""

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
from datetime import UTC, datetime
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


def _view_exists(conn: sqlite3.Connection, view: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='view' AND name=?",
        (view,),
    ).fetchone()
    return row is not None


def _view_for_scope(scope: str) -> str:
    if scope == "active":
        return "v_dj_pool_candidates_active_v3"
    return "v_dj_pool_candidates_active_orphan_v3"


def _sanitize_component(value: str, fallback: str) -> str:
    text = (value or "").strip()
    if not text:
        text = fallback
    text = re.sub(r"[\\/:*?\"<>|]", " ", text)
    text = re.sub(r"[\x00-\x1f\x7f]", " ", text)
    text = re.sub(r"\s+", " ", text).strip().strip(".")
    if not text:
        text = fallback
    if len(text) > SAFE_MAX_NAME:
        text = text[:SAFE_MAX_NAME].rstrip()
    return text


def _hash_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def _is_inside(parent: Path, child: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _guard_out_dir(out_dir: Path) -> bool:
    text = str(out_dir.expanduser()).strip()
    if not text or text == "/":
        return False
    resolved = out_dir.expanduser().resolve()
    return len(str(resolved)) >= 4


def _roles_clause(roles: list[str]) -> tuple[str, list[str]]:
    clean = [role.strip().lower() for role in roles if role.strip()]
    if not clean:
        return "", []
    placeholders = ",".join("?" for _ in clean)
    return f"dj_set_role IN ({placeholders})", clean


def _select_rows(
    conn: sqlite3.Connection,
    *,
    scope: str,
    min_rating: int | None,
    min_energy: int | None,
    set_roles: list[str],
    only_profiled: bool,
    limit: int | None,
) -> list[sqlite3.Row]:
    role_sql, role_params = _roles_clause(set_roles)
    view_name = _view_for_scope(scope)

    where: list[str] = []
    params: list[object] = []

    if only_profiled:
        where.append("dj_updated_at IS NOT NULL")
    if min_rating is not None:
        where.append("dj_rating >= ?")
        params.append(int(min_rating))
    if min_energy is not None:
        where.append("dj_energy >= ?")
        params.append(int(min_energy))
    if role_sql:
        where.append(role_sql)
        params.extend(role_params)

    where_sql = " AND ".join(where)

    where_prefix = ""
    if where_sql:
        where_prefix = f"WHERE {where_sql}"

    limit_sql = ""
    if limit is not None:
        limit_sql = " LIMIT ?"
        params.append(int(limit))

    query = f"""
        SELECT
            identity_id,
            preferred_asset_id,
            asset_path AS source_path,
            sha256 AS source_sha256,
            artist,
            title,
            genre,
            dj_set_role AS set_role
        FROM {view_name}
        {where_prefix}
        ORDER BY LOWER(COALESCE(artist,'')), LOWER(COALESCE(title,'')), identity_id ASC
        {limit_sql}
    """
    return conn.execute(query, tuple(params)).fetchall()


def _dest_path(out_dir: Path, row: sqlite3.Row, layout: str, fmt: str) -> Path:
    artist = _sanitize_component(str(row["artist"] or ""), "Unknown Artist")
    title = _sanitize_component(str(row["title"] or ""), "Unknown Title")
    role = _sanitize_component(str(row["set_role"] or ""), "unassigned")
    genre = _sanitize_component(str(row["genre"] or ""), "Unknown")
    identity_id = int(row["identity_id"])

    source_ext = Path(str(row["source_path"])).suffix.lower() or ".flac"
    ext = ".mp3" if fmt == "mp3" else source_ext
    name = _sanitize_component(f"{artist} - {title} [{identity_id}]", f"track-{identity_id}") + ext

    if layout == "by_role":
        return out_dir / role / name
    if layout == "by_genre":
        return out_dir / genre / name
    return out_dir / name


def _write_manifest(path: Path, rows: list[ExportRow]) -> Path:
    resolved = path.expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    with resolved.open("w", encoding="utf-8", newline="") as handle:
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
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)
    return resolved


def _append_receipt(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _write_failure_rows(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build deterministic downstream DJ pool from v3 preferred assets")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--receipts", type=Path)
    parser.add_argument("--layout", choices=["by_role", "by_genre", "flat"], default="by_role")
    parser.add_argument("--scope", choices=["active", "active+orphan"], default="active")
    parser.add_argument("--min-rating", type=int)
    parser.add_argument("--min-energy", type=int)
    parser.add_argument("--set-role", action="append", default=[])
    parser.add_argument("--only-profiled", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--plan", dest="execute", action="store_false")
    parser.add_argument("--execute", dest="execute", action="store_true")
    parser.set_defaults(execute=False)
    parser.add_argument("--fail-fast", action="store_true", help="Stop on first copy/transcode failure.")
    parser.add_argument(
        "--transcode-timeout-s",
        type=int,
        default=None,
        help="Per-track ffmpeg timeout in seconds (only for --format mp3).",
    )
    parser.add_argument("--overwrite", choices=["never", "if_same_hash", "always"], default="if_same_hash")
    parser.add_argument("--format", choices=["copy", "mp3"], default="copy")
    parser.add_argument("--mp3-bitrate", default="320k")
    parser.add_argument("--strict", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("-v", "--verbose", action="store_true", help="Print per-file actions")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    out_dir = args.out_dir.expanduser().resolve()
    manifest_path = (args.manifest or (out_dir / "manifest.csv")).expanduser().resolve()
    receipts_path = (args.receipts or (out_dir / "receipts.jsonl")).expanduser().resolve()

    if args.limit is not None and int(args.limit) <= 0:
        print("--limit must be > 0")
        return 2

    if args.execute:
        if not _guard_out_dir(out_dir):
            print("refusing unsafe --out-dir")
            return 2
        library_root = os.environ.get("LIBRARY_ROOT", "").strip()
        if library_root and _is_inside(Path(library_root).expanduser().resolve(), out_dir):
            print("refusing --out-dir inside LIBRARY_ROOT")
            return 2

    ffmpeg = shutil.which("ffmpeg")
    if args.execute and args.format == "mp3" and not ffmpeg:
        print("ffmpeg not found; install ffmpeg for --format mp3")
        return 2

    try:
        conn = _connect_ro(args.db)
    except FileNotFoundError as exc:
        print(str(exc))
        return 2

    try:
        view_name = _view_for_scope(args.scope)
        if not _view_exists(conn, view_name):
            print(f"missing required view: {view_name}")
            print('hint: run "make apply-v3-schema V3=<db>" to install missing views')
            return 2
        rows = _select_rows(
            conn,
            scope=args.scope,
            min_rating=args.min_rating,
            min_energy=args.min_energy,
            set_roles=args.set_role,
            only_profiled=bool(args.only_profiled),
            limit=args.limit,
        )
    finally:
        conn.close()

    manifest_rows: list[ExportRow] = []
    copy_count = 0
    transcode_count = 0
    skip_count = 0

    for row in rows:
        source = Path(str(row["source_path"])).expanduser().resolve()
        dest = _dest_path(out_dir, row, args.layout, args.format)
        source_sha = str(row["source_sha256"] or "")

        action = "transcode" if args.format == "mp3" else "copy"
        reason = "selected"

        if not source.exists():
            action = "skip"
            reason = "source_missing"
            if args.strict:
                skip_count += 1
        elif dest.exists():
            if args.overwrite == "never":
                action = "skip"
                reason = "exists_overwrite_never"
            elif args.overwrite == "if_same_hash":
                if source_sha and _hash_file(dest) == source_sha:
                    action = "skip"
                    reason = "exists_same_hash"
                else:
                    reason = "exists_overwrite_if_same_hash"
            else:
                reason = "exists_overwrite_always"

        if action == "copy":
            copy_count += 1
        elif action == "transcode":
            transcode_count += 1
        else:
            skip_count += 1

        manifest_rows.append(
            ExportRow(
                identity_id=int(row["identity_id"]),
                preferred_asset_id=int(row["preferred_asset_id"]),
                source_path=str(source),
                dest_path=str(dest),
                action=action,
                reason=reason,
                sha256=source_sha,
            )
        )
        if args.verbose:
            print(f"{action}: {source} -> {dest} ({reason})")

    manifest_rows.sort(key=lambda r: (r.dest_path.casefold(), r.identity_id))
    manifest_written = _write_manifest(manifest_path, manifest_rows)

    failure_rows: list[dict[str, object]] = []
    fail_fast_message: str | None = None
    if args.execute:
        failure_path = out_dir / "export_failures.jsonl"
        for item in manifest_rows:
            if item.action == "skip":
                continue
            src = Path(item.source_path)
            dst = Path(item.dest_path)
            dst.parent.mkdir(parents=True, exist_ok=True)
            if item.action == "copy":
                try:
                    shutil.copy2(src, dst)
                except Exception as exc:
                    failure_rows.append(
                        {
                            "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
                            "identity_id": item.identity_id,
                            "source_path": item.source_path,
                            "dest_path": item.dest_path,
                            "action": item.action,
                            "error": str(exc),
                        }
                    )
                    if args.fail_fast:
                        fail_fast_message = f"Copy failed for {src}: {exc}"
                        break
                    continue
            else:
                cmd = [
                    ffmpeg or "ffmpeg",
                    "-y",
                    "-i",
                    str(src),
                    "-vn",
                    "-c:a",
                    "libmp3lame",
                    "-b:a",
                    str(args.mp3_bitrate),
                    str(dst),
                ]
                try:
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        errors="replace",
                        timeout=args.transcode_timeout_s,
                        check=False,
                    )
                except subprocess.TimeoutExpired:
                    failure_rows.append(
                        {
                            "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
                            "identity_id": item.identity_id,
                            "source_path": item.source_path,
                            "dest_path": item.dest_path,
                            "action": item.action,
                            "error": f"ffmpeg_timeout_{args.transcode_timeout_s}s",
                            "stderr": "timeout",
                        }
                    )
                    if args.fail_fast:
                        fail_fast_message = f"ffmpeg timeout for {src}"
                        break
                    continue
                if result.returncode != 0:
                    stderr = (result.stderr or "").strip()
                    failure_rows.append(
                        {
                            "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
                            "identity_id": item.identity_id,
                            "source_path": item.source_path,
                            "dest_path": item.dest_path,
                            "action": item.action,
                            "error": f"ffmpeg_exit_{result.returncode}",
                            "stderr": stderr[:2000],
                        }
                    )
                    if args.fail_fast:
                        fail_fast_message = f"ffmpeg failed for {src}: {stderr[:2000]}"
                        break
                    continue

            _append_receipt(
                receipts_path,
                {
                    "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
                    "identity_id": item.identity_id,
                    "source_path": item.source_path,
                    "dest_path": item.dest_path,
                    "action": item.action,
                    "overwrite_policy": args.overwrite,
                    "tool": "build_pool_v3",
                },
            )

        _write_failure_rows(failure_path, failure_rows)
        if fail_fast_message:
            print(fail_fast_message, file=sys.stderr)
            return 1

    if args.strict and any(row.reason == "source_missing" for row in manifest_rows):
        print("strict mode: one or more selected sources are missing")
        return 2

    print(f"selected_identities: {len(rows)}")
    print(f"copy: {copy_count}")
    print(f"transcode: {transcode_count}")
    print(f"skip: {skip_count}")
    print(f"manifest: {manifest_written}")
    if args.execute:
        print(f"receipts: {receipts_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
