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


def build_mp3_from_identity(
    conn: sqlite3.Connection,
    *,
    identity_ids: list[int] | None = None,
    dj_root: Path,
    dry_run: bool = True,
) -> Mp3BuildResult:
    """Transcode preferred FLAC master(s) to MP3 and register in mp3_asset.

    Only processes identities that do not already have a mp3_asset row with
    status='ok'. Uses the preferred_asset table to find the canonical FLAC.

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
