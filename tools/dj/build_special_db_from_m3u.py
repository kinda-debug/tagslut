#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import mutagen  # type: ignore
from mutagen.easyid3 import EasyID3  # type: ignore
from mutagen.id3 import ID3  # type: ignore

from tagslut.storage.schema import init_db


DEFAULT_AUDIO_EXTS = {
    ".flac", ".mp3", ".m4a", ".mp4", ".aac",
    ".ogg", ".opus", ".wav", ".aif", ".aiff",
    ".wv", ".ape", ".asf",
}


@dataclass(frozen=True)
class SourceEntry:
    resolved_path: Path
    item_index: int
    raw_entry: str
    extinf: str | None
    playlist_path: Path | None = None
    playlist_name: str | None = None
    pool_root: Path | None = None
    source_kind: str = "playlist"


def _read_playlist_entries(playlist_path: Path) -> list[SourceEntry]:
    resolved_playlist = playlist_path.expanduser().resolve()
    playlist_dir = resolved_playlist.parent
    playlist_name = resolved_playlist.stem
    entries: list[SourceEntry] = []
    pending_extinf: str | None = None

    for raw_line in resolved_playlist.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#EXTINF:"):
            _, _, label = line.partition(",")
            pending_extinf = label.strip() or None
            continue
        if line.startswith("#"):
            continue
        item_path = Path(line).expanduser()
        if not item_path.is_absolute():
            item_path = playlist_dir / item_path
        entries.append(
            SourceEntry(
                resolved_path=item_path.resolve(),
                item_index=len(entries) + 1,
                raw_entry=line,
                extinf=pending_extinf,
                playlist_path=resolved_playlist,
                playlist_name=playlist_name,
                source_kind="playlist",
            )
        )
        pending_extinf = None
    return entries


def _read_pool_entries(pool_root: Path) -> list[SourceEntry]:
    resolved_pool = pool_root.expanduser().resolve()
    entries: list[SourceEntry] = []
    for dirpath, dirnames, filenames in os.walk(resolved_pool):
        dirnames.sort()
        for filename in sorted(filenames):
            file_path = Path(dirpath) / filename
            if file_path.suffix.lower() not in DEFAULT_AUDIO_EXTS:
                continue
            rel_path = file_path.relative_to(resolved_pool).as_posix()
            entries.append(
                SourceEntry(
                    resolved_path=file_path.resolve(),
                    item_index=len(entries) + 1,
                    raw_entry=rel_path,
                    extinf=None,
                    pool_root=resolved_pool,
                    source_kind="pool",
                )
            )
    return entries


def _jsonable(value: Any, *, depth: int = 0, max_depth: int = 6) -> Any:
    if depth >= max_depth:
        return str(value)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (bytes, bytearray)):
        return {
            "__type__": "bytes",
            "size": len(value),
        }
    if isinstance(value, dict):
        return {str(key): _jsonable(item, depth=depth + 1, max_depth=max_depth) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item, depth=depth + 1, max_depth=max_depth) for item in value]
    if hasattr(value, "__dict__"):
        payload: dict[str, Any] = {"__type__": type(value).__name__}
        for key, item in vars(value).items():
            if key.startswith("_"):
                continue
            if key == "data" and isinstance(item, (bytes, bytearray)):
                payload[key] = {"__type__": "bytes", "size": len(item)}
                continue
            payload[key] = _jsonable(item, depth=depth + 1, max_depth=max_depth)
        if len(payload) > 1:
            return payload
    return str(value)


def _serialize_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    try:
        items = value.items()
    except Exception:
        try:
            items = ((key, value[key]) for key in value.keys())
        except Exception:
            return {}
    return {str(key): _jsonable(item) for key, item in items}


def _text_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (int, float)):
        return [str(value)]
    if isinstance(value, (bytes, bytearray)):
        return []
    if hasattr(value, "text"):
        return _text_values(getattr(value, "text"))
    if hasattr(value, "url"):
        return _text_values(getattr(value, "url"))
    if isinstance(value, (list, tuple, set)):
        values: list[str] = []
        for item in value:
            values.extend(_text_values(item))
        return values
    text = str(value).strip()
    return [text] if text else []


