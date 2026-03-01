#!/usr/bin/env python3
"""Migrate a legacy tagslut (v1/epoch) database to the current v2 schema.

Usage:
    poetry run python scripts/migrate_legacy_db.py <source_db> <dest_db> [--execute] [--remap-root OLD NEW]

Steps performed:
    1. Copy the source DB to dest (unless --in-place is given).
    2. Run init_db() to add missing v2 columns via ALTER TABLE.
    3. Run the 0002_add_dj_fields backfill (canonical_bpm→bpm, canonical_key→key_camelot,
       canonical_isrc→isrc, plus metadata_json fallback).
    4. Backfill genre from canonical_genre.
    5. Backfill dj_flag from is_dj_material.
    6. Compute quality_rank from bit_depth / sample_rate / bitrate.
    7. Normalise download_source values (fix rows where artist names leaked in).
    8. Optionally remap path roots (e.g. /Volumes/MUSIC/LIBRARY/ → /Volumes/DJSSD/).
    9. Print a summary report.

Requires --execute to actually write changes.  Without it, the script runs in
dry-run mode and reports what it *would* do.
"""

from __future__ import annotations

import argparse
import importlib.util
import logging
import shutil
import sqlite3
import sys
from pathlib import Path

# Add project root to path so imports work when run as a script
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from tagslut.core.quality import compute_quality_rank  # noqa: E402
from tagslut.storage.schema import init_db  # noqa: E402


