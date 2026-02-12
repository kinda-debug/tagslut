#!/usr/bin/env python3
"""Backfill canonical metadata from epoch 2026-02-08 into current DB.

Matches on ISRC, Beatport ID, and exact normalized title+artist+album.
Only fills fields that are NULL/empty in the target DB.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple


CANON_FIELDS = [
    "canonical_title",
    "canonical_artist",
    "canonical_album",
    "canonical_isrc",
    "canonical_duration",
    "canonical_duration_source",
    "canonical_year",
    "canonical_release_date",
    "canonical_bpm",
    "canonical_key",
    "canonical_genre",
    "canonical_sub_genre",
    "canonical_label",
    "canonical_catalog_number",
    "canonical_mix_name",
    "canonical_explicit",
    "canonical_energy",
    "canonical_danceability",
    "canonical_valence",
    "canonical_acousticness",
    "canonical_instrumentalness",
    "canonical_loudness",
    "canonical_album_art_url",
    "spotify_id",
    "beatport_id",
    "tidal_id",
    "qobuz_id",
    "itunes_id",
    "metadata_health",
    "metadata_health_reason",
]


@dataclass(frozen=True)
class RefRow:
    canonical_isrc: str | None
    beatport_id: str | None
    title: str | None
    artist: str | None
    album: str | None
    metadata_json: str | None
    fields: Dict[str, Any]


def norm_text(val: str | None) -> str:
    if not val:
        return ""
    return " ".join(val.strip().lower().split())


def load_json(val: str | None) -> Dict[str, Any]:
    if not val:
        return {}
    try:
        return json.loads(val)
    except Exception:
        return {}


def get_from_metadata(meta: Dict[str, Any], keys: Iterable[str]) -> str | None:
    for k in keys:
        v = meta.get(k)
        if v:
            return str(v)
    return None


def build_refs(conn: sqlite3.Connection) -> Tuple[dict, dict, dict]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            canonical_isrc,
            beatport_id,
            canonical_title,
            canonical_artist,
            canonical_album,
            metadata_json,
            """
        + ",".join(CANON_FIELDS)
        + " FROM files"
    )

    isrc_index: Dict[str, RefRow] = {}
    beatport_index: Dict[str, RefRow] = {}
    exact_index: Dict[str, RefRow] = {}

    for row in cur.fetchall():
        row = list(row)
        canonical_isrc = row[0]
        beatport_id = row[1]
        title = row[2]
        artist = row[3]
        album = row[4]
        metadata_json = row[5]
        meta = load_json(metadata_json)

        # Fallbacks from metadata_json
        if not canonical_isrc:
            canonical_isrc = get_from_metadata(meta, ["isrc", "ISRC", "canonical_isrc"])
        if not beatport_id:
            beatport_id = get_from_metadata(meta, ["beatport_id", "beatport_track_id", "beatportId"])
        if not title:
            title = get_from_metadata(meta, ["title", "track_title", "name"])
        if not artist:
            artist = get_from_metadata(meta, ["artist", "artists", "track_artist", "album_artist"])
        if not album:
            album = get_from_metadata(meta, ["album", "release", "album_title"])

        fields = {k: row[6 + i] for i, k in enumerate(CANON_FIELDS)}
        ref = RefRow(canonical_isrc, beatport_id, title, artist, album, metadata_json, fields)

        if canonical_isrc:
            isrc_index.setdefault(canonical_isrc, ref)
        if beatport_id:
            beatport_index.setdefault(str(beatport_id), ref)
        key = "|".join([norm_text(title), norm_text(artist), norm_text(album)])
        if key.strip("|"):
            exact_index.setdefault(key, ref)

    return isrc_index, beatport_index, exact_index


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--epoch-db", required=True)
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    target = sqlite3.connect(args.db)
    target.row_factory = sqlite3.Row
    epoch = sqlite3.connect(args.epoch_db)
    epoch.row_factory = sqlite3.Row

    isrc_index, beatport_index, exact_index = build_refs(epoch)

    cur = target.cursor()
    cur.execute(
        """
        SELECT path, canonical_isrc, beatport_id,
               canonical_title, canonical_artist, canonical_album,
               metadata_json, """
        + ",".join(CANON_FIELDS)
        + " FROM files"
    )

    updates = 0
    matched_isrc = 0
    matched_beatport = 0
    matched_exact = 0

    for row in cur.fetchall():
        row = dict(row)
        meta = load_json(row.get("metadata_json"))

        isrc = row.get("canonical_isrc") or get_from_metadata(meta, ["isrc", "ISRC", "canonical_isrc"])
        beatport_id = row.get("beatport_id") or get_from_metadata(meta, ["beatport_id", "beatport_track_id", "beatportId"])
        title = row.get("canonical_title") or get_from_metadata(meta, ["title", "track_title", "name"])
        artist = row.get("canonical_artist") or get_from_metadata(meta, ["artist", "artists", "track_artist", "album_artist"])
        album = row.get("canonical_album") or get_from_metadata(meta, ["album", "release", "album_title"])

        ref = None
        if isrc and isrc in isrc_index:
            ref = isrc_index[isrc]
            matched_isrc += 1
        elif beatport_id and str(beatport_id) in beatport_index:
            ref = beatport_index[str(beatport_id)]
            matched_beatport += 1
        else:
            key = "|".join([norm_text(title), norm_text(artist), norm_text(album)])
            if key in exact_index:
                ref = exact_index[key]
                matched_exact += 1

        if not ref:
            continue

        # Fill only empty fields
        updates_needed = {}
        for field in CANON_FIELDS:
            if row.get(field) in (None, "") and ref.fields.get(field) not in (None, ""):
                updates_needed[field] = ref.fields.get(field)

        if updates_needed:
            updates += 1
            if args.execute:
                set_clause = ", ".join([f"{k} = ?" for k in updates_needed])
                values = list(updates_needed.values())
                values.append(row["path"])
                target.execute(
                    f"UPDATE files SET {set_clause} WHERE path = ?",
                    values,
                )

    if args.execute:
        target.commit()

    target.close()
    epoch.close()

    print("matched_isrc", matched_isrc)
    print("matched_beatport", matched_beatport)
    print("matched_exact", matched_exact)
    print("rows_updated", updates)


if __name__ == "__main__":
    main()
