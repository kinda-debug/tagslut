"""Build and reconcile MP3 derivative assets from canonical master state.

build_mp3_from_identity()   — transcode preferred FLAC master(s) to MP3 and register
                               the result in mp3_asset
reconcile_mp3_library()     — scan an existing MP3 root, match files to canonical
                               identities via ISRC or title/artist, and register them
                               in mp3_asset without re-transcoding
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
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
