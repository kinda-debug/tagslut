"""Import Lexicon DJ library metadata and playlists into TAGSLUT_DB."""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _norm(s: str | None) -> str:
    """Normalise for matching: lower, strip, collapse whitespace."""
    if not s:
        return ""
    return re.sub(r"\s+", " ", s.lower().strip())


def _write_log(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    source: str,
    action: str,
    confidence: str = "",
    mp3_path: str = "",
    identity_id: int | None = None,
    lexicon_track_id: int | None = None,
    details: dict,
    jsonl_fh,
    dry_run: bool,
) -> None:
    ts = _now_iso()
    details_json = json.dumps(details)
    if not dry_run:
        conn.execute(
            """
            INSERT INTO reconcile_log
              (run_id, source, action, confidence, mp3_path, identity_id,
               lexicon_track_id, details_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, source, action, confidence, mp3_path, identity_id,
             lexicon_track_id, details_json),
        )
    entry = {
        "ts": ts,
        "run_id": run_id,
        "action": action,
        "path": mp3_path,
        "result": "ok",
        "details": {**details, "identity_id": identity_id,
                    "lexicon_track_id": lexicon_track_id},
    }
    jsonl_fh.write(json.dumps(entry) + "\n")


# ---------------------------------------------------------------------------
# Task 4 — import_lexicon_metadata()
# ---------------------------------------------------------------------------

# Lexicon DB columns → track_identity / dj_track_profile fields
_IDENTITY_FIELD_MAP = {
    # (lexicon_col, identity_col)
    "bpm": "canonical_bpm",
    "key": "canonical_key",
    "genre": "canonical_genre",
    "label": "canonical_label",
    "remixer": "canonical_mix_name",
}

_PROFILE_FIELD_MAP = {
    # (lexicon_col, profile_col)
    "energy": "energy",
    "rating": "rating",
    "lastPlayed": "last_played_at",
}


def import_lexicon_metadata(
    conn: sqlite3.Connection,
    *,
    lexicon_db_path: Path,
    run_id: str,
    log_dir: Path,
    prefer_lexicon: bool = False,
    dry_run: bool = True,
) -> dict:
    """Import Lexicon DJ library metadata into TAGSLUT_DB.

    For each active Lexicon track in DJ_LIBRARY or DJ_POOL_MANUAL_MP3:
    - Match to a track_identity (via mp3_asset.path, title+artist, or streamingId).
    - Write NULL fields in track_identity and dj_track_profile (or overwrite if
      prefer_lexicon=True).

    HARD RULES (enforced regardless of prefer_lexicon):
    - NEVER modify dj_tags_json.
    - NEVER touch a dj_track_profile row where set_role = 'peak'.
    - NEVER create a new dj_track_profile row.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = log_dir / f"reconcile_lexicon_{run_id}.jsonl"

    counters = {
        "matched": 0,
        "fields_written": 0,
        "skipped_non_null": 0,
        "unmatched": 0,
        "errors": 0,
    }

    try:
        conn.execute(f"ATTACH DATABASE '{lexicon_db_path}' AS lex")
    except sqlite3.OperationalError:
        pass  # Already attached

    lex_rows = conn.execute(
        """
        SELECT id, title, artist, location, bpm, key, energy, rating,
               lastPlayed, color, genre, label, remixer, extra1, extra2,
               streamingId, archived, incoming
        FROM lex.Track
        WHERE archived = 0 AND incoming = 0
          AND (location LIKE '/Volumes/MUSIC/DJ_LIBRARY/%'
               OR location LIKE '/Volumes/MUSIC/DJ_POOL_MANUAL_MP3/%')
        """
    ).fetchall()

    try:
        with open(jsonl_path, "a", encoding="utf-8") as jsonl_fh:
            for lex_row in lex_rows:
                try:
                    _process_lex_track(
                        conn=conn,
                        lex_row=lex_row,
                        run_id=run_id,
                        prefer_lexicon=prefer_lexicon,
                        counters=counters,
                        jsonl_fh=jsonl_fh,
                        dry_run=dry_run,
                    )
                except Exception as exc:
                    counters["errors"] += 1
                    jsonl_fh.write(
                        json.dumps({
                            "ts": _now_iso(), "run_id": run_id, "action": "error",
                            "path": str(lex_row[3] or ""), "result": "error",
                            "details": {"error": str(exc), "lexicon_id": lex_row[0]},
                        }) + "\n"
                    )

            if not dry_run:
                conn.commit()

    except Exception:
        if not dry_run:
            conn.rollback()
        raise
    finally:
        try:
            conn.execute("DETACH DATABASE lex")
        except Exception:
            pass

    return counters


def _process_lex_track(
    *,
    conn: sqlite3.Connection,
    lex_row,
    run_id: str,
    prefer_lexicon: bool,
    counters: dict,
    jsonl_fh,
    dry_run: bool,
) -> None:
    (
        lex_id, title, artist, location, bpm, key, energy, rating,
        last_played, color, genre, label, remixer, extra1, extra2,
        streaming_id, _archived, _incoming,
    ) = lex_row

    # --- Find identity_id ---
    identity_id: int | None = None

    # 1. path match
    if location:
        row = conn.execute(
            "SELECT identity_id FROM mp3_asset WHERE path = ? LIMIT 1",
            (location,),
        ).fetchone()
        if row:
            identity_id = row[0]

    # 2. title+artist normalised
    if identity_id is None and title and artist:
        key_norm = (_norm(artist), _norm(title))
        row = conn.execute(
            """
            SELECT id FROM track_identity
            WHERE lower(artist_norm) = ? AND lower(title_norm) = ?
            LIMIT 1
            """,
            key_norm,
        ).fetchone()
        if row:
            identity_id = row[0]

    # 3. streamingId
    if identity_id is None and streaming_id:
        sid = str(streaming_id).strip()
        for col in (
            "spotify_id", "beatport_id", "tidal_id", "qobuz_id",
            "apple_music_id", "deezer_id", "traxsource_id", "itunes_id",
        ):
            row = conn.execute(
                f"SELECT id FROM track_identity WHERE {col} = ? LIMIT 1", (sid,)
            ).fetchone()
            if row:
                identity_id = row[0]
                break

    if identity_id is None:
        counters["unmatched"] += 1
        return

    counters["matched"] += 1

    # Always set mp3_asset.lexicon_track_id
    if not dry_run and location:
        conn.execute(
            "UPDATE mp3_asset SET lexicon_track_id = ? WHERE path = ? AND lexicon_track_id IS NULL",
            (lex_id, location),
        )

    # --- Write identity fields ---
    id_fields = {
        "canonical_bpm": bpm,
        "canonical_key": key,
        "canonical_genre": genre,
        "canonical_label": label,
        "canonical_mix_name": remixer,
    }
    id_row = conn.execute(
        "SELECT canonical_bpm, canonical_key, canonical_genre, canonical_label, canonical_mix_name FROM track_identity WHERE id = ?",
        (identity_id,),
    ).fetchone()
    if id_row:
        current_vals = {
            "canonical_bpm": id_row[0],
            "canonical_key": id_row[1],
            "canonical_genre": id_row[2],
            "canonical_label": id_row[3],
            "canonical_mix_name": id_row[4],
        }
        for col, new_val in id_fields.items():
            if new_val is None:
                continue
            current = current_vals.get(col)
            if current is None or prefer_lexicon:
                if not dry_run:
                    conn.execute(
                        f"UPDATE track_identity SET {col} = ? WHERE id = ?",
                        (new_val, identity_id),
                    )
                _write_log(
                    conn, run_id=run_id, source="lexicon_import",
                    action="field_written", confidence="",
                    mp3_path=location or "", identity_id=identity_id,
                    lexicon_track_id=lex_id,
                    details={"field": col, "value": new_val},
                    jsonl_fh=jsonl_fh, dry_run=dry_run,
                )
                counters["fields_written"] += 1
            else:
                counters["skipped_non_null"] += 1

    # --- Write dj_track_profile fields ---
    # NEVER modify dj_tags_json; NEVER touch set_role='peak'; NEVER create new row
    profile_row = conn.execute(
        "SELECT identity_id, rating, energy, set_role, last_played_at, notes FROM dj_track_profile WHERE identity_id = ?",
        (identity_id,),
    ).fetchone()

    if profile_row:
        if profile_row[3] == "peak":
            # Hard rule: never touch peak rows
            return

        current_rating = profile_row[1]
        current_energy = profile_row[2]
        current_lp = profile_row[4]
        current_notes = profile_row[5] or ""

        profile_writes: list[tuple[str, object]] = []
        if energy is not None and (current_energy is None or prefer_lexicon):
            profile_writes.append(("energy", energy))
        if rating is not None and (current_rating is None or prefer_lexicon):
            profile_writes.append(("rating", rating))
        if last_played is not None and (current_lp is None or prefer_lexicon):
            profile_writes.append(("last_played_at", last_played))

        for col, val in profile_writes:
            if not dry_run:
                conn.execute(
                    f"UPDATE dj_track_profile SET {col} = ? WHERE identity_id = ?",
                    (val, identity_id),
                )
            _write_log(
                conn, run_id=run_id, source="lexicon_import",
                action="profile_field_written", confidence="",
                mp3_path=location or "", identity_id=identity_id,
                lexicon_track_id=lex_id,
                details={"field": col, "value": val},
                jsonl_fh=jsonl_fh, dry_run=dry_run,
            )
            counters["fields_written"] += 1

        # Append color and extra1/extra2 to notes (never dj_tags_json)
        notes_additions = []
        if color:
            tag = f"lexicon_color:{color}"
            if tag not in current_notes:
                notes_additions.append(tag)
        if extra1:
            tag = f"lexicon_extra1:{extra1}"
            if tag not in current_notes:
                notes_additions.append(tag)
        if extra2:
            tag = f"lexicon_extra2:{extra2}"
            if tag not in current_notes:
                notes_additions.append(tag)

        if notes_additions:
            sep = " | " if current_notes else ""
            new_notes = current_notes + sep + " | ".join(notes_additions)
            if not dry_run:
                conn.execute(
                    "UPDATE dj_track_profile SET notes = ? WHERE identity_id = ?",
                    (new_notes, identity_id),
                )
            _write_log(
                conn, run_id=run_id, source="lexicon_import",
                action="notes_appended", confidence="",
                mp3_path=location or "", identity_id=identity_id,
                lexicon_track_id=lex_id,
                details={"additions": notes_additions},
                jsonl_fh=jsonl_fh, dry_run=dry_run,
            )
            counters["fields_written"] += 1


# ---------------------------------------------------------------------------
# Task 5 — import_lexicon_playlists()
# ---------------------------------------------------------------------------

# Playlists to import (name → playlist_type, optional flags)
_PLAYLIST_EXACT: dict[str, dict] = {
    "tagged_lexicon": {"playlist_type": "curated"},
    "lexicon_manual_pool": {"playlist_type": "curated"},
    "happy": {"playlist_type": "mood"},
    "HAPPY_FROM_CSV_plus2": {"playlist_type": "mood"},
    "fucked": {"playlist_type": "admin", "status_override": "needs_review"},
}

_PLAYLIST_PREFIX: list[tuple[str, dict]] = [
    ("dj-This Is Kölsch-", {"playlist_type": "artist_set"}),
    ("Duplicate Tracks ", {"playlist_type": "admin", "is_duplicate": True}),
]

_SKIP_PREFIXES = (
    "Unnamed", "lexicon_missing_", "velocity_dj_", "lexicon_enrichable_",
    "lexicon_export_", "lexicon_newlyadded_", "lexicon-since-",
    "lexicon-tagged-batch_", "Text Matched", "roon-tidal-",
)

_SKIP_EXACT = frozenset({
    "no bpm", "diff", "ok", "e", "done", "yes", "new", "newnew", "nos",
    "g", "cvr", "cvryes", "antig", "k", "new23", "ROOT", "Dump", "Lexicon",
    "playlist", "missing_genre_lexicon_consolidated_20260226_134220",
    "Lexicon_tagged_tracks",
})


def _should_import_playlist(name: str, node_type: int, track_count: int) -> tuple[bool, dict]:
    """Return (should_import, metadata_dict) for a Lexicon playlist."""
    # Skip folder nodes and empty playlists
    if node_type == 1 or track_count == 0:
        return False, {}

    # Skip by exact name
    if name in _SKIP_EXACT:
        return False, {}

    # Skip by prefix
    for prefix in _SKIP_PREFIXES:
        if name.startswith(prefix):
            return False, {}

    # Check exact match
    if name in _PLAYLIST_EXACT:
        return True, _PLAYLIST_EXACT[name].copy()

    # Check prefixes
    for prefix, meta in _PLAYLIST_PREFIX:
        if name.startswith(prefix):
            return True, meta.copy()

    return False, {}


def import_lexicon_playlists(
    conn: sqlite3.Connection,
    *,
    lexicon_db_path: Path,
    run_id: str,
    log_dir: Path,
    dry_run: bool = True,
) -> dict:
    """Import selected Lexicon playlists into dj_playlist and dj_playlist_track.

    Only imports the specific playlists defined in the allow-list. Idempotent.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = log_dir / f"reconcile_playlists_{run_id}.jsonl"

    counters = {
        "playlists_imported": 0,
        "tracks_linked": 0,
        "skipped": 0,
    }

    try:
        conn.execute(f"ATTACH DATABASE '{lexicon_db_path}' AS lex")
    except sqlite3.OperationalError:
        pass  # Already attached

    # Fetch all playlists from Lexicon
    # Lexicon uses PlaylistNode / PlaylistItem or similar schema
    # Try common table names
    playlist_table = _detect_lexicon_playlist_table(conn)
    track_table = _detect_lexicon_track_in_playlist_table(conn)

    if not playlist_table or not track_table:
        # Cannot find Lexicon playlist tables; log and return
        return counters

    lex_playlists = conn.execute(
        f"SELECT id, name, type, (SELECT COUNT(*) FROM lex.{track_table} WHERE playlistId = p.id) AS track_count FROM lex.{playlist_table} p"
    ).fetchall()

    try:
        with open(jsonl_path, "a", encoding="utf-8") as jsonl_fh:
            for pl_row in lex_playlists:
                pl_id = pl_row[0]
                pl_name = pl_row[1] or ""
                pl_type_raw = pl_row[2] or 0
                pl_track_count = pl_row[3] or 0

                should, meta = _should_import_playlist(pl_name, int(pl_type_raw), int(pl_track_count))
                if not should:
                    counters["skipped"] += 1
                    continue

                playlist_type = meta.get("playlist_type", "standard")
                is_duplicate = meta.get("is_duplicate", False)
                status_override = meta.get("status_override", None)

                # Insert playlist
                if not dry_run:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO dj_playlist
                          (name, lexicon_playlist_id, playlist_type)
                        VALUES (?, ?, ?)
                        """,
                        (pl_name, pl_id, playlist_type),
                    )

                db_playlist = conn.execute(
                    "SELECT id FROM dj_playlist WHERE name = ? LIMIT 1",
                    (pl_name,),
                ).fetchone()

                if db_playlist is None and dry_run:
                    # Simulate an ID for dry-run logging
                    db_playlist_id = -1
                elif db_playlist:
                    db_playlist_id = db_playlist[0]
                else:
                    continue

                # Fetch tracks for this playlist
                track_rows = conn.execute(
                    f"SELECT trackId, position FROM lex.{track_table} WHERE playlistId = ? ORDER BY position ASC",
                    (pl_id,),
                ).fetchall()

                for tr_row in track_rows:
                    lex_track_id = tr_row[0]
                    ordinal = tr_row[1] or 0

                    # Find identity via mp3_asset.lexicon_track_id
                    identity_row = conn.execute(
                        "SELECT identity_id FROM mp3_asset WHERE lexicon_track_id = ? LIMIT 1",
                        (lex_track_id,),
                    ).fetchone()
                    if not identity_row:
                        continue
                    identity_id = identity_row[0]
                    if not identity_id:
                        continue

                    # Find or create dj_admission
                    admission_row = conn.execute(
                        "SELECT id FROM dj_admission WHERE identity_id = ? LIMIT 1",
                        (identity_id,),
                    ).fetchone()

                    if admission_row:
                        admission_id = admission_row[0]
                    elif not dry_run:
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO dj_admission
                              (identity_id, status, source)
                            VALUES (?, 'pending', 'lexicon_playlist_import')
                            """,
                            (identity_id,),
                        )
                        new_row = conn.execute(
                            "SELECT id FROM dj_admission WHERE identity_id = ? LIMIT 1",
                            (identity_id,),
                        ).fetchone()
                        admission_id = new_row[0] if new_row else None
                    else:
                        admission_id = None

                    if admission_id is None:
                        continue

                    # Status override (e.g. "fucked" → needs_review)
                    if status_override and not dry_run:
                        conn.execute(
                            "UPDATE dj_admission SET status = ? WHERE id = ? AND status != ?",
                            (status_override, admission_id, status_override),
                        )

                    # Duplicate flag
                    if is_duplicate and not dry_run:
                        adm_row = conn.execute(
                            "SELECT notes FROM dj_admission WHERE id = ?",
                            (admission_id,),
                        ).fetchone()
                        existing_notes = (adm_row[0] or "") if adm_row else ""
                        if "is_duplicate:true" not in existing_notes:
                            sep = " | " if existing_notes else ""
                            conn.execute(
                                "UPDATE dj_admission SET notes = ? WHERE id = ?",
                                (existing_notes + sep + "is_duplicate:true", admission_id),
                            )

                    # Insert playlist_track
                    if not dry_run:
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO dj_playlist_track
                              (playlist_id, dj_admission_id, ordinal)
                            VALUES (?, ?, ?)
                            """,
                            (db_playlist_id, admission_id, ordinal),
                        )

                    counters["tracks_linked"] += 1
                    _write_log(
                        conn, run_id=run_id, source="lexicon_playlists",
                        action="track_linked", confidence="",
                        mp3_path="", identity_id=identity_id,
                        lexicon_track_id=lex_track_id,
                        details={
                            "playlist": pl_name, "ordinal": ordinal,
                            "playlist_id": db_playlist_id,
                        },
                        jsonl_fh=jsonl_fh, dry_run=dry_run,
                    )

                counters["playlists_imported"] += 1
                _write_log(
                    conn, run_id=run_id, source="lexicon_playlists",
                    action="playlist_imported", confidence="",
                    mp3_path="", identity_id=None, lexicon_track_id=None,
                    details={"playlist": pl_name, "playlist_type": playlist_type},
                    jsonl_fh=jsonl_fh, dry_run=dry_run,
                )

            if not dry_run:
                conn.commit()

    except Exception:
        if not dry_run:
            conn.rollback()
        raise
    finally:
        try:
            conn.execute("DETACH DATABASE lex")
        except Exception:
            pass

    return counters


def _detect_lexicon_playlist_table(conn: sqlite3.Connection) -> str | None:
    """Detect the Lexicon playlist table name (varies by Lexicon version)."""
    for name in ("PlaylistNode", "Playlist", "PlaylistFolder"):
        try:
            conn.execute(f"SELECT id, name FROM lex.{name} LIMIT 1")
            return name
        except sqlite3.OperationalError:
            continue
    return None


def _detect_lexicon_track_in_playlist_table(conn: sqlite3.Connection) -> str | None:
    """Detect the Lexicon playlist-track join table name."""
    for name in ("PlaylistItem", "PlaylistTrack", "PlaylistEntry"):
        try:
            conn.execute(f"SELECT playlistId, trackId, position FROM lex.{name} LIMIT 1")
            return name
        except sqlite3.OperationalError:
            continue
    return None