def _text_mapping(value: Any) -> dict[str, list[str]]:
    if value is None:
        return {}
    try:
        items = value.items()
    except Exception:
        try:
            items = ((key, value[key]) for key in value.keys())
        except Exception:
            return {}
    mapping: dict[str, list[str]] = {}
    for key, item in items:
        values = _text_values(item)
        if values:
            mapping[str(key)] = values
    return mapping


def _serialize_audio_info(audio: Any) -> dict[str, Any]:
    info = getattr(audio, "info", None) if audio is not None else None
    if info is None:
        return {}

    payload: dict[str, Any] = {"__type__": type(info).__name__}
    attrs = {
        "bitrate",
        "bitrate_mode",
        "bits_per_sample",
        "channels",
        "codec",
        "codec_description",
        "encoder_info",
        "encoder_settings",
        "layer",
        "length",
        "mode",
        "protected",
        "sample_rate",
    }
    try:
        attrs.update(key for key in vars(info).keys() if not key.startswith("_"))
    except TypeError:
        pass
    for key in sorted(attrs):
        if not hasattr(info, key):
            continue
        item = getattr(info, key)
        if callable(item):
            continue
        payload[key] = _jsonable(item)
    return payload


def _tag_source(audio: Any) -> Any:
    if audio is None:
        return None
    tags = getattr(audio, "tags", None)
    return tags if tags is not None else audio


def _coerce_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, tuple)):
        for item in value:
            text = _coerce_text(item)
            if text:
                return text
        return None
    if isinstance(value, dict):
        for item in value.values():
            text = _coerce_text(item)
            if text:
                return text
        return None
    text = str(value).strip()
    return text or None