def _load_dj_fields_migration():
    """Import 0002_add_dj_fields.py (numeric prefix is not a valid module name)."""
    spec = importlib.util.spec_from_file_location(
        "add_dj_fields_0002",
        _PROJECT_ROOT / "tagslut" / "migrations" / "0002_add_dj_fields.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

logger = logging.getLogger("migrate_legacy_db")

# ── Known-good download source labels ───────────────────────────────────────
VALID_SOURCES = frozenset({
    "bpdl", "tiddl", "tidal", "mdl", "deezer",
    "legacy", "dropbox", "dropbox_hires", "bandcamp",
    "soulseek", "soundcloud", "youtube",
})


# ── Helpers ─────────────────────────────────────────────────────────────────

def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    try:
        cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    except sqlite3.OperationalError:
        return False
    return column in cols


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row[0] > 0


def _upgrade_schema_migrations_table(conn: sqlite3.Connection) -> None:
    """Upgrade the legacy schema_migrations table to v2 format if needed.

    The legacy table has columns (name TEXT, applied_at TEXT).
    The v2 table expects (id INTEGER, schema_name TEXT, version INTEGER,
    applied_at TEXT, note TEXT).  If the old schema is detected, drop and
    let init_db() recreate it.
    """
    if not _table_exists(conn, "schema_migrations"):
        return
    if _has_column(conn, "schema_migrations", "schema_name"):
        return  # already v2 format
    logger.info("Upgrading legacy schema_migrations table to v2 format")
    conn.execute("DROP TABLE schema_migrations")



def _count(conn: sqlite3.Connection, where: str = "1=1") -> int:
    return conn.execute(f"SELECT COUNT(*) FROM files WHERE {where}").fetchone()[0]


def _fix_download_sources(conn: sqlite3.Connection, *, execute: bool) -> dict:
    """Normalise download_source: set unknown values to 'legacy'."""
    cursor = conn.execute(
        "SELECT download_source, COUNT(*) FROM files "
        "WHERE download_source IS NOT NULL "
        "GROUP BY download_source ORDER BY COUNT(*) DESC"
    )
    bad_sources: dict[str, int] = {}
    for src, cnt in cursor.fetchall():
        normalised = src.strip().lower()
        if normalised not in VALID_SOURCES:
            bad_sources[src] = cnt

    if execute and bad_sources:
        for src in bad_sources:
            conn.execute(
                "UPDATE files SET download_source = 'legacy' WHERE download_source = ?",
                (src,),
            )
    return bad_sources


def _backfill_genre(conn: sqlite3.Connection, *, execute: bool) -> int:
    """Copy canonical_genre → genre where genre is NULL."""
    if not _has_column(conn, "files", "canonical_genre"):
        return 0
    if not _has_column(conn, "files", "genre"):
        # dry-run: v2 column not yet added; count from source column
        return _count(conn, "canonical_genre IS NOT NULL")
    pending = _count(conn, "genre IS NULL AND canonical_genre IS NOT NULL")
    if execute and pending:
        conn.execute(
            "UPDATE files SET genre = canonical_genre "
            "WHERE genre IS NULL AND canonical_genre IS NOT NULL"
        )
    return pending


def _backfill_dj_flag(conn: sqlite3.Connection, *, execute: bool) -> int:
    """Copy is_dj_material → dj_flag where dj_flag is 0/NULL."""
    if not _has_column(conn, "files", "is_dj_material"):
        return 0
    if not _has_column(conn, "files", "dj_flag"):
        # dry-run: v2 column not yet added; count from source column
        return _count(conn, "is_dj_material = 1")
    pending = _count(
        conn,
        "(dj_flag IS NULL OR dj_flag = 0) AND is_dj_material = 1",
    )
    if execute and pending:
        conn.execute(
            "UPDATE files SET dj_flag = 1 "
            "WHERE (dj_flag IS NULL OR dj_flag = 0) AND is_dj_material = 1"
        )
    return pending


def _backfill_quality_rank(conn: sqlite3.Connection, *, execute: bool) -> int:
    """Compute quality_rank from bit_depth / sample_rate / bitrate."""
    if not _has_column(conn, "files", "quality_rank"):
        # dry-run: v2 column not yet added; count eligible rows
        return _count(conn, "bit_depth IS NOT NULL AND sample_rate IS NOT NULL")
    cursor = conn.execute(
        "SELECT path, bit_depth, sample_rate, bitrate FROM files "
        "WHERE quality_rank IS NULL AND bit_depth IS NOT NULL AND sample_rate IS NOT NULL"
    )
    rows = cursor.fetchall()
    updated = 0
    for path, bd, sr, br in rows:
        rank = int(compute_quality_rank(bd, sr, br or 0))
        if execute:
            conn.execute(
                "UPDATE files SET quality_rank = ? WHERE path = ?",
                (rank, path),
            )
        updated += 1
    return updated


def _remap_paths(
    conn: sqlite3.Connection,
    old_root: str,
    new_root: str,
    *,
    execute: bool,
) -> int:
    """Rewrite path column: replace old_root prefix with new_root."""
    # Ensure trailing slashes for clean replacement
    if not old_root.endswith("/"):
        old_root += "/"
    if not new_root.endswith("/"):
        new_root += "/"

    pending = _count(conn, f"path LIKE '{old_root}%'")
    if execute and pending:
        conn.execute(
            "UPDATE files SET path = ? || SUBSTR(path, ?) "
            "WHERE path LIKE ? || '%'",
            (new_root, len(old_root) + 1, old_root),
        )
    return pending


# ── Main ────────────────────────────────────────────────────────────────────

def migrate(
    source: Path,
    dest: Path,
    *,
    execute: bool = False,
    remap_root: tuple[str, str] | None = None,
) -> dict:
    """Run the full legacy → v2 migration.  Returns a summary dict."""
    summary: dict = {"execute": execute}

    if not source.exists():
        logger.error("Source DB not found: %s", source)
        sys.exit(1)

    # Step 1: copy
    if dest != source:
        if dest.exists() and not execute:
            logger.info("[dry-run] Would overwrite %s", dest)
        if execute:
            shutil.copy2(source, dest)
            logger.info("Copied %s → %s", source, dest)
        summary["copied"] = str(dest)
    else:
        summary["copied"] = "(in-place)"

    # Open the target DB
    db_path = dest if execute else source
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    total_before = _count(conn)
    summary["total_rows"] = total_before

    # Step 2: init_db() — additive schema migration
    if execute:
        _upgrade_schema_migrations_table(conn)
        init_db(conn)
        logger.info("init_db(): schema upgraded")
    summary["schema_upgraded"] = True

    # Step 3: DJ fields backfill (0002)
    if execute:
        dj_mod = _load_dj_fields_migration()
        dj_mod.up(conn)
        logger.info("0002_add_dj_fields: backfill complete")
    summary["dj_fields_backfill"] = True

    # Step 4: genre backfill
    genre_count = _backfill_genre(conn, execute=execute)
    summary["genre_backfilled"] = genre_count

    # Step 5: dj_flag backfill
    dj_flag_count = _backfill_dj_flag(conn, execute=execute)
    summary["dj_flag_backfilled"] = dj_flag_count

    # Step 6: quality_rank
    qr_count = _backfill_quality_rank(conn, execute=execute)
    summary["quality_rank_computed"] = qr_count

    # Step 7: download_source cleanup
    bad_sources = _fix_download_sources(conn, execute=execute)
    summary["download_source_fixed"] = bad_sources

    # Step 8: path remapping
    if remap_root:
        remap_count = _remap_paths(conn, remap_root[0], remap_root[1], execute=execute)
        summary["paths_remapped"] = remap_count

    # Commit
    if execute:
        conn.commit()
        logger.info("All changes committed.")

    # Step 9: summary
    if execute:
        summary["post_stats"] = {
            "total": _count(conn),
            "with_bpm": _count(conn, "bpm IS NOT NULL"),
            "with_key": _count(conn, "key_camelot IS NOT NULL"),
            "with_isrc": _count(conn, "isrc IS NOT NULL"),
            "with_genre": _count(conn, "genre IS NOT NULL"),
            "with_dj_flag": _count(conn, "dj_flag = 1"),
            "with_quality_rank": _count(conn, "quality_rank IS NOT NULL"),
        }

    conn.close()
    return summary


def _print_summary(summary: dict) -> None:
    mode = "EXECUTE" if summary["execute"] else "DRY-RUN"
    print(f"\n{'='*60}")
    print(f"  Legacy DB Migration — {mode}")
    print(f"{'='*60}")
    print(f"  Total rows: {summary['total_rows']:,}")
    print(f"  DB copied to: {summary['copied']}")
    print(f"  Schema upgraded: {summary['schema_upgraded']}")
    print(f"  DJ fields backfill: {summary['dj_fields_backfill']}")
    print(f"  Genre backfilled: {summary['genre_backfilled']:,}")
    print(f"  DJ flag backfilled: {summary['dj_flag_backfilled']:,}")
    print(f"  Quality rank computed: {summary['quality_rank_computed']:,}")

    if summary.get("download_source_fixed"):
        print(f"\n  Download source fixes:")
        for src, cnt in summary["download_source_fixed"].items():
            print(f"    '{src}' → 'legacy' ({cnt} rows)")
    else:
        print(f"  Download source fixes: none needed")

    if "paths_remapped" in summary:
        print(f"  Paths remapped: {summary['paths_remapped']:,}")

    if "post_stats" in summary:
        ps = summary["post_stats"]
        print(f"\n  Post-migration stats:")
        print(f"    Total:        {ps['total']:>7,}")
        print(f"    BPM:          {ps['with_bpm']:>7,}")
        print(f"    Key:          {ps['with_key']:>7,}")
        print(f"    ISRC:         {ps['with_isrc']:>7,}")
        print(f"    Genre:        {ps['with_genre']:>7,}")
        print(f"    DJ flag:      {ps['with_dj_flag']:>7,}")
        print(f"    Quality rank: {ps['with_quality_rank']:>7,}")

    print(f"{'='*60}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate a legacy tagslut DB to the current v2 schema.",
    )
    parser.add_argument("source", type=Path, help="Path to legacy music.db")
    parser.add_argument("dest", type=Path, help="Path for migrated output DB")
    parser.add_argument(
        "--execute", action="store_true",
        help="Actually write changes (default: dry-run)",
    )
    parser.add_argument(
        "--remap-root", nargs=2, metavar=("OLD", "NEW"),
        help="Rewrite path prefixes, e.g. --remap-root /Volumes/MUSIC/LIBRARY/ /Volumes/DJSSD/LIBRARY/",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    summary = migrate(
        args.source,
        args.dest,
        execute=args.execute,
        remap_root=tuple(args.remap_root) if args.remap_root else None,
    )
    _print_summary(summary)


if __name__ == "__main__":
    main()
