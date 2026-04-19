"""Build and reconcile MP3 derivative assets with lossless-first lineage.

build_mp3_from_identity()   — transcode preferred source asset(s) to MP3 and register
                               the result in mp3_asset
reconcile_mp3_library()     — scan an existing MP3 root, match files to canonical
                               identities via ISRC or title/artist, and register them
                               in mp3_asset while preserving provisional lineage
scan_mp3_roots()            — scan MP3 root directories and write a CSV manifest
reconcile_mp3_scan()        — reconcile a scan CSV against the DB using multi-tier matching
generate_missing_masters_report() — report orphaned MP3s and lossless-ready-but-no-MP3
"""
from __future__ import annotations

import csv
import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


from tagslut.exec.mp3_reconcile import (
    normalize_artist_for_match,
    normalize_isrc,
    normalize_title_for_match,
)
from tagslut.cli._progress import ProgressCallback
from tagslut.storage.v3.resolver import ResolverInput, resolve_identity
from tagslut.utils.fs import normalize_path


MP3_ASSET_PROFILE_FULL_TAGS = "mp3_asset_320_cbr_full"
DJ_COPY_PROFILE = "dj_copy_320_cbr"
_TRUSTED_SOURCE_ROOTS = (
    normalize_path(Path("/Volumes/MUSIC/MASTER_LIBRARY")),
    normalize_path(Path("/Volumes/MUSIC/MP3_LIBRARY")),
)


def source_provenance_for_path(path: Path) -> tuple[str | None, str]:
    """Return the trusted source root and canonical source path for a file."""
    source_path = normalize_path(path)
    for root in _TRUSTED_SOURCE_ROOTS:
        try:
            source_path.relative_to(root)
        except ValueError:
            continue
        return str(root), str(source_path)
    return None, str(source_path)


def insert_mp3_asset_row(
    conn: sqlite3.Connection,
    *,
    identity_id: int,
    asset_id: int,
    profile: str,
    path: Path,
    status: str = "verified",
    source_root: str | None = None,
    source_path: str | None = None,
) -> None:
    _upsert_mp3_asset_row(
        conn,
        path=path,
        identity_id=identity_id,
        asset_id=asset_id,
        profile=profile,
        status=status,
        source_root=source_root,
        source_path=source_path,
        transcoded_at=datetime.now(timezone.utc).isoformat(),
    )


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {
            str(row[1])
            for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
            if row and row[1]
        }
    except sqlite3.OperationalError:
        return set()


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    try:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
            (table,),
        ).fetchone()
    except sqlite3.OperationalError:
        return False
    return row is not None


