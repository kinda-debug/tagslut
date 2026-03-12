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
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from tagslut.exec.transcoder import transcode_to_mp3_from_snapshot
from tagslut.storage.v3 import open_db_v3
from tagslut.storage.v3.analysis_service import resolve_dj_tag_snapshot

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


def _row_get(row: sqlite3.Row | dict[str, object], *keys: str) -> object | None:
    for key in keys:
        if not key:
            continue
        try:
            value = row[key]
        except (IndexError, KeyError, TypeError):
            continue
        if value is not None:
            return value
    return None


def _row_text(row: sqlite3.Row | dict[str, object], *keys: str) -> str:
    value = _row_get(row, *keys)
    if value is None:
        return ""
    return str(value).strip()


def _row_int(row: sqlite3.Row | dict[str, object], *keys: str) -> int | None:
    value = _row_get(row, *keys)
    if value is None:
        return None
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(float(str(value)))


def _row_source_path(row: sqlite3.Row | dict[str, object]) -> str:
    return _row_text(row, "selected_asset_path", "preferred_path", "source_path")


def _connect_db(path: Path) -> sqlite3.Connection:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"v3 DB not found: {resolved}")
    return open_db_v3(resolved, create=False)


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
    identity_ids: set[int] | None,
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
    if identity_ids is not None:
        if not identity_ids:
            return []
        placeholders = ",".join("?" for _ in sorted(identity_ids))
        where.append(f"identity_id IN ({placeholders})")
        params.extend(sorted(identity_ids))

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
            preferred_asset_id AS selected_asset_id,
            preferred_asset_id,
            asset_path AS selected_asset_path,
            asset_path AS source_path,
            sha256 AS source_sha256,
            asset_mtime AS source_mtime,
            artist AS canonical_artist,
            artist,
            title AS canonical_title,
            title,
            album AS canonical_album,
            bpm AS canonical_bpm,
            musical_key AS canonical_key,
            genre AS canonical_genre,
            sub_genre AS canonical_sub_genre,
            genre,
            identity_status AS canonical_status,
            dj_set_role AS set_role
        FROM {view_name}
        {where_prefix}
        ORDER BY
            LOWER(COALESCE(canonical_artist, artist, '')),
            LOWER(COALESCE(canonical_title, title, '')),
            identity_id ASC
        {limit_sql}
    """
    return conn.execute(query, tuple(params)).fetchall()


def _dest_path(
    out_dir: Path,
    row: sqlite3.Row,
    layout: str,
    fmt: str,
    *,
    artist_override: str | None = None,
    title_override: str | None = None,
    genre_override: str | None = None,
) -> Path:
    artist_raw = (
        artist_override
        or _row_text(row, "canonical_artist", "artist")
    ).strip()
    title_raw = (
        title_override
        or _row_text(row, "canonical_title", "title")
    ).strip()
    if not artist_raw or not title_raw:
        raise ValueError(f"missing artist/title for identity_id={int(row['identity_id'])}")
    artist = _sanitize_component(artist_raw, "")
    title = _sanitize_component(title_raw, "")
    role = _sanitize_component(_row_text(row, "set_role", "dj_set_role"), "unassigned")
    genre = _sanitize_component(
        genre_override or _row_text(row, "canonical_genre", "genre"),
        "Unknown",
    )
    identity_id = int(row["identity_id"])

    source_ext = Path(_row_source_path(row)).suffix.lower() or ".flac"
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
                "mtime",
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
    parser.add_argument(
        "--source-mode",
        choices=["preferred"],
        default="preferred",
        help="Legacy compatibility flag; v3 pool builds always use preferred assets.",
    )
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--receipts", type=Path)
    parser.add_argument("--identity-id-file", type=Path)
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
    parser.add_argument("--ffmpeg-path")
    parser.add_argument(
        "--no-essentia",
        action="store_true",
        help="Skip Essentia-based DJ analysis refresh and use existing DB metadata only.",
    )
    parser.add_argument("--strict", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("-v", "--verbose", action="store_true", help="Print per-file actions")
    return parser.parse_args(argv)


def _load_identity_ids(path: Path | None) -> set[int] | None:
    if path is None:
        return None
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"identity id file not found: {resolved}")
    values: set[int] = set()
    for line in resolved.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        values.add(int(text))
    return values


def _parse_mp3_bitrate(value: str) -> int:
    text = value.strip().lower()
    if text.endswith("k"):
        text = text[:-1]
    bitrate = int(text)
    if bitrate <= 0:
        raise ValueError("bitrate must be > 0")
    return bitrate


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
        library_root = (os.environ.get("MASTER_LIBRARY") or os.environ.get("LIBRARY_ROOT", "")).strip()
        if library_root and _is_inside(Path(library_root).expanduser().resolve(), out_dir):
            print("refusing --out-dir inside MASTER_LIBRARY")
            return 2

    ffmpeg = args.ffmpeg_path or shutil.which("ffmpeg")
    if args.execute and args.format == "mp3" and not ffmpeg:
        print("ffmpeg not found; set --ffmpeg-path or install ffmpeg")
        return 2
    try:
        identity_ids = _load_identity_ids(args.identity_id_file)
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc))
        return 2
    try:
        mp3_bitrate = _parse_mp3_bitrate(str(args.mp3_bitrate))
    except ValueError as exc:
        print(f"--mp3-bitrate invalid: {exc}")
        return 2

    try:
        conn = _connect_db(args.db)
    except FileNotFoundError as exc:
        print(str(exc))
        return 2

    try:
        view_name = _view_for_scope(args.scope)
        if not _view_exists(conn, view_name):
            print(f"missing required view: {view_name}")
            print('hint: run "make apply-v3-schema V3=<db>" to install missing views')
            return 2
        if args.format == "mp3" and not _view_exists(conn, "v_dj_export_metadata_v1"):
            print("missing required view: v_dj_export_metadata_v1")
            print('hint: apply the latest v3 schema/migrations before mp3 export')
            return 2
        rows = _select_rows(
            conn,
            scope=args.scope,
            min_rating=args.min_rating,
            min_energy=args.min_energy,
            set_roles=args.set_role,
            only_profiled=bool(args.only_profiled),
            limit=args.limit,
            identity_ids=identity_ids,
        )
        manifest_rows: list[ExportRow] = []
        snapshots_by_identity: dict[int, object] = {}
        copy_count = 0
        transcode_count = 0
        skip_count = 0
        existing_files = 0

        for row in rows:
            source = Path(_row_source_path(row)).expanduser().resolve()
            snapshot = None
            if args.format == "mp3":
                snapshot = resolve_dj_tag_snapshot(
                    conn,
                    int(row["identity_id"]),
                    run_essentia=bool(args.execute and not args.no_essentia),
                    dry_run=not args.execute,
                )
                snapshots_by_identity[int(row["identity_id"])] = snapshot
            try:
                dest = _dest_path(
                    out_dir,
                    row,
                    args.layout,
                    args.format,
                    artist_override=getattr(snapshot, "artist", None),
                    title_override=getattr(snapshot, "title", None),
                    genre_override=getattr(snapshot, "genre", None),
                )
            except ValueError as exc:
                source = Path(_row_source_path(row)).expanduser().resolve()
                source_sha = str(row["source_sha256"] or "")
                source_mtime = str(row["source_mtime"] or "")
                manifest_rows.append(
                    ExportRow(
                        identity_id=int(row["identity_id"]),
                        preferred_asset_id=int(_row_int(row, "selected_asset_id", "preferred_asset_id") or 0),
                        source_path=str(source),
                        dest_path="",
                        action="skip",
                        reason="missing_artist_or_title",
                        sha256=source_sha,
                        mtime=source_mtime,
                    )
                )
                skip_count += 1
                if args.verbose:
                    print(f"skip: {source} ({exc})")
                continue
            source_sha = str(row["source_sha256"] or "")
            source_mtime = str(row["source_mtime"] or "")

            action = "transcode" if args.format == "mp3" else "copy"
            reason = "selected"

            if not source.exists():
                action = "skip"
                reason = "source_missing" if args.strict else "source_missing_non_strict"
            elif dest.exists():
                existing_files += 1
                if args.overwrite == "never":
                    action = "skip"
                    reason = "exists_overwrite_never"
                elif args.overwrite == "if_same_hash":
                    if source_sha:
                        if _hash_file(dest) == source_sha:
                            action = "skip"
                            reason = "exists_same_hash"
                        else:
                            reason = "exists_different_hash_overwrite"
                    else:
                        reason = "exists_no_source_hash_overwrite"
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
                    preferred_asset_id=int(_row_int(row, "selected_asset_id", "preferred_asset_id") or 0),
                    source_path=str(source),
                    dest_path=str(dest),
                    action=action,
                    reason=reason,
                    sha256=source_sha,
                    mtime=source_mtime,
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
                    try:
                        snapshot = snapshots_by_identity[item.identity_id]
                        transcode_to_mp3_from_snapshot(
                            src,
                            dst.parent,
                            snapshot,
                            bitrate=mp3_bitrate,
                            overwrite=True,
                            ffmpeg_path=ffmpeg,
                            dest_path=dst,
                        )
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
                            fail_fast_message = f"Transcode failed for {src}: {exc}"
                            break
                        continue

                snapshot = snapshots_by_identity.get(item.identity_id)
                partial_metadata = False
                if snapshot is not None:
                    partial_metadata = any(
                        value is None
                        for value in (
                            snapshot.bpm,
                            snapshot.musical_key,
                            snapshot.energy_1_10,
                        )
                    )
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
                        "tool_version": "build_pool_v3",
                        "partial_metadata": partial_metadata,
                        "tag_snapshot": snapshot.as_dict() if snapshot is not None else None,
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
        print(f"existing_files: {existing_files}")
        print(f"copy: {copy_count}")
        print(f"transcode: {transcode_count}")
        print(f"skip: {skip_count}")
        print(f"manifest: {manifest_written}")
        if args.execute:
            print(f"receipts: {receipts_path}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
