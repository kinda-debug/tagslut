#!/usr/bin/env python3
"""Manually ingest FLAC metadata into the ``library_files`` table."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Iterable, Optional, Union

from dedupe import health_score
from mutagen import MutagenError
from mutagen.flac import FLAC

LIBRARY_COLUMNS = (
    "path",
    "size_bytes",
    "mtime",
    "checksum",
    "duration",
    "sample_rate",
    "bit_rate",
    "channels",
    "bit_depth",
    "tags_json",
    "fingerprint",
    "fingerprint_duration",
    "dup_group",
    "duplicate_rank",
    "is_canonical",
    "extra_json",
    "library_state",
    "flac_ok",
)


def fix_checksum(
    md5sig: Union[bytes, bytearray, int, None],
    file_path: str,
) -> Optional[str]:
    """Return a usable hex digest from Mutagen's md5_signature."""

    if isinstance(md5sig, (bytes, bytearray)):
        try:
            return md5sig.decode("ascii")
        except UnicodeDecodeError:
            pass

    if isinstance(md5sig, int):
        return f"{md5sig:032x}"

    try:
        hasher = hashlib.md5()
        with open(file_path, "rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except OSError:
        return None


def get_metadata(file_path: Path) -> Optional[dict[str, object]]:
    """Extract the columns needed for a ``library_files`` row."""

    health = health_score.score_flac(str(file_path))
    extra_payload: dict[str, object] = {
        "health_score": health["health_score"],
        "health_metrics": health["metrics"],
    }

    try:
        audio = FLAC(file_path)
        size = file_path.stat().st_size
        mtime = file_path.stat().st_mtime

        tags = {key: audio.get(key) for key in audio.keys()}
        duration = audio.info.length
        sample_rate = audio.info.sample_rate
        bit_rate = getattr(audio.info, "bitrate", None)
        bit_depth = audio.info.bits_per_sample
        channels = audio.info.channels
        checksum = fix_checksum(audio.info.md5_signature, str(file_path))

        return {
            "path": str(file_path),
            "size_bytes": size,
            "mtime": mtime,
            "checksum": checksum,
            "duration": duration,
            "sample_rate": sample_rate,
            "bit_rate": bit_rate,
            "channels": channels,
            "bit_depth": bit_depth,
            "tags_json": json.dumps(
                tags, sort_keys=True, separators=(",", ":")
            ),
            "fingerprint": None,
            "fingerprint_duration": None,
            "dup_group": None,
            "duplicate_rank": None,
            "is_canonical": 1,
            "extra_json": json.dumps(
                extra_payload, sort_keys=True, separators=(",", ":")
            ),
            "library_state": "FINAL",
            "flac_ok": 1 if health["health_score"] > 0 else 0,
        }

    except (MutagenError, OSError) as exc:
        print("ERROR:", file_path, exc)
        extra_payload["error"] = str(exc)
        size = file_path.stat().st_size if file_path.exists() else None
        mtime = file_path.stat().st_mtime if file_path.exists() else None
        checksum = fix_checksum(None, str(file_path)) if file_path.exists() else None

        return {
            "path": str(file_path),
            "size_bytes": size,
            "mtime": mtime,
            "checksum": checksum,
            "duration": None,
            "sample_rate": None,
            "bit_rate": None,
            "channels": None,
            "bit_depth": None,
            "tags_json": json.dumps({}, sort_keys=True, separators=(",", ":")),
            "fingerprint": None,
            "fingerprint_duration": None,
            "dup_group": None,
            "duplicate_rank": None,
            "is_canonical": 0,
            "extra_json": json.dumps(
                extra_payload, sort_keys=True, separators=(",", ":")
            ),
            "library_state": "FINAL",
            "flac_ok": 0,
        }


def validate_schema(connection: sqlite3.Connection) -> None:
    """Ensure the ``library_files`` table matches the expected column order."""

    rows = connection.execute("PRAGMA table_info(library_files);").fetchall()
    existing = tuple(column[1] for column in rows)
    if existing != LIBRARY_COLUMNS:
        raise SystemExit(
            "library_files schema mismatch. Expected columns: "
            f"{', '.join(LIBRARY_COLUMNS)}. Found: {', '.join(existing)}"
        )


def ingest_paths(connection: sqlite3.Connection, paths: Iterable[str]) -> None:
    """Insert or replace the provided file paths into ``library_files``."""

    placeholders = ", ".join("?" for _ in LIBRARY_COLUMNS)
    sql = (
        "INSERT OR REPLACE INTO library_files ("
        + ", ".join(LIBRARY_COLUMNS)
        + f") VALUES ({placeholders})"
    )

    for path_text in paths:
        if not path_text:
            continue
        file_path = Path(path_text)
        metadata = get_metadata(file_path)
        if not metadata:
            continue
        connection.execute(sql, tuple(metadata[column] for column in LIBRARY_COLUMNS))


def main() -> None:
    """Load a list of file paths into the final library database."""

    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "db_path",
        type=Path,
        help="Path to the SQLite database containing the library_files table",
    )
    parser.add_argument(
        "list_path",
        type=Path,
        help="Text file with one absolute file path per line",
    )
    args = parser.parse_args()

    with sqlite3.connect(args.db_path) as connection:
        validate_schema(connection)
        with args.list_path.open("r", encoding="utf8") as file_list:
            ingest_paths(connection, [line.strip() for line in file_list])
        connection.commit()


if __name__ == "__main__":
    main()
