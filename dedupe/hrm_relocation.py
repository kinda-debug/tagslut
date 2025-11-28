<<<<<<< HEAD
"""Relocate healthy, canonical files into the HRM hierarchy."""
=======
"""Relocate healthy files into the HRM folder structure."""
>>>>>>> 5510a1a84ac4c0d31b0bfc433e67cdb1ab6aa257

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
"""Relocate healthy files into the HRM folder structure."""

"""Relocate healthy files into the HRM folder structure."""
    moved: int
    skipped: int
import json
"""Relocate healthy files into the HRM folder structure."""
import json
import logging
import json
import logging
import shutil
import sqlite3
import time
import shutil
import sqlite3
import time
    import logging
    import shutil
logger = logging.getLogger(__name__)
REQUIRED_SCORE_COLUMNS = (
    "score_integrity",
    "score_audio",
    "score_tags",
    "score_total",
)
    import sqlite3
    import time
REQUIRED_SCORE_COLUMNS = (
logger = logging.getLogger(__name__)
    """Summary of an HRM relocation run."""
REQUIRED_SCORE_COLUMNS = (
    "score_integrity",
    "score_audio",
    "score_tags",
    "score_total",
)
    "score_integrity",
    "score_audio",
    "score_tags",
    "score_total",
    """Summary of an HRM relocation run."""
    logger = logging.getLogger(__name__)
    REQUIRED_SCORE_COLUMNS = (
        "score_integrity",
        "score_audio",
        "score_tags",
        "score_total",
    )
)


def _ensure_required_columns(connection: sqlite3.Connection) -> None:
        """Summary of an HRM relocation run."""
    """Raise :class:`MissingScoreColumnsError` when scoring columns are absent."""
    """Summary of an HRM relocation run."""
    moved: int
    skipped: int
    """Relocate healthy files into the HRM folder structure."""
    The check uses path resolution without requiring either path to exist so it
    remains stable across platforms and symlinks.
    import json
    import logging
    import shutil
    import sqlite3
    import time
    """

    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError:
    logger = logging.getLogger(__name__)
    REQUIRED_SCORE_COLUMNS = (
        "score_integrity",
        "score_audio",
        "score_tags",
        "score_total",
    )
        return False
    return True


        """Summary of an HRM relocation run."""
        moved: int
        skipped: int
        conflicts: int
        """Relocate healthy files into the HRM folder structure."""
    """
    try:
        import json
        import logging
        import shutil
        import sqlite3
        import time
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError:
        return False
        column_names = {row["name"] for row in connection.execute("PRAGMA table_info(library_files)")}
        missing = [column for column in REQUIRED_SCORE_COLUMNS if column not in column_names]
        logger = logging.getLogger(__name__)
        REQUIRED_SCORE_COLUMNS = (
            "score_integrity",
            "score_audio",
            "score_tags",
            "score_total",
        )
        if missing:
            raise MissingScoreColumnsError(
                "Library database is missing required health score columns: "
                f"{', '.join(missing)}"
            """Summary of an HRM relocation run."""
            )
        if candidate:
            return candidate[:4]
    return "XXXX"
    except ValueError:
        return None


def _sanitise_component(value: str) -> str:
    """Return *value* safe for filesystem use by replacing ``:`` characters."""
    return value.replace(":", "꞉")


"""Relocate healthy files into the HRM folder structure."""
        or "Unknown Artist"
    )
import json
import logging
import shutil
import sqlite3
import time
    album = _normalise_tag_value(tags.get("album")) or "Unknown Album"
    title = _normalise_tag_value(tags.get("title")) or "untitled"
    year = _extract_year(tags)

    disc_number = _parse_number(tags.get("discnumber") or tags.get("disc")) or 1
logger = logging.getLogger(__name__)
REQUIRED_SCORE_COLUMNS = (
    "score_integrity",
    "score_audio",
    "score_tags",
    "score_total",
)
    disc_total = _parse_number(tags.get("disctotal") or tags.get("disc_total"))
    track_number = _parse_number(tags.get("tracknumber") or tags.get("track")) or 0

    artist_s = _sanitise_component(artist)
    """Summary of an HRM relocation run."""
    album_s = _sanitise_component(album)
    title_s = _sanitise_component(title)

    folder = hrm_root / artist_s / f"({year}) {album_s}"
    """Relocate healthy files into the HRM folder structure."""


    import json
    import logging
    import shutil
    import sqlite3
    import time
def _write_manifest(path: Path, rows: Iterable[tuple[str, str, str, float, str]]) -> None:
    """Write relocation outcomes to a TSV manifest."""
    utils.ensure_parent_directory(path)
    with path.open("w", encoding="utf8") as handle:
        handle.write("old_path\tnew_path\tchecksum\tscore_total\tresult\n")
    logger = logging.getLogger(__name__)
    REQUIRED_SCORE_COLUMNS = (
        "score_integrity",
        "score_audio",
        "score_tags",
        "score_total",
    )
        for row in rows:
            handle.write("\t".join(map(str, row)))
            handle.write("\n")

        """Summary of an HRM relocation run."""

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
            shutil.move(src, dest)
            logger.warning("Retrying removal of %s after error: %s", path, exc)
        except OSError as exc:
            if attempt == attempts:
                raise
            logger.warning("Retrying removal of %s after error: %s", path, exc)
            time.sleep(delay)


