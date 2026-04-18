#!/usr/bin/env python3
"""
Scan a directory of audio files and store metadata snapshots in SQLite.

Requires:
    pip install mutagen

Usage:
    python scan_audio_metadata_to_db.py /path/to/music metadata.sqlite
    python scan_audio_metadata_to_db.py /path/to/music metadata.sqlite --verbose

Query example:
    sqlite3 metadata.sqlite 'select path, json_extract(metadata_json, "$.tags.TIT2.text[0]") from file_metadata;'
"""

from __future__ import annotations

import argparse
import base64
import json
import sqlite3
import sys
from collections.abc import Iterator, Mapping
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from mutagen import File as MutagenFile

DEFAULT_EXTENSIONS = (
    ".mp3",
    ".flac",
    ".m4a",
    ".mp4",
    ".aac",
    ".ogg",
    ".opus",
    ".wav",
    ".aif",
    ".aiff",
    ".ape",
    ".wv",
    ".dsf",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recursively scan audio files and save metadata snapshots to SQLite."
    )
    parser.add_argument("root", help="Directory to scan")
    parser.add_argument("db_path", help="SQLite database file to create/update")
    parser.add_argument(
        "--extensions",
        default=",".join(DEFAULT_EXTENSIONS),
        help="Comma-separated file extensions to scan",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print progress and per-file scan results",
    )
    return parser.parse_args()


def normalize_extensions(raw: str) -> set[str]:
    extensions: set[str] = set()
    for item in raw.split(","):
        cleaned = item.strip().lower()
        if not cleaned:
            continue
        if not cleaned.startswith("."):
            cleaned = f".{cleaned}"
        extensions.add(cleaned)
    return extensions or set(DEFAULT_EXTENSIONS)


def iter_audio_files(root: Path, extensions: set[str]) -> Iterator[Path]:
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in extensions:
            yield path


def log(message: str, *, verbose: bool = True) -> None:
    if verbose:
        print(message, file=sys.stderr)


def to_jsonable(value: Any, depth: int = 0) -> Any:
    if depth > 10:
        return {"__type__": type(value).__name__, "__repr__": repr(value)}

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, bytes):
        return {"__bytes_base64__": base64.b64encode(value).decode("ascii")}

    if isinstance(value, Enum):
        return value.name

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(item, depth + 1) for item in value]

    if isinstance(value, Mapping):
        return {str(key): to_jsonable(item, depth + 1) for key, item in value.items()}

    if hasattr(value, "items") and callable(value.items):
        try:
            return {
                str(key): to_jsonable(item, depth + 1)
                for key, item in value.items()
            }
        except Exception:
            pass

    if hasattr(value, "__dict__"):
        data = {
            key: to_jsonable(item, depth + 1)
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
        if data:
            return {"__type__": type(value).__name__, **data}

    payload: dict[str, Any] = {
        "__type__": type(value).__name__,
        "__repr__": repr(value),
    }
    for attr in ("text", "desc", "lang", "mime", "type", "data", "encoding", "url", "owner"):
        if not hasattr(value, attr):
            continue
        try:
            payload[attr] = to_jsonable(getattr(value, attr), depth + 1)
        except Exception:
            continue
    return payload


def extract_metadata(root: Path, path: Path) -> dict[str, Any]:
    stat = path.stat()
    metadata: dict[str, Any] = {
        "path": str(path.resolve()),
        "relative_path": str(path.relative_to(root)),
        "filename": path.name,
        "suffix": path.suffix.lower(),
        "size_bytes": stat.st_size,
        "modified_at_ns": stat.st_mtime_ns,
    }

    try:
        audio = MutagenFile(path, easy=False)
        if audio is None:
            metadata["scan_error"] = "unsupported_or_unreadable"
            return metadata

        metadata["mutagen_type"] = type(audio).__name__
        metadata["mime_types"] = list(getattr(audio, "mime", []) or [])
        metadata["info"] = to_jsonable(getattr(audio, "info", None))
        metadata["tags"] = to_jsonable(getattr(audio, "tags", None))
    except Exception as exc:
        metadata["scan_error"] = f"{type(exc).__name__}: {exc}"

    return metadata


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS file_metadata (
            path TEXT PRIMARY KEY,
            metadata_json TEXT NOT NULL,
            scanned_at TEXT NOT NULL
        )
        """
    )


def upsert_metadata(conn: sqlite3.Connection, metadata: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO file_metadata (path, metadata_json, scanned_at)
        VALUES (?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
            metadata_json = excluded.metadata_json,
            scanned_at = excluded.scanned_at
        """,
        (
            metadata["path"],
            json.dumps(metadata, ensure_ascii=False, sort_keys=True),
            datetime.now(timezone.utc).isoformat(),
        ),
    )


def main() -> int:
    args = parse_args()

    root = Path(args.root).expanduser().resolve()
    db_path = Path(args.db_path).expanduser().resolve()
    extensions = normalize_extensions(args.extensions)

    if not root.is_dir():
        print(f"Scan root is not a directory: {root}", file=sys.stderr)
        return 1

    db_path.parent.mkdir(parents=True, exist_ok=True)
    files = list(iter_audio_files(root, extensions))

    log(f"[scan] root={root}", verbose=args.verbose)
    log(f"[scan] db={db_path}", verbose=args.verbose)
    log(f"[scan] extensions={','.join(sorted(extensions))}", verbose=args.verbose)
    log(f"[scan] files_found={len(files)}", verbose=args.verbose)

    conn = sqlite3.connect(str(db_path))
    try:
        init_db(conn)
        log("[db] initialized file_metadata table", verbose=args.verbose)
        processed = 0
        errored = 0

        with conn:
            for path in files:
                relative_path = path.relative_to(root)
                log(f"[file] scanning {relative_path}", verbose=args.verbose)
                metadata = extract_metadata(root, path)
                upsert_metadata(conn, metadata)
                processed += 1
                if metadata.get("scan_error"):
                    errored += 1
                    log(
                        f"[file] error {relative_path}: {metadata['scan_error']}",
                        verbose=True,
                    )
                else:
                    log(
                        f"[file] saved {relative_path} type={metadata.get('mutagen_type', 'unknown')}",
                        verbose=args.verbose,
                    )
    finally:
        conn.close()
        log("[db] connection closed", verbose=args.verbose)

    print(f"indexed={processed} errored={errored} db={db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
