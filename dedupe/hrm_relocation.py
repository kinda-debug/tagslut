"""Relocate healthy, canonical files into the HRM hierarchy."""

from __future__ import annotations

import json
import logging
import shutil
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from . import utils

LOGGER = logging.getLogger(__name__)

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


class MissingScoreColumnsError(RuntimeError):
    """Raised when the database lacks required scoring columns."""


def _ensure_required_columns(connection: sqlite3.Connection) -> None:
    """Raise :class:`MissingScoreColumnsError` when scoring columns are absent."""

    column_names = {row["name"] for row in connection.execute("PRAGMA table_info(library_files)")}
    missing = [column for column in REQUIRED_SCORE_COLUMNS if column not in column_names]
    if missing:
        raise MissingScoreColumnsError(
            "Library database is missing required health score columns: "
            f"{', '.join(missing)}"
        )


def _is_under_root(path: Path, root: Path) -> bool:
    """Return ``True`` when *path* is nested beneath *root*.

    The check uses path resolution without requiring either path to exist so it
    remains stable across platforms and symlinks.
    """

    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError:
        return False
    return True


def _normalise_tag_value(value: Optional[object]) -> Optional[str]:
    """Return a string representation of a tag value.

    Lists are collapsed to the first element, empty iterables and ``None`` are
    treated as missing.
    """
    if value is None:
        return None
    if isinstance(value, list):
        if not value:
            return None
        return str(value[0])
    return str(value)


def _extract_year(tags: dict[str, object]) -> str:
    """Return the best-effort release year from tag values."""
    for key in ("date", "originalyear", "originaldate"):
        candidate = _normalise_tag_value(tags.get(key))
        if candidate:
            return candidate[:4]
    return "XXXX"


def _parse_number(value: Optional[object]) -> Optional[int]:
    """Coerce a tag value such as ``"2/5"`` or ``"2"`` into an integer."""
    normalised = _normalise_tag_value(value)
    if normalised is None:
        return None
    try:
        return int(normalised.split("/")[0])
    except ValueError:
        return None


def _sanitise_component(value: str) -> str:
    """Return *value* safe for filesystem use by replacing ``:`` characters."""
    return value.replace(":", "꞉")


def _build_destination(tags: dict[str, object], hrm_root: Path) -> Path:
    """Construct the destination HRM path for a file based on its tags."""
    artist = (
        _normalise_tag_value(tags.get("albumartist"))
        or _normalise_tag_value(tags.get("artist"))
        or "Unknown Artist"
    )
    album = _normalise_tag_value(tags.get("album")) or "Unknown Album"
    title = _normalise_tag_value(tags.get("title")) or "untitled"
    year = _extract_year(tags)

    disc_number = _parse_number(tags.get("discnumber") or tags.get("disc")) or 1
    disc_total = _parse_number(tags.get("disctotal") or tags.get("disc_total"))
    track_number = _parse_number(tags.get("tracknumber") or tags.get("track")) or 0

    artist_s = _sanitise_component(artist)
    album_s = _sanitise_component(album)
    title_s = _sanitise_component(title)

    folder = hrm_root / artist_s / f"({year}) {album_s}"
    filename = f"{artist_s} - ({year}) {album_s} - "
    if (disc_total and disc_total > 1) or disc_number > 1:
        filename += f"{disc_number:02d}-"
    filename += f"{track_number:02d}. {title_s}.flac"
    return folder / filename


def _write_manifest(path: Path, rows: Iterable[tuple[str, str, str, float, str]]) -> None:
    """Write relocation outcomes to a TSV manifest."""
    utils.ensure_parent_directory(path)
    with path.open("w", encoding="utf8") as handle:
        handle.write("old_path\tnew_path\tchecksum\tscore_total\tresult\n")
        for row in rows:
            handle.write("\t".join(map(str, row)))
            handle.write("\n")


def _remove_with_retries(path: Path, attempts: int = 3, delay: float = 0.5) -> None:
    """Remove *path* with simple retry handling."""
    for attempt in range(1, attempts + 1):
        try:
            path.unlink()
            return
        except OSError as exc:
            if attempt == attempts:
                raise
            LOGGER.warning("Retrying removal of %s after error: %s", path, exc)
            time.sleep(delay)


def _move_with_retries(src: Path, dest: Path, attempts: int = 3, delay: float = 0.5) -> None:
    """Move *src* to *dest* with retry handling for transient filesystem errors."""
    for attempt in range(1, attempts + 1):
        try:
            shutil.move(src, dest)
            return
        except OSError as exc:
            if attempt == attempts:
                raise
            LOGGER.warning("Retrying move %s -> %s after error: %s", src, dest, exc)
            time.sleep(delay)


def _log_skip(path: Path, reason: str) -> None:
    """Log a skipped relocation candidate with context."""
    LOGGER.info("Skipping %s: %s", path, reason)


