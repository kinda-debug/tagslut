"""
USB export engine for Pioneer CDJ compatibility.

Copies MP3/FLAC files to a USB drive and writes a Rekordbox-compatible
PIONEER/ database using pyrekordbox.

Master FLAC files in the source library are never modified.
"""
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("tagslut.usb_export")

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

    try:
        db = pyrekordbox.Rb6Database(pioneer_dir / "rekordbox.db")
    except Exception:
        db = pyrekordbox.Rb6Database.create(pioneer_dir / "rekordbox.db")

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
    logger.info("Rekordbox DB written: %s (%d tracks)", pioneer_dir, len(track_ids))


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
    except Exception:
        return None, None
