"""Migration 0007: scaffold ISRC-first identity enforcement for v3 track_identity."""

import argparse
import json
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path


logger = logging.getLogger(__name__)

UNIQUE_INDEX_NAME = "idx_track_identity_isrc_unique_norm"
INSERT_TRIGGER_NAME = "trg_track_identity_isrc_required_insert"
UPDATE_TRIGGER_NAME = "trg_track_identity_isrc_required_update"
TRACK_IDENTITY_TABLE = "track_identity"
LEGACY_FILES_TABLE = "files"
SOURCE_TABLE = "library_track_sources"
ISRC_JSON_KEYS = ("isrc", "tsrc", "canonical_isrc")
PROVIDER_COLUMN_MAP = {
    "beatport_id": "beatport_id",
    "tidal_id": "tidal_id",
    "qobuz_id": "qobuz_id",
    "spotify_id": "spotify_id",
    "apple_music_id": "itunes_id",
    "deezer_id": "deezer_id",
    "traxsource_id": "traxsource_id",
    "itunes_id": "itunes_id",
    "musicbrainz_id": "musicbrainz_id",
}


@dataclass(frozen=True)
class PendingUpdate:
    identity_id: int
    isrc: str
    source: str


@dataclass(frozen=True)
class UnresolvedRow:
    identity_id: int
    identity_key: str
    candidate_count: int
    candidate_sources: tuple[str, ...]


@dataclass(frozen=True)
class Report:
    mode: str
    total_rows: int
    rows_with_isrc_before: int
    planned_updates: tuple[PendingUpdate, ...]
    unresolved_rows: tuple[UnresolvedRow, ...]
    duplicate_isrc_groups: tuple[tuple[str, tuple[int, ...]], ...]


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except sqlite3.OperationalError:
        return False
    return any(str(row[1]) == column for row in rows)


def _normalize_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_isrc(value: object) -> str | None:
    text = _normalize_text(value)
    if not text:
        return None
    return text.upper()


def _json_payload(raw: object) -> dict[str, object]:
    text = _normalize_text(raw)
    if not text:
        return {}
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _extract_isrc_from_json(raw: object) -> str | None:
    payload = _json_payload(raw)
    lowered = {str(key).lower(): value for key, value in payload.items()}
    for key in ISRC_JSON_KEYS:
        normalized = _normalize_isrc(lowered.get(key))
        if normalized:
            return normalized
    return None


def _identity_key_isrc(identity_key: object) -> str | None:
    text = _normalize_text(identity_key)
    if not text:
        return None
    prefix = "isrc:"
    if not text.lower().startswith(prefix):
        return None
    return _normalize_isrc(text[len(prefix):])


def _add_candidate(candidates: dict[str, set[str]], value: str | None, source: str) -> None:
    if not value:
        return
    candidates.setdefault(value, set()).add(source)


def _track_identity_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    columns = [
        "id",
        "identity_key",
        "isrc",
        "beatport_id",
        "tidal_id",
        "qobuz_id",
        "spotify_id",
        "apple_music_id",
        "deezer_id",
        "traxsource_id",
        "itunes_id",
        "musicbrainz_id",
    ]
    select_parts = []
    for column in columns:
        if _has_column(conn, TRACK_IDENTITY_TABLE, column):
            select_parts.append(column)
        else:
            select_parts.append(f"NULL AS {column}")
    return conn.execute(
        f"""
        SELECT
            {", ".join(select_parts)}
        FROM track_identity
        ORDER BY id
        """
    ).fetchall()


