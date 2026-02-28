"""
Gig set builder: orchestrates filter -> transcode -> USB export pipeline.
"""

import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from tagslut.exec.transcoder import TranscodeError, transcode_to_mp3
from tagslut.exec.usb_export import copy_to_usb, write_manifest, write_rekordbox_db
from tagslut.filters.gig_filter import parse_filter

logger = logging.getLogger("tagslut.gig_builder")


@dataclass
class GigBuildResult:
    gig_name: str
    tracks_found: int = 0
    tracks_transcoded: int = 0
    tracks_copied: int = 0
    tracks_skipped: int = 0
    errors: List[str] = field(default_factory=list)
    manifest_path: Optional[Path] = None

    def summary(self) -> str:
        return (
            f"Gig '{self.gig_name}': "
            f"{self.tracks_found} found, "
            f"{self.tracks_transcoded} transcoded, "
            f"{self.tracks_copied} exported, "
            f"{self.tracks_skipped} skipped, "
            f"{len(self.errors)} errors"
        )


class GigBuilder:
    """
    Builds a gig set end-to-end:
      1. Query inventory for matching tracks
      2. Ensure MP3 exists for each track (transcode if needed)
      3. Copy to USB
      4. Write Rekordbox database
      5. Write manifest
      6. Register gig set in DB
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        dj_pool_dir: Path,
        mp3_bitrate: int = 320,
    ) -> None:
        self._conn = conn
        self._dj_pool_dir = dj_pool_dir
        self._mp3_bitrate = mp3_bitrate

    def build(
        self,
        name: str,
        filter_expr: str,
        usb_path: Path,
        dry_run: bool = False,
    ) -> GigBuildResult:
        result = GigBuildResult(gig_name=name)
        where, params = parse_filter(filter_expr)

        query = (
            "SELECT path, dj_pool_path, canonical_artist, canonical_title "
            "FROM files WHERE "
            + where
            + " AND path IS NOT NULL"
        )
        rows = self._conn.execute(query, params).fetchall()

        result.tracks_found = len(rows)
        if not rows:
            logger.warning("No tracks matched filter: %s", filter_expr)
            return result

        if dry_run:
            return result

        mp3_tracks: List[Path] = []

        for row in rows:
            flac_path = Path(row[0])
            existing_mp3 = Path(row[1]) if row[1] else None

            if existing_mp3 and existing_mp3.exists():
                mp3_tracks.append(existing_mp3)
                result.tracks_skipped += 1
                continue

            if not flac_path.exists():
                result.errors.append(f"Master not found: {flac_path}")
                continue

            try:
                mp3_path = transcode_to_mp3(
                    flac_path,
                    self._dj_pool_dir,
                    bitrate=self._mp3_bitrate,
                )
                self._conn.execute(
                    "UPDATE files SET dj_pool_path = ? WHERE path = ?",
                    (str(mp3_path), str(flac_path)),
                )
                mp3_tracks.append(mp3_path)
                result.tracks_transcoded += 1
            except TranscodeError as exc:
                result.errors.append(str(exc))

        dest_tracks = copy_to_usb(mp3_tracks, usb_path, name, dry_run=False)
        result.tracks_copied = len(dest_tracks)

        write_rekordbox_db(dest_tracks, usb_path, name, dry_run=False)
        result.manifest_path = write_manifest(dest_tracks, usb_path, name)

        exported_at = datetime.now().isoformat()
        self._conn.execute(
            """
            INSERT INTO gig_sets (name, filter_expr, usb_path, track_count, exported_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, filter_expr, str(usb_path), result.tracks_copied, exported_at),
        )

        for row in rows:
            self._conn.execute(
                "UPDATE files SET last_exported_usb = ? WHERE path = ?",
                (exported_at, row[0]),
            )
        self._conn.commit()

        return result