def relocate_hrm(
    db_path: Path,
    root: Path,
    hrm_root: Path,
    min_score: float = 10,
) -> RelocationStats:
    """Relocate healthy files into the HRM folder hierarchy.

    The function validates scoring columns, filters eligible records, moves
    files safely with checksum verification, and writes a TSV manifest
    describing the outcome of each attempt.
    """

    db_path = Path(utils.normalise_path(str(db_path)))
    root = Path(utils.normalise_path(str(root)))
    hrm_root = Path(utils.normalise_path(str(hrm_root)))

    manifest_path = Path("artifacts/manifests/hrm_relocation.tsv")
    manifest_rows: list[tuple[str, str, str, float, str]] = []

    stats = RelocationStats(moved=0, skipped=0, conflicts=0, missing=0, manifest_path=manifest_path)

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
            LOGGER.warning("Missing source file: %s", src)
            stats.missing += 1
            manifest_rows.append((str(src), "", checksum, score_total, "missing_source"))
            continue

        try:
            source_checksum = utils.compute_md5(src)
        except OSError as exc:
            _log_skip(src, f"unable to read checksum: {exc}")
            stats.skipped += 1
            manifest_rows.append((str(src), "", checksum, score_total, "skipped"))
            continue

        if checksum and checksum != source_checksum:
            LOGGER.warning(
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

        dest = _build_destination(tags, hrm_root)
        utils.ensure_parent_directory(dest)

        LOGGER.info("Relocating %s -> %s", src, dest)

        if dest.exists():
            try:
                dest_checksum = utils.compute_md5(dest)
            except OSError as exc:
                _log_skip(
                    dest,
                    f"unable to read existing destination checksum: {exc}",
                )
                stats.skipped += 1
                manifest_rows.append(
                    (
                        str(src),
                        str(dest),
                        checksum or source_checksum,
                        score_total,
                        "skipped",
                    )
                )
                continue
            if dest_checksum == source_checksum:
                LOGGER.info("Destination already contains identical file; removing source %s", src)
                try:
                    _remove_with_retries(src)
                except OSError as exc:
                    _log_skip(src, f"failed to remove after match: {exc}")
                    stats.skipped += 1
                    manifest_rows.append(
                        (
                            str(src),
                            str(dest),
                            checksum or source_checksum,
                            score_total,
                            "skipped",
                        )
                    )
                    continue
                stats.moved += 1
                manifest_rows.append(
                    (
                        str(src),
                        str(dest),
                        checksum or source_checksum,
                        score_total,
                        "moved",
                    )
                )
                with db.connect() as connection:
                    connection.execute(
                        "UPDATE library_files SET path=? WHERE path=?",
                        (
                            utils.normalise_path(str(dest)),
                            utils.normalise_path(str(src)),
                        ),
                    )
                    connection.commit()
            else:
                LOGGER.warning("Destination conflict for %s (different checksum)", dest)
                stats.conflicts += 1
                manifest_rows.append(
                    (
                        str(src),
                        str(dest),
                        checksum or source_checksum,
                        score_total,
                        "conflict",
                    )
                )
            continue

        try:
            _move_with_retries(src, dest)
        except OSError as exc:
            _log_skip(src, f"filesystem error during move: {exc}")
            stats.skipped += 1
            manifest_rows.append(
                (str(src), str(dest), checksum or source_checksum, score_total, "skipped")
            )
            continue

        try:
            dest_checksum = utils.compute_md5(dest)
        except OSError as exc:
            LOGGER.error("Unable to compute checksum after move for %s: %s", dest, exc)
            stats.conflicts += 1
            manifest_rows.append(
                (
                    str(src),
                    str(dest),
                    checksum or source_checksum,
                    score_total,
                    "conflict",
                )
            )
            continue

        if dest_checksum != source_checksum:
            LOGGER.error(
                "Checksum mismatch after move for %s (expected %s, got %s)",
                dest,
                source_checksum,
                dest_checksum,
            )
            try:
                shutil.move(dest, src)
            except OSError as exc:  # pragma: no cover - defensive logging
                LOGGER.error("Failed to restore original file after mismatch: %s", exc)
            stats.conflicts += 1
            manifest_rows.append(
                (
                    str(src),
                    str(dest),
                    checksum or source_checksum,
                    score_total,
                    "conflict",
                )
            )
            continue

        stats.moved += 1
        manifest_rows.append(
            (str(src), str(dest), checksum or source_checksum, score_total, "moved")
        )

        with db.connect() as connection:
            connection.execute(
                "UPDATE library_files SET path=? WHERE path=?",
                (utils.normalise_path(str(dest)), utils.normalise_path(str(src))),
            )
            connection.commit()

    _write_manifest(manifest_path, manifest_rows)
    LOGGER.info(
        "Relocation complete: moved=%s skipped=%s conflicts=%s missing=%s manifest=%s",
        stats.moved,
        stats.skipped,
        stats.conflicts,
        stats.missing,
        manifest_path,
    )
    return stats
