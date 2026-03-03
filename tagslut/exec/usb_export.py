"""
USB export engine for Pioneer CDJ compatibility.

Copies MP3/FLAC files to a USB drive and writes a Rekordbox-compatible
PIONEER/ database using pyrekordbox.

Master FLAC files in the source library are never modified.
"""
import logging
import sqlite3
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".mp3", ".flac", ".aif", ".aiff", ".wav", ".m4a"}


def scan_source(source_dir: Path) -> List[Path]:
    """
    Recursively scan source_dir and return all supported audio files.
    """
    return sorted(
        p
        for p in source_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def copy_to_usb(
    tracks: List[Path],
    usb_path: Path,
    crate_name: str,
    dry_run: bool = False,
) -> List[Path]:
    """
    Copy track files to USB under /MUSIC/<crate_name>/.

    Returns list of destination paths (for database registration).
    Does not modify source files.
    """
    dest_dir = usb_path / "MUSIC" / crate_name
    copied: List[Path] = []

    for track in tracks:
        dest = dest_dir / track.name
        if dry_run:
            logger.info("[DRY RUN] Would copy: %s -> %s", track, dest)
            copied.append(dest)
            continue

        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(track, dest)
        logger.info("Copied: %s -> %s", track, dest)
        copied.append(dest)

    return copied


def write_rekordbox_db(
    tracks: List[Path],
    usb_path: Path,
    crate_name: str,
    dry_run: bool = False,
) -> None:
    """
    Write the PIONEER/ database to the USB using pyrekordbox.

    Creates a crate named `crate_name` containing all tracks.
    BPM and key are read from file tags if available.

    Raises ImportError if pyrekordbox is not installed.
    """
    if dry_run:
        logger.info("[DRY RUN] Would write Rekordbox DB for %d tracks", len(tracks))
        return

    try:
        import pyrekordbox
    except ImportError as e:
        raise ImportError(
            "pyrekordbox is required for USB export. "
            "Run: poetry add pyrekordbox"
        ) from e

    pioneer_dir = usb_path / "PIONEER"
    pioneer_dir.mkdir(parents=True, exist_ok=True)
    db_path = pioneer_dir / "rekordbox.db"

    # pyrekordbox has divergent APIs across versions. Prefer native bindings,
    # and fall back to a lightweight local DB if creation/open is unavailable.
    if hasattr(pyrekordbox, "Rb6Database"):
        _write_rekordbox_db_legacy(pyrekordbox, tracks, db_path, crate_name)
    elif hasattr(pyrekordbox, "Rekordbox6Database"):
        _write_rekordbox_db_modern(pyrekordbox, tracks, db_path, crate_name)
    else:
        logger.warning(
            "Unsupported pyrekordbox API surface; writing fallback DB at %s",
            db_path,
        )
        _write_fallback_rekordbox_db(tracks, db_path, crate_name)


def _write_rekordbox_db_legacy(
    pyrekordbox_module: object,
    tracks: List[Path],
    db_path: Path,
    crate_name: str,
) -> None:
    db_cls = getattr(pyrekordbox_module, "Rb6Database")

    try:
        db = db_cls(db_path)
    except Exception as e:
        logger.warning("Failed to open existing Rekordbox DB at %s: %s", db_path, e)
        db = db_cls.create(db_path)

    track_ids = []
    for track_path in tracks:
        try:
            bpm, key = _read_bpm_key(track_path)
            track_id = db.add_track(
                path=str(track_path),
                bpm=bpm,
                key=key,
            )
            track_ids.append(track_id)
        except Exception as exc:
            logger.warning("Failed to add track %s to DB: %s", track_path, exc)

    if track_ids:
        db.create_playlist(name=crate_name, track_ids=track_ids)

    db.save()
    logger.info("Rekordbox DB written: %s (%d tracks)", db_path.parent, len(track_ids))


def _write_rekordbox_db_modern(
    pyrekordbox_module: object,
    tracks: List[Path],
    db_path: Path,
    crate_name: str,
) -> None:
    db_cls = getattr(pyrekordbox_module, "Rekordbox6Database")
    if not db_path.exists():
        logger.warning(
            "Rekordbox6Database cannot create new DB at %s; writing fallback DB.",
            db_path,
        )
        _write_fallback_rekordbox_db(tracks, db_path, crate_name)
        return

    try:
        db = db_cls(db_path, unlock=False)
    except Exception as exc:
        logger.warning("Failed to open Rekordbox6 DB at %s: %s", db_path, exc)
        _write_fallback_rekordbox_db(tracks, db_path, crate_name)
        return

    written = 0
    try:
        playlist = db.create_playlist(crate_name)
        for track_path in tracks:
            try:
                content = db.add_content(path=str(track_path))
                db.add_to_playlist(playlist, content)
                written += 1
            except Exception as exc:
                logger.warning("Failed to add track %s to Rekordbox6 DB: %s", track_path, exc)
        db.commit()
        logger.info("Rekordbox6 DB updated: %s (%d tracks)", db_path.parent, written)
    finally:
        db.close()


def _write_fallback_rekordbox_db(
    tracks: List[Path],
    db_path: Path,
    crate_name: str,
) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS exported_tracks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    crate_name TEXT NOT NULL,
                    track_path TEXT NOT NULL,
                    bpm REAL,
                    musical_key TEXT,
                    exported_at TEXT NOT NULL
                )
                """
            )
            now = datetime.now().isoformat(timespec="seconds")
            rows = []
            for track_path in tracks:
                bpm, key = _read_bpm_key(track_path)
                rows.append((crate_name, str(track_path), bpm, key, now))
            conn.executemany(
                """
                INSERT INTO exported_tracks (
                    crate_name, track_path, bpm, musical_key, exported_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                rows,
            )
    finally:
        conn.close()
    logger.info("Fallback Rekordbox DB written: %s (%d tracks)", db_path.parent, len(tracks))


def write_manifest(
    tracks: List[Path],
    usb_path: Path,
    crate_name: str,
) -> Path:
    """
    Write a human-readable manifest file to the USB root.
    Returns the manifest path.
    """
    manifest_path = usb_path / f"gig_manifest_{datetime.now().strftime('%Y-%m-%d')}.txt"
    lines = [
        "# tagslut gig manifest",
        f"# Crate: {crate_name}",
        f"# Exported: {datetime.now().isoformat()}",
        f"# Tracks: {len(tracks)}",
        "",
    ]
    for i, track in enumerate(tracks, 1):
        lines.append(f"{i:04d}  {track.name}")

    manifest_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Manifest written: %s", manifest_path)
    return manifest_path


def _read_bpm_key(path: Path) -> tuple[Optional[float], Optional[str]]:
    """Read BPM and key from file tags. Returns (None, None) on failure."""
    try:
        from mutagen import File as MutagenFile  # type: ignore  # TODO: mypy-strict

        f = MutagenFile(path, easy=True)
        if f is None:
            return None, None
        bpm_raw = f.get("bpm") or f.get("TBPM")
        key_raw = f.get("initialkey") or f.get("TKEY")
        bpm = float(bpm_raw[0]) if bpm_raw else None
        key = str(key_raw[0]) if key_raw else None
        return bpm, key
    except Exception as e:
        logger.warning("Failed to read BPM/key from %s: %s", path, e)
        return None, None