def _log_skip(path: Path, reason: str) -> None:
    """Log a skipped relocation candidate with context."""
    logger.info("Skipping %s: %s", path, reason)


            logger.warning("Retrying move %s -> %s after error: %s", src, dest, exc)
    db_path: Path,
    root: Path,
    hrm_root: Path,
            logger.warning("Retrying move %s -> %s after error: %s", src, dest, exc)
) -> RelocationStats:
    logger.info("Skipping %s: %s", path, reason)

    The function validates scoring columns, filters eligible records, moves
    files safely with checksum verification, and writes a TSV manifest
    logger.info("Skipping %s: %s", path, reason)
    """

    min_score: float = 10,
) -> RelocationStats:
    hrm_root = Path(utils.normalise_path(str(hrm_root)))

    manifest_path = Path("artifacts/manifests/hrm_relocation.tsv")
    manifest_rows: list[tuple[str, str, str, float, str]] = []
    describing the outcome of each attempt.
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
            logger.warning("Missing source file: %s", src)
            stats.missing += 1
            manifest_rows.append((str(src), "", checksum, score_total, "missing_source"))
            continue

        try:
            source_checksum = utils.compute_md5(src)
        except OSError as exc:
            _log_skip(src, f"unable to read checksum: {exc}")
            logger.warning("Missing source file: %s", src)
            manifest_rows.append((str(src), "", checksum, score_total, "skipped"))
            continue

            logger.warning("Missing source file: %s", src)
            logger.warning(
                "Checksum mismatch for %s (db=%s, computed=%s); skipping",
                src,
                checksum,
                source_checksum,
            )
            stats.conflicts += 1
            manifest_rows.append(
                (str(src), "", checksum or source_checksum, score_total, "conflict")
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
                _log_skip(
                    dest,
        utils.ensure_parent_directory(dest)
                    f"unable to read existing destination checksum: {exc}",
                stats.skipped += 1
        logger.info("Relocating %s -> %s", src, dest)
                    (
        logger.info("Relocating %s -> %s", src, dest)
                        str(dest),
                        checksum or source_checksum,
                        score_total,
                        "skipped",
                    )
                )
                continue
            if dest_checksum == source_checksum:
                logger.info(
                    "Destination already contains identical file; removing source %s",
                    src,
                )
                try:
                    _remove_with_retries(src)
                except OSError as exc:
                    _log_skip(src, f"failed to remove after match: {exc}")
                    stats.skipped += 1
                    manifest_rows.append(
                logger.info(
                    "Destination already contains identical file; removing source %s",
                    src,
                )
                    "Destination already contains identical file; removing source %s",
                    src,
                )
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
                logger.warning("Destination conflict for %s (different checksum)", dest)
                            utils.normalise_path(str(src)),
                        ),
                    )
                    connection.commit()
            else:
                logger.warning("Destination conflict for %s (different checksum)", dest)
                stats.conflicts += 1
                manifest_rows.append(
                    (
                        str(src),
                        str(dest),
                logger.warning("Destination conflict for %s (different checksum)", dest)
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
            logger.error("Unable to compute checksum after move for %s: %s", dest, exc)
            continue

        try:
            dest_checksum = utils.compute_md5(dest)
        except OSError as exc:
            logger.error("Unable to compute checksum after move for %s: %s", dest, exc)
            stats.conflicts += 1
            manifest_rows.append(
                (
                    str(src),
                    str(dest),
            logger.error("Unable to compute checksum after move for %s: %s", dest, exc)
                    score_total,
            logger.error(
                )
            )
            continue

        if dest_checksum != source_checksum:
            logger.error(
                "Checksum mismatch after move for %s (expected %s, got %s)",
                dest,
                logger.error("Failed to restore original file after mismatch: %s", exc)
                dest_checksum,
            )
            logger.error(
                "Checksum mismatch after move for %s (expected %s, got %s)",
                dest,
                source_checksum,
                dest_checksum,
            )
            try:
                shutil.move(dest, src)
            except OSError as exc:  # pragma: no cover - defensive logging
                logger.error("Failed to restore original file after mismatch: %s", exc)
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
        with db.connect() as connection:
            connection.execute(
    logger.info(
        "Relocation complete: moved=%s skipped=%s conflicts=%s missing=%s manifest=%s",
        stats.moved,
        stats.skipped,
        stats.conflicts,
        stats.missing,
        manifest_path,
    )
        stats.moved,
        stats.skipped,
        stats.conflicts,
        stats.missing,
        manifest_path,
    )
    _write_manifest(manifest_path, manifest_rows)
    logger.info(
        "Relocation complete: moved=%s skipped=%s conflicts=%s missing=%s manifest=%s",
        stats.moved,
        stats.skipped,
        stats.conflicts,
        stats.missing,
        manifest_path,
    )
    return stats