def _insert_reconcile_log_row(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    source: str,
    action: str,
    confidence: str,
    mp3_path: str,
    identity_id: int | None,
    details: dict,
    dry_run: bool = False,
) -> None:
    if dry_run or not _table_exists(conn, "reconcile_log"):
        return
    conn.execute(
        """
        INSERT INTO reconcile_log
          (run_id, source, action, confidence, mp3_path, identity_id, lexicon_track_id, details_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            source,
            action,
            confidence,
            mp3_path,
            identity_id,
            None,
            json.dumps(details, ensure_ascii=False, sort_keys=True),
        ),
    )


def _insert_track_identity_stub(
    conn: sqlite3.Connection,
    *,
    identity_key: str,
    title: str | None,
    artist: str | None,
    isrc: str | None,
    source: str,
) -> int | None:
    columns = _table_columns(conn, "track_identity")
    if not columns:
        return None

    values: dict[str, object] = {
        "identity_key": identity_key,
        "canonical_title": title or "",
        "canonical_artist": artist or "",
        "artist_norm": normalize_artist_for_match(artist),
        "title_norm": normalize_title_for_match(title),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "ingestion_method": source,
        "ingestion_source": f"{source}_stub",
        "ingestion_confidence": "uncertain",
        "status": "stub_pending_master",
        "source": source,
    }
    if isrc:
        values["isrc"] = isrc

    insert_keys = [key for key in values if key in columns]
    if insert_keys:
        conn.execute(
            f"""
            INSERT OR IGNORE INTO track_identity ({', '.join(insert_keys)})
            VALUES ({', '.join('?' for _ in insert_keys)})
            """,
            [values[key] for key in insert_keys],
        )

    row = conn.execute(
        "SELECT id FROM track_identity WHERE identity_key = ?",
        (identity_key,),
    ).fetchone()
    return int(row[0]) if row else None


def _upsert_mp3_asset_row(
    conn: sqlite3.Connection,
    *,
    path: Path,
    identity_id: int | None,
    asset_id: int | None = None,
    profile: str = "mp3_320_cbr_reconciled",
    status: str = "verified",
    source: str = "mp3_reconcile",
    zone: str | None = None,
    content_sha256: str | None = None,
    size_bytes: int | None = None,
    bitrate: int | None = None,
    sample_rate: int | None = None,
    duration_s: float | None = None,
    source_root: str | None = None,
    source_path: str | None = None,
    ingest_session: str | None = None,
    ingest_at: str | None = None,
    transcoded_at: str | None = None,
    reconciled_at: str | None = None,
    lexicon_track_id: int | None = None,
) -> None:
    columns = _table_columns(conn, "mp3_asset")
    if not columns:
        return

    insert_cols: list[str] = []
    insert_vals: list[object] = []
    update_sets: list[str] = []

    def add(col: str, value: object | None, *, update: bool = True) -> None:
        if col not in columns or value is None:
            return
        insert_cols.append(col)
        insert_vals.append(value)
        if update:
            update_sets.append(f"{col} = excluded.{col}")

    add("identity_id", identity_id)
    add("asset_id", asset_id)
    add("path", str(path), update=False)
    add("profile", profile)
    add("status", status)
    add("source", source)
    add("zone", zone)
    add("content_sha256", content_sha256)
    add("size_bytes", size_bytes)
    add("bitrate", bitrate)
    add("sample_rate", sample_rate)
    add("duration_s", duration_s)
    add("source_root", source_root)
    add("source_path", source_path)
    add("ingest_session", ingest_session)
    add("ingest_at", ingest_at)
    add("transcoded_at", transcoded_at)
    add("reconciled_at", reconciled_at)
    add("lexicon_track_id", lexicon_track_id)

    if "updated_at" in columns:
        update_sets.append("updated_at = CURRENT_TIMESTAMP")

    if not insert_cols:
        return

    placeholders = ", ".join("?" for _ in insert_cols)
    if update_sets:
        on_conflict = f"DO UPDATE SET {', '.join(update_sets)}"
    else:
        on_conflict = "DO NOTHING"
    conn.execute(
        f"""
        INSERT INTO mp3_asset ({', '.join(insert_cols)})
        VALUES ({placeholders})
        ON CONFLICT(path) {on_conflict}
        """,
        insert_vals,
    )


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
            flac_path_db = Path(flac_path)
            flac_path_fs = normalize_path(flac_path_db)
            if not flac_path_fs.exists():
                result.failed += 1
                result.errors.append(f"FLAC not found on disk: {flac_path_db}")
                continue

            identity_id, asset_id = _resolve_identity_and_asset_for_flac_path(
                conn, flac_path=flac_path_db
            )
            if asset_id is None:
                result.failed += 1
                result.errors.append(f"FLAC not registered in asset_file: {flac_path_db}")
                continue

            dest_path = _mp3_asset_dest_for_flac_path(
                flac_path=flac_path_db,
                mp3_root=mp3_root,
                library_root=library_root,
            )
            dest_path_fs = normalize_path(dest_path)
            dest_path_fs.parent.mkdir(parents=True, exist_ok=True)

            existing = conn.execute(
                "SELECT id FROM mp3_asset WHERE path = ? LIMIT 1",
                (str(dest_path),),
            ).fetchone()
            if existing and dest_path_fs.exists() and not overwrite:
                result.skipped += 1
                continue

            if dry_run:
                result.built += 1
                continue

            source_root, source_path = source_provenance_for_path(flac_path_fs)
            transcode_to_mp3_full_tags(
                flac_path_fs,
                dest_path_fs,
                bitrate=320,
                overwrite=overwrite,
                ffmpeg_path=None,
            )

            _upsert_mp3_asset_row(
                conn,
                path=dest_path,
                identity_id=identity_id,
                asset_id=asset_id,
                profile=MP3_ASSET_PROFILE_FULL_TAGS,
                status="verified",
                source_root=source_root,
                source_path=source_path,
                transcoded_at=datetime.now(timezone.utc).isoformat(),
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
            flac_path_db = Path(flac_path)
            flac_path_fs = normalize_path(flac_path_db)
            if not flac_path_fs.exists():
                result.failed += 1
                result.errors.append(f"FLAC not found on disk: {flac_path_db}")
                continue

            identity_id, asset_id = _resolve_identity_and_asset_for_flac_path(
                conn, flac_path=flac_path_db
            )
            if identity_id is None or asset_id is None:
                result.failed += 1
                result.errors.append(
                    f"FLAC not registered with an active identity: {flac_path_db}"
                )
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
                result.errors.append(
                    f"No full-tag mp3_asset found for identity {identity_id} ({flac_path_db})"
                )
                continue

            src_mp3_path_db = Path(str(mp3_row[1]))
            src_mp3_path_fs = normalize_path(src_mp3_path_db)
            if not src_mp3_path_fs.exists():
                result.failed += 1
                result.errors.append(
                    f"Full-tag MP3 not found on disk: {src_mp3_path_db}"
                )
                continue

            dj_root_fs = normalize_path(dj_root)
            dj_root_fs.mkdir(parents=True, exist_ok=True)
            dj_dest_path = (dj_root / build_dj_copy_filename(flac_path_db)).resolve()
            dj_dest_path_fs = normalize_path(dj_dest_path)
            if dj_dest_path_fs.resolve() == src_mp3_path_fs.resolve():
                raise RuntimeError("DJ copy path would equal mp3_asset path (roots or naming conflict)")

            existing = conn.execute(
                "SELECT id FROM mp3_asset WHERE path = ? LIMIT 1",
                (str(dj_dest_path),),
            ).fetchone()
            if existing and dj_dest_path_fs.exists() and not overwrite:
                result.skipped += 1
                continue

            if dry_run:
                result.built += 1
                continue

            source_root, source_path = source_provenance_for_path(flac_path_fs)
            if not dj_dest_path_fs.exists() or overwrite:
                dj_dest_path_fs.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_mp3_path_fs, dj_dest_path_fs)

            tag_mp3_as_dj_copy(dj_dest_path_fs, flac_path_fs)

            _upsert_mp3_asset_row(
                conn,
                path=dj_dest_path,
                identity_id=identity_id,
                asset_id=asset_id,
                profile=DJ_COPY_PROFILE,
                status="verified",
                source_root=source_root,
                source_path=source_path,
                transcoded_at=datetime.now(timezone.utc).isoformat(),
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
    progress_cb: "ProgressCallback | None" = None,
) -> Mp3BuildResult:
    """Transcode preferred source asset(s) to MP3 and register in mp3_asset.

    Only processes identities that do not already have a mp3_asset row with
    status='verified'. Uses the active asset_link rows to find the source audio.

    When dry_run=True, counts what would be built without writing anything.
    """
    from tagslut.exec.transcoder import transcode_to_mp3

    result = Mp3BuildResult()
    dj_root_fs = normalize_path(dj_root)

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

    for idx, (identity_id, asset_id, flac_path) in enumerate(rows, 1):
        flac_path_db = Path(flac_path)
        flac_path_fs = normalize_path(flac_path_db)
        source_root, source_path = source_provenance_for_path(flac_path_fs)
        if not flac_path_fs.exists():
            result.failed += 1
            result.errors.append(
                f"identity {identity_id}: FLAC not found on disk: {flac_path}"
            )
            if progress_cb is not None:
                progress_cb(flac_path_db.name, idx, len(rows))
            continue

        if dry_run:
            result.built += 1
            if progress_cb is not None:
                progress_cb(flac_path_db.name, idx, len(rows))
            continue

        try:
            mp3_path = transcode_to_mp3(flac_path_fs, dest_dir=dj_root_fs)
        except Exception as exc:
            result.failed += 1
            result.errors.append(f"identity {identity_id}: transcode error: {exc}")
            if progress_cb is not None:
                progress_cb(flac_path_db.name, idx, len(rows))
            continue

        if mp3_path is None:
            result.skipped += 1
            if progress_cb is not None:
                progress_cb(flac_path_db.name, idx, len(rows))
            continue

        _upsert_mp3_asset_row(
            conn,
            path=mp3_path,
            identity_id=identity_id,
            asset_id=asset_id,
            profile="mp3_320_cbr",
            status="verified",
            source_root=source_root,
            source_path=source_path,
            transcoded_at=datetime.now(timezone.utc).isoformat(),
        )
        conn.commit()
        result.built += 1
        if progress_cb is not None:
            progress_cb(flac_path_db.name, idx, len(rows))

    return result


@dataclass
class Mp3ReconcileResult:
    linked: int = 0
    provisional: int = 0
    unmatched: int = 0
    skipped_existing: int = 0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"mp3 reconcile: linked={self.linked} provisional={self.provisional} "
            f"skipped_existing={self.skipped_existing} "
            f"unmatched={self.unmatched}"
        )


def reconcile_mp3_library(
    conn: sqlite3.Connection,
    *,
    mp3_root: Path,
    dry_run: bool = True,
    progress_cb: ProgressCallback | None = None,
) -> Mp3ReconcileResult:
    """Scan mp3_root and register discovered MP3s in mp3_asset.

    Matches each MP3 to a canonical identity via:
    1. ISRC tag (TSRC ID3 frame) — preferred
    2. Exact lower-cased title + artist match against track_identity

    Skips files that already have an mp3_asset row.
    When dry_run=True, counts what would be linked without writing anything.
    When no master exists, writes a provisional lineage row instead of dropping
    the MP3 on the floor.
    """
    try:
        from mutagen.id3 import ID3, ID3NoHeaderError  # type: ignore[import-untyped]
        from mutagen.mp3 import MP3  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "mutagen is required for mp3 reconcile. "
            "Install it with: pip install mutagen"
        ) from exc

    result = Mp3ReconcileResult()
    mp3_root_fs = normalize_path(mp3_root)
    run_id = f"mp3_reconcile:{mp3_root.name}:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
    ingest_session = run_id
    source_root = str(mp3_root_fs)

    mp3_files = sorted(mp3_root_fs.rglob("*.mp3"))
    total = len(mp3_files)
    for idx, mp3_file in enumerate(mp3_files, 1):
        mp3_file_fs = normalize_path(mp3_file)
        try:
            tags = ID3(str(mp3_file_fs))
        except ID3NoHeaderError:
            result.errors.append(f"No ID3 header: {mp3_file}")
            if progress_cb is not None:
                progress_cb(mp3_file.name, idx, total)
            continue
        except Exception as exc:
            result.errors.append(f"Cannot read tags ({exc}): {mp3_file}")
            if progress_cb is not None:
                progress_cb(mp3_file.name, idx, total)
            continue

        isrc_frame = tags.get("TSRC")
        isrc_raw = str(isrc_frame.text[0]) if isrc_frame and isrc_frame.text else None
        title_frame = tags.get("TIT2")
        title_raw = str(title_frame.text[0]) if title_frame and title_frame.text else None
        artist_frame = tags.get("TPE1")
        artist_raw = str(artist_frame.text[0]) if artist_frame and artist_frame.text else None

        identity_id: int | None = None
        tier: int | None = None
        isrc_key = normalize_isrc(isrc_raw)
        resolver_result = resolve_identity(
            conn,
            ResolverInput(
                path=str(mp3_file_fs),
                isrc=isrc_key or isrc_raw,
                artist=artist_raw,
                title=title_raw,
                source_system="mp3_reconcile",
                source_ref=str(mp3_file_fs),
                payload={"zone": mp3_root.name, "run_id": run_id},
            ),
            persist=not dry_run,
            allow_text_auto_match=False,
        )
        accepted_by = str(resolver_result.reasons.get("accepted_by", ""))
        if resolver_result.decision == "accepted" and resolver_result.identity_id is not None:
            identity_id = resolver_result.identity_id
            tier = {
                "asset_link": 1,
                "lexicon_path": 1,
                "content_sha256": 1,
                "streaminfo_md5": 1,
                "isrc": 2,
                "provider_id": 2,
                "chromaprint": 2,
            }.get(accepted_by)
        elif resolver_result.decision in {"ambiguous", "candidate_only"}:
            result.unmatched += 1
            candidate_ids = [
                candidate.identity_id for candidate in resolver_result.candidates
            ]
            result.errors.append(
                f"Identity review required for {mp3_file.name} "
                f"(decision={resolver_result.decision}, candidates={candidate_ids})"
            )
            _insert_reconcile_log_row(
                conn,
                run_id=run_id,
                source="mp3_reconcile",
                action="identity_review_required",
                confidence="LOW",
                mp3_path=str(mp3_file),
                identity_id=None,
                details={
                    "decision": resolver_result.decision,
                    "candidate_identity_ids": candidate_ids,
                    "isrc": isrc_raw,
                    "title": title_raw,
                    "artist": artist_raw,
                },
                dry_run=dry_run,
            )
            if progress_cb is not None:
                progress_cb(mp3_file.name, idx, total)
            continue

        if identity_id is None:
            result.unmatched += 1
            result.provisional += 1
            result.errors.append(
                f"No identity match for {mp3_file.name} "
                f"(isrc={isrc_raw!r}, title={title_raw!r}, artist={artist_raw!r}) "
                "-> stubbed provisional record"
            )
            stub_id: int | None = None
            if not dry_run:
                import uuid as _uuid

                stub_key = f"stub_{_uuid.uuid4().hex[:12]}"
                stub_id = _insert_track_identity_stub(
                    conn,
                    identity_key=stub_key,
                    title=title_raw or mp3_file.stem,
                    artist=artist_raw,
                    isrc=isrc_raw,
                    source="mp3_reconcile",
                )
                now_iso = datetime.now(timezone.utc).isoformat()
                bitrate = sample_rate = None
                duration_s = None
                try:
                    audio = MP3(str(mp3_file_fs))
                    bitrate = int(audio.info.bitrate) if getattr(audio.info, "bitrate", None) else None
                    sample_rate = int(audio.info.sample_rate) if getattr(audio.info, "sample_rate", None) else None
                    duration_s = round(float(audio.info.length), 3) if getattr(audio.info, "length", None) else None
                except Exception:
                    pass
                _upsert_mp3_asset_row(
                    conn,
                    path=mp3_file_fs,
                    identity_id=stub_id,
                    asset_id=None,
                    profile="mp3_320_cbr_reconciled",
                    status="unverified",
                    source="mp3_reconcile",
                    zone=mp3_root.name,
                    content_sha256=_compute_sha256(mp3_file_fs),
                    size_bytes=mp3_file_fs.stat().st_size,
                    bitrate=bitrate,
                    sample_rate=sample_rate,
                    duration_s=duration_s,
                    source_root=source_root,
                    source_path=str(mp3_file_fs),
                    ingest_session=ingest_session,
                    ingest_at=now_iso,
                    reconciled_at=now_iso,
                )
                conn.commit()
            _insert_reconcile_log_row(
                conn,
                run_id=run_id,
                source="mp3_reconcile",
                action="orphan_stubbed",
                confidence="",
                mp3_path=str(mp3_file),
                identity_id=stub_id,
                details={
                    "isrc": isrc_raw,
                    "title": title_raw,
                    "artist": artist_raw,
                    "source_root": source_root,
                    "stub_identity_id": stub_id,
                },
                dry_run=dry_run,
            )
            if progress_cb is not None:
                progress_cb(mp3_file.name, idx, total)
            continue

        # Already registered?
        existing = conn.execute(
            "SELECT id FROM mp3_asset WHERE path = ?", (str(mp3_file),)
        ).fetchone()
        if existing:
            result.skipped_existing += 1
            if progress_cb is not None:
                progress_cb(mp3_file.name, idx, total)
            continue

        # Find the master asset for this identity.
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

        confidence = "HIGH" if tier in (1, 2) else "MEDIUM" if tier == 3 else ""
        if dry_run:
            if master_row is None:
                result.provisional += 1
                result.unmatched += 1
            else:
                result.linked += 1
            _insert_reconcile_log_row(
                conn,
                run_id=run_id,
                source="mp3_reconcile",
                    action="provisional_registered" if master_row is None else f"matched_tier{tier}",
                confidence=confidence,
                mp3_path=str(mp3_file),
                identity_id=identity_id,
                details={
                    "tier": tier,
                    "zone": mp3_root.name,
                    "has_master": master_row is not None,
                    "source_root": source_root,
                },
                dry_run=dry_run,
            )
            if progress_cb is not None:
                progress_cb(mp3_file.name, idx, total)
            continue

        bitrate = sample_rate = None
        duration_s = None
        try:
            audio = MP3(str(mp3_file_fs))
            bitrate = int(audio.info.bitrate) if getattr(audio.info, "bitrate", None) else None
            sample_rate = int(audio.info.sample_rate) if getattr(audio.info, "sample_rate", None) else None
            duration_s = round(float(audio.info.length), 3) if getattr(audio.info, "length", None) else None
        except Exception:
            pass

        now_iso = datetime.now(timezone.utc).isoformat()
        content_sha256 = _compute_sha256(mp3_file_fs)
        size_bytes = mp3_file_fs.stat().st_size
        if master_row is None:
            result.errors.append(
                f"identity {identity_id}: no master asset found for {mp3_file.name}"
            )
            result.unmatched += 1
            _upsert_mp3_asset_row(
                conn,
                path=mp3_file_fs,
                identity_id=identity_id,
                asset_id=None,
                profile="mp3_320_cbr_reconciled",
                status="unverified",
                source="mp3_reconcile",
                zone=mp3_root.name,
                content_sha256=content_sha256,
                size_bytes=size_bytes,
                bitrate=bitrate,
                sample_rate=sample_rate,
                duration_s=duration_s,
                source_root=source_root,
                source_path=str(mp3_file_fs),
                ingest_session=ingest_session,
                ingest_at=now_iso,
                reconciled_at=now_iso,
            )
            conn.commit()
            result.provisional += 1
            _insert_reconcile_log_row(
                conn,
                run_id=run_id,
                source="mp3_reconcile",
                action="provisional_registered",
                confidence=confidence,
                mp3_path=str(mp3_file),
                identity_id=identity_id,
                details={
                    "tier": tier,
                    "zone": mp3_root.name,
                    "has_master": False,
                    "source_root": source_root,
                    "content_sha256": content_sha256,
                },
                dry_run=dry_run,
            )
        else:
            _upsert_mp3_asset_row(
                conn,
                path=mp3_file_fs,
                identity_id=identity_id,
                asset_id=int(master_row[0]),
                profile="mp3_320_cbr_reconciled",
                status="verified",
                source="mp3_reconcile",
                zone=mp3_root.name,
                content_sha256=content_sha256,
                size_bytes=size_bytes,
                bitrate=bitrate,
                sample_rate=sample_rate,
                duration_s=duration_s,
                source_root=source_root,
                source_path=str(mp3_file_fs),
                ingest_session=ingest_session,
                ingest_at=now_iso,
                reconciled_at=now_iso,
            )
            conn.commit()
            result.linked += 1
        confidence = "HIGH" if tier in (1, 2) else "MEDIUM" if tier == 3 else ""
        _insert_reconcile_log_row(
            conn,
            run_id=run_id,
            source="mp3_reconcile",
            action=f"matched_tier{tier if tier is not None else 'unknown'}",
            confidence=confidence,
            mp3_path=str(mp3_file),
            identity_id=identity_id,
                details={
                    "tier": tier,
                    "zone": mp3_root.name,
                    "has_master": True,
                    "source_root": source_root,
                    "content_sha256": content_sha256,
                },
                dry_run=dry_run,
            )
        if progress_cb is not None:
            progress_cb(mp3_file.name, idx, total)

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
    path = normalize_path(path)
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

    path = normalize_path(path)
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
        root_fs = normalize_path(root)
        for mp3 in sorted(root_fs.rglob("*.mp3")):
            if exclude_patterns:
                skip = any(
                    re.search(pat, str(mp3)) for pat in exclude_patterns
                )
                if skip:
                    continue
            all_files.append((mp3, zone))

    all_files.sort(key=lambda item: str(item[0]))
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


def _parse_filename(filename: str) -> tuple[str, str] | None:
    """Return (artist_norm, title_norm) from a filename or None."""
    m = _FILENAME_RE.match(filename)
    if not m:
        return None
    artist = normalize_artist_for_match(m.group("artist"))
    title = normalize_title_for_match(m.group("title"))
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
    progress_cb: ProgressCallback | None = None,
) -> dict:
    """Reconcile a scan CSV against the DB using the shared v3 resolver.

    Strong evidence such as ISRC may bind automatically. Filename and ID3
    title/artist evidence creates review candidates instead of durable links.
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

    with (
        open(scan_csv, newline="", encoding="utf-8") as csv_fh,
        open(jsonl_path, "a", encoding="utf-8") as jsonl_fh,
    ):
        reader = csv.DictReader(csv_fh)
        rows = list(reader)

    total = len(rows)
    try:
        with open(jsonl_path, "a", encoding="utf-8") as jsonl_fh:
            for idx, row in enumerate(rows, 1):
                path_str = row.get("path", "")
                try:
                    _process_reconcile_row(
                        conn=conn,
                        row=row,
                        path_str=path_str,
                        run_id=run_id,
                        counters=counters,
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
                if progress_cb is not None:
                    progress_cb(Path(path_str).name, idx, total)
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
    mp3_file_fs = normalize_path(Path(path_str))
    isrc_raw = (row.get("id3_isrc") or "").strip() or None
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

    parsed = _parse_filename(filename)
    filename_artist = filename_title = None
    if parsed:
        filename_artist, filename_title = parsed
    resolver_result = resolve_identity(
        conn,
        ResolverInput(
            path=path_str,
            content_sha256=sha256,
            isrc=normalize_isrc(isrc_raw),
            artist=id3_artist or filename_artist,
            title=id3_title or filename_title,
            duration_s=duration_s,
            source_system="mp3_reconcile_scan",
            source_ref=path_str,
            payload={"run_id": run_id, "zone": zone},
        ),
        persist=not dry_run,
        allow_text_auto_match=False,
    )
    accepted_by = str(resolver_result.reasons.get("accepted_by", ""))
    if resolver_result.decision == "accepted" and resolver_result.identity_id is not None:
        identity_id = resolver_result.identity_id
        tier = {
            "asset_link": 1,
            "lexicon_path": 1,
            "content_sha256": 1,
            "streaminfo_md5": 1,
            "isrc": 2,
            "provider_id": 2,
            "chromaprint": 2,
        }.get(accepted_by)
        confidence = "HIGH"
    elif resolver_result.decision in {"ambiguous", "candidate_only"}:
        if resolver_result.decision == "ambiguous":
            counters["conflicts"] += 1
            action = "CONFLICT"
        else:
            counters["fuzzy"] += 1
            action = "candidate_review_required"
        candidate_ids = [candidate.identity_id for candidate in resolver_result.candidates]
        _log_reconcile(
            conn,
            run_id=run_id,
            source="mp3_reconcile",
            action=action,
            confidence="LOW",
            mp3_path=path_str,
            identity_id=None,
            lexicon_track_id=None,
            details={
                "decision": resolver_result.decision,
                "candidate_identity_ids": candidate_ids,
                "isrc": isrc_raw,
                "id3_title": id3_title,
                "id3_artist": id3_artist,
            },
            jsonl_fh=jsonl_fh,
            dry_run=dry_run,
        )
        return

    # No match → stub
    if identity_id is None:
        action = "orphan_stubbed"
        stub_id: int | None = None

        if not dry_run:
            # Insert track_identity stub
            import uuid as _uuid
            import sqlite3 as _sqlite3
            stub_key = f"stub_{_uuid.uuid4().hex[:12]}"

            try:
                columns = {
                    str(r[1])
                    for r in conn.execute("PRAGMA table_info(track_identity)").fetchall()
                }
            except _sqlite3.OperationalError:
                columns = set()

            from datetime import datetime as _dt, timezone as _tz

            values = {
                "identity_key": stub_key,
                "canonical_title": id3_title or filename,
                "canonical_artist": id3_artist or "",
                "artist_norm": normalize_artist_for_match(id3_artist),
                "title_norm": normalize_title_for_match(id3_title or filename),
                # v3 ingestion provenance (required on v3 schemas)
                "ingested_at": _dt.now(tz=_tz.utc).isoformat(),
                "ingestion_method": "mp3_reconcile",
                "ingestion_source": "mp3_reconcile_stub",
                "ingestion_confidence": "uncertain",
                # legacy/minimal schemas
                "status": "stub_pending_master",
                "source": "mp3_reconcile",
            }

            insert_keys = [k for k in values.keys() if k in columns]
            if insert_keys:
                cols_sql = ", ".join(insert_keys)
                placeholders = ", ".join("?" for _ in insert_keys)
                params = [values[k] for k in insert_keys]
                conn.execute(
                    f"INSERT OR IGNORE INTO track_identity ({cols_sql}) VALUES ({placeholders})",
                    params,
                )
            stub_row = conn.execute(
                "SELECT id FROM track_identity WHERE identity_key = ?", (stub_key,)
            ).fetchone()
            stub_id = stub_row[0] if stub_row else None

            if stub_id:
                now_iso = datetime.now(timezone.utc).isoformat()
                _upsert_mp3_asset_row(
                    conn,
                    path=mp3_file_fs,
                    identity_id=stub_id,
                    asset_id=None,
                    profile="mp3_320_cbr_reconciled",
                    status="unverified",
                    source="mp3_reconcile",
                    zone=zone,
                    content_sha256=sha256,
                    size_bytes=int(row.get("size_bytes") or 0) or None,
                    bitrate=bitrate,
                    sample_rate=sample_rate,
                    duration_s=duration_s,
                    source_root=zone,
                    source_path=path_str,
                    ingest_session=run_id,
                    ingest_at=now_iso,
                    reconciled_at=now_iso,
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
    confidence = "HIGH" if tier in (1, 2) else "MEDIUM" if tier == 3 else ""
    action_name = f"matched_tier{tier}"
    if tier == 1:
        counters["matched_t1"] += 1
    elif tier == 2:
        counters["matched_t2"] += 1
    elif tier == 3:
        counters["matched_t3"] += 1

    if not dry_run:
        now_iso = datetime.now(timezone.utc).isoformat()
        size_bytes = int(row.get("size_bytes") or 0) or None
        # Insert this MP3 first.
        _upsert_mp3_asset_row(
            conn,
            path=mp3_file_fs,
            identity_id=identity_id,
            asset_id=None,
            profile="mp3_320_cbr_reconciled",
            status="unverified",
            source="mp3_reconcile",
            zone=zone,
            content_sha256=sha256,
            size_bytes=size_bytes,
            bitrate=bitrate,
            sample_rate=sample_rate,
            duration_s=duration_s,
            source_root=zone,
            source_path=path_str,
            ingest_session=run_id,
            ingest_at=now_iso,
            reconciled_at=now_iso,
        )

        # Keep the highest bitrate MP3 as 'verified', others 'superseded'.
        # This must also promote the first (only) MP3 for an identity to 'verified',
        # otherwise Stage 3 `dj backfill` will admit zero rows.
        all_mp3s = conn.execute(
            "SELECT id, bitrate FROM mp3_asset WHERE identity_id = ? AND status != 'superseded'",
            (identity_id,),
        ).fetchall()
        if all_mp3s:
            best_row = max(all_mp3s, key=lambda r: r[1] or 0)
            best_id = best_row[0]
            for mp3_row in all_mp3s:
                if mp3_row[0] == best_id:
                    conn.execute(
                        "UPDATE mp3_asset SET status='verified' WHERE id=?",
                        (mp3_row[0],),
                    )
                elif len(all_mp3s) > 1:
                    conn.execute(
                        "UPDATE mp3_asset SET status='superseded' WHERE id=?",
                        (mp3_row[0],),
                    )

    _log_reconcile(
        conn,
        run_id=run_id,
        source="mp3_reconcile",
        action=action_name,
        confidence=confidence,
        mp3_path=path_str,
        identity_id=identity_id,
        lexicon_track_id=None,
        details={"tier": tier, "zone": zone, "bitrate": bitrate},
        jsonl_fh=jsonl_fh,
        dry_run=dry_run,
    )


# ---------------------------------------------------------------------------
# Task 7 — generate_missing_masters_report()
# ---------------------------------------------------------------------------


def generate_missing_masters_report(
    conn: sqlite3.Connection,
    *,
    out_path: Path,
    run_id: str,
    log_dir: Path,
) -> dict:
    """Generate a Markdown report of missing lossless masters for DJ MP3s.

    Section A — Orphaned MP3s (no identity or stub identity).
    Section B — lossless masters ready but no MP3 built.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = log_dir / f"reconcile_missing_masters_{run_id}.jsonl"

    def _col_exists(table: str, col: str) -> bool:
        try:
            return any(
                str(r[1]) == col
                for r in conn.execute(f"PRAGMA table_info({table})").fetchall()
            )
        except sqlite3.OperationalError:
            return False

    has_status = _col_exists("track_identity", "status")
    has_identity_key = _col_exists("track_identity", "identity_key")
    has_ingestion_method = _col_exists("track_identity", "ingestion_method")

    # Section A — orphaned mp3_asset rows
    stub_clause = "0"
    if has_status:
        stub_clause = "ti.status = 'stub_pending_master'"
    elif has_identity_key and has_ingestion_method:
        stub_clause = "ti.identity_key LIKE 'stub_%' AND ti.ingestion_method = 'mp3_reconcile'"
    elif has_identity_key:
        stub_clause = "ti.identity_key LIKE 'stub_%'"

    orphan_rows = conn.execute(
        f"""
        SELECT
          ma.path,
          ma.zone,
          ma.bitrate,
          ma.lexicon_track_id,
          ma.identity_id,
          ti.canonical_title,
          ti.canonical_artist,
          ti.canonical_bpm,
          ti.canonical_key,
          dp.energy
        FROM mp3_asset ma
        LEFT JOIN track_identity ti ON ti.id = ma.identity_id
        LEFT JOIN dj_track_profile dp ON dp.identity_id = ma.identity_id
        WHERE ma.identity_id IS NULL OR ({stub_clause})
        """,
    ).fetchall()

    # Determine playlist membership for priority
    in_playlist: set[int] = set()
    for r in conn.execute(
        """
        SELECT DISTINCT da.identity_id
        FROM dj_playlist_track dpt
        JOIN dj_admission da ON da.id = dpt.dj_admission_id
        """
    ).fetchall():
        if r and r[0] is not None:
            in_playlist.add(int(r[0]))

    section_a: list[tuple[str, dict]] = []  # (priority, row)
    high = medium = low = 0

    for r in orphan_rows:
        (
            path,
            zone,
            bitrate,
            lex_id,
            identity_id,
            title,
            artist,
            bpm,
            key,
            energy,
        ) = r

        is_high = False
        if identity_id is not None and int(identity_id) in in_playlist:
            is_high = True
        if not is_high and lex_id is not None and energy is not None:
            try:
                is_high = int(energy) > 5
            except Exception:
                is_high = False

        if is_high:
            prio = "HIGH"
            high += 1
        elif bpm is not None and key is not None:
            prio = "MEDIUM"
            medium += 1
        else:
            prio = "LOW"
            low += 1
        section_a.append(
            (
                prio,
                {
                    "priority": prio,
                    "zone": zone or "",
                    "title": title or "",
                    "artist": artist or "",
                    "path": path,
                    "bitrate": bitrate,
                },
            )
        )

    # Sort by priority
    _prio_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    section_a.sort(key=lambda x: (_prio_order[x[0]], str(x[1].get("path") or "")))

    # Section B — identities with asset_link but no mp3_asset
    section_b: list[tuple[object, object, object, object, object]] = []
    try:
        section_b_rows = conn.execute(
            """
            SELECT identity_id, identity_key, canonical_artist, canonical_title, asset_path
            FROM v_dj_ready_candidates
            WHERE NOT EXISTS (
                SELECT 1 FROM mp3_asset ma WHERE ma.identity_id = v_dj_ready_candidates.identity_id
            )
            """
        ).fetchall()
        section_b = [(r[0], r[1], r[2], r[3], r[4]) for r in section_b_rows]
    except sqlite3.OperationalError:
        section_b_rows = conn.execute(
            """
            SELECT ti.identity_key, ti.canonical_artist, ti.canonical_title, af.path
            FROM track_identity ti
            JOIN asset_link al ON al.identity_id = ti.id
            JOIN asset_file af ON af.id = al.asset_id
            WHERE NOT EXISTS (
                SELECT 1 FROM mp3_asset ma WHERE ma.identity_id = ti.id
            )
            ORDER BY lower(ti.canonical_artist), lower(ti.canonical_title)
            """
        ).fetchall()
        section_b = [(None, r[0], r[1], r[2], r[3]) for r in section_b_rows]

    lines: list[str] = [
        "# Missing Masters Report",
        f"\nGenerated: {datetime.now(tz=timezone.utc).isoformat()}",
        "",
        f"## Section A — Orphaned MP3s ({len(section_a)} total)",
        f"Priority breakdown: HIGH={high} MEDIUM={medium} LOW={low}",
        "",
    ]
    for prio, row in section_a:
        artist = str(row.get("artist") or "?").strip() or "?"
        title = str(row.get("title") or "?").strip() or "?"
        zone = str(row.get("zone") or "").strip()
        path = str(row.get("path") or "")
        bitrate = row.get("bitrate")
        br = str(bitrate) if bitrate is not None else ""
        lines.append(f"- [ ] `{prio}` | `{zone}` | {artist} — {title} | `{path}` | {br}")

    lines += [
        "",
        f"## Section B — FLACs ready, no MP3 ({len(section_b)} total)",
        "",
    ]
    for identity_id, identity_key, artist, title, asset_path in section_b:
        suggest = f"tagslut mp3 build --identity-ids {identity_id}" if identity_id else "tagslut mp3 build --identity-ids <id>"
        label = f"`{identity_key}` | {artist or '?'} — {title or '?'} | `{asset_path}` | `{suggest}`"
        lines.append(f"- [ ] {label}")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with open(jsonl_path, "a", encoding="utf-8") as jsonl_fh:
        jsonl_fh.write(
            json.dumps(
                {
                    "ts": datetime.now(tz=timezone.utc).isoformat(),
                    "run_id": run_id,
                    "action": "report_generated",
                    "path": str(out_path),
                    "result": "ok",
                    "details": {
                        "section_a": len(section_a),
                        "high": high,
                        "medium": medium,
                        "low": low,
                        "section_b": len(section_b),
                    },
                }
            )
            + "\n"
        )

    return {
        "section_a_count": len(section_a),
        "high": high,
        "medium": medium,
        "low": low,
        "section_b_count": len(section_b),
    }
