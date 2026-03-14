"""lexicon_backfill.py

Joins Lexicon DJ's Track table against tagslut's track_identity to backfill:
  - energy, danceability, happiness, popularity  → canonical_payload_json
  - tempomarkers                                  → reconcile_log (summary per track)

Match strategy (tried in order, first hit wins):
  1. beatport_id  — track_identity.beatport_id == Lexicon streamingId WHERE streamingService='beatport'
  2. spotify_id   — track_identity.spotify_id  == Lexicon streamingId WHERE streamingService='spotify'
  3. text         — _norm(artist) + _norm(title) exact match

All decisions are appended to reconcile_log with run_id, confidence, and details_json.
track_identity.canonical_payload_json is updated only for fields that are currently NULL/0.

Usage:
    python -m tagslut.dj.reconcile.lexicon_backfill [--dry-run] [--run-id RUN_ID]
    python -m tagslut.dj.reconcile.lexicon_backfill --db /path/to/music_v3.db --lex /Volumes/MUSIC/lexicondj.db
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("tagslut.reconcile.lexicon_backfill")


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def _norm(text: str | None) -> str:
    """Lowercase, strip accents, collapse whitespace, strip non-word chars."""
    if not text:
        return ""
    t = unicodedata.normalize("NFD", str(text))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = t.lower()
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class LexTrack:
    lex_id: int
    title: str
    artist: str
    bpm: float | None
    key: str | None
    energy: int
    danceability: int
    happiness: int
    popularity: int
    streaming_service: str | None
    streaming_id: str | None
    tempomarkers: list[tuple[float, float]] = field(default_factory=list)


@dataclass
class MatchResult:
    identity_id: int
    lex_track: LexTrack
    confidence: str   # 'high' | 'medium' | 'low'
    method: str       # 'beatport_id' | 'spotify_id' | 'text'


# ---------------------------------------------------------------------------
# Lexicon loading
# ---------------------------------------------------------------------------

def _load_lex_tracks(lex_conn: sqlite3.Connection) -> list[LexTrack]:
    rows = lex_conn.execute(
        """
        SELECT id, title, artist, bpm, key,
               energy, danceability, happiness, popularity,
               streamingService, streamingId
        FROM Track
        """
    ).fetchall()
    return [
        LexTrack(
            lex_id=r[0],
            title=r[1] or "",
            artist=r[2] or "",
            bpm=float(r[3]) if r[3] else None,
            key=r[4] or None,
            energy=int(r[5] or 0),
            danceability=int(r[6] or 0),
            happiness=int(r[7] or 0),
            popularity=int(r[8] or 0),
            streaming_service=r[9] or None,
            streaming_id=r[10] or None,
        )
        for r in rows
    ]


def _load_tempomarkers(
    lex_conn: sqlite3.Connection, lex_ids: list[int]
) -> dict[int, list[tuple[float, float]]]:
    if not lex_ids:
        return {}
    placeholders = ",".join("?" * len(lex_ids))
    rows = lex_conn.execute(
        f"SELECT trackId, startTime, bpm FROM Tempomarker "
        f"WHERE trackId IN ({placeholders}) ORDER BY trackId, startTime",
        lex_ids,
    ).fetchall()
    result: dict[int, list[tuple[float, float]]] = {}
    for r in rows:
        result.setdefault(r[0], []).append((float(r[1]), float(r[2])))
    return result


# ---------------------------------------------------------------------------
# Index building
# ---------------------------------------------------------------------------

def _build_indexes(
    tracks: list[LexTrack],
) -> tuple[dict[str, LexTrack], dict[str, LexTrack], dict[str, LexTrack]]:
    beatport: dict[str, LexTrack] = {}
    spotify:  dict[str, LexTrack] = {}
    text:     dict[str, LexTrack] = {}

    for t in tracks:
        svc = (t.streaming_service or "").lower().strip()
        sid = str(t.streaming_id or "").strip()
        if sid:
            if svc == "beatport":
                beatport[sid] = t
            elif svc == "spotify":
                spotify[sid] = t

        key = f"{_norm(t.artist)}|{_norm(t.title)}"
        if key and key not in text:   # first occurrence wins on duplicates
            text[key] = t

    return beatport, spotify, text


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def _match(
    row: sqlite3.Row,
    beatport_idx: dict[str, LexTrack],
    spotify_idx:  dict[str, LexTrack],
    text_idx:     dict[str, LexTrack],
) -> MatchResult | None:
    iid = row["id"]

    bp = str(row["beatport_id"] or "").strip()
    if bp and bp in beatport_idx:
        lt = beatport_idx[bp]
        return MatchResult(iid, lt, "high", "beatport_id")

    sp = str(row["spotify_id"] or "").strip()
    if sp and sp in spotify_idx:
        lt = spotify_idx[sp]
        return MatchResult(iid, lt, "high", "spotify_id")

    an = str(row["artist_norm"] or "").strip()
    tn = str(row["title_norm"]  or "").strip()
    if an and tn:
        key = f"{_norm(an)}|{_norm(tn)}"
        if key in text_idx:
            lt = text_idx[key]
            conf = "medium" if (lt.energy > 0 or lt.bpm) else "low"
            return MatchResult(iid, lt, conf, "text")

    return None


# ---------------------------------------------------------------------------
# Payload merge
# ---------------------------------------------------------------------------

def _merge_payload(existing_json: str | None, updates: dict[str, Any]) -> str:
    try:
        payload: dict[str, Any] = json.loads(existing_json) if existing_json else {}
    except (json.JSONDecodeError, TypeError):
        payload = {}
    payload.update(updates)
    return json.dumps(payload, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Main backfill
# ---------------------------------------------------------------------------

def run_backfill(
    db_path:  Path | str,
    lex_path: Path | str,
    *,
    run_id:  str | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    db_path  = Path(db_path)
    lex_path = Path(lex_path)
    run_id   = run_id or uuid.uuid4().hex
    now      = datetime.now(timezone.utc).isoformat(timespec="seconds")

    stats: dict[str, int] = dict(
        identities_scanned=0,
        matched_beatport=0, matched_spotify=0, matched_text=0,
        unmatched=0, payload_updated=0,
        tempomarkers_logged=0, log_rows_written=0,
    )

    logger.info("run_id=%s  db=%s  lex=%s  dry_run=%s", run_id, db_path, lex_path, dry_run)

    lex_conn = sqlite3.connect(f"file:{lex_path}?mode=ro", uri=True)
    lex_conn.row_factory = sqlite3.Row

    lex_tracks = _load_lex_tracks(lex_conn)
    logger.info("Loaded %d Lexicon tracks", len(lex_tracks))

    beatport_idx, spotify_idx, text_idx = _build_indexes(lex_tracks)
    logger.info("Index sizes — beatport:%d  spotify:%d  text:%d",
                len(beatport_idx), len(spotify_idx), len(text_idx))

    v3_conn = sqlite3.connect(db_path)
    v3_conn.row_factory = sqlite3.Row
    v3_conn.execute("PRAGMA journal_mode=WAL")
    v3_conn.execute("PRAGMA foreign_keys=ON")

    # Detect available columns on track_identity
    ti_cols = {r[1] for r in v3_conn.execute("PRAGMA table_info(track_identity)").fetchall()}
    has_lexicon_col = "lexicon_track_id" in ti_cols

    identity_rows = v3_conn.execute(
        "SELECT id, beatport_id, spotify_id, artist_norm, title_norm, "
        "       canonical_bpm, canonical_key, canonical_payload_json "
        "FROM track_identity"
    ).fetchall()

    log_batch:    list[tuple] = []
    update_batch: list[tuple] = []
    matched_lex_ids: list[int] = []

    for row in identity_rows:
        stats["identities_scanned"] += 1
        m = _match(row, beatport_idx, spotify_idx, text_idx)

        if m is None:
            stats["unmatched"] += 1
            continue

        lt = m.lex_track
        if   m.method == "beatport_id": stats["matched_beatport"] += 1
        elif m.method == "spotify_id":  stats["matched_spotify"]  += 1
        else:                           stats["matched_text"]     += 1

        matched_lex_ids.append(lt.lex_id)

        # Only write fields not already present
        payload_updates: dict[str, Any] = {}
        if lt.energy      > 0: payload_updates["lexicon_energy"]       = lt.energy
        if lt.danceability > 0: payload_updates["lexicon_danceability"] = lt.danceability
        if lt.happiness   > 0: payload_updates["lexicon_happiness"]    = lt.happiness
        if lt.popularity  > 0: payload_updates["lexicon_popularity"]   = lt.popularity
        if lt.bpm and not row["canonical_bpm"]:  payload_updates["lexicon_bpm"] = lt.bpm
        if lt.key and not row["canonical_key"]:  payload_updates["lexicon_key"] = lt.key
        payload_updates["lexicon_track_id"] = lt.lex_id

        new_payload = _merge_payload(row["canonical_payload_json"], payload_updates)

        log_batch.append((
            run_id, now, "lexicondj", "backfill_metadata",
            m.confidence, None,           # mp3_path
            m.identity_id, lt.lex_id,
            json.dumps({
                "method": m.method, "lex_id": lt.lex_id,
                "lex_artist": lt.artist, "lex_title": lt.title,
                "payload_keys_set": list(payload_updates.keys()),
            }, ensure_ascii=False),
        ))
        stats["log_rows_written"] += 1

        if payload_updates:
            update_batch.append((new_payload, lt.lex_id, m.identity_id))
            stats["payload_updated"] += 1

    # Tempomarkers for matched tracks
    tempo_map = _load_tempomarkers(lex_conn, list(set(matched_lex_ids)))
    lex_conn.close()

    for lex_id, markers in tempo_map.items():
        if not markers:
            continue
        log_batch.append((
            run_id, now, "lexicondj", "backfill_tempomarkers",
            "high", None, None, lex_id,
            json.dumps({
                "count": len(markers),
                "first_bpm": markers[0][1],
                "markers_preview": markers[:5],
            }, ensure_ascii=False),
        ))
        stats["tempomarkers_logged"] += len(markers)
        stats["log_rows_written"]    += 1

    _print_summary(stats, dry_run=dry_run)

    if dry_run:
        logger.info("[DRY RUN] No writes performed.")
        v3_conn.close()
        return stats

    with v3_conn:
        v3_conn.executemany(
            """INSERT INTO reconcile_log
               (run_id, event_time, source, action, confidence,
                mp3_path, identity_id, lexicon_track_id, details_json)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            log_batch,
        )

        if has_lexicon_col:
            v3_conn.executemany(
                """UPDATE track_identity
                   SET canonical_payload_json = ?,
                       lexicon_track_id       = COALESCE(lexicon_track_id, ?),
                       updated_at             = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                update_batch,
            )
        else:
            v3_conn.executemany(
                """UPDATE track_identity
                   SET canonical_payload_json = ?,
                       updated_at             = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                [(p, iid) for p, _, iid in update_batch],
            )

    v3_conn.close()
    logger.info("Done. run_id=%s", run_id)
    return stats


