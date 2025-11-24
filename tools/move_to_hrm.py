"""Move canonical, healthy files into the HRM hierarchy."""

from __future__ import annotations

import json
import logging
import shutil
import sqlite3
from pathlib import Path

from dedupe import healthcheck, scanner, utils

LOGGER = logging.getLogger(__name__)


def _year_from_tags(tags: dict) -> str:
    """Return the best-effort release year from tag candidates."""

    for key in ("date", "originalyear", "originaldate"):
        value = tags.get(key)
        if isinstance(value, list):
            value = value[0] if value else None
        if value:
            return str(value)[:4]
    return "XXXX"


def _sanitise_component(value: str) -> str:
    """Replace unsupported characters for filesystem use."""

    return value.replace(":", "꞉")


def _format_target(tags: dict, root: Path, filename: str) -> Path:
    """Construct the destination HRM path for a FLAC file."""

    albumartist = tags.get("albumartist") or tags.get("artist") or "Unknown"
    album = tags.get("album") or "Unknown Album"
    disc = tags.get("discnumber") or tags.get("disc") or 1
    track = tags.get("tracknumber") or tags.get("track") or 0
    title = tags.get("title") or "untitled"
    year = _year_from_tags(tags)

    try:
        disc_num = int(str(disc).split("/")[0])
    except (TypeError, ValueError):
        disc_num = 1
    try:
        track_num = int(str(track).split("/")[0])
    except (TypeError, ValueError):
        track_num = 0

    albumartist_s = _sanitise_component(str(albumartist))
    album_s = _sanitise_component(str(album))
    title_s = _sanitise_component(str(title))

    folder = root / albumartist_s / f"{year} {album_s}"
    filename = f"{albumartist_s} - {year} {album_s} - "
    if disc_num > 1:
        filename += f"{disc_num:02d}-"
    filename += f"{track_num:02d}. {title_s}.flac"
    return folder / filename


def move_canonical_to_hrm(db_path: Path, hrm_root: Path) -> int:
    """Move canonical, perfect-score files into the HRM tree."""

    db_path = Path(utils.normalise_path(str(db_path)))
    hrm_root = Path(utils.normalise_path(str(hrm_root)))
    utils.ensure_parent_directory(hrm_root / "stub")

    db = utils.DatabaseContext(db_path)
    moved = 0
    with db.connect() as connection:
        scanner.initialise_database(connection)
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT path, tags_json
            FROM library_files
            WHERE is_canonical = 1
            """
        ).fetchall()

    for row in rows:
        src = Path(row["path"])
        tags = {k.lower(): v for k, v in json.loads(row["tags_json"] or "{}").items()}
        health = healthcheck.score_file(src)
        if health["score"] != 10:
            LOGGER.debug("Skipping %s with score %s", src, health["score"])
            continue
        dest = _format_target(tags, hrm_root, src.name)
        utils.ensure_parent_directory(dest)
        try:
            shutil.move(src, dest)
        except OSError as exc:
            LOGGER.warning("Failed to move %s: %s", src, exc)
            continue
        moved += 1
        with db.connect() as connection:
            connection.execute(
                "UPDATE library_files SET path=? WHERE path=?",
                (utils.normalise_path(str(dest)), utils.normalise_path(str(src))),
            )
            connection.commit()
    return moved


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Move canonical files into HRM")
    parser.add_argument("database")
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    count = move_canonical_to_hrm(Path(args.database), Path(args.root))
    print(f"Moved {count} files")
