#!/usr/bin/env python3
"""Match duration_status='unknown' in current DB to EPOCH_2026-02-08 DB.

Match order:
1) ISRC
2) Beatport ID
3) Normalized exact title+artist+album
4) Fuzzy within prefix bucket (title+artist)

Updates duration_ref_ms/source/track_id and duration_status in current DB.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

from tagslut.cli.main import _duration_thresholds_from_config, _duration_check_version, _duration_status


def norm(s: str | None) -> str:
    if not s:
        return ""
    if isinstance(s, (list, tuple)):
        s = s[0] if s else ""
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def norm_id(value: str | None) -> str | None:
    if not value:
        return None
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    if value is None:
        return None
    return str(value).strip() or None


def score(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current-db", required=True)
    parser.add_argument("--epoch-db", required=True)
    parser.add_argument("--min-score", type=float, default=0.90)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    current_db = Path(args.current_db)
    epoch_db = Path(args.epoch_db)

    ok_max_ms, warn_max_ms = _duration_thresholds_from_config()
    version = _duration_check_version(ok_max_ms, warn_max_ms)
    now_iso = datetime.now(timezone.utc).isoformat()

    conn_cur = sqlite3.connect(str(current_db))
    conn_cur.row_factory = sqlite3.Row
    conn_epoch = sqlite3.connect(str(epoch_db))
    conn_epoch.row_factory = sqlite3.Row

    # Build reference indexes from epoch DB
    by_isrc: dict[str, int] = {}
    by_bp: dict[str, int] = {}
    by_exact: dict[tuple[str, str, str], int] = {}
    by_bucket: dict[str, list[tuple[str, str, str, int]]] = {}

    cur = conn_epoch.execute(
        """
        SELECT canonical_isrc, beatport_id, canonical_title, canonical_artist, canonical_album,
               duration_measured_ms, canonical_duration, duration, metadata_json
        FROM files
        """
    )
    for row in cur:
        duration_ref_ms = None
        if row[5] is not None:
            duration_ref_ms = int(row[5])
        elif row[6] is not None:
            duration_ref_ms = int(round(float(row[6]) * 1000))
        elif row[7] is not None:
            duration_ref_ms = int(round(float(row[7]) * 1000))
        if duration_ref_ms is None:
            continue

        isrc = norm_id(row[0])
        bp = norm_id(row[1])
        title = row[2]
        artist = row[3]
        album = row[4]
        metadata_json = row[8]
        if metadata_json:
            try:
                md = json.loads(metadata_json)
                isrc = isrc or norm_id(md.get("isrc") or md.get("ISRC"))
                bp = bp or norm_id(md.get("beatport_track_id") or md.get("BEATPORT_TRACK_ID"))
                title = title or md.get("title")
                artist = artist or md.get("artist") or md.get("albumartist")
                album = album or md.get("album")
            except Exception:
                pass
        title = norm(title)
        artist = norm(artist)
        album = norm(album)

        if isrc:
            by_isrc.setdefault(isrc, duration_ref_ms)
        if bp:
            by_bp.setdefault(str(bp), duration_ref_ms)

        key = (title, artist, album)
        if title and artist:
            by_exact.setdefault(key, duration_ref_ms)
            bucket = (title[:4] + "_" + artist[:4]).strip("_")
            by_bucket.setdefault(bucket, []).append((title, artist, album, duration_ref_ms))

    # Load unknowns from current DB
    cur = conn_cur.execute(
        """
        SELECT path, canonical_isrc, beatport_id, canonical_title, canonical_artist, canonical_album,
               duration_measured_ms, metadata_json
        FROM files
        WHERE duration_status = 'unknown'
        """
    )
    unknowns = [dict(row) for row in cur]

    matched_isrc = 0
    matched_bp = 0
    matched_exact = 0
    matched_fuzzy = 0
    no_match = 0
    updated = 0

    for row in unknowns:
        path = row["path"]
        isrc = norm_id(row["canonical_isrc"])
        bp = norm_id(row["beatport_id"])
        title = row["canonical_title"]
        artist = row["canonical_artist"]
        album = row["canonical_album"]
        metadata_json = row["metadata_json"]
        if metadata_json:
            try:
                md = json.loads(metadata_json)
                isrc = isrc or norm_id(md.get("isrc") or md.get("ISRC"))
                bp = bp or norm_id(md.get("beatport_track_id") or md.get("BEATPORT_TRACK_ID"))
                title = title or md.get("title")
                artist = artist or md.get("artist") or md.get("albumartist")
                album = album or md.get("album")
            except Exception:
                pass
        title = norm(title)
        artist = norm(artist)
        album = norm(album)
        measured = row["duration_measured_ms"]

        ref_ms = None
        ref_source = None
        ref_track_id = None

        if isrc and isrc in by_isrc:
            ref_ms = by_isrc[isrc]
            ref_source = "epoch_2026-02-08:isrc"
            ref_track_id = isrc
            matched_isrc += 1
        elif bp and str(bp) in by_bp:
            ref_ms = by_bp[str(bp)]
            ref_source = "epoch_2026-02-08:beatport"
            ref_track_id = str(bp)
            matched_bp += 1
        else:
            key = (title, artist, album)
            if key in by_exact:
                ref_ms = by_exact[key]
                ref_source = "epoch_2026-02-08:exact"
                matched_exact += 1
            else:
                # fuzzy within bucket
                bucket = (title[:4] + "_" + artist[:4]).strip("_")
                cands = by_bucket.get(bucket, [])
                best_sc = 0.0
                best_ms = None
                for ct, ca, calb, dur in cands:
                    s1 = score(title + " " + artist, ct + " " + ca)
                    s2 = score(album, calb)
                    sc = 0.7 * s1 + 0.3 * s2
                    if sc > best_sc:
                        best_sc = sc
                        best_ms = dur
                if best_ms is not None and best_sc >= args.min_score:
                    ref_ms = best_ms
                    ref_source = f"epoch_2026-02-08:fuzzy:{best_sc:.3f}"
                    matched_fuzzy += 1

        if ref_ms is None:
            no_match += 1
            continue

        delta_ms = measured - ref_ms if (measured is not None and ref_ms is not None) else None
        status = _duration_status(delta_ms, ok_max_ms, warn_max_ms)

        if args.execute:
            conn_cur.execute(
                """
                UPDATE files SET
                    duration_ref_ms = ?,
                    duration_ref_source = ?,
                    duration_ref_track_id = ?,
                    duration_ref_updated_at = ?,
                    duration_delta_ms = ?,
                    duration_status = ?,
                    duration_check_version = ?
                WHERE path = ?
                """,
                (
                    ref_ms,
                    ref_source,
                    ref_track_id,
                    now_iso,
                    delta_ms,
                    status,
                    version,
                    path,
                ),
            )
        updated += 1

    if args.execute:
        conn_cur.commit()

    conn_cur.close()
    conn_epoch.close()

    print(
        "\n".join(
            [
                f"unknown_total={len(unknowns)}",
                f"matched_isrc={matched_isrc}",
                f"matched_beatport={matched_bp}",
                f"matched_exact={matched_exact}",
                f"matched_fuzzy={matched_fuzzy}",
                f"no_match={no_match}",
                f"updated={updated}",
            ]
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
