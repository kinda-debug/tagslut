"""
Gig set builder: orchestrates filter -> transcode -> USB export pipeline.
"""

import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from tagslut.exec.transcoder import TranscodeError, transcode_to_mp3, transcode_to_mp3_from_snapshot
from tagslut.exec.usb_export import copy_to_usb, write_manifest, write_rekordbox_db
from tagslut.filters.gig_filter import parse_filter
from tagslut.storage.v3 import (
    record_provenance_event,
    resolve_asset_id_by_path,
    resolve_dj_tag_snapshot_for_path,
    resolve_latest_dj_export_path,
)

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


GigResult = GigBuildResult


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

        # (master FLAC path, ready MP3 path, was_transcoded_in_this_run)
        export_pairs: List[tuple[Path, Path, bool]] = []

        for row in rows:
            flac_path = Path(row[0])
            existing_mp3 = resolve_latest_dj_export_path(self._conn, source_path=flac_path)
            if existing_mp3 is None and row[1]:
                existing_mp3 = Path(row[1])

            if existing_mp3 and existing_mp3.exists():
                export_pairs.append((flac_path, existing_mp3, False))
                result.tracks_skipped += 1
                continue

            if not flac_path.exists():
                result.errors.append(f"Master not found: {flac_path}")
                continue

            if dry_run:
                planned_mp3 = self._dj_pool_dir / f"{flac_path.stem}.mp3"
                export_pairs.append((flac_path, planned_mp3, True))
                result.tracks_transcoded += 1
                continue

            try:
                snapshot = None
                try:
                    snapshot = resolve_dj_tag_snapshot_for_path(
                        self._conn,
                        flac_path,
                        run_essentia=True,
                        dry_run=False,
                    )
                except FileNotFoundError:
                    snapshot = resolve_dj_tag_snapshot_for_path(
                        self._conn,
                        flac_path,
                        run_essentia=False,
                        dry_run=True,
                    )

                if snapshot is not None:
                    mp3_path = transcode_to_mp3_from_snapshot(
                        flac_path,
                        self._dj_pool_dir,
                        snapshot,
                        bitrate=self._mp3_bitrate,
                    )
                else:
                    mp3_path = transcode_to_mp3(
                        flac_path,
                        self._dj_pool_dir,
                        bitrate=self._mp3_bitrate,
                    )

                self._conn.execute(
                    "UPDATE files SET dj_pool_path = ? WHERE path = ?",
                    (str(mp3_path), str(flac_path)),
                )
                record_provenance_event(
                    self._conn,
                    event_type="dj_export",
                    status="success",
                    asset_id=resolve_asset_id_by_path(self._conn, flac_path),
                    identity_id=snapshot.identity_id if snapshot is not None else None,
                    source_path=str(flac_path),
                    dest_path=str(mp3_path),
                    details={
                        "format": "mp3",
                        "bitrate": self._mp3_bitrate,
                        "tool_version": "gig_builder",
                        "partial_metadata": (
                            any(
                                value is None
                                for value in (
                                    snapshot.bpm,
                                    snapshot.musical_key,
                                    snapshot.energy_1_10,
                                )
                            )
                            if snapshot is not None
                            else True
                        ),
                        "tag_snapshot": snapshot.as_dict() if snapshot is not None else None,
                    },
                )
                export_pairs.append((flac_path, mp3_path, True))
                result.tracks_transcoded += 1
            except TranscodeError as exc:
                result.errors.append(str(exc))

        if not dry_run:
            mp3_tracks = [mp3_path for _, mp3_path, _ in export_pairs]
            dest_tracks = copy_to_usb(mp3_tracks, usb_path, name, dry_run=False)
            result.tracks_copied = len(dest_tracks)

            try:
                write_rekordbox_db(dest_tracks, usb_path, name, dry_run=False)
            except Exception as exc:
                result.errors.append(f"Rekordbox export failed: {exc}")

            try:
                result.manifest_path = write_manifest(dest_tracks, usb_path, name)
            except Exception as exc:
                result.errors.append(f"Manifest write failed: {exc}")

        if dry_run:
            # Dry-run planning only: no filesystem or DB writes.
            result.tracks_copied = len(export_pairs)
            return result

        exported_at = datetime.now().isoformat()
        manifest_path_str = str(result.manifest_path) if result.manifest_path else None
        self._conn.execute(
            """
            INSERT INTO gig_sets (name, filter_expr, usb_path, manifest_path, track_count, exported_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name, filter_expr, str(usb_path), manifest_path_str, result.tracks_copied, exported_at),
        )
        gig_set_id = int(self._conn.execute("SELECT last_insert_rowid()").fetchone()[0])

        for (master_path, mp3_path, was_transcoded), usb_dest_path in zip(export_pairs, dest_tracks):
            self._conn.execute(
                """
                INSERT INTO gig_set_tracks (
                    gig_set_id, file_path, mp3_path, usb_dest_path, transcoded_at, exported_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    gig_set_id,
                    str(master_path),
                    str(mp3_path),
                    str(usb_dest_path),
                    exported_at if was_transcoded else None,
                    exported_at,
                ),
            )
            self._conn.execute(
                "UPDATE files SET last_exported_usb = ? WHERE path = ?",
                (exported_at, str(master_path)),
            )
        self._conn.commit()

        return result
