#!/usr/bin/env python3
"""Match duration_status='unknown' files in current DB to EPOCH_2026-02-08 DB
and apply duration refs (isrc/beatport/fuzzy) then recompute duration_status.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

import pandas as pd

from dedupe.cli.main import _duration_thresholds_from_config, _duration_check_version, _duration_status


@dataclass
class RefRow:
    path: str
    isrc: str | None
    beatport_id: str | None
    title: str | None
    artist: str | None
    album: str | None
    duration_ref_ms: int | None


def norm(s: str | None) -> str:
    if not s:
        return ""
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def score(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def iter_epoch_refs(conn: sqlite3.Connection) -> Iterable[RefRow]:
    cur = conn.execute(
        """
        SELECT path, canonical_isrc, beatport_id, canonical_title, canonical_artist,
               canonical_album, duration_measured_ms, canonical_duration, duration
        FROM files
        """
    )
    for row in cur:
        duration_ref_ms = None
        if row[6] is not None:
            duration_ref_ms = int(row[6])
        elif row[7] is not None:
            duration_ref_ms = int(round(float(row[7]) * 1000))
        elif row[8] is not None:
            duration_ref_ms = int(round(float(row[8]) * 1000))
        yield RefRow(
            path=row[0],
            isrc=row[1],
            beatport_id=row[2],
            title=row[3],
            artist=row[4],
            album=row[5],
            duration_ref_ms=duration_ref_ms,
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current-db", required=True)
    parser.add_argument("--epoch-db", required=True)
    parser.add_argument("--min-score", type=float, default=0.86)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    current_db = Path(args.current_db)
    epoch_db = Path(args.epoch_db)

    now_iso = datetime.now(timezone.utc).isoformat()
    ok_max_ms, warn_max_ms = _duration_thresholds_from_config()
    version = _duration_check_version(ok_max_ms, warn_max_ms)

    conn_cur = sqlite3.connect(str(current_db))
    conn_cur.row_factory = sqlite3.Row
    conn_epoch = sqlite3.connect(str(epoch_db))
    conn_epoch.row_factory = sqlite3.Row

    # Build indexes from epoch DB
    by_isrc: dict[str, int] = {}
    by_bp: dict[str, int] = {}
    by_key: dict[tuple[str, str, str], list[tuple[str, str, str, str, int]]] = {}

    for ref in iter_epoch_refs(conn_epoch):
        if ref.duration_ref_ms is None:
            continue
        if ref.isrc:
            by_isrc.setdefault(ref.isrc, ref.duration_ref_ms)
        if ref.beatport_id:
            by_bp.setdefault(str(ref.beatport_id), ref.duration_ref_ms)
        k = (norm(ref.title), norm(ref.artist), norm(ref.album))
        by_key.setdefault(k, []).append((ref.path, k[0], k[1], k[2], ref.duration_ref_ms))

    # Load unknowns from current DB
    cur = conn_cur.execute(
        """
        SELECT path, canonical_isrc, beatport_id, canonical_title, canonical_artist, canonical_album,
               duration_measured_ms
        FROM files
        WHERE duration_status = 'unknown'
        """
    )
    unknowns = [dict(row) for row in cur]

    results = []
    updated = 0
    matched_isrc = 0
    matched_bp = 0
    matched_fuzzy = 0
    no_match = 0

    for row in unknowns:
        path = row["path"]
        isrc = row["canonical_isrc"]
        bp = row["beatport_id"]
        title = row["canonical_title"]
        artist = row["canonical_artist"]
        album = row["canonical_album"]
        measured = row["duration_measured_ms"]

        ref_ms = None
        ref_source = None
        ref_track_id = None
        match_score = None
        match_type = None

        if isrc and isrc in by_isrc:
            ref_ms = by_isrc[isrc]
            ref_source = "epoch_2026-02-08:isrc"
            ref_track_id = isrc
            match_type = "isrc"
            matched_isrc += 1
        elif bp and str(bp) in by_bp:
            ref_ms = by_bp[str(bp)]
            ref_source = "epoch_2026-02-08:beatport"
            ref_track_id = str(bp)
            match_type = "beatport"
            matched_bp += 1
        else:
            # fuzzy on normalized title+artist+album
            nt = norm(title)
            na = norm(artist)
            nalb = norm(album)
            key = (nt, na, nalb)
            cands = by_key.get(key, [])
            best = None
            best_sc = 0.0
            # fallback: compare title+artist if exact key not present
            if not cands:
                # brute force on small heuristic: same first 8 chars of title+artist
                prefix = (nt[:8], na[:8])
                for (kt, ka, kalb), vals in by_key.items():
                    if kt[:8] == prefix[0] and ka[:8] == prefix[1]:
                        cands.extend(vals)
            for cpath, ct, ca, calb, dur in cands:
                s1 = score(nt + " " + na, ct + " " + ca)
                s2 = score(nalb, calb)
                sc = 0.7 * s1 + 0.3 * s2
                if sc > best_sc:
                    best_sc = sc
                    best = (cpath, dur)
            if best and best_sc >= args.min_score:
                ref_ms = best[1]
                ref_source = f"epoch_2026-02-08:fuzzy:{best_sc:.3f}"
                ref_track_id = None
                match_type = "fuzzy"
                match_score = best_sc
                matched_fuzzy += 1

        if ref_ms is None:
            no_match += 1
            results.append({
                "path": path,
                "match_type": None,
                "match_score": match_score,
                "ref_ms": None,
                "ref_source": None,
                "duration_measured_ms": measured,
            })
            continue

        # compute status
        delta_ms = measured - ref_ms if (measured is not None and ref_ms is not None) else None
        status = _duration_status(delta_ms, ok_max_ms, warn_max_ms)

        results.append({
            "path": path,
            "match_type": match_type,
            "match_score": match_score,
            "ref_ms": ref_ms,
            "ref_source": ref_source,
            "duration_measured_ms": measured,
            "duration_delta_ms": delta_ms,
            "duration_status": status,
        })

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
            if ref_track_id:
                conn_cur.execute(
                    """
                    INSERT OR REPLACE INTO track_duration_refs
                        (ref_id, ref_type, duration_ref_ms, ref_source, ref_updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (ref_track_id, "id", ref_ms, ref_source, now_iso),
                )
            updated += 1

    if args.execute:
        conn_cur.commit()

    conn_cur.close()
    conn_epoch.close()

    outdir = Path('/Users/georgeskhawam/Projects/dedupe/output/spreadsheet')
    outdir.mkdir(parents=True, exist_ok=True)
    report = outdir / 'ALL_unknown_matched_to_EPOCH_2026-02-08.xlsx'
    df = pd.DataFrame(results)
    with pd.ExcelWriter(report, engine='openpyxl') as w:
        df.to_excel(w, index=False, sheet_name='matches')
        df[df['match_type'].isin(['isrc','beatport'])].to_excel(w, index=False, sheet_name='id_matches')
        df[df['match_type']=='fuzzy'].to_excel(w, index=False, sheet_name='fuzzy_matches')
        df[df['match_type'].isna()].to_excel(w, index=False, sheet_name='no_match')

    stats = {
        'unknown_total': len(unknowns),
        'matched_isrc': matched_isrc,
        'matched_beatport': matched_bp,
        'matched_fuzzy': matched_fuzzy,
        'no_match': no_match,
        'updated': updated,
        'report': str(report),
    }
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
