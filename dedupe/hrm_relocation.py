"""Relocate healthy files into the HRM folder structure."""

from __future__ import annotations

import json
import logging
import shutil
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from . import utils

logger = logging.getLogger(__name__)

REQUIRED_SCORE_COLUMNS = (
    "score_integrity",
    "score_audio",
    "score_tags",
    "score_total",
)


@dataclass(slots=True)
class RelocationStats:
    """Summary of an HRM relocation run."""

    moved: int
    skipped: int
    conflicts: int
    missing: int
    manifest_path: Path


class MissingScoreColumnsError(Exception):
    """Raised when required score columns are missing from the library DB."""


def _is_under_root(path: Path, root: Path) -> bool:
    """Return ``True`` when *path* is inside *root*.

    This helper does not require the path to exist on disk.
    """

    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except ValueError:
        return False


def _normalise_tag_value(value: object) -> str | None:
    """Return a string tag value, supporting list-style tags."""

    if isinstance(value, list):
        return value[0] if value else None
    if value is None:
        return None
    return str(value)


def _parse_number(value: object) -> int | None:
    """Parse an integer track/disc component from tag values."""

    try:
        return int(str(value).split("/")[0])
    except (TypeError, ValueError):
        return None


def _extract_year(tags: dict[str, object]) -> str:
    """Return a four-digit year extracted from tag metadata."""

    for key in ("date", "originalyear", "originaldate"):
        value = _normalise_tag_value(tags.get(key))
        if value:
            return value[:4]
    return "XXXX"


def _sanitise_component(value: str) -> str:
    """Return *value* safe for filesystem use by replacing ``:`` characters."""

    return value.replace(":", "꞉")


def _write_manifest(path: Path, rows: Iterable[tuple[str, str, str, float, str]]) -> None:
    """Write relocation outcomes to a TSV manifest."""

    utils.ensure_parent_directory(path)
    with path.open("w", encoding="utf8") as handle:
        handle.write("old_path\tnew_path\tchecksum\tscore_total\tresult\n")
        for row in rows:
            handle.write("\t".join(map(str, row)))
            handle.write("\n")


def _ensure_required_columns(connection: sqlite3.Connection) -> None:
    """Raise :class:`MissingScoreColumnsError` when scoring columns are absent."""

    column_names = {
        row["name"] for row in connection.execute("PRAGMA table_info(library_files)")
    }
    missing = [column for column in REQUIRED_SCORE_COLUMNS if column not in column_names]
    if missing:
        raise MissingScoreColumnsError(
            "Library database is missing required health score columns: "
            f"{', '.join(missing)}"
        )


def _remove_with_retries(path: Path, attempts: int = 3, delay: float = 0.5) -> None:
    """Remove *path* with simple retry handling."""

    for attempt in range(1, attempts + 1):
        try:
            path.unlink()
            return
        except OSError as exc:
            if attempt == attempts:
                raise
            logger.warning("Retrying removal of %s after error: %s", path, exc)
            time.sleep(delay)


def _move_with_retries(src: Path, dest: Path, attempts: int = 3, delay: float = 0.5) -> None:
    """Move *src* to *dest* with retry handling for transient filesystem errors."""

    for attempt in range(1, attempts + 1):
        try:
            shutil.move(str(src), str(dest))
            return
        except OSError as exc:
            if attempt == attempts:
                raise
            logger.warning("Retrying move %s -> %s after error: %s", src, dest, exc)
            time.sleep(delay)


def _log_skip(path: Path, reason: str) -> None:
    """Log a skipped relocation candidate with context."""

    logger.info("Skipping %s: %s", path, reason)


def _build_destination(
    src: Path,
    tags: dict[str, object],
    hrm_root: Path,
) -> Path:
    """Build the destination path for a relocation candidate."""

    artist = _normalise_tag_value(tags.get("albumartist") or tags.get("artist"))
    album = _normalise_tag_value(tags.get("album"))
    title = _normalise_tag_value(tags.get("title"))

    artist_s = _sanitise_component(artist or "Unknown Artist")
    album_s = _sanitise_component(album or "Unknown Album")
    title_s = _sanitise_component(title or "untitled")
    year = _extract_year(tags)
    disc_number = _parse_number(tags.get("discnumber") or tags.get("disc")) or 1
    track_number = _parse_number(tags.get("tracknumber") or tags.get("track")) or 0

    folder = hrm_root / artist_s / f"({year}) {album_s}"
    filename = (
        f"{artist_s} - ({year}) {album_s} - "
        f"{disc_number:02d}-{track_number:02d}. {title_s}{src.suffix}"
    )
    return folder / filename


def relocate_hrm(
    db_path: Path,
    root: Path,
    hrm_root: Path,
    min_score: float = 10,
) -> RelocationStats:
    """Relocate files in *db_path* into the HRM hierarchy."""

    hrm_root = Path(utils.normalise_path(str(hrm_root)))
    manifest_path = Path("artifacts/manifests/hrm_relocation.tsv")
    manifest_rows: list[tuple[str, str, str, float, str]] = []
    stats = RelocationStats(
        moved=0,
        skipped=0,
        conflicts=0,
        missing=0,
        manifest_path=manifest_path,
    )

    db = utils.DatabaseContext(db_path)
    with db.connect() as connection:
        _ensure_required_columns(connection)
        rows = connection.execute(
            """
            SELECT path, checksum, tags_json, score_total
            FROM library_files
            WHERE score_total >= ?
              AND (dup_group IS NULL OR duplicate_rank = 1)
            """,
            (min_score,),
        ).fetchall()

    for row in rows:
        src = Path(row["path"])
        checksum = row["checksum"] or ""
        score_total = float(row["score_total"])
        try:
            tags = json.loads(row["tags_json"] or "{}")
        except json.JSONDecodeError:
            tags = {}

        if not _is_under_root(src, root):
            _log_skip(src, "outside source root")
            stats.skipped += 1
            manifest_rows.append((str(src), "", checksum, score_total, "skipped"))
            continue
        if not src.exists():
            logger.warning("Missing source file: %s", src)
            stats.missing += 1
            manifest_rows.append((str(src), "", checksum, score_total, "missing_source"))
            continue

        try:
            source_checksum = utils.compute_md5(src)
        except OSError as exc:
            _log_skip(src, f"unable to read checksum: {exc}")
            manifest_rows.append((str(src), "", checksum, score_total, "skipped"))
            stats.skipped += 1
            continue
        if checksum != source_checksum:
            logger.warning(
                "Checksum mismatch for %s (db=%s, computed=%s); skipping",
                src,
                checksum,
                source_checksum,
            )
            stats.conflicts += 1
            manifest_rows.append(
                (str(src), "", checksum or source_checksum, score_total, "conflict")
            )
            continue

        dest = _build_destination(src, tags, hrm_root)
        utils.ensure_parent_directory(dest)

        try:
            _move_with_retries(src, dest)
        except OSError as exc:
            _log_skip(src, f"filesystem error during move: {exc}")
            stats.skipped += 1
            manifest_rows.append((str(src), str(dest), checksum, score_total, "skipped"))
            continue

        with db.connect() as connection:
            connection.execute(
                "UPDATE library_files SET path=? WHERE checksum=?",
                (utils.normalise_path(str(dest)), checksum),
            )
            connection.commit()

        stats.moved += 1
        manifest_rows.append((str(src), str(dest), checksum, score_total, "moved"))

    _write_manifest(manifest_path, manifest_rows)
    return stats
