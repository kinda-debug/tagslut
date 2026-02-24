#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sqlite3
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from mutagen.flac import FLAC


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalize(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("&", " and ")
    text = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text)
    return " ".join(text.split())


def _get_tag(tags: dict, *keys: str) -> str:
    for key in keys:
        value = tags.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            for item in value:
                item = str(item).strip()
                if item:
                    return item
        else:
            value = str(value).strip()
            if value:
                return value
    return ""


def _parse_filename(path: Path) -> tuple[str, str]:
    stem = path.stem
    # strip leading track numbers
    while stem and stem[0].isdigit():
        stem = stem[1:]
    stem = stem.lstrip(" .-_")
    if " - " in stem:
        artist, title = stem.split(" - ", 1)
        return artist.strip(), title.strip()
    return "", stem.strip()


def _infer_zone(path: Path) -> str:
    text = str(path)
    if "/_QUARANTINE_CORRUPT/" in text:
        return "quarantine"
    if "/_UNRESOLVED/" in text:
        return "unresolved"
    return "accepted"


def _load_clean_index(source_root: Path) -> tuple[dict[str, Path], dict[str, Path], dict[str, Path]]:
    by_beatport: dict[str, Path] = {}
    by_isrc: dict[str, Path] = {}
    by_artist_title: dict[str, Path] = {}

    for flac_path in sorted(source_root.rglob("*.flac")):
        try:
            audio = FLAC(flac_path)
        except Exception:
            continue
        tags = audio.tags or {}
        beatport_id = _get_tag(tags, "beatport_track_id", "BEATPORT_TRACK_ID", "bp_track_id")
        isrc = _get_tag(tags, "isrc", "ISRC").upper()
        artist = _get_tag(tags, "artist", "ARTIST")
        title = _get_tag(tags, "title", "TITLE")
        if not artist or not title:
            artist_f, title_f = _parse_filename(flac_path)
            artist = artist or artist_f
            title = title or title_f

        if beatport_id and beatport_id not in by_beatport:
            by_beatport[beatport_id] = flac_path
        if isrc and isrc not in by_isrc:
            by_isrc[isrc] = flac_path
        if artist and title:
            key = f"{_normalize(artist)}||{_normalize(title)}"
            if key and key not in by_artist_title:
                by_artist_title[key] = flac_path

    return by_beatport, by_isrc, by_artist_title


