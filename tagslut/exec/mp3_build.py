"""Build and reconcile MP3 derivative assets from canonical master state.

build_mp3_from_identity()   — transcode preferred FLAC master(s) to MP3 and register
                               the result in mp3_asset
reconcile_mp3_library()     — scan an existing MP3 root, match files to canonical
                               identities via ISRC or title/artist, and register them
                               in mp3_asset without re-transcoding
scan_mp3_roots()            — scan MP3 root directories and write a CSV manifest
reconcile_mp3_scan()        — reconcile a scan CSV against the DB using multi-tier matching
generate_missing_masters_report() — report orphaned MP3s and FLACs-ready-but-no-MP3
"""
from __future__ import annotations

import csv
import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


MP3_ASSET_PROFILE_FULL_TAGS = "mp3_asset_320_cbr_full"
DJ_COPY_PROFILE = "dj_copy_320_cbr"


@dataclass
class Mp3BuildResult:
    built: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"mp3 build: built={self.built} skipped={self.skipped} failed={self.failed}"
        )


def _resolve_identity_and_asset_for_flac_path(
    conn: sqlite3.Connection,
    *,
    flac_path: Path,
) -> tuple[int | None, int | None]:
    row = conn.execute(
        """
        SELECT af.id AS asset_id, al.identity_id
        FROM asset_file af
        LEFT JOIN asset_link al
          ON al.asset_id = af.id
         AND (al.active IS NULL OR al.active = 1)
        WHERE af.path = ?
        ORDER BY al.confidence DESC, al.id ASC
        LIMIT 1
        """,
        (str(flac_path),),
    ).fetchone()
    if not row:
        return None, None
    asset_id = int(row[0]) if row[0] is not None else None
    identity_id = int(row[1]) if row[1] is not None else None
    return identity_id, asset_id


def _mp3_asset_dest_for_flac_path(
    *,
    flac_path: Path,
    mp3_root: Path,
    library_root: Path | None,
) -> Path:
    rel: Path
    if library_root is not None:
        try:
            rel = flac_path.resolve().relative_to(library_root.resolve())
        except ValueError:
            rel = Path(flac_path.name)
    else:
        rel = Path(flac_path.name)
    return (mp3_root / rel).with_suffix(".mp3")


def build_full_tag_mp3_assets_from_flac_paths(
    conn: sqlite3.Connection,
    *,
    flac_paths: list[Path],
    mp3_root: Path,
    dry_run: bool = True,
    overwrite: bool = False,
) -> Mp3BuildResult:
    """Build full-tag MP3 assets under mp3_root and register as mp3_asset rows."""
    from tagslut.exec.transcoder import transcode_to_mp3_full_tags
    from tagslut.utils.env_paths import get_volume

    result = Mp3BuildResult()
    library_root = get_volume("library", required=False)

    for flac_path in flac_paths:
        try:
            flac_path = Path(flac_path)
            if not flac_path.exists():
                result.failed += 1
                result.errors.append(f"FLAC not found on disk: {flac_path}")
                continue

            identity_id, asset_id = _resolve_identity_and_asset_for_flac_path(conn, flac_path=flac_path)
            if asset_id is None:
                result.failed += 1
                result.errors.append(f"FLAC not registered in asset_file: {flac_path}")
                continue

            dest_path = _mp3_asset_dest_for_flac_path(
                flac_path=flac_path,
                mp3_root=mp3_root,
                library_root=library_root,
            )
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            existing = conn.execute(
                "SELECT id FROM mp3_asset WHERE path = ? LIMIT 1",
                (str(dest_path),),
            ).fetchone()
            if existing and dest_path.exists() and not overwrite:
                result.skipped += 1
                continue

            if dry_run:
                result.built += 1
                continue

            transcode_to_mp3_full_tags(
                flac_path,
                dest_path,
                bitrate=320,
                overwrite=overwrite,
                ffmpeg_path=None,
            )

            conn.execute(
                """
                INSERT OR IGNORE INTO mp3_asset
                  (identity_id, asset_id, profile, path, status, transcoded_at)
                VALUES (?, ?, ?, ?, 'verified', datetime('now'))
                """,
                (identity_id, asset_id, MP3_ASSET_PROFILE_FULL_TAGS, str(dest_path)),
            )
            conn.commit()
            result.built += 1
        except Exception as exc:
            result.failed += 1
            result.errors.append(f"{flac_path}: {exc}")

    return result


