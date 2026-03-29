"""Scan the MASTER_LIBRARY FLAC tree and register asset_file + asset_link rows."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _norm(s: str | None) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", s.lower().strip())


def _read_flac_tags(path: Path) -> dict:
    """Read FLAC metadata via mutagen. Returns a flat dict of tag values."""
    try:
        from mutagen.flac import FLAC  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError("mutagen is required — pip install mutagen") from exc

    info: dict = {
        "isrc": None,
        "title": None,
        "artist": None,
        "album": None,
        "year": None,
        "genre": None,
        "label": None,
        "bpm": None,
        "key": None,
        "duration_s": None,
    }

    try:
        audio = FLAC(str(path))
        info["duration_s"] = round(float(audio.info.length), 3) if audio.info and audio.info.length else None

        def _first(tag: str) -> str | None:
            vals = audio.get(tag.upper()) or audio.get(tag.lower())
            if vals:
                v = str(vals[0]).strip()
                return v if v else None
            return None

        info["isrc"] = _first("ISRC")
        info["title"] = _first("TITLE")
        info["artist"] = _first("ARTIST")
        info["album"] = _first("ALBUM")
        info["year"] = _first("DATE") or _first("YEAR")
        info["genre"] = _first("GENRE")
        info["label"] = _first("LABEL") or _first("ORGANIZATION")
        info["bpm"] = _first("BPM") or _first("TBPM")
        info["key"] = _first("KEY") or _first("INITIALKEY")

    except Exception:
        pass

    return info


def scan_master_library(
    conn: sqlite3.Connection,
    *,
    master_root: Path,
    run_id: str,
    log_dir: Path,
    dry_run: bool = True,
) -> dict:
    """Scan the MASTER_LIBRARY tree, register asset_file rows and link identities.

    Idempotent: paths already in asset_file are skipped.
    Prints progress every 1,000 files.
    Logs every decision to reconcile_log and a JSONL file.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = log_dir / f"reconcile_master_{run_id}.jsonl"

    counters = {
        "assets_inserted": 0,
        "matched_existing": 0,
        "stubs_created": 0,
        "skipped_existing": 0,
        "errors": 0,
    }

    # Pre-build identity lookup maps
    _isrc_map: dict[str, int] = {}
    _norm_map: dict[tuple[str, str], int] = {}
    for id_row in conn.execute(
        "SELECT id, isrc, artist_norm, title_norm FROM track_identity WHERE merged_into_id IS NULL"
    ).fetchall():
        iid = id_row[0]
        if id_row[1]:
            _isrc_map[id_row[1].strip()] = iid
        a_n = _norm(id_row[2])
        t_n = _norm(id_row[3])
        if a_n and t_n:
            _norm_map[(a_n, t_n)] = iid

    all_flacs = sorted(master_root.rglob("*.flac"))
    total = len(all_flacs)

    try:
        with open(jsonl_path, "a", encoding="utf-8") as jsonl_fh:
            for idx, flac_path in enumerate(all_flacs, start=1):
                if idx % 1000 == 0:
                    print(f"[MASTER SCAN] {idx}/{total}...")

                path_str = str(flac_path)
                try:
                    # Idempotency check
                    existing = conn.execute(
                        "SELECT id FROM asset_file WHERE path = ? LIMIT 1",
                        (path_str,),
                    ).fetchone()
                    if existing:
                        counters["skipped_existing"] += 1
                        continue

                    # File stats
                    stat = flac_path.stat()
                    size_bytes = stat.st_size
                    mtime = datetime.fromtimestamp(
                        stat.st_mtime, tz=timezone.utc
                    ).isoformat()
                    sha256 = _compute_sha256(flac_path)
                    tags = _read_flac_tags(flac_path)

                    asset_id: int | None = None
                    if not dry_run:
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO asset_file
                              (path, zone, library, size_bytes, mtime,
                               content_sha256, duration_s, first_seen_at)
                            VALUES (?, 'MASTER_LIBRARY', 'master', ?, ?, ?, ?, datetime('now'))
                            """,
                            (path_str, size_bytes, mtime,
                             sha256, tags["duration_s"]),
                        )
                        row = conn.execute(
                            "SELECT id FROM asset_file WHERE path = ? LIMIT 1",
                            (path_str,),
                        ).fetchone()
                        asset_id = row[0] if row else None

                    counters["assets_inserted"] += 1

                    # Identity matching
                    identity_id: int | None = None
                    confidence = "MEDIUM"
                    is_stub = False

                    isrc_val = tags.get("isrc")
                    if isrc_val and isrc_val in _isrc_map:
                        identity_id = _isrc_map[isrc_val]
                        confidence = "HIGH"
                    else:
                        a_n = _norm(tags.get("artist"))
                        t_n = _norm(tags.get("title"))
                        if a_n and t_n:
                            identity_id = _norm_map.get((a_n, t_n))

                    if identity_id is not None:
                        counters["matched_existing"] += 1
                    else:
                        # Create stub
                        is_stub = True
                        if not dry_run:
                            stub_key = f"stub_master_{uuid.uuid4().hex[:12]}"
                            conn.execute(
                                """
                                INSERT OR IGNORE INTO track_identity
                                  (identity_key, canonical_title, canonical_artist,
                                   artist_norm, title_norm, isrc,
                                   ingested_at, ingestion_method, ingestion_source, ingestion_confidence)
                                VALUES (?, ?, ?, ?, ?, ?,
                                        datetime('now'), 'master_scan', 'master_scan_stub', 'uncertain')
                                """,
                                (
                                    stub_key,
                                    tags.get("title") or flac_path.stem,
                                    tags.get("artist") or "",
                                    _norm(tags.get("artist")),
                                    _norm(tags.get("title") or flac_path.stem),
                                    isrc_val,
                                ),
                            )
                            stub_row = conn.execute(
                                "SELECT id FROM track_identity WHERE identity_key = ? LIMIT 1",
                                (stub_key,),
                            ).fetchone()
                            identity_id = stub_row[0] if stub_row else None
                        counters["stubs_created"] += 1

                    # Insert asset_link
                    if not dry_run and asset_id and identity_id:
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO asset_link
                              (asset_id, identity_id, confidence, link_source, active)
                            VALUES (?, ?, ?, 'master_scan', 1)
                            """,
                            (asset_id, identity_id, confidence),
                        )

                    # Log
                    action = "stub_created" if is_stub else "matched"
                    _ts = _now_iso()
                    log_details = {
                        "isrc": isrc_val,
                        "title": tags.get("title"),
                        "artist": tags.get("artist"),
                        "confidence": confidence,
                        "identity_id": identity_id,
                    }
                    if not dry_run:
                        conn.execute(
                            """
                            INSERT INTO reconcile_log
                              (run_id, source, action, confidence, mp3_path,
                               identity_id, lexicon_track_id, details_json)
                            VALUES (?, 'master_scan', ?, ?, ?, ?, NULL, ?)
                            """,
                            (run_id, action, confidence, path_str,
                             identity_id, json.dumps(log_details)),
                        )
                    jsonl_fh.write(
                        json.dumps({
                            "ts": _ts, "run_id": run_id, "action": action,
                            "path": path_str, "result": "ok",
                            "details": log_details,
                        }) + "\n"
                    )

                except Exception as exc:
                    counters["errors"] += 1
                    _ts = _now_iso()
                    jsonl_fh.write(
                        json.dumps({
                            "ts": _ts, "run_id": run_id, "action": "error",
                            "path": path_str, "result": "error",
                            "details": {"error": str(exc)},
                        }) + "\n"
                    )

            if not dry_run:
                conn.commit()

    except Exception:
        if not dry_run:
            conn.rollback()
        raise

    return counters