def _load_corrupt_rows(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append({k: (v or "").strip() for k, v in row.items()})
    return rows


def _clone_row(conn: sqlite3.Connection, source_path: str, dest_path: str, zone: str) -> None:
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM files WHERE path = ?", (source_path,)).fetchone()
    if not row:
        raise RuntimeError(f"DB row missing for template path: {source_path}")

    columns = [desc[1] for desc in conn.execute("PRAGMA table_info(files)").fetchall()]
    data = {col: row[col] for col in columns}
    data["path"] = dest_path
    data["zone"] = zone
    data["mgmt_status"] = "replaced_corrupt"
    if not data.get("original_path"):
        data["original_path"] = source_path

    placeholders = ",".join(["?"] * len(columns))
    col_list = ",".join(columns)
    values = [data[col] for col in columns]
    conn.execute(f"INSERT INTO files ({col_list}) VALUES ({placeholders})", values)


def _find_template_by_beatport_id(conn: sqlite3.Connection, beatport_id: str) -> str | None:
    if not beatport_id:
        return None
    row = conn.execute(
        "SELECT path FROM files WHERE beatport_id = ? LIMIT 1",
        (beatport_id,),
    ).fetchone()
    if row:
        return row[0]
    return None


def _md5_hex_for_file(path: Path) -> str:
    audio = FLAC(path)
    value = audio.info.md5_signature
    if isinstance(value, int):
        return f"{value:032x}"
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    return str(value)


def _find_template_by_hash(conn: sqlite3.Connection, flac_path: Path) -> str | None:
    try:
        md5_hex = _md5_hex_for_file(flac_path)
    except Exception:
        return None
    row = conn.execute(
        "SELECT path FROM files WHERE streaminfo_md5 = ? LIMIT 1",
        (md5_hex,),
    ).fetchone()
    return row[0] if row else None


def _build_metadata_json(tags: dict) -> str:
    data = {}
    for key in ("artist", "albumartist", "title", "album", "isrc", "genre", "label", "bpm", "key"):
        value = _get_tag(tags, key, key.upper())
        if value:
            data[key] = value
    beatport_id = _get_tag(tags, "beatport_track_id", "BEATPORT_TRACK_ID", "bp_track_id")
    if beatport_id:
        data["beatport_track_id"] = beatport_id
    return json.dumps(data, ensure_ascii=False)


def _insert_minimal_row(conn: sqlite3.Connection, dest_path: Path, zone: str) -> None:
    audio = FLAC(dest_path)
    tags = audio.tags or {}
    artist = _get_tag(tags, "artist", "ARTIST")
    title = _get_tag(tags, "title", "TITLE")
    album = _get_tag(tags, "album", "ALBUM")
    isrc = _get_tag(tags, "isrc", "ISRC")
    beatport_id = _get_tag(tags, "beatport_track_id", "BEATPORT_TRACK_ID", "bp_track_id")

    info = getattr(audio, "info", None)
    duration = getattr(info, "length", None)
    bit_depth = getattr(info, "bits_per_sample", None)
    sample_rate = getattr(info, "sample_rate", None)
    bitrate = getattr(info, "bitrate", None)
    streaminfo_md5 = _md5_hex_for_file(dest_path)

    stat = dest_path.stat()
    metadata_json = _build_metadata_json(tags)

    conn.execute(
        """
        INSERT INTO files (
            path, zone, mtime, size, streaminfo_md5, duration,
            bit_depth, sample_rate, bitrate,
            metadata_json, flac_ok, integrity_state, integrity_checked_at,
            canonical_artist, canonical_title, canonical_album, canonical_isrc,
            beatport_id, download_source, download_date, mgmt_status
        ) VALUES (
            ?, ?, ?, ?, ?, ?,
            ?, ?, ?,
            ?, 1, 'valid', ?,
            ?, ?, ?, ?,
            ?, 'bpdl', ?, 'replaced_corrupt'
        )
        """,
        (
            str(dest_path),
            zone,
            stat.st_mtime,
            stat.st_size,
            streaminfo_md5,
            duration,
            bit_depth,
            sample_rate,
            bitrate,
            metadata_json,
            _now_iso(),
            artist or None,
            title or None,
            album or None,
            isrc or None,
            beatport_id or None,
            _now_iso(),
        ),
    )
def _update_row_path(conn: sqlite3.Connection, src: str, dest: str, zone: str) -> int:
    cur = conn.execute(
        """
        UPDATE files
        SET original_path = COALESCE(original_path, path),
            path = ?,
            zone = ?,
            mgmt_status = 'replaced_corrupt'
        WHERE path = ?
        """,
        (dest, zone, src),
    )
    return cur.rowcount


def main() -> int:
    ap = argparse.ArgumentParser(description="Replace corrupt files with clean Beatport downloads.")
    ap.add_argument("--input", required=True, type=Path, help="CSV with corrupt paths + beatport_id")
    ap.add_argument("--source-path", required=True, type=Path, help="Root containing clean FLAC downloads")
    ap.add_argument("--db", required=True, type=Path, help="SQLite DB path")
    ap.add_argument("--backup-root", type=Path, help="Backup root for corrupt files")
    ap.add_argument("--log", type=Path, help="JSONL log path")
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    if not args.input.exists():
        print(f"Missing input CSV: {args.input}", file=sys.stderr)
        return 2
    if not args.source_path.exists():
        print(f"Missing source path: {args.source_path}", file=sys.stderr)
        return 2
    if not args.db.exists():
        print(f"Missing DB: {args.db}", file=sys.stderr)
        return 2

    backup_root = args.backup_root
    if not backup_root:
        backup_root = Path("/Volumes/MUSIC/LIBRARY/_QUARANTINE_CORRUPT") / datetime.now().strftime("%Y-%m-%d") / "_REPLACED"
    backup_root.mkdir(parents=True, exist_ok=True)

    log_path = args.log or Path("artifacts") / f"replace_corrupt_kalabrese_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    clean_by_bp, clean_by_isrc, clean_by_key = _load_clean_index(args.source_path)
    corrupt_rows = _load_corrupt_rows(args.input)

    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in corrupt_rows:
        beatport_id = row.get("beatport_id", "")
        groups[beatport_id].append(row)

    conn = sqlite3.connect(str(args.db))
    conn.row_factory = sqlite3.Row
    used_templates: dict[str, str] = {}
    stats = {"matched": 0, "missing": 0, "moved": 0, "copied": 0, "skipped": 0}

    try:
        for beatport_id, rows in groups.items():
            clean_path = None
            if beatport_id:
                clean_path = clean_by_bp.get(beatport_id)
            if clean_path is None and rows:
                artist = rows[0].get("artist", "")
                title = rows[0].get("title", "")
                key = f"{_normalize(artist)}||{_normalize(title)}"
                clean_path = clean_by_key.get(key)
            if clean_path is None and rows:
                # If we don't have a clean file in the source root, check if the corrupt path
                # already contains a clean Beatport-tagged file and update DB accordingly.
                for row in rows:
                    corrupt_path = Path(row.get("path", "")).expanduser()
                    zone = _infer_zone(corrupt_path)
                    current_bp = ""
                    try:
                        current_audio = FLAC(corrupt_path)
                        current_bp = _get_tag(current_audio.tags or {}, "beatport_track_id", "BEATPORT_TRACK_ID", "bp_track_id")
                    except Exception:
                        current_bp = ""

                    if current_bp and current_bp == beatport_id:
                        exists = conn.execute("SELECT 1 FROM files WHERE path = ?", (str(corrupt_path),)).fetchone()
                        if not exists:
                            template = _find_template_by_beatport_id(conn, beatport_id)
                            if template is None:
                                template = _find_template_by_hash(conn, corrupt_path)
                            if template:
                                _clone_row(conn, template, str(corrupt_path), zone)
                            else:
                                _insert_minimal_row(conn, corrupt_path, zone)
                        stats["matched"] += 1
                        with log_path.open("a", encoding="utf-8") as handle:
                            handle.write(json.dumps({
                                "ts": _now_iso(),
                                "action": "already_clean",
                                "corrupt_path": str(corrupt_path),
                                "beatport_id": beatport_id,
                                "zone": zone,
                            }) + "\n")
                        continue

                    stats["missing"] += 1
                    with log_path.open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps({
                            "ts": _now_iso(),
                            "action": "missing_clean",
                            "corrupt_path": row.get("path"),
                            "beatport_id": beatport_id,
                        }) + "\n")
                continue

            template_path = used_templates.get(str(clean_path))

            for idx, row in enumerate(rows):
                corrupt_path = Path(row.get("path", "")).expanduser()
                if not corrupt_path.exists():
                    stats["skipped"] += 1
                    with log_path.open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps({
                            "ts": _now_iso(),
                            "action": "missing_corrupt",
                            "corrupt_path": str(corrupt_path),
                            "beatport_id": beatport_id,
                        }) + "\n")
                    continue

                dest_path = corrupt_path
                zone = _infer_zone(dest_path)

                if not args.execute:
                    stats["matched"] += 1
                    with log_path.open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps({
                            "ts": _now_iso(),
                            "action": "plan_replace",
                            "corrupt_path": str(corrupt_path),
                            "clean_path": str(clean_path),
                            "beatport_id": beatport_id,
                            "zone": zone,
                        }) + "\n")
                    continue

                # backup corrupt file
                try:
                    rel = None
                    try:
                        rel = corrupt_path.relative_to(Path("/Volumes/MUSIC/LIBRARY"))
                    except Exception:
                        rel = corrupt_path.name
                    backup_path = backup_root / rel
                    backup_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(corrupt_path), str(backup_path))
                except Exception:
                    backup_path = None

                dest_path.parent.mkdir(parents=True, exist_ok=True)

                # If the corrupt path already contains the clean file, just ensure DB row exists.
                try:
                    current_audio = FLAC(dest_path)
                    current_bp = _get_tag(current_audio.tags or {}, "beatport_track_id", "BEATPORT_TRACK_ID", "bp_track_id")
                except Exception:
                    current_bp = ""

                if current_bp and current_bp == beatport_id:
                    exists = conn.execute("SELECT 1 FROM files WHERE path = ?", (str(dest_path),)).fetchone()
                    if not exists:
                        template = _find_template_by_beatport_id(conn, beatport_id)
                        if template is None:
                            template = _find_template_by_hash(conn, dest_path)
                        if template:
                            _clone_row(conn, template, str(dest_path), zone)
                        else:
                            _insert_minimal_row(conn, dest_path, zone)
                    stats["matched"] += 1
                    with log_path.open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps({
                            "ts": _now_iso(),
                            "action": "already_clean",
                            "corrupt_path": str(corrupt_path),
                            "beatport_id": beatport_id,
                            "zone": zone,
                        }) + "\n")
                    continue

                if template_path is None:
                    # First use of this clean file -> move and update DB row
                    shutil.move(str(clean_path), str(dest_path))
                    conn.execute("DELETE FROM files WHERE path = ?", (str(dest_path),))
                    updated = _update_row_path(conn, str(clean_path), str(dest_path), zone)
                    if updated != 1:
                        template = _find_template_by_beatport_id(conn, beatport_id)
                        if template is None:
                            template = _find_template_by_hash(conn, dest_path)
                        if template:
                            _clone_row(conn, template, str(dest_path), zone)
                        else:
                            _insert_minimal_row(conn, dest_path, zone)
                    used_templates[str(clean_path)] = str(dest_path)
                    template_path = str(dest_path)
                    stats["moved"] += 1
                else:
                    # Duplicate corrupt entry -> copy from template and clone DB row
                    shutil.copy2(template_path, str(dest_path))
                    conn.execute("DELETE FROM files WHERE path = ?", (str(dest_path),))
                    _clone_row(conn, template_path, str(dest_path), zone)
                    stats["copied"] += 1

                stats["matched"] += 1
                with log_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps({
                        "ts": _now_iso(),
                        "action": "replaced",
                        "corrupt_path": str(corrupt_path),
                        "clean_path": str(clean_path),
                        "beatport_id": beatport_id,
                        "backup_path": str(backup_path) if backup_path else None,
                        "zone": zone,
                    }) + "\n")

        if args.execute:
            conn.commit()
    finally:
        conn.close()

    print("RESULTS")
    for key, value in stats.items():
        print(f"{key}={value}")
    print(f"log={log_path}")
    if not args.execute:
        print("Dry-run only. Use --execute to apply changes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