def build_dj_copies_from_full_tag_mp3_assets(
    conn: sqlite3.Connection,
    *,
    flac_paths: list[Path],
    dj_root: Path,
    dry_run: bool = True,
    overwrite: bool = False,
) -> Mp3BuildResult:
    """Create DJ copies by copying from full-tag MP3 assets (no re-encode)."""
    import shutil

    from tagslut.exec.transcoder import build_dj_copy_filename, tag_mp3_as_dj_copy

    result = Mp3BuildResult()
    for flac_path in flac_paths:
        try:
            flac_path = Path(flac_path)
            if not flac_path.exists():
                result.failed += 1
                result.errors.append(f"FLAC not found on disk: {flac_path}")
                continue

            identity_id, asset_id = _resolve_identity_and_asset_for_flac_path(conn, flac_path=flac_path)
            if identity_id is None or asset_id is None:
                result.failed += 1
                result.errors.append(f"FLAC not registered with an active identity: {flac_path}")
                continue

            mp3_row = conn.execute(
                """
                SELECT id, path
                FROM mp3_asset
                WHERE identity_id = ?
                  AND asset_id = ?
                  AND profile = ?
                  AND status = 'verified'
                ORDER BY id DESC
                LIMIT 1
                """,
                (identity_id, asset_id, MP3_ASSET_PROFILE_FULL_TAGS),
            ).fetchone()
            if not mp3_row:
                result.failed += 1
                result.errors.append(f"No full-tag mp3_asset found for identity {identity_id} ({flac_path})")
                continue

            src_mp3_path = Path(str(mp3_row[1]))
            if not src_mp3_path.exists():
                result.failed += 1
                result.errors.append(f"Full-tag MP3 not found on disk: {src_mp3_path}")
                continue

            dj_root.mkdir(parents=True, exist_ok=True)
            dj_dest_path = (dj_root / build_dj_copy_filename(flac_path)).resolve()
            if dj_dest_path == src_mp3_path.resolve():
                raise RuntimeError("DJ copy path would equal mp3_asset path (roots or naming conflict)")

            existing = conn.execute(
                "SELECT id FROM mp3_asset WHERE path = ? LIMIT 1",
                (str(dj_dest_path),),
            ).fetchone()
            if existing and dj_dest_path.exists() and not overwrite:
                result.skipped += 1
                continue

            if dry_run:
                result.built += 1
                continue

            if not dj_dest_path.exists() or overwrite:
                dj_dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_mp3_path, dj_dest_path)

            tag_mp3_as_dj_copy(dj_dest_path, flac_path)

            conn.execute(
                """
                INSERT OR IGNORE INTO mp3_asset
                  (identity_id, asset_id, profile, path, status, transcoded_at)
                VALUES (?, ?, ?, ?, 'verified', datetime('now'))
                """,
                (identity_id, asset_id, DJ_COPY_PROFILE, str(dj_dest_path)),
            )
            conn.commit()
            result.built += 1
        except Exception as exc:
            result.failed += 1
            result.errors.append(f"{flac_path}: {exc}")

    return result


def build_mp3_from_identity(
    conn: sqlite3.Connection,
    *,
    identity_ids: list[int] | None = None,
    dj_root: Path,
    dry_run: bool = True,
) -> Mp3BuildResult:
    """Transcode preferred FLAC master(s) to MP3 and register in mp3_asset.

    Only processes identities that do not already have a mp3_asset row with
    status='verified'. Uses the active asset_link rows to find the source FLAC.

    When dry_run=True, counts what would be built without writing anything.
    """
    from tagslut.exec.transcoder import transcode_to_mp3

    result = Mp3BuildResult()

    base_query = """
        SELECT
            ti.id          AS identity_id,
            af.id          AS asset_id,
            af.path        AS flac_path
        FROM track_identity ti
        JOIN (
            SELECT identity_id, asset_id
            FROM asset_link
            WHERE (active IS NULL OR active = 1)
            ORDER BY confidence DESC, id ASC
        ) best_link ON best_link.identity_id = ti.id
        JOIN asset_file af ON af.id = best_link.asset_id
        WHERE NOT EXISTS (
            SELECT 1 FROM mp3_asset ma
            WHERE ma.identity_id = ti.id AND ma.status = 'verified'
        )
    """
    if identity_ids:
        placeholders = ", ".join("?" * len(identity_ids))
        query = base_query + f" AND ti.id IN ({placeholders})"
        rows = conn.execute(query, identity_ids).fetchall()
    else:
        rows = conn.execute(base_query).fetchall()

    for identity_id, asset_id, flac_path in rows:
        if not Path(flac_path).exists():
            result.failed += 1
            result.errors.append(
                f"identity {identity_id}: FLAC not found on disk: {flac_path}"
            )
            continue

        if dry_run:
            result.built += 1
            continue

        try:
            mp3_path = transcode_to_mp3(Path(flac_path), dest_dir=dj_root)
        except Exception as exc:
            result.failed += 1
            result.errors.append(f"identity {identity_id}: transcode error: {exc}")
            continue

        if mp3_path is None:
            result.skipped += 1
            continue

        conn.execute(
            """
            INSERT OR IGNORE INTO mp3_asset
              (identity_id, asset_id, profile, path, status, transcoded_at)
            VALUES (?, ?, 'mp3_320_cbr', ?, 'verified', datetime('now'))
            """,
            (identity_id, asset_id, str(mp3_path)),
        )
        conn.commit()
        result.built += 1

    return result