def _candidate_isrcs_from_sources(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
) -> dict[str, set[str]]:
    candidates: dict[str, set[str]] = {}

    _add_candidate(
        candidates,
        _identity_key_isrc(row["identity_key"]),
        "identity_key",
    )

    if _table_exists(conn, SOURCE_TABLE):
        source_rows = conn.execute(
            """
            SELECT provider, provider_track_id, metadata_json, raw_payload_json
            FROM library_track_sources
            WHERE identity_key = ?
            ORDER BY id
            """,
            (str(row["identity_key"] or ""),),
        ).fetchall()
        for source_row in source_rows:
            provider = _normalize_text(source_row[0]) or "unknown"
            _add_candidate(
                candidates,
                _extract_isrc_from_json(source_row[2]),
                f"library_track_sources.metadata_json:{provider}",
            )
            _add_candidate(
                candidates,
                _extract_isrc_from_json(source_row[3]),
                f"library_track_sources.raw_payload_json:{provider}",
            )
            if provider.lower() == "isrc":
                _add_candidate(
                    candidates,
                    _normalize_isrc(source_row[1]),
                    "library_track_sources.provider_track_id:isrc",
                )

    if not _table_exists(conn, LEGACY_FILES_TABLE):
        return candidates

    for identity_column, files_column in PROVIDER_COLUMN_MAP.items():
        if not _has_column(conn, TRACK_IDENTITY_TABLE, identity_column):
            continue
        if not _has_column(conn, LEGACY_FILES_TABLE, files_column):
            continue
        provider_id = _normalize_text(row[identity_column])
        if not provider_id:
            continue

        file_select_parts = ["isrc"] if _has_column(conn, LEGACY_FILES_TABLE, "isrc") else ["NULL AS isrc"]
        if _has_column(conn, LEGACY_FILES_TABLE, "canonical_isrc"):
            file_select_parts.append("canonical_isrc")
        else:
            file_select_parts.append("NULL AS canonical_isrc")
        file_rows = conn.execute(
            f"""
            SELECT {", ".join(file_select_parts)}
            FROM {LEGACY_FILES_TABLE}
            WHERE {files_column} = ?
            """,
            (provider_id,),
        ).fetchall()
        for file_row in file_rows:
            _add_candidate(
                candidates,
                _normalize_isrc(file_row[0]),
                f"files.{files_column}:isrc",
            )
            _add_candidate(
                candidates,
                _normalize_isrc(file_row[1]),
                f"files.{files_column}:canonical_isrc",
            )

    return candidates


def _find_duplicate_isrc_groups(conn: sqlite3.Connection) -> tuple[tuple[str, tuple[int, ...]], ...]:
    rows = conn.execute(
        """
        SELECT id, isrc
        FROM track_identity
        WHERE isrc IS NOT NULL AND TRIM(isrc) != ''
        ORDER BY id
        """
    ).fetchall()
    grouped: dict[str, list[int]] = {}
    for identity_id, raw_isrc in rows:
        normalized = _normalize_isrc(raw_isrc)
        if not normalized:
            continue
        grouped.setdefault(normalized, []).append(int(identity_id))
    duplicates = [
        (isrc, tuple(ids))
        for isrc, ids in sorted(grouped.items())
        if len(ids) > 1
    ]
    return tuple(duplicates)


def _ensure_isrc_column(conn: sqlite3.Connection) -> None:
    if not _has_column(conn, TRACK_IDENTITY_TABLE, "isrc"):
        conn.execute("ALTER TABLE track_identity ADD COLUMN isrc TEXT")


def _apply_updates(conn: sqlite3.Connection, updates: tuple[PendingUpdate, ...]) -> None:
    has_updated_at = _has_column(conn, TRACK_IDENTITY_TABLE, "updated_at")
    for update in updates:
        if has_updated_at:
            conn.execute(
                """
                UPDATE track_identity
                SET isrc = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (update.isrc, update.identity_id),
            )
        else:
            conn.execute(
                """
                UPDATE track_identity
                SET isrc = ?
                WHERE id = ?
                """,
                (update.isrc, update.identity_id),
            )


def _create_unique_index(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS {UNIQUE_INDEX_NAME}
        ON track_identity(UPPER(TRIM(isrc)))
        WHERE isrc IS NOT NULL AND TRIM(isrc) != ''
        """
    )


def _create_not_null_guards(conn: sqlite3.Connection) -> None:
    conn.execute(f"DROP TRIGGER IF EXISTS {INSERT_TRIGGER_NAME}")
    conn.execute(f"DROP TRIGGER IF EXISTS {UPDATE_TRIGGER_NAME}")
    conn.execute(
        f"""
        CREATE TRIGGER {INSERT_TRIGGER_NAME}
        BEFORE INSERT ON track_identity
        FOR EACH ROW
        WHEN NEW.isrc IS NULL OR TRIM(NEW.isrc) = ''
        BEGIN
            SELECT RAISE(ABORT, 'track_identity.isrc is required for new identities');
        END;
        """
    )
    conn.execute(
        f"""
        CREATE TRIGGER {UPDATE_TRIGGER_NAME}
        BEFORE UPDATE OF isrc ON track_identity
        FOR EACH ROW
        WHEN NEW.isrc IS NULL OR TRIM(NEW.isrc) = ''
        BEGIN
            SELECT RAISE(ABORT, 'track_identity.isrc cannot be cleared once set');
        END;
        """
    )


