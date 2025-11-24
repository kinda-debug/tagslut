#!/usr/bin/env python3
import hashlib
import json
import os
import sqlite3
import sys
from typing import Optional, Union

from mutagen import MutagenError
from mutagen.flac import FLAC

db_path = sys.argv[1]
list_path = sys.argv[2]

conn = sqlite3.connect(db_path)
cur = conn.cursor()


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


def get_metadata(file_path: str) -> Optional[dict[str, object]]:
    try:
        audio = FLAC(file_path)

        size = os.path.getsize(file_path)
        mtime = os.path.getmtime(file_path)

        tags = {k: audio.get(k) for k in audio.keys()}
        duration = audio.info.length
        sample_rate = audio.info.sample_rate
        bit_depth = audio.info.bits_per_sample
        channels = audio.info.channels

        checksum = fix_checksum(audio.info.md5_signature, file_path)

        return {
            "path": file_path,
            "size_bytes": size,
            "mtime": mtime,
            "checksum": checksum,
            "duration": duration,
            "sample_rate": sample_rate,
            "bit_rate": None,
            "channels": channels,
            "bit_depth": bit_depth,
            "tags_json": json.dumps(tags, ensure_ascii=False),
            "fingerprint": None,
            "fingerprint_duration": None,
        }

    except (MutagenError, OSError) as exc:
        print("ERROR:", file_path, exc)
        return None


with open(list_path, "r", encoding="utf8") as file_list:
    for line in file_list:
        file_path = line.strip()
        if not file_path:
            continue
        row = get_metadata(file_path)
        if row:
            cur.execute(
                """
                INSERT OR REPLACE INTO library_files (
                    path,
                    size_bytes,
                    mtime,
                    checksum,
                    duration,
                    sample_rate,
                    bit_rate,
                    channels,
                    bit_depth,
                    tags_json,
                    fingerprint,
                    fingerprint_duration,
                    dup_group,
                    duplicate_rank,
                    is_canonical
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["path"],
                    row["size_bytes"],
                    row["mtime"],
                    row["checksum"],
                    row["duration"],
                    row["sample_rate"],
                    row["bit_rate"],
                    row["channels"],
                    row["bit_depth"],
                    row["tags_json"],
                    row["fingerprint"],
                    row["fingerprint_duration"],
                    None,
                    None,
                    1,
                ),
            )

conn.commit()
conn.close()