@dataclass
class Mp3ReconcileResult:
    linked: int = 0
    unmatched: int = 0
    skipped_existing: int = 0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"mp3 reconcile: linked={self.linked} "
            f"skipped_existing={self.skipped_existing} "
            f"unmatched={self.unmatched}"
        )


def reconcile_mp3_library(
    conn: sqlite3.Connection,
    *,
    mp3_root: Path,
    dry_run: bool = True,
) -> Mp3ReconcileResult:
    """Scan mp3_root and register discovered MP3s in mp3_asset.

    Matches each MP3 to a canonical identity via:
    1. ISRC tag (TSRC ID3 frame) — preferred
    2. Exact lower-cased title + artist match against track_identity

    Skips files that already have an mp3_asset row.
    When dry_run=True, counts what would be linked without writing anything.
    """
    try:
        from mutagen.id3 import ID3, ID3NoHeaderError  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "mutagen is required for mp3 reconcile. "
            "Install it with: pip install mutagen"
        ) from exc

    result = Mp3ReconcileResult()

    for mp3_file in sorted(mp3_root.rglob("*.mp3")):
        try:
            tags = ID3(str(mp3_file))
        except ID3NoHeaderError:
            result.errors.append(f"No ID3 header: {mp3_file}")
            continue
        except Exception as exc:
            result.errors.append(f"Cannot read tags ({exc}): {mp3_file}")
            continue

        isrc_frame = tags.get("TSRC")
        isrc = str(isrc_frame.text[0]) if isrc_frame and isrc_frame.text else None
        title_frame = tags.get("TIT2")
        title = str(title_frame.text[0]) if title_frame and title_frame.text else None
        artist_frame = tags.get("TPE1")
        artist = str(artist_frame.text[0]) if artist_frame and artist_frame.text else None

        identity_id: int | None = None
        if isrc:
            row = conn.execute(
                "SELECT id FROM track_identity WHERE isrc = ? LIMIT 1",
                (isrc,),
            ).fetchone()
            if row:
                identity_id = row[0]

        if identity_id is None and title and artist:
            row = conn.execute(
                """
                SELECT id FROM track_identity
                WHERE lower(title_norm)  = lower(?)
                  AND lower(artist_norm) = lower(?)
                LIMIT 1
                """,
                (title, artist),
            ).fetchone()
            if row:
                identity_id = row[0]

        if identity_id is None:
            result.unmatched += 1
            result.errors.append(
                f"No identity match for {mp3_file.name} "
                f"(isrc={isrc!r}, title={title!r}, artist={artist!r})"
            )
            continue

        # Already registered?
        existing = conn.execute(
            "SELECT id FROM mp3_asset WHERE path = ?", (str(mp3_file),)
        ).fetchone()
        if existing:
            result.skipped_existing += 1
            continue

        if dry_run:
            result.linked += 1
            continue

        # Find the master asset for this identity
        master_row = conn.execute(
            """
            SELECT af.id FROM asset_file af
            JOIN asset_link al ON al.asset_id = af.id
            WHERE al.identity_id = ?
            ORDER BY al.id ASC
            LIMIT 1
            """,
            (identity_id,),
        ).fetchone()
        if master_row is None:
            result.errors.append(
                f"identity {identity_id}: no master asset found for {mp3_file.name}"
            )
            result.unmatched += 1
            continue

        conn.execute(
            """
            INSERT OR IGNORE INTO mp3_asset
              (identity_id, asset_id, profile, path, status, transcoded_at)
            VALUES (?, ?, 'mp3_320_cbr_reconciled', ?, 'verified', datetime('now'))
            """,
            (identity_id, master_row[0], str(mp3_file)),
        )
        conn.commit()
        result.linked += 1

    return result


# ---------------------------------------------------------------------------
# Task 2 — Mp3ScanResult + scan_mp3_roots()
# ---------------------------------------------------------------------------


@dataclass
class Mp3ScanResult:
    total: int = 0
    errors: list[str] = field(default_factory=list)
    csv_path: str = ""


