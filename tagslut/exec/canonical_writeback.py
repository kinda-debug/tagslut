"""Canonical FLAC tag writeback.

Reads linked `track_identity.canonical_*` fields first and falls back to
`files.canonical_*` mirrors when identity fields are blank. Existing FLAC tags
are preserved unless `force=True`.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence

from mutagen.flac import FLAC

from tagslut.metadata.genre_normalization import default_genre_normalizer


@dataclass(frozen=True)
class CanonicalWritebackStats:
    scanned: int
    updated: int
    skipped: int
    missing: int


def iter_flacs_from_root(root: Path) -> Iterable[Path]:
    if root.is_file():
        yield root
        return
    yield from root.rglob("*.flac")


def iter_flacs_from_m3u(m3u_path: Path) -> Iterable[Path]:
    for raw in m3u_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        path = Path(line)
        if path.suffix.lower() == ".flac":
            yield path


def _column_exists(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(str(row[1]) == column_name for row in rows)


def _canonical_row_for_path(conn: sqlite3.Connection, path: Path) -> sqlite3.Row | None:
    conn.row_factory = sqlite3.Row
    active_join = "AND al.active = 1" if _column_exists(conn, "asset_link", "active") else ""
    merged_join = "AND ti.merged_into_id IS NULL" if _column_exists(conn, "track_identity", "merged_into_id") else ""
    return conn.execute(
        f"""
        SELECT
            COALESCE(NULLIF(TRIM(CAST(ti.canonical_artist AS TEXT)), ''), NULLIF(TRIM(CAST(f.canonical_artist AS TEXT)), '')) AS canonical_artist,
            COALESCE(NULLIF(TRIM(CAST(ti.canonical_title AS TEXT)), ''), NULLIF(TRIM(CAST(f.canonical_title AS TEXT)), '')) AS canonical_title,
            COALESCE(NULLIF(TRIM(CAST(ti.canonical_album AS TEXT)), ''), NULLIF(TRIM(CAST(f.canonical_album AS TEXT)), '')) AS canonical_album,
            COALESCE(NULLIF(TRIM(CAST(ti.canonical_genre AS TEXT)), ''), NULLIF(TRIM(CAST(f.canonical_genre AS TEXT)), '')) AS canonical_genre,
            COALESCE(NULLIF(TRIM(CAST(ti.canonical_sub_genre AS TEXT)), ''), NULLIF(TRIM(CAST(f.canonical_sub_genre AS TEXT)), '')) AS canonical_sub_genre,
            COALESCE(NULLIF(TRIM(CAST(ti.canonical_label AS TEXT)), ''), NULLIF(TRIM(CAST(f.canonical_label AS TEXT)), '')) AS canonical_label,
            COALESCE(NULLIF(TRIM(CAST(ti.canonical_catalog_number AS TEXT)), ''), NULLIF(TRIM(CAST(f.canonical_catalog_number AS TEXT)), '')) AS canonical_catalog_number,
            COALESCE(NULLIF(TRIM(CAST(ti.canonical_year AS TEXT)), ''), NULLIF(TRIM(CAST(f.canonical_year AS TEXT)), '')) AS canonical_year,
            COALESCE(NULLIF(TRIM(CAST(ti.canonical_release_date AS TEXT)), ''), NULLIF(TRIM(CAST(f.canonical_release_date AS TEXT)), '')) AS canonical_release_date,
            COALESCE(NULLIF(TRIM(CAST(ti.canonical_bpm AS TEXT)), ''), NULLIF(TRIM(CAST(f.canonical_bpm AS TEXT)), '')) AS canonical_bpm,
            COALESCE(NULLIF(TRIM(CAST(ti.canonical_key AS TEXT)), ''), NULLIF(TRIM(CAST(f.canonical_key AS TEXT)), '')) AS canonical_key,
            COALESCE(NULLIF(TRIM(CAST(ti.isrc AS TEXT)), ''), NULLIF(TRIM(CAST(f.canonical_isrc AS TEXT)), '')) AS isrc,
            COALESCE(NULLIF(TRIM(CAST(ti.beatport_id AS TEXT)), ''), NULLIF(TRIM(CAST(f.beatport_id AS TEXT)), '')) AS beatport_id
        FROM files f
        LEFT JOIN asset_file af ON af.path = f.path
        LEFT JOIN asset_link al ON al.asset_id = af.id {active_join}
        LEFT JOIN track_identity ti ON ti.id = al.identity_id {merged_join}
        WHERE f.path = ?
        ORDER BY al.id ASC
        LIMIT 1
        """,
        (str(path),),
    ).fetchone()


def _tag_exists(tags: object, key: str) -> bool:
    if tags is None:
        return False
    return key in tags and bool(tags[key])  # type: ignore[index]


def _set_tag(tags: object, key: str, value: str) -> None:
    tags[key] = [value]  # type: ignore[index]


def write_canonical_tags(
    conn: sqlite3.Connection,
    sources: Sequence[Path],
    *,
    force: bool = False,
    execute: bool = False,
    progress_interval: int = 100,
    echo: Callable[[str], None] | None = None,
) -> CanonicalWritebackStats:
    updated = 0
    skipped = 0
    missing = 0

    for idx, path in enumerate(sources, start=1):
        resolved = path.expanduser().resolve()
        if not resolved.exists():
            missing += 1
            if echo is not None and progress_interval > 0 and idx % progress_interval == 0:
                echo(f"Writeback {idx}/{len(sources)} updated={updated} skipped={skipped} missing={missing}")
            continue

        row = _canonical_row_for_path(conn, resolved)
        if row is None:
            skipped += 1
            if echo is not None and progress_interval > 0 and idx % progress_interval == 0:
                echo(f"Writeback {idx}/{len(sources)} updated={updated} skipped={skipped} missing={missing}")
            continue

        audio = FLAC(resolved)
        tags = audio.tags
        updates: list[str] = []

        def maybe_set(tag_key: str, value: object) -> None:
            if value in (None, ""):
                return
            if force or not _tag_exists(tags, tag_key):
                _set_tag(tags, tag_key, str(value))
                updates.append(tag_key)

        maybe_set("ARTIST", row["canonical_artist"])
        maybe_set("TITLE", row["canonical_title"])
        maybe_set("ALBUM", row["canonical_album"])

        date_value = row["canonical_release_date"] or row["canonical_year"]
        if date_value is not None:
            maybe_set("DATE", date_value)

        maybe_set("ISRC", row["isrc"])
        maybe_set("LABEL", row["canonical_label"])
        maybe_set("CATALOGNUMBER", row["canonical_catalog_number"])
        maybe_set("BEATPORT_TRACK_ID", row["beatport_id"])
        maybe_set("BPM", row["canonical_bpm"])
        maybe_set("INITIALKEY", row["canonical_key"])

        genre, sub_genre = default_genre_normalizer().normalize_pair(
            row["canonical_genre"],
            row["canonical_sub_genre"],
        )
        maybe_set("GENRE", genre)
        maybe_set("SUBGENRE", sub_genre)
        if genre and sub_genre:
            maybe_set("GENRE_FULL", f"{genre} | {sub_genre}")
            maybe_set("GENRE_PREFERRED", sub_genre)

        if updates:
            if execute:
                audio.save()
            updated += 1
        else:
            skipped += 1

        if echo is not None and progress_interval > 0 and idx % progress_interval == 0:
            echo(f"Writeback {idx}/{len(sources)} updated={updated} skipped={skipped} missing={missing}")

    return CanonicalWritebackStats(scanned=len(sources), updated=updated, skipped=skipped, missing=missing)