def _first_from_maps(*maps: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for mapping in maps:
        for key in keys:
            if key in mapping:
                text = _coerce_text(mapping[key])
                if text:
                    return text
            lowered = key.lower()
            if lowered in mapping:
                text = _coerce_text(mapping[lowered])
                if text:
                    return text
            uppered = key.upper()
            if uppered in mapping:
                text = _coerce_text(mapping[uppered])
                if text:
                    return text
    return None


def _split_extinf(extinf: str | None) -> tuple[str | None, str | None]:
    if not extinf:
        return None, None
    if " - " not in extinf:
        return None, extinf.strip() or None
    artist, title = extinf.split(" - ", 1)
    artist = artist.strip()
    title = title.strip()
    return artist or None, title or None


def _extract_file_payload(path: Path, entry: SourceEntry, library_label: str) -> dict[str, Any]:
    stat = path.stat()
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    easy_audio = None
    audio = None
    read_error: str | None = None
    try:
        audio = mutagen.File(str(path), easy=False)
    except Exception as exc:
        read_error = f"{type(exc).__name__}: {exc}"
    try:
        easy_audio = mutagen.File(str(path), easy=True)
    except Exception:
        easy_audio = None
    if audio is None and path.suffix.lower() == ".mp3":
        try:
            audio = ID3(str(path))
        except Exception:
            audio = None
    if easy_audio is None and path.suffix.lower() == ".mp3":
        try:
            easy_audio = EasyID3(str(path))
        except Exception:
            easy_audio = None

    raw_tags_obj = _tag_source(audio)
    easy_tags_obj = _tag_source(easy_audio)
    raw_tags = _serialize_mapping(raw_tags_obj)
    easy_tags = _serialize_mapping(easy_tags_obj)
    raw_text_tags = _text_mapping(raw_tags_obj)
    easy_text_tags = _text_mapping(easy_tags_obj)
    extinf_artist, extinf_title = _split_extinf(entry.extinf)

    title = _first_from_maps(easy_text_tags, raw_text_tags, keys=("title", "TIT2", "\xa9nam")) or extinf_title or path.stem
    artist = _first_from_maps(
        easy_text_tags,
        raw_text_tags,
        keys=("artist", "albumartist", "TPE1", "TPE2", "\xa9ART", "aART"),
    ) or extinf_artist
    album = _first_from_maps(easy_text_tags, raw_text_tags, keys=("album", "TALB", "\xa9alb"))
    genre = _first_from_maps(easy_text_tags, raw_text_tags, keys=("genre", "TCON", "\xa9gen"))
    bpm_text = _first_from_maps(easy_text_tags, raw_text_tags, keys=("bpm", "TBPM", "tmpo"))
    key_text = _first_from_maps(easy_text_tags, raw_text_tags, keys=("initialkey", "key", "TKEY"))
    isrc = _first_from_maps(easy_text_tags, raw_text_tags, keys=("isrc", "TSRC", "----:com.apple.iTunes:ISRC"))
    year = _first_from_maps(easy_text_tags, raw_text_tags, keys=("date", "year", "TDRC", "TYER", "\xa9day"))

    bpm: float | None = None
    if bpm_text:
        try:
            bpm = float(str(bpm_text).replace(",", "."))
        except ValueError:
            bpm = None

    info = _serialize_audio_info(audio)
    duration_seconds: float | None = None
    bitrate: int | None = None
    sample_rate: int | None = None
    bit_depth: int | None = None

    length_value = info.get("length")
    if isinstance(length_value, (int, float)):
        duration_seconds = float(length_value)
    bitrate_value = info.get("bitrate")
    if isinstance(bitrate_value, int):
        bitrate = bitrate_value
    sample_rate_value = info.get("sample_rate")
    if isinstance(sample_rate_value, int):
        sample_rate = sample_rate_value
    bit_depth_value = info.get("bits_per_sample")
    if isinstance(bit_depth_value, int):
        bit_depth = bit_depth_value

    metadata_payload = {
        "source": {
            "kind": entry.source_kind,
            "raw_entry": entry.raw_entry,
            "item_index": entry.item_index,
        },
        "playlist": {
            "playlist_path": str(entry.playlist_path) if entry.playlist_path is not None else None,
            "playlist_name": entry.playlist_name,
            "item_index": entry.item_index if entry.playlist_path is not None else None,
            "raw_entry": entry.raw_entry if entry.playlist_path is not None else None,
            "extinf": entry.extinf,
        },
        "pool": {
            "pool_root": str(entry.pool_root) if entry.pool_root is not None else None,
            "relative_path": entry.raw_entry if entry.pool_root is not None else None,
        },
        "file": {
            "path": str(path),
            "basename": path.name,
            "suffix": path.suffix.lower(),
            "size": stat.st_size,
            "mtime": stat.st_mtime,
        },
        "audio": {
            "container_type": type(audio).__name__ if audio is not None else None,
            "mime": getattr(audio, "mime", None) if audio is not None else None,
            "info": info,
            "read_error": read_error,
        },
        "easy_tags": easy_tags,
        "raw_tags": raw_tags,
    }

    return {
        "path": str(path),
        "library": library_label,
        "mtime": stat.st_mtime,
        "size": stat.st_size,
        "duration": duration_seconds,
        "bit_depth": bit_depth,
        "sample_rate": sample_rate,
        "bitrate": bitrate,
        "metadata_json": json.dumps(metadata_payload, ensure_ascii=False, sort_keys=True),
        "m3u_path": str(entry.playlist_path) if entry.playlist_path is not None else None,
        "dj_pool_path": str(path),
        "is_dj_material": 1,
        "duration_measured_ms": int(round(duration_seconds * 1000.0)) if duration_seconds is not None else None,
        "duration_measured_at": now_iso,
        "duration_status": "measured" if duration_seconds is not None else None,
        "duration_check_version": "special_db_v1",
        "canonical_title": title,
        "canonical_artist": artist,
        "canonical_album": album,
        "canonical_genre": genre,
        "canonical_bpm": bpm,
        "genre": genre,
        "bpm": bpm,
        "key_camelot": key_text,
        "isrc": isrc,
        "canonical_year": int(year[:4]) if year and year[:4].isdigit() else None,
    }


def _ensure_special_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS playlist_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            playlist_path TEXT NOT NULL,
            playlist_name TEXT NOT NULL,
            item_index INTEGER NOT NULL,
            raw_entry TEXT NOT NULL,
            resolved_path TEXT NOT NULL,
            extinf TEXT,
            file_exists INTEGER NOT NULL,
            UNIQUE(playlist_path, item_index)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_playlist_items_resolved_path ON playlist_items(resolved_path)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_playlist_items_playlist_path ON playlist_items(playlist_path)"
    )


