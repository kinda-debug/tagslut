#!/usr/bin/env python3
"""
sync_tags_from_files.py

Sync canonical_* fields from embedded file tags (metadata_json) and emit an M3U
for files missing important tags.

This is meant to pick up tag edits made by Lexicon (or other tag editors)
by copying BPM/Key/Genre/Energy/Danceability from file tags into canonical columns.
Genre values are normalized through the shared Beatport-hybrid taxonomy before
they are promoted into canonical fields.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tagslut.utils.db import DbResolutionError, resolve_cli_env_db_path
from tagslut.metadata.genre_normalization import default_genre_normalizer


def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _first_value(val: Any) -> str | None:
    if isinstance(val, list):
        if not val:
            return None
        val = val[0]
    if val is None:
        return None
    text = str(val).strip()
    return text or None


def _first_tag(meta: dict[str, Any], keys: Iterable[str]) -> str | None:
    for key in keys:
        if key in meta:
            text = _first_value(meta.get(key))
            if text:
                return text
    return None


def _first_comment(meta: dict[str, Any]) -> str | None:
    for key, val in meta.items():
        key_norm = str(key).lower()
        if key_norm in {"comment", "description"} or key_norm.startswith("comm"):
            text = _first_value(val)
            if text:
                return text
    return None


_COMMENT_SCORE_RE = re.compile(r"(\\d+(?:\\.\\d+)?)\\s*(energy|dance|danceability)", re.I)


def _parse_comment_scores(comment: str | None) -> tuple[float | None, float | None]:
    if not comment:
        return None, None
    energy: float | None = None
    dance: float | None = None
    for match in _COMMENT_SCORE_RE.finditer(comment):
        value = _parse_float(match.group(1))
        if value is None:
            continue
        label = match.group(2).lower()
        if label.startswith("energy"):
            energy = value
        elif label.startswith("dance"):
            dance = value
    return energy, dance


def _parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).strip())
    except Exception:
        return None


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (int, float)):
        return value <= 0
    text = str(value).strip().lower()
    return text in {"", "none", "unknown", "n/a"}


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Sync canonical BPM/Key/Genre/Energy/Danceability from file tags and emit M3U for missing tags."
    )
    ap.add_argument("--db", help="SQLite DB path")
    ap.add_argument(
        "--path",
        default=os.environ.get("MASTER_LIBRARY") or os.environ.get("LIBRARY_ROOT", "./library"),
        help="Root path filter (prefix match)",
    )
    ap.add_argument(
        "--missing-fields",
        default="bpm,key,genre,energy,danceability",
        help="Comma-separated canonical fields to flag as missing",
    )
    ap.add_argument("--m3u-out", default="", help="Output M3U path")
    ap.add_argument("--execute", action="store_true", help="Write updates to DB")
    ap.add_argument(
        "--read-files",
        action="store_true",
        help="Read tags directly from audio files instead of metadata_json",
    )
    args = ap.parse_args()

    purpose = "write" if args.execute else "read"
    try:
        db_resolution = resolve_cli_env_db_path(args.db, purpose=purpose, source_label="--db")
    except DbResolutionError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    db_path = db_resolution.path
    print(f"Resolved DB path: {db_path}")

    prefix = str(Path(args.path).expanduser().resolve())
    if not prefix.endswith("/"):
        prefix += "/"

    fields = [f.strip().lower() for f in args.missing_fields.split(",") if f.strip()]
    if not fields:
        fields = ["bpm", "key", "genre", "energy", "danceability"]

    default_root = Path(os.environ.get("MASTER_LIBRARY") or os.environ.get("LIBRARY_ROOT", "./library"))
    out_path = Path(args.m3u_out).expanduser().resolve() if args.m3u_out else (
        default_root / f"missing_tags_{_now_stamp()}.m3u"
    )

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    updated = 0
    skipped = 0
    missing_rows: list[tuple[str, list[str]]] = []

    try:
        if args.read_files:
            try:
                from mutagen import File as MutagenFile  # type: ignore
            except Exception as exc:
                raise SystemExit(f"mutagen is required for --read-files: {exc}") from exc

        if args.execute:
            conn.execute("BEGIN")

        rows = conn.execute(
            """
            SELECT path, metadata_json,
                   canonical_bpm, canonical_key, canonical_genre,
                   canonical_energy, canonical_danceability
            FROM files
            WHERE path LIKE ?
            """,
            (prefix + "%",),
        ).fetchall()

        for row in rows:
            path = row["path"]
            meta: dict[str, Any] | None = None
            if args.read_files:
                path_obj = Path(path)
                if not path_obj.exists():
                    skipped += 1
                    continue
                try:
                    audio = MutagenFile(str(path_obj), easy=False)  # type: ignore[misc]
                except Exception:
                    skipped += 1
                    continue
                if audio is None or not getattr(audio, "tags", None):
                    skipped += 1
                    continue
                meta = {str(k).lower(): v for k, v in audio.tags.items()}
            else:
                meta_json = row["metadata_json"]
                if not meta_json:
                    skipped += 1
                    continue
                try:
                    raw = json.loads(meta_json)
                except Exception:
                    skipped += 1
                    continue
                if not isinstance(raw, dict):
                    skipped += 1
                    continue
                meta = {str(k).lower(): v for k, v in raw.items()}

            bpm_raw = _first_tag(meta, ["bpm", "tbpm"])
            key_raw = _first_tag(meta, ["initialkey", "tkey", "key"])
            genre_raw = _first_tag(meta, ["genre", "tcon"])
            energy_raw = _first_tag(meta, ["1t_energy", "energy"])
            dance_raw = _first_tag(meta, ["1t_danceability", "danceability"])
            comment_raw = _first_comment(meta)

            bpm_val = _parse_float(bpm_raw)
            energy_val = _parse_float(energy_raw)
            dance_val = _parse_float(dance_raw)
            if energy_val is None or dance_val is None:
                c_energy, c_dance = _parse_comment_scores(comment_raw)
                if energy_val is None and c_energy is not None:
                    energy_val = c_energy
                if dance_val is None and c_dance is not None:
                    dance_val = c_dance

            updates: dict[str, Any] = {}
            if bpm_val is not None and bpm_val > 0:
                updates["canonical_bpm"] = bpm_val
            if key_raw:
                updates["canonical_key"] = key_raw
            if genre_raw:
                canonical_genre, canonical_sub_genre = default_genre_normalizer().normalize_pair(genre_raw, None)
                if canonical_genre:
                    updates["canonical_genre"] = canonical_genre
                if canonical_sub_genre:
                    updates["canonical_sub_genre"] = canonical_sub_genre
            if energy_val is not None and energy_val > 0:
                updates["canonical_energy"] = energy_val
            if dance_val is not None and dance_val > 0:
                updates["canonical_danceability"] = dance_val

            if updates and args.execute:
                set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
                values = list(updates.values()) + [path]
                conn.execute(f"UPDATE files SET {set_clause} WHERE path = ?", values)
                updated += 1
            elif updates:
                updated += 1
            else:
                skipped += 1

            # Missing tag tracking after updates
            row_values = {k: row[k] for k in row.keys()}
            row_values.update(updates)
            missing = []
            for f in fields:
                col = f"canonical_{f}"
                if col not in row_values:
                    continue
                if _is_missing(row_values[col]):
                    missing.append(f)
            if missing:
                missing_rows.append((path, missing))

        if args.execute:
            conn.commit()
    finally:
        conn.close()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        handle.write("#EXTM3U\n")
        handle.write(f"# Generated {datetime.now().isoformat(timespec='seconds')}\n")
        handle.write(f"# Missing fields: {', '.join(fields)}\n")
        for path, missing in missing_rows:
            handle.write(f"# missing: {', '.join(missing)}\n")
            handle.write(f"{path}\n")

    print(f"Updated rows: {updated}")
    print(f"Skipped rows: {skipped}")
    print(f"Missing-tag tracks: {len(missing_rows)}")
    print(f"M3U: {out_path}")
    if not args.execute:
        print("DRY-RUN: use --execute to write canonical updates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