def build_report(conn: sqlite3.Connection, *, mode: str) -> Report:
    if not _table_exists(conn, TRACK_IDENTITY_TABLE):
        return Report(
            mode=mode,
            total_rows=0,
            rows_with_isrc_before=0,
            planned_updates=(),
            unresolved_rows=(),
            duplicate_isrc_groups=(),
        )

    if mode == "execute":
        _ensure_isrc_column(conn)
    elif not _has_column(conn, TRACK_IDENTITY_TABLE, "isrc"):
        return Report(
            mode=mode,
            total_rows=0,
            rows_with_isrc_before=0,
            planned_updates=(),
            unresolved_rows=(),
            duplicate_isrc_groups=(),
        )
    rows = _track_identity_rows(conn)
    planned_updates: list[PendingUpdate] = []
    unresolved_rows: list[UnresolvedRow] = []

    rows_with_isrc_before = 0
    for row in rows:
        current_isrc = _normalize_isrc(row["isrc"])
        if current_isrc:
            rows_with_isrc_before += 1
            continue

        candidates = _candidate_isrcs_from_sources(conn, row)
        if len(candidates) == 1:
            isrc, sources = next(iter(sorted(candidates.items())))
            planned_updates.append(
                PendingUpdate(
                    identity_id=int(row["id"]),
                    isrc=isrc,
                    source=";".join(sorted(sources)),
                )
            )
            continue

        unresolved_rows.append(
            UnresolvedRow(
                identity_id=int(row["id"]),
                identity_key=str(row["identity_key"] or ""),
                candidate_count=len(candidates),
                candidate_sources=tuple(
                    f"{candidate}<-{','.join(sorted(sources))}"
                    for candidate, sources in sorted(candidates.items())
                ),
            )
        )

    if mode == "execute":
        _apply_updates(conn, tuple(planned_updates))

    duplicates = _find_duplicate_isrc_groups(conn)
    return Report(
        mode=mode,
        total_rows=len(rows),
        rows_with_isrc_before=rows_with_isrc_before,
        planned_updates=tuple(planned_updates),
        unresolved_rows=tuple(unresolved_rows),
        duplicate_isrc_groups=duplicates,
    )


def apply(conn: sqlite3.Connection, *, execute: bool) -> Report:
    if not _table_exists(conn, TRACK_IDENTITY_TABLE):
        return build_report(conn, mode="execute" if execute else "dry-run")

    report = build_report(conn, mode="execute" if execute else "dry-run")
    if report.duplicate_isrc_groups:
        detail = "; ".join(
            f"{isrc}: ids={list(identity_ids)}"
            for isrc, identity_ids in report.duplicate_isrc_groups
        )
        raise RuntimeError(f"duplicate ISRC values block uniqueness enforcement: {detail}")

    if execute:
        _create_unique_index(conn)
        _create_not_null_guards(conn)
        if report.unresolved_rows:
            logger.warning(
                "ISRC primary-key scaffold left %d identities unresolved; hard NOT NULL promotion is deferred.",
                len(report.unresolved_rows),
            )
    return report


def up(conn: sqlite3.Connection) -> None:
    original_factory = conn.row_factory
    try:
        conn.row_factory = sqlite3.Row
        apply(conn, execute=True)
    finally:
        conn.row_factory = original_factory


def _format_report(report: Report) -> str:
    lines = [
        f"mode: {report.mode}",
        f"track_identity_rows: {report.total_rows}",
        f"rows_with_isrc_before: {report.rows_with_isrc_before}",
        f"planned_backfills: {len(report.planned_updates)}",
        f"remaining_null_rows: {len(report.unresolved_rows)}",
        f"duplicate_isrc_groups: {len(report.duplicate_isrc_groups)}",
    ]
    for update in report.planned_updates:
        lines.append(
            f"backfill identity_id={update.identity_id} isrc={update.isrc} source={update.source}"
        )
    for unresolved in report.unresolved_rows:
        details = " | ".join(unresolved.candidate_sources) if unresolved.candidate_sources else "none"
        lines.append(
            "unresolved "
            f"identity_id={unresolved.identity_id} "
            f"identity_key={unresolved.identity_key} "
            f"candidate_count={unresolved.candidate_count} "
            f"candidates={details}"
        )
    for isrc, identity_ids in report.duplicate_isrc_groups:
        lines.append(f"duplicate isrc={isrc} identity_ids={list(identity_ids)}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scaffold ISRC-first enforcement for v3 track_identity."
    )
    parser.add_argument("--db", required=True, type=Path, help="Path to SQLite DB")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply updates and constraints (default: dry-run report only)",
    )
    args = parser.parse_args(argv)

    db_path = args.db.expanduser().resolve()
    if not db_path.exists():
        print(f"db not found: {db_path}")
        return 2

    conn = sqlite3.connect(str(db_path))
    original_factory = conn.row_factory
    try:
        conn.row_factory = sqlite3.Row
        report = apply(conn, execute=bool(args.execute))
        if args.execute:
            conn.commit()
        print(_format_report(report))
    except Exception as exc:  # noqa: BLE001
        if args.execute:
            conn.rollback()
        print(f"error: {exc}")
        return 1
    finally:
        conn.row_factory = original_factory
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
