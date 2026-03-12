#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from mutagen.easyid3 import EasyID3


def _safe_slug(value: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "pool"


def _read_playlist(path: Path) -> list[Path]:
    items: list[Path] = []
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        items.append(Path(line).expanduser().resolve())
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
            fieldnames=["playlist_name", "source_path", "dest_path"],
        )
        writer.writeheader()
        for row in manifest_rows:
            writer.writerow(
                {
                    "playlist_name": row.playlist_name,
                    "source_path": str(row.source_path),
                    "dest_path": str((pool_root / row.dest_rel_path).resolve()),
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
    }
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
    args = parser.parse_args()

    pool_name = (args.pool_name or "").strip()
    if not pool_name:
        pool_name = _safe_slug("special_pool")

    summary = build_special_pool(
        playlist_paths=[Path(item).expanduser().resolve() for item in args.playlists],
        out_root=Path(args.out_root),
        pool_name=pool_name,
        source_root=Path(args.source_root),
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