def _compute_sha256(path: Path) -> str:
    """Compute hex SHA-256 of a file."""
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_mp3_tags(path: Path) -> dict:
    """Read MP3 audio info and ID3 tags via mutagen. Returns a flat dict."""
    try:
        from mutagen.id3 import ID3, ID3NoHeaderError  # type: ignore[import-untyped]
        from mutagen.mp3 import MP3  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError("mutagen is required — pip install mutagen") from exc

    info: dict = {
        "bitrate": None,
        "sample_rate": None,
        "duration_s": None,
        "id3_title": None,
        "id3_artist": None,
        "id3_album": None,
        "id3_year": None,
        "id3_bpm": None,
        "id3_key": None,
        "id3_genre": None,
        "id3_label": None,
        "id3_remixer": None,
        "id3_isrc": None,
        "id3_comment": None,
    }

    try:
        audio = MP3(str(path))
        info["bitrate"] = int(audio.info.bitrate) if audio.info.bitrate else None
        info["sample_rate"] = int(audio.info.sample_rate) if audio.info.sample_rate else None
        info["duration_s"] = round(float(audio.info.length), 3) if audio.info.length else None
    except Exception:
        pass

    def _first(tags: "ID3", frame_id: str) -> str | None:
        frame = tags.get(frame_id)
        if frame is None:
            return None
        text_attr = getattr(frame, "text", None)
        if text_attr and len(text_attr) > 0:
            val = str(text_attr[0]).strip()
            return val if val else None
        return None

    try:
        tags = ID3(str(path))
        info["id3_title"] = _first(tags, "TIT2")
        info["id3_artist"] = _first(tags, "TPE1")
        info["id3_album"] = _first(tags, "TALB")
        info["id3_year"] = _first(tags, "TDRC") or _first(tags, "TYER")
        info["id3_bpm"] = _first(tags, "TBPM")
        info["id3_key"] = _first(tags, "TKEY")
        info["id3_genre"] = _first(tags, "TCON")
        info["id3_label"] = _first(tags, "TPUB")
        info["id3_remixer"] = _first(tags, "TPE4")
        info["id3_isrc"] = _first(tags, "TSRC")
        # COMM frames — take the first one
        comm_frames = [v for k, v in tags.items() if k.startswith("COMM")]
        if comm_frames:
            text_attr = getattr(comm_frames[0], "text", None)
            if text_attr and len(text_attr) > 0:
                info["id3_comment"] = str(text_attr[0]).strip() or None
    except Exception:
        pass

    return info


_SCAN_CSV_HEADERS = [
    "path", "zone", "size_bytes", "mtime", "sha256", "bitrate", "sample_rate",
    "duration_s", "id3_title", "id3_artist", "id3_album", "id3_year",
    "id3_bpm", "id3_key", "id3_genre", "id3_label", "id3_remixer",
    "id3_isrc", "id3_comment",
]


def scan_mp3_roots(
    roots: list[Path],
    out_csv: Path,
    run_id: str,
    log_dir: Path,
    *,
    exclude_patterns: list[str] | None = None,
) -> Mp3ScanResult:
    """Scan one or more root directories for MP3 files and write a manifest CSV.

    Each file's path, zone (root basename), size, mtime, sha256, audio info,
    and ID3 tags are collected. Progress is printed every 500 files.
    Every file is logged as a JSON line in log_dir/reconcile_scan_{run_id}.jsonl.
    """
    result = Mp3ScanResult(csv_path=str(out_csv))
    log_dir.mkdir(parents=True, exist_ok=True)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    jsonl_path = log_dir / f"reconcile_scan_{run_id}.jsonl"

    # Collect all files first for progress reporting
    all_files: list[tuple[Path, str]] = []
    for root in roots:
        zone = root.name
        for mp3 in sorted(root.rglob("*.mp3")):
            if exclude_patterns:
                skip = any(
                    re.search(pat, str(mp3)) for pat in exclude_patterns
                )
                if skip:
                    continue
            all_files.append((mp3, zone))

    total = len(all_files)

    with (
        open(out_csv, "w", newline="", encoding="utf-8") as csv_fh,
        open(jsonl_path, "a", encoding="utf-8") as jsonl_fh,
    ):
        writer = csv.DictWriter(csv_fh, fieldnames=_SCAN_CSV_HEADERS)
        writer.writeheader()

        for idx, (mp3, zone) in enumerate(all_files, start=1):
            if idx % 500 == 0:
                print(f"[SCAN] {idx}/{total} files processed...")

            ts = datetime.now(tz=timezone.utc).isoformat()
            try:
                stat = mp3.stat()
                size_bytes = stat.st_size
                mtime = datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat()
                sha256 = _compute_sha256(mp3)
                tags = _read_mp3_tags(mp3)

                row = {
                    "path": str(mp3),
                    "zone": zone,
                    "size_bytes": size_bytes,
                    "mtime": mtime,
                    "sha256": sha256,
                    **tags,
                }
                writer.writerow(row)
                result.total += 1

                entry = {
                    "ts": ts,
                    "run_id": run_id,
                    "action": "scanned",
                    "path": str(mp3),
                    "result": "ok",
                    "details": {"zone": zone, "size_bytes": size_bytes},
                }
            except Exception as exc:
                result.errors.append(f"{mp3}: {exc}")
                entry = {
                    "ts": ts,
                    "run_id": run_id,
                    "action": "scanned",
                    "path": str(mp3),
                    "result": "error",
                    "details": {"error": str(exc)},
                }

            jsonl_fh.write(json.dumps(entry) + "\n")

    return result


