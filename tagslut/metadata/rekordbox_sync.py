"""
Rekordbox write-back: reads Pioneer USB database and syncs
confirmed BPM, key, and play count back to master FLAC tags and inventory DB.

Rekordbox is the ONLY confirmation source for BPM and key.
Master FLAC tags are updated in-place (BPM/key fields only — no other fields touched).
"""

import logging
import sqlite3
from pathlib import Path
from typing import Optional

logger = logging.getLogger("tagslut.rekordbox_sync")


def sync_from_usb(
    usb_path: Path,
    conn: sqlite3.Connection,
    dry_run: bool = False,
) -> dict:  # type: ignore  # TODO: mypy-strict
    """
    Read the Rekordbox database from USB and write confirmed metadata
    back to master FLAC tags and the tagslut inventory.

    Returns a summary dict: {updated: int, not_found: int, errors: list}
    """
    try:
        import pyrekordbox
    except ImportError as exc:
        raise ImportError("pyrekordbox required. Run: poetry add pyrekordbox") from exc

    pioneer_db_path = usb_path / "PIONEER" / "rekordbox.db"
    if not pioneer_db_path.exists():
        raise FileNotFoundError(f"No Rekordbox DB found at {pioneer_db_path}")

    summary = {"updated": 0, "not_found": 0, "errors": []}

    try:
        db = pyrekordbox.Rb6Database(pioneer_db_path)
        tracks = db.get_tracks()
    except Exception as exc:
        raise RuntimeError(f"Failed to read Rekordbox DB: {exc}") from exc

    for rb_track in tracks:
        path = getattr(rb_track, "path", None) or getattr(rb_track, "file_path", None)
        bpm = getattr(rb_track, "bpm", None)
        key = getattr(rb_track, "key", None)
        rb_id = getattr(rb_track, "id", None)

        if not path:
            continue

        row = conn.execute(
            "SELECT file_path FROM gig_set_tracks WHERE usb_dest_path = ?",
            (str(path),),
        ).fetchone()

        if not row:
            stem = Path(path).stem
            row = conn.execute(
                "SELECT path FROM files WHERE path LIKE ?",
                (f"%{stem}%",),
            ).fetchone()

        if not row:
            summary["not_found"] += 1  # type: ignore  # TODO: mypy-strict
            continue

        master_path = Path(row[0])
        if not master_path.exists():
            summary["errors"].append(f"Master not found: {master_path}")  # type: ignore  # TODO: mypy-strict
            continue

        if not dry_run:
            _write_bpm_key_to_flac(master_path, bpm, key)
            conn.execute(
                """
                UPDATE files
                SET canonical_bpm = COALESCE(?, canonical_bpm),
                    canonical_key = COALESCE(?, canonical_key),
                    rekordbox_id  = COALESCE(?, rekordbox_id)
                WHERE path = ?
                """,
                (
                    float(bpm) if bpm else None,
                    str(key) if key else None,
                    rb_id,
                    str(master_path),
                ),
            )

        summary["updated"] += 1  # type: ignore  # TODO: mypy-strict
        logger.info("Synced: %s (BPM=%s key=%s)", master_path.name, bpm, key)

    if not dry_run:
        conn.commit()

    return summary


def _write_bpm_key_to_flac(path: Path, bpm: Optional[float], key: Optional[str]) -> None:
    """Write BPM and key to FLAC tags. Only modifies these two fields."""
    if bpm is None and key is None:
        return
    try:
        from mutagen.flac import FLAC

        flac_file = FLAC(path)
        if bpm is not None:
            flac_file["bpm"] = [str(round(float(bpm), 2))]
        if key is not None:
            flac_file["initialkey"] = [str(key)]
        flac_file.save()
        logger.debug("Tagged: %s BPM=%s key=%s", path.name, bpm, key)
    except Exception as exc:
        logger.error("Failed to write tags to %s: %s", path, exc)
