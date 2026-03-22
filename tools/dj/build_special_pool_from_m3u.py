#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sqlite3
import subprocess
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from mutagen.easyid3 import EasyID3

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SYNC_MP3_TAGS_SCRIPT = PROJECT_ROOT / "tools" / "metadata_scripts" / "sync_mp3_tags_from_flac.py"


def _safe_slug(value: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "pool"


def _read_playlist(path: Path) -> list[Path]:
    items: list[Path] = []
    playlist_dir = path.expanduser().resolve().parent
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        item_path = Path(line).expanduser()
        if not item_path.is_absolute():
            item_path = playlist_dir / item_path
        items.append(item_path.resolve())
    return items


def _read_tags(path: Path) -> tuple[str, str]:
    try:
        tags = EasyID3(str(path))
    except Exception:
        return "", ""
    title = (tags.get("title") or [""])[0].strip()
    artist = (tags.get("artist") or [""])[0].strip()
    return artist, title


def _dest_rel_path(source_path: Path, source_root: Path) -> Path:
    try:
        return source_path.relative_to(source_root)
    except ValueError:
        digest = hashlib.sha1(str(source_path).encode("utf-8")).hexdigest()[:10]
        filename = f"{source_path.stem}-{digest}{source_path.suffix.lower()}"
        return Path("_external") / filename


@dataclass(frozen=True)
class PoolRow:
    playlist_name: str
    source_path: Path
    dest_rel_path: Path


def _chunked(items: list[Path], size: int = 500) -> list[list[Path]]:
    return [items[idx : idx + size] for idx in range(0, len(items), size)]


def _load_flac_lookup(db_path: Path, source_paths: list[Path]) -> dict[Path, Path]:
    if not source_paths:
        return {}
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        lookup: dict[Path, Path] = {}
        for chunk in _chunked(source_paths):
            placeholders = ",".join("?" for _ in chunk)
            query = f"""
                SELECT path, dj_pool_path
                FROM files
                WHERE dj_pool_path IN ({placeholders})
            """
            params = tuple(str(path) for path in chunk)
            for row in conn.execute(query, params):
                source_mp3 = Path(str(row["dj_pool_path"])).expanduser().resolve()
                flac_path = Path(str(row["path"])).expanduser().resolve()
                lookup[source_mp3] = flac_path
        return lookup
    finally:
        conn.close()


def _write_tag_sync_report(path: Path, pool_root: Path, source_to_dest: dict[Path, Path], flac_lookup: dict[Path, Path]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    matched = 0
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["path", "flac_path", "source_path", "status"],
        )
        writer.writeheader()
        for source_path in sorted(source_to_dest, key=lambda item: str(item)):
            flac_path = flac_lookup.get(source_path)
            if flac_path is not None:
                matched += 1
            writer.writerow(
                {
                    "path": str((pool_root / source_to_dest[source_path]).resolve()),
                    "flac_path": str(flac_path) if flac_path is not None else "",
                    "source_path": str(source_path),
                    "status": "planned" if flac_path is not None else "missing_flac",
                }
            )
    return matched


def _summarize_status_csv(path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not path.exists():
        return counts
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            status = (row.get("status") or "").strip() or "unknown"
            counts[status] = counts.get(status, 0) + 1
    return counts


def _write_playlist(path: Path, rel_paths: list[Path], pool_root: Path) -> None:
    lines = ["#EXTM3U"]
    for rel_path in rel_paths:
        dest_path = (pool_root / rel_path).resolve()
        artist, title = _read_tags(dest_path)
        label = " - ".join(part for part in (artist, title) if part) or dest_path.stem
        playlist_ref = Path(os.path.relpath(dest_path, path.parent))
        lines.append(f"#EXTINF:-1,{label}")
        lines.append(str(playlist_ref))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_special_pool(
    *,
    playlist_paths: list[Path],
    out_root: Path,
    pool_name: str,
    source_root: Path,
    db_path: Path | None = None,
    sync_tags: bool = False,
) -> dict[str, object]:
    out_root = out_root.expanduser().resolve()
    source_root = source_root.expanduser().resolve()
    run_root = out_root / pool_name
    pool_root = run_root / "pool"
    playlists_root = run_root / "playlists"
    run_root.mkdir(parents=True, exist_ok=True)
    pool_root.mkdir(parents=True, exist_ok=True)
    playlists_root.mkdir(parents=True, exist_ok=True)

    manifest_rows: list[PoolRow] = []
    per_playlist: dict[str, list[Path]] = {}
    unique_order: list[Path] = []
    unique_seen: set[Path] = set()
    source_to_dest: dict[Path, Path] = {}
    missing_sources: list[str] = []

    for playlist_path in playlist_paths:
        playlist_name = playlist_path.stem
        playlist_items = _read_playlist(playlist_path)
        playlist_rel_paths: list[Path] = []
        seen_in_playlist: set[Path] = set()
        for source_path in playlist_items:
            if not source_path.exists():
                missing_sources.append(str(source_path))
                continue
            if source_path in seen_in_playlist:
                continue
            seen_in_playlist.add(source_path)
            dest_rel_path = _dest_rel_path(source_path, source_root)
            source_to_dest[source_path] = dest_rel_path
            playlist_rel_paths.append(dest_rel_path)
            manifest_rows.append(
                PoolRow(
                    playlist_name=playlist_name,
                    source_path=source_path,
                    dest_rel_path=dest_rel_path,
                )
            )
            if source_path not in unique_seen:
                unique_seen.add(source_path)
                unique_order.append(source_path)
        per_playlist[playlist_name] = playlist_rel_paths

    copied = 0
    for source_path in unique_order:
        dest_path = pool_root / source_to_dest[source_path]
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, dest_path)
        copied += 1

    flac_lookup: dict[Path, Path] = {}
    tag_sync_report = run_root / "tag_sync_report.csv"
    matched_flac_rows = 0
    tag_sync_result: dict[str, int] = {}
    if db_path is not None:
        flac_lookup = _load_flac_lookup(db_path.expanduser().resolve(), unique_order)
        matched_flac_rows = _write_tag_sync_report(tag_sync_report, pool_root, source_to_dest, flac_lookup)
        if sync_tags:
            result_csv = run_root / "tag_sync_result.csv"
            backup_jsonl = run_root / "tag_sync_backup.jsonl"
            subprocess.run(
                [
                    sys.executable,
                    str(SYNC_MP3_TAGS_SCRIPT),
                    "--db",
                    str(db_path.expanduser().resolve()),
                    "--mp3-root",
                    str(pool_root),
                    "--mp3-report",
                    str(tag_sync_report),
                    "--copy-core-tags",
                    "--copy-dj-tags",
                    "--execute",
                    "--out",
                    str(result_csv),
                    "--backup",
                    str(backup_jsonl),
                ],
                check=True,
                cwd=PROJECT_ROOT,
            )
            tag_sync_result = _summarize_status_csv(result_csv)

    for playlist_path in playlist_paths:
        playlist_name = playlist_path.stem
        out_playlist = playlists_root / f"{playlist_name}.m3u"
        _write_playlist(out_playlist, per_playlist[playlist_name], pool_root)

    merged_rel_paths = [source_to_dest[source_path] for source_path in unique_order]
    merged_playlist = playlists_root / f"{pool_name}_all.m3u"
    _write_playlist(merged_playlist, merged_rel_paths, pool_root)

    manifest_path = run_root / "manifest.csv"
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["playlist_name", "source_path", "dest_path", "flac_path"],
        )
        writer.writeheader()
        for row in manifest_rows:
            writer.writerow(
                {
                    "playlist_name": row.playlist_name,
                    "source_path": str(row.source_path),
                    "dest_path": str((pool_root / row.dest_rel_path).resolve()),
                    "flac_path": str(flac_lookup.get(row.source_path, "")),
                }
            )

    summary = {
        "run_root": str(run_root),
        "pool_root": str(pool_root),
        "playlists_root": str(playlists_root),
        "manifest_csv": str(manifest_path),
        "merged_playlist": str(merged_playlist),
        "source_playlists": [str(path) for path in playlist_paths],
        "playlist_count": len(playlist_paths),
        "copied_tracks": copied,
        "unique_tracks": len(unique_order),
        "playlist_rows": sum(len(rows) for rows in per_playlist.values()),
        "missing_sources": len(missing_sources),
        "flac_lookup_rows": matched_flac_rows,
    }
    if db_path is not None:
        summary["tag_sync_report"] = str(tag_sync_report)
    if tag_sync_result:
        summary["tag_sync_result"] = tag_sync_result
    (run_root / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if missing_sources:
        (run_root / "missing_sources.txt").write_text("\n".join(missing_sources) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a self-contained DJ pool from one or more M3U playlists.")
    parser.add_argument("playlists", nargs="+", help="Input M3U paths")
    parser.add_argument("--out-root", required=True, help="Root directory for the generated pool run")
    parser.add_argument("--pool-name", required=False, help="Subdirectory name for this pool run")
    parser.add_argument("--source-root", required=True, help="Root used to preserve relative source layout")
    parser.add_argument("--db", required=False, help="Optional DB path used to map source MP3s back to FLACs")
    parser.add_argument("--sync-tags", action="store_true", help="Sync copied MP3 tags from mapped FLAC sources")
    args = parser.parse_args()

    pool_name = (args.pool_name or "").strip()
    if not pool_name:
        pool_name = _safe_slug("special_pool")

    summary = build_special_pool(
        playlist_paths=[Path(item).expanduser().resolve() for item in args.playlists],
        out_root=Path(args.out_root),
        pool_name=pool_name,
        source_root=Path(args.source_root),
        db_path=Path(args.db).expanduser().resolve() if args.db else None,
        sync_tags=bool(args.sync_tags),
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