# ---------------------------------------------------------------------------
# Task 3 — reconcile_mp3_scan()
# ---------------------------------------------------------------------------

_FILENAME_RE = re.compile(
    r"""
    ^
    (?P<artist>[^–\-]+?)          # Artist (before em-dash or ascii dash)
    \s*[–\-]\s*                    # separator
    (?:
        (?P<album>[^–\-]+?)        # Optional album
        \s*[–\-]\s*
        \d{2}\s+                   # Track number
    )?
    (?P<title>.+?)                 # Title
    \.mp3$
    """,
    re.VERBOSE | re.IGNORECASE,
)


def _norm(s: str | None) -> str:
    """Normalise a string for matching: lower, strip, collapse whitespace."""
    if not s:
        return ""
    return re.sub(r"\s+", " ", s.lower().strip())


def _parse_filename(filename: str) -> tuple[str, str] | None:
    """Return (artist_norm, title_norm) from a filename or None."""
    m = _FILENAME_RE.match(filename)
    if not m:
        return None
    artist = _norm(m.group("artist"))
    title = _norm(m.group("title"))
    if artist and title:
        return artist, title
    return None


def _log_reconcile(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    source: str,
    action: str,
    confidence: str,
    mp3_path: str,
    identity_id: int | None,
    lexicon_track_id: int | None,
    details: dict,
    jsonl_fh,
    dry_run: bool,
) -> None:
    """Write one row to reconcile_log and one line to JSONL."""
    ts = datetime.now(tz=timezone.utc).isoformat()
    details_json = json.dumps(details)

    if not dry_run:
        conn.execute(
            """
            INSERT INTO reconcile_log
              (run_id, source, action, confidence, mp3_path, identity_id,
               lexicon_track_id, details_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id, source, action, confidence, mp3_path,
                identity_id, lexicon_track_id, details_json,
            ),
        )

    entry = {
        "ts": ts,
        "run_id": run_id,
        "action": action,
        "path": mp3_path,
        "result": "ok",
        "details": {**details, "confidence": confidence, "identity_id": identity_id},
    }
    jsonl_fh.write(json.dumps(entry) + "\n")


def reconcile_mp3_scan(
    conn: sqlite3.Connection,
    *,
    scan_csv: Path,
    run_id: str,
    log_dir: Path,
    out_json: Path,
    dry_run: bool = True,
) -> dict:
    """Reconcile a scan CSV against the DB using multi-tier identity matching.

    Tier 1 — filename pattern (HIGH confidence)
    Tier 2 — ISRC tag (HIGH confidence)
    Tier 3 — ID3 title+artist normalised (MEDIUM confidence)
    Tier 4 — fuzzy (LOW confidence, flagged for review only)
    No match — insert track_identity stub + mp3_asset (orphan_stubbed)

    Duplicate MP3s for the same identity: keep highest bitrate, mark others
    'superseded'. Idempotent — paths already in mp3_asset are skipped.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    out_json.parent.mkdir(parents=True, exist_ok=True)

    jsonl_path = log_dir / f"reconcile_reconcile_{run_id}.jsonl"

    counters: dict[str, int] = {
        "matched_t1": 0,
        "matched_t2": 0,
        "matched_t3": 0,
        "fuzzy": 0,
        "stubs": 0,
        "conflicts": 0,
        "skipped": 0,
        "errors": 0,
    }

    # Try to import thefuzz / rapidfuzz for Tier 4
    _fuzzy_ratio = None
    try:
        from rapidfuzz import fuzz as _rf  # type: ignore[import-untyped]
        _fuzzy_ratio = lambda a, b: _rf.token_sort_ratio(a, b) / 100.0
    except ImportError:
        try:
            from thefuzz import fuzz as _tf  # type: ignore[import-untyped]
            _fuzzy_ratio = lambda a, b: _tf.token_sort_ratio(a, b) / 100.0
        except ImportError:
            pass  # Tier 4 skipped

    with (
        open(scan_csv, newline="", encoding="utf-8") as csv_fh,
        open(jsonl_path, "a", encoding="utf-8") as jsonl_fh,
    ):
        reader = csv.DictReader(csv_fh)
        rows = list(reader)

    # Build identity lookup maps for batch efficiency
    # norm_key → list of identity_ids
    _norm_map: dict[tuple[str, str], list[int]] = {}
    _isrc_map: dict[str, list[int]] = {}
    for id_row in conn.execute(
        "SELECT id, isrc, artist_norm, title_norm FROM track_identity WHERE merged_into_id IS NULL"
    ).fetchall():
        iid = id_row[0]
        isrc_val = id_row[1]
        a_norm = _norm(id_row[2])
        t_norm = _norm(id_row[3])
        if isrc_val:
            _isrc_map.setdefault(isrc_val.strip(), []).append(iid)
        if a_norm and t_norm:
            _norm_map.setdefault((a_norm, t_norm), []).append(iid)

    try:
        with open(jsonl_path, "a", encoding="utf-8") as jsonl_fh:
            for row in rows:
                path_str = row.get("path", "")
                try:
                    _process_reconcile_row(
                        conn=conn,
                        row=row,
                        path_str=path_str,
                        run_id=run_id,
                        counters=counters,
                        norm_map=_norm_map,
                        isrc_map=_isrc_map,
                        fuzzy_ratio=_fuzzy_ratio,
                        jsonl_fh=jsonl_fh,
                        dry_run=dry_run,
                    )
                except Exception as exc:
                    counters["errors"] += 1
                    ts = datetime.now(tz=timezone.utc).isoformat()
                    jsonl_fh.write(
                        json.dumps({
                            "ts": ts, "run_id": run_id, "action": "error",
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

    out_json.write_text(json.dumps(counters, indent=2))
    return counters


def _process_reconcile_row(
    *,
    conn: sqlite3.Connection,
    row: dict,
    path_str: str,
    run_id: str,
    counters: dict,
    norm_map: dict,
    isrc_map: dict,
    fuzzy_ratio,
    jsonl_fh,
    dry_run: bool,
) -> None:
    """Process one CSV row for reconcile_mp3_scan (extracted for clarity)."""
    # Already in mp3_asset?
    existing = conn.execute(
        "SELECT id FROM mp3_asset WHERE path = ?", (path_str,)
    ).fetchone()
    if existing:
        counters["skipped"] += 1
        _log_reconcile(
            conn, run_id=run_id, source="mp3_reconcile",
            action="skipped_existing", confidence="", mp3_path=path_str,
            identity_id=None, lexicon_track_id=None,
            details={"reason": "path already in mp3_asset"},
            jsonl_fh=jsonl_fh, dry_run=dry_run,
        )
        return

    filename = Path(path_str).name
    isrc_val = (row.get("id3_isrc") or "").strip() or None
    id3_title = (row.get("id3_title") or "").strip() or None
    id3_artist = (row.get("id3_artist") or "").strip() or None
    bitrate_raw = row.get("bitrate")
    bitrate = int(bitrate_raw) if bitrate_raw else None
    sample_rate_raw = row.get("sample_rate")
    sample_rate = int(sample_rate_raw) if sample_rate_raw else None
    duration_raw = row.get("duration_s")
    duration_s = float(duration_raw) if duration_raw else None
    sha256 = row.get("sha256") or None
    zone = row.get("zone") or ""

    identity_id: int | None = None
    tier: int | None = None
    confidence: str = ""

    # Tier 1 — filename pattern
    parsed = _parse_filename(filename)
    if parsed:
        fn_artist, fn_title = parsed
        candidates = norm_map.get((fn_artist, fn_title), [])
        if len(candidates) == 1:
            identity_id = candidates[0]
            tier = 1
            confidence = "HIGH"

    # Tier 2 — ISRC
    if identity_id is None and isrc_val:
        candidates = isrc_map.get(isrc_val, [])
        if len(candidates) == 1:
            identity_id = candidates[0]
            tier = 2
            confidence = "HIGH"
        elif len(candidates) > 1:
            counters["conflicts"] += 1
            _log_reconcile(
                conn, run_id=run_id, source="mp3_reconcile",
                action="CONFLICT", confidence="HIGH", mp3_path=path_str,
                identity_id=None, lexicon_track_id=None,
                details={"tier": 2, "candidates": candidates, "isrc": isrc_val},
                jsonl_fh=jsonl_fh, dry_run=dry_run,
            )
            return

    # Tier 3 — ID3 title+artist normalised
    if identity_id is None and id3_title and id3_artist:
        key = (_norm(id3_artist), _norm(id3_title))
        candidates = norm_map.get(key, [])
        if len(candidates) == 1:
            identity_id = candidates[0]
            tier = 3
            confidence = "MEDIUM"
        elif len(candidates) > 1:
            counters["conflicts"] += 1
            _log_reconcile(
                conn, run_id=run_id, source="mp3_reconcile",
                action="CONFLICT", confidence="MEDIUM", mp3_path=path_str,
                identity_id=None, lexicon_track_id=None,
                details={"tier": 3, "candidates": candidates},
                jsonl_fh=jsonl_fh, dry_run=dry_run,
            )
            return

    # Tier 4 — fuzzy
    if identity_id is None and fuzzy_ratio and id3_title and id3_artist:
        query_str = f"{_norm(id3_artist)} {_norm(id3_title)}"
        best_score = 0.0
        best_id: int | None = None
        for (a_n, t_n), iids in norm_map.items():
            candidate_str = f"{a_n} {t_n}"
            score = fuzzy_ratio(query_str, candidate_str)
            if score > best_score:
                best_score = score
                best_id = iids[0] if len(iids) == 1 else None
        if best_score >= 0.92 and best_id is not None:
            counters["fuzzy"] += 1
            _log_reconcile(
                conn, run_id=run_id, source="mp3_reconcile",
                action="fuzzy_match", confidence="LOW", mp3_path=path_str,
                identity_id=best_id, lexicon_track_id=None,
                details={"score": round(best_score, 4), "candidate_id": best_id},
                jsonl_fh=jsonl_fh, dry_run=dry_run,
            )
            return  # Do NOT insert mp3_asset for fuzzy

    # No match → stub
    if identity_id is None:
        action = "orphan_stubbed"
        stub_id: int | None = None

        if not dry_run:
            # Insert track_identity stub
            import uuid as _uuid
            stub_key = f"stub_{_uuid.uuid4().hex[:12]}"
            conn.execute(
                """
                INSERT OR IGNORE INTO track_identity
                  (identity_key, canonical_title, canonical_artist,
                   artist_norm, title_norm,
                   ingested_at, ingestion_method, ingestion_source, ingestion_confidence)
                VALUES (?, ?, ?, ?, ?,
                        datetime('now'), 'mp3_reconcile', 'mp3_reconcile_stub', 'uncertain')
                """,
                (stub_key, id3_title or filename, id3_artist or "",
                 _norm(id3_artist), _norm(id3_title or filename)),
            )
            stub_row = conn.execute(
                "SELECT id FROM track_identity WHERE identity_key = ?", (stub_key,)
            ).fetchone()
            stub_id = stub_row[0] if stub_row else None

            if stub_id:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO mp3_asset
                      (identity_id, path, zone, content_sha256, bitrate,
                       sample_rate, duration_s, status, source, reconciled_at,
                       lexicon_track_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'unverified', 'mp3_reconcile',
                            datetime('now'), NULL)
                    """,
                    (stub_id, path_str, zone, sha256, bitrate, sample_rate, duration_s),
                )

        counters["stubs"] += 1
        _log_reconcile(
            conn, run_id=run_id, source="mp3_reconcile",
            action=action, confidence="", mp3_path=path_str,
            identity_id=stub_id, lexicon_track_id=None,
            details={"id3_title": id3_title, "id3_artist": id3_artist},
            jsonl_fh=jsonl_fh, dry_run=dry_run,
        )
        return

    # Matched (Tier 1/2/3) — handle duplicate MP3s for same identity
    if not dry_run:
        existing_mp3s = conn.execute(
            """
            SELECT id, bitrate, status FROM mp3_asset
            WHERE identity_id = ? AND status IN ('verified','unverified','superseded')
            """,
            (identity_id,),
        ).fetchall()

        # Insert this MP3 first
        conn.execute(
            """
            INSERT OR IGNORE INTO mp3_asset
              (identity_id, path, zone, content_sha256, bitrate,
               sample_rate, duration_s, status, source, reconciled_at,
               lexicon_track_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'unverified', 'mp3_reconcile',
                    datetime('now'), NULL)
            """,
            (identity_id, path_str, zone, sha256, bitrate, sample_rate, duration_s),
        )

        # Duplicate handling: keep highest bitrate as 'verified', others 'superseded'
        if existing_mp3s:
            all_mp3s = conn.execute(
                "SELECT id, bitrate FROM mp3_asset WHERE identity_id = ? AND status != 'superseded'",
                (identity_id,),
            ).fetchall()
            if len(all_mp3s) > 1:
                best_row = max(all_mp3s, key=lambda r: r[1] or 0)
                best_id = best_row[0]
                for mp3_row in all_mp3s:
                    if mp3_row[0] == best_id:
                        conn.execute(
                            "UPDATE mp3_asset SET status='verified' WHERE id=?",
                            (mp3_row[0],),
                        )
                    else:
                        conn.execute(
                            "UPDATE mp3_asset SET status='superseded' WHERE id=?",
                            (mp3_row[0],),
                        )

    action_name = f"matched_tier{tier}"
    if tier == 1:
        counters["matched_t1"] += 1
    elif tier == 2:
        counters["matched_t2"] += 1
    elif tier == 3:
        counters["matched_t3"] += 1

    _log_reconcile(
        conn, run_id=run_id, source="mp3_reconcile",
        action=action_name, confidence=confidence, mp3_path=path_str,
        identity_id=identity_id, lexicon_track_id=None,
        details={"tier": tier, "zone": zone, "bitrate": bitrate},
        jsonl_fh=jsonl_fh, dry_run=dry_run,
    )


# ---------------------------------------------------------------------------
# Task 7 — generate_missing_masters_report()
# ---------------------------------------------------------------------------


def generate_missing_masters_report(
    conn: sqlite3.Connection,
    *,
    out_path: Path,
) -> dict:
    """Generate a Markdown report of missing master FLACs for DJ MP3s.

    Section A — Orphaned MP3s (no identity or stub identity).
    Section B — FLACs ready but no MP3 built.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Section A — orphaned mp3_asset rows
    orphan_rows = conn.execute(
        """
        SELECT ma.id, ma.path, ma.zone, ma.bitrate, ma.lexicon_track_id,
               ti.canonical_bpm, ti.canonical_key, ti.status AS id_status
        FROM mp3_asset ma
        LEFT JOIN track_identity ti ON ti.id = ma.identity_id
        WHERE ma.identity_id IS NULL
           OR (ti.status = 'stub_pending_master')
        """,
    ).fetchall()

    # Determine playlist membership for priority
    in_playlist = set()
    for r in conn.execute(
        """
        SELECT ma.path
        FROM mp3_asset ma
        JOIN dj_admission da ON da.identity_id = ma.identity_id
        JOIN dj_playlist_track dpt ON dpt.dj_admission_id = da.id
        """
    ).fetchall():
        in_playlist.add(r[0])

    section_a: list[tuple[str, str]] = []  # (priority, path)
    high = medium = low = 0

    for r in orphan_rows:
        path = r[1]
        lex_id = r[4]
        bpm = r[5]
        key = r[6]

        if path in in_playlist or lex_id is not None:
            prio = "HIGH"
            high += 1
        elif bpm and key:
            prio = "MEDIUM"
            medium += 1
        else:
            prio = "LOW"
            low += 1
        section_a.append((prio, path))

    # Sort by priority
    _prio_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    section_a.sort(key=lambda x: _prio_order[x[0]])

    # Section B — identities with asset_link but no mp3_asset
    section_b_rows = conn.execute(
        """
        SELECT ti.id, ti.canonical_artist, ti.canonical_title
        FROM track_identity ti
        JOIN asset_link al ON al.identity_id = ti.id
        WHERE NOT EXISTS (
            SELECT 1 FROM mp3_asset ma WHERE ma.identity_id = ti.id
        )
        """,
    ).fetchall()
    section_b = [(r[0], r[1], r[2]) for r in section_b_rows]

    lines: list[str] = [
        "# Missing Masters Report",
        f"\nGenerated: {datetime.now(tz=timezone.utc).isoformat()}",
        "",
        f"## Section A — Orphaned MP3s ({len(section_a)} total)",
        f"Priority breakdown: HIGH={high} MEDIUM={medium} LOW={low}",
        "",
    ]
    for prio, path in section_a:
        lines.append(f"- [ ] `{prio}` {path}")

    lines += [
        "",
        f"## Section B — FLACs ready, no MP3 ({len(section_b)} total)",
        "",
    ]
    for iid, artist, title in section_b:
        label = f"{artist or '?'} — {title or '?'} (id={iid})"
        lines.append(f"- [ ] {label}")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {
        "section_a_count": len(section_a),
        "high": high,
        "medium": medium,
        "low": low,
        "section_b_count": len(section_b),
    }