# ---------------------------------------------------------------------------
# Summary printer
# ---------------------------------------------------------------------------

def _print_summary(stats: dict[str, int], *, dry_run: bool = False) -> None:
    total = stats["matched_beatport"] + stats["matched_spotify"] + stats["matched_text"]
    scanned = max(stats["identities_scanned"], 1)
    tag = "  [DRY RUN — no writes]" if dry_run else ""
    print(f"""
╔══════════════════════════════════════════════╗
║      Lexicon → tagslut Backfill{tag:<14}║
╠══════════════════════════════════════════════╣
  Identities scanned   : {stats['identities_scanned']:>7}
  Matched (beatport)   : {stats['matched_beatport']:>7}
  Matched (spotify)    : {stats['matched_spotify']:>7}
  Matched (text)       : {stats['matched_text']:>7}
  Total matched        : {total:>7}   ({total/scanned*100:.1f}%)
  Unmatched            : {stats['unmatched']:>7}
  Payload rows updated : {stats['payload_updated']:>7}
  Tempomarkers logged  : {stats['tempomarkers_logged']:>7}
  reconcile_log rows   : {stats['log_rows_written']:>7}
╚══════════════════════════════════════════════╝
""")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )
    p = argparse.ArgumentParser(description="Backfill Lexicon DJ metadata into music_v3.db")
    p.add_argument("--db",      default="/Users/georgeskhawam/Projects/tagslut_db/EPOCH_2026-03-04/music_v3.db")
    p.add_argument("--lex",     default="/Volumes/MUSIC/lexicondj.db")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--run-id",  default=None)
    args = p.parse_args()
    run_backfill(db_path=args.db, lex_path=args.lex,
                 run_id=args.run_id, dry_run=args.dry_run)


if __name__ == "__main__":
    _cli()