def build_special_db(
    *,
    playlist_path: Path | None = None,
    pool_root: Path | None = None,
    db_path: Path,
    overwrite: bool = False,
    library_label: str | None = None,
) -> dict[str, Any]:
    if playlist_path is None and pool_root is None:
        raise ValueError("Provide playlist_path, pool_root, or both")
    resolved_playlist = playlist_path.expanduser().resolve() if playlist_path is not None else None
    resolved_pool_root = pool_root.expanduser().resolve() if pool_root is not None else None
    resolved_db = db_path.expanduser().resolve()
    if resolved_db.exists():
        if not overwrite:
            raise FileExistsError(f"DB already exists: {resolved_db}")
        resolved_db.unlink()
    resolved_db.parent.mkdir(parents=True, exist_ok=True)

    playlist_entries = _read_playlist_entries(resolved_playlist) if resolved_playlist is not None else []
    file_entries = _read_pool_entries(resolved_pool_root) if resolved_pool_root is not None else list(playlist_entries)
    playlist_entry_by_path = {
        entry.resolved_path: entry for entry in playlist_entries if entry.resolved_path.exists()
    }
    if resolved_pool_root is not None and resolved_pool_root.name == "pool":
        default_library_label = resolved_pool_root.parent.name
    elif resolved_pool_root is not None:
        default_library_label = resolved_pool_root.name
    elif resolved_playlist is not None and resolved_playlist.parent.name == "playlists":
        default_library_label = resolved_playlist.parent.parent.name
    elif resolved_playlist is not None:
        default_library_label = resolved_playlist.stem
    else:
        default_library_label = "special_pool"
    label = (library_label or default_library_label).strip() or default_library_label

    conn = sqlite3.connect(str(resolved_db))
    conn.row_factory = sqlite3.Row
    try:
        init_db(conn)
        _ensure_special_schema(conn)

        existing_files = 0
        missing_files = 0
        inserted_files = 0
        seen_paths: set[Path] = set()

        with conn:
            for entry in playlist_entries:
                exists_flag = entry.resolved_path.exists()
                conn.execute(
                    """
                    INSERT INTO playlist_items (
                        playlist_path,
                        playlist_name,
                        item_index,
                        raw_entry,
                        resolved_path,
                        extinf,
                        file_exists
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(entry.playlist_path),
                        entry.playlist_name,
                        entry.item_index,
                        entry.raw_entry,
                        str(entry.resolved_path),
                        entry.extinf,
                        1 if exists_flag else 0,
                    ),
                )
            for entry in file_entries:
                exists_flag = entry.resolved_path.exists()
                if not exists_flag:
                    missing_files += 1
                    continue
                existing_files += 1
                if entry.resolved_path in seen_paths:
                    continue
                seen_paths.add(entry.resolved_path)
                payload = _extract_file_payload(
                    entry.resolved_path,
                    playlist_entry_by_path.get(entry.resolved_path, entry),
                    label,
                )
                conn.execute(
                    """
                    INSERT INTO files (
                        path,
                        library,
                        mtime,
                        size,
                        duration,
                        bit_depth,
                        sample_rate,
                        bitrate,
                        metadata_json,
                        m3u_path,
                        dj_pool_path,
                        is_dj_material,
                        duration_measured_ms,
                        duration_measured_at,
                        duration_status,
                        duration_check_version,
                        canonical_title,
                        canonical_artist,
                        canonical_album,
                        canonical_genre,
                        canonical_bpm,
                        canonical_year,
                        genre,
                        bpm,
                        key_camelot,
                        isrc
                    ) VALUES (
                        :path,
                        :library,
                        :mtime,
                        :size,
                        :duration,
                        :bit_depth,
                        :sample_rate,
                        :bitrate,
                        :metadata_json,
                        :m3u_path,
                        :dj_pool_path,
                        :is_dj_material,
                        :duration_measured_ms,
                        :duration_measured_at,
                        :duration_status,
                        :duration_check_version,
                        :canonical_title,
                        :canonical_artist,
                        :canonical_album,
                        :canonical_genre,
                        :canonical_bpm,
                        :canonical_year,
                        :genre,
                        :bpm,
                        :key_camelot,
                        :isrc
                    )
                    ON CONFLICT(path) DO UPDATE SET
                        library = excluded.library,
                        mtime = excluded.mtime,
                        size = excluded.size,
                        duration = excluded.duration,
                        bit_depth = excluded.bit_depth,
                        sample_rate = excluded.sample_rate,
                        bitrate = excluded.bitrate,
                        metadata_json = excluded.metadata_json,
                        m3u_path = excluded.m3u_path,
                        dj_pool_path = excluded.dj_pool_path,
                        is_dj_material = excluded.is_dj_material,
                        duration_measured_ms = excluded.duration_measured_ms,
                        duration_measured_at = excluded.duration_measured_at,
                        duration_status = excluded.duration_status,
                        duration_check_version = excluded.duration_check_version,
                        canonical_title = excluded.canonical_title,
                        canonical_artist = excluded.canonical_artist,
                        canonical_album = excluded.canonical_album,
                        canonical_genre = excluded.canonical_genre,
                        canonical_bpm = excluded.canonical_bpm,
                        canonical_year = excluded.canonical_year,
                        genre = excluded.genre,
                        bpm = excluded.bpm,
                        key_camelot = excluded.key_camelot,
                        isrc = excluded.isrc
                    """,
                    payload,
                )
                inserted_files += 1
        if resolved_pool_root is not None and resolved_playlist is not None:
            source_mode = "pool+playlist"
        elif resolved_pool_root is not None:
            source_mode = "pool"
        else:
            source_mode = "playlist"
        summary = {
            "source_mode": source_mode,
            "playlist_path": str(resolved_playlist) if resolved_playlist is not None else None,
            "pool_root": str(resolved_pool_root) if resolved_pool_root is not None else None,
            "db_path": str(resolved_db),
            "library_label": label,
            "playlist_entries": len(playlist_entries),
            "source_entries": len(file_entries),
            "pool_files": len(file_entries) if resolved_pool_root is not None else None,
            "existing_entries": existing_files,
            "missing_entries": missing_files,
            "unique_files": len(seen_paths),
            "inserted_files": inserted_files,
        }
    finally:
        conn.close()

    summary_path = resolved_db.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a SQLite metadata DB from a special-pool playlist and/or pool root.")
    parser.add_argument("playlist", nargs="?", help="Input M3U playlist path")
    parser.add_argument("--pool-root", required=False, help="Optional pool directory to index recursively")
    parser.add_argument("--db", required=False, help="Output SQLite DB path")
    parser.add_argument("--library-label", required=False, help="Optional library label written into files.library")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite the output DB if it already exists")
    args = parser.parse_args()

    if not args.playlist and not args.pool_root:
        parser.error("Provide a playlist path, --pool-root, or both")
    playlist_path = Path(args.playlist).expanduser().resolve() if args.playlist else None
    pool_root = Path(args.pool_root).expanduser().resolve() if args.pool_root else None
    if args.db:
        db_path = Path(args.db).expanduser().resolve()
    elif pool_root is not None and pool_root.name == "pool":
        db_path = pool_root.parent / f"{pool_root.parent.name}_metadata.db"
    elif pool_root is not None:
        db_path = pool_root / f"{pool_root.name}_metadata.db"
    elif playlist_path is not None:
        db_path = playlist_path.parent.parent / f"{playlist_path.stem}_metadata.db"
    else:
        parser.error("Could not determine DB path")
    summary = build_special_db(
        playlist_path=playlist_path,
        pool_root=pool_root,
        db_path=db_path,
        overwrite=bool(args.overwrite),
        library_label=args.library_label,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
