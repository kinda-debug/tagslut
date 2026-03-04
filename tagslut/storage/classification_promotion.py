from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


PromotionStatus = Literal["dry_run", "promoted", "already_promoted"]


class PromotionError(RuntimeError):
    """Raised when classification promotion cannot be completed safely."""


@dataclass(frozen=True)
class PromotionResult:
    status: PromotionStatus
    message: str
    method: str | None
    sqlite_version: str
    db_path: Path
    backup_path: Path | None
    total_rows: int
    remove_rows: int
    remove_pct: float
    genre_blank_rows: int
    genre_blank_pct: float
    distribution: dict[str, int]


def _quote_ident(name: str) -> str:
    escaped = name.replace('"', '""')
    return f'"{escaped}"'


def _sqlite_version_tuple(version: str) -> tuple[int, int, int]:
    parts = version.split(".")
    major = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else 0
    minor = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    patch_part = parts[2] if len(parts) > 2 else "0"
    patch_digits = ""
    for ch in patch_part:
        if ch.isdigit():
            patch_digits += ch
        else:
            break
    patch = int(patch_digits) if patch_digits else 0
    return major, minor, patch


def _supports_rename_column(sqlite_version: str) -> bool:
    return _sqlite_version_tuple(sqlite_version) >= (3, 25, 0)


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, table_name: str) -> list[sqlite3.Row]:
    return conn.execute(f"PRAGMA table_info({_quote_ident(table_name)})").fetchall()


def _has_column(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    return any(str(row["name"]) == column_name for row in _table_columns(conn, table_name))


def _distribution_for_column(conn: sqlite3.Connection, column_name: str) -> dict[str, int]:
    if column_name not in {"classification", "classification_v2"}:
        raise PromotionError(f"Unsupported classification column: {column_name}")

    rows = conn.execute(
        f"""
        SELECT COALESCE(NULLIF(TRIM({_quote_ident(column_name)}), ''), '(blank)') AS bucket,
               COUNT(*) AS n
        FROM files
        GROUP BY bucket
        ORDER BY n DESC, bucket
        """
    ).fetchall()
    return {str(row["bucket"]): int(row["n"]) for row in rows}


def _remove_metrics(conn: sqlite3.Connection, column_name: str) -> tuple[int, int, float]:
    total_rows = int(conn.execute("SELECT COUNT(*) FROM files").fetchone()[0])
    remove_rows = int(
        conn.execute(
            f"SELECT COUNT(*) FROM files WHERE LOWER(TRIM(COALESCE({_quote_ident(column_name)}, ''))) = 'remove'"
        ).fetchone()[0]
    )
    remove_pct = (100.0 * remove_rows / total_rows) if total_rows else 0.0
    return total_rows, remove_rows, remove_pct


def _genre_blank_metrics(conn: sqlite3.Connection) -> tuple[int, float]:
    has_genre = _has_column(conn, "files", "genre")
    has_canonical_genre = _has_column(conn, "files", "canonical_genre")
    if not has_genre and not has_canonical_genre:
        return 0, 0.0

    if has_genre and has_canonical_genre:
        blank_rows = int(
            conn.execute(
                "SELECT COUNT(*) FROM files WHERE TRIM(COALESCE(genre, canonical_genre, '')) = ''"
            ).fetchone()[0]
        )
    elif has_genre:
        blank_rows = int(
            conn.execute(
                "SELECT COUNT(*) FROM files WHERE TRIM(COALESCE(genre, '')) = ''"
            ).fetchone()[0]
        )
    else:
        blank_rows = int(
            conn.execute(
                "SELECT COUNT(*) FROM files WHERE TRIM(COALESCE(canonical_genre, '')) = ''"
            ).fetchone()[0]
        )

    total_rows = int(conn.execute("SELECT COUNT(*) FROM files").fetchone()[0])
    blank_pct = (100.0 * blank_rows / total_rows) if total_rows else 0.0
    return blank_rows, blank_pct


def _collect_metrics(
    conn: sqlite3.Connection,
    classification_column: str,
) -> tuple[int, int, float, int, float, dict[str, int]]:
    distribution = _distribution_for_column(conn, classification_column)
    total_rows, remove_rows, remove_pct = _remove_metrics(conn, classification_column)
    genre_blank_rows, genre_blank_pct = _genre_blank_metrics(conn)
    return total_rows, remove_rows, remove_pct, genre_blank_rows, genre_blank_pct, distribution


def _enforce_tripwires(remove_pct: float, genre_blank_pct: float) -> None:
    if remove_pct > 80.0:
        raise PromotionError(
            f"Tripwire triggered: remove% is {remove_pct:.2f} (> 80.00). "
            "Promotion aborted and rolled back."
        )
    if genre_blank_pct > 20.0:
        raise PromotionError(
            f"Tripwire triggered: genre_blank% is {genre_blank_pct:.2f} (> 20.00). "
            "Promotion aborted and rolled back."
        )


def _create_backup(db_path: Path, backup_path: Path) -> None:
    if backup_path.exists():
        backup_path.unlink()

    source_conn = sqlite3.connect(str(db_path))
    backup_conn = sqlite3.connect(str(backup_path))
    try:
        source_conn.backup(backup_conn)
    finally:
        backup_conn.close()
        source_conn.close()


def _choose_unique_table_name(conn: sqlite3.Connection, base_name: str) -> str:
    candidate = base_name
    suffix = 0
    while _table_exists(conn, candidate):
        suffix += 1
        candidate = f"{base_name}_{suffix}"
    return candidate


def _promote_with_rename(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE files RENAME COLUMN classification TO classification_v1")
    conn.execute("ALTER TABLE files RENAME COLUMN classification_v2 TO classification")


def _column_definitions_for_copy(columns: list[sqlite3.Row]) -> tuple[list[str], list[str], list[str], list[str]]:
    create_defs: list[str] = []
    insert_cols: list[str] = []
    select_exprs: list[str] = []
    composite_pk: list[str] = []

    for row in columns:
        old_name = str(row["name"])
        if old_name == "classification":
            new_name = "classification_v1"
        elif old_name == "classification_v2":
            new_name = "classification"
        else:
            new_name = old_name

        col_type = str(row["type"] or "").strip()
        notnull = int(row["notnull"] or 0) == 1
        default = row["dflt_value"]
        pk_order = int(row["pk"] or 0)

        parts = [_quote_ident(new_name)]
        if col_type:
            parts.append(col_type)

        if pk_order > 0 and sum(int(r["pk"] or 0) > 0 for r in columns) == 1:
            parts.append("PRIMARY KEY")
        elif pk_order > 0:
            composite_pk.append(_quote_ident(new_name))

        if notnull:
            parts.append("NOT NULL")
        if default is not None:
            parts.append(f"DEFAULT {default}")

        create_defs.append(" ".join(parts))
        insert_cols.append(_quote_ident(new_name))
        select_exprs.append(_quote_ident(old_name))

    return create_defs, insert_cols, select_exprs, composite_pk


def _promote_with_classic_copy(conn: sqlite3.Connection) -> None:
    columns = _table_columns(conn, "files")
    if not columns:
        raise PromotionError("Could not inspect files table columns for classic-copy promotion.")

    create_defs, insert_cols, select_exprs, composite_pk = _column_definitions_for_copy(columns)
    if composite_pk:
        create_defs.append(f"PRIMARY KEY ({', '.join(composite_pk)})")

    tmp_table = _choose_unique_table_name(conn, "files_promotion_tmp")
    archived_table = _choose_unique_table_name(conn, "files_pre_classification_promotion")

    conn.execute(f"CREATE TABLE {_quote_ident(tmp_table)} ({', '.join(create_defs)})")
    conn.execute(
        f"""
        INSERT INTO {_quote_ident(tmp_table)} ({', '.join(insert_cols)})
        SELECT {', '.join(select_exprs)}
        FROM files
        """
    )
    conn.execute(f"ALTER TABLE files RENAME TO {_quote_ident(archived_table)}")
    conn.execute(f"ALTER TABLE {_quote_ident(tmp_table)} RENAME TO files")


def promote_classification_v2(
    db_path: Path | str,
    *,
    dry_run: bool = False,
    sqlite_version_override: str | None = None,
) -> PromotionResult:
    path = Path(db_path).expanduser().resolve()
    if not path.exists():
        raise PromotionError(f"Database not found: {path}")

    preflight_conn = sqlite3.connect(str(path))
    preflight_conn.row_factory = sqlite3.Row
    try:
        sqlite_version = (
            sqlite_version_override
            or str(preflight_conn.execute("SELECT sqlite_version()").fetchone()[0])
        )

        if not _table_exists(preflight_conn, "files"):
            raise PromotionError("files table not found in database.")

        has_classification = _has_column(preflight_conn, "files", "classification")
        has_classification_v2 = _has_column(preflight_conn, "files", "classification_v2")

        if not has_classification_v2:
            if not has_classification:
                raise PromotionError(
                    "Neither files.classification nor files.classification_v2 exists; cannot determine promotion state."
                )
            (
                total_rows,
                remove_rows,
                remove_pct,
                genre_blank_rows,
                genre_blank_pct,
                distribution,
            ) = _collect_metrics(preflight_conn, "classification")
            return PromotionResult(
                status="already_promoted",
                message="Already promoted: classification_v2 column not found.",
                method=None,
                sqlite_version=sqlite_version,
                db_path=path,
                backup_path=None,
                total_rows=total_rows,
                remove_rows=remove_rows,
                remove_pct=remove_pct,
                genre_blank_rows=genre_blank_rows,
                genre_blank_pct=genre_blank_pct,
                distribution=distribution,
            )

        if not has_classification:
            raise PromotionError(
                "files.classification column missing while classification_v2 exists; refusing to run unsafe promotion."
            )

        method = "rename-column" if _supports_rename_column(sqlite_version) else "classic-copy"
        (
            total_rows,
            remove_rows,
            remove_pct,
            genre_blank_rows,
            genre_blank_pct,
            distribution,
        ) = _collect_metrics(preflight_conn, "classification_v2")

        if dry_run:
            return PromotionResult(
                status="dry_run",
                message="Dry-run: promotion plan generated.",
                method=method,
                sqlite_version=sqlite_version,
                db_path=path,
                backup_path=None,
                total_rows=total_rows,
                remove_rows=remove_rows,
                remove_pct=remove_pct,
                genre_blank_rows=genre_blank_rows,
                genre_blank_pct=genre_blank_pct,
                distribution=distribution,
            )
    finally:
        preflight_conn.close()

    backup_path = Path(f"{path}.backup")
    _create_backup(path, backup_path)

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN IMMEDIATE")
        has_classification = _has_column(conn, "files", "classification")
        has_classification_v2 = _has_column(conn, "files", "classification_v2")
        if not has_classification_v2:
            conn.rollback()
            return PromotionResult(
                status="already_promoted",
                message="Already promoted: classification_v2 column not found.",
                method=None,
                sqlite_version=sqlite_version,
                db_path=path,
                backup_path=backup_path,
                total_rows=0,
                remove_rows=0,
                remove_pct=0.0,
                genre_blank_rows=0,
                genre_blank_pct=0.0,
                distribution={},
            )
        if not has_classification:
            raise PromotionError(
                "files.classification column missing while classification_v2 exists; refusing to run unsafe promotion."
            )

        if method == "rename-column":
            _promote_with_rename(conn)
        else:
            _promote_with_classic_copy(conn)

        (
            total_rows,
            remove_rows,
            remove_pct,
            genre_blank_rows,
            genre_blank_pct,
            distribution,
        ) = _collect_metrics(conn, "classification")
        _enforce_tripwires(remove_pct, genre_blank_pct)
        conn.commit()
        return PromotionResult(
            status="promoted",
            message="Promotion complete.",
            method=method,
            sqlite_version=sqlite_version,
            db_path=path,
            backup_path=backup_path,
            total_rows=total_rows,
            remove_rows=remove_rows,
            remove_pct=remove_pct,
            genre_blank_rows=genre_blank_rows,
            genre_blank_pct=genre_blank_pct,
            distribution=distribution,
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def format_promotion_result(result: PromotionResult) -> list[str]:
    lines = [
        f"Status: {result.status}",
        result.message,
        f"Database: {result.db_path}",
        f"SQLite version: {result.sqlite_version}",
    ]
    if result.method:
        lines.append(f"Method: {result.method}")
    if result.backup_path:
        lines.append(f"Backup: {result.backup_path}")

    lines.extend(
        [
            f"Total rows: {result.total_rows}",
            f"remove rows: {result.remove_rows} ({result.remove_pct:.2f}%)",
            f"genre blank rows: {result.genre_blank_rows} ({result.genre_blank_pct:.2f}%)",
            "Classification distribution:",
        ]
    )
    if result.distribution:
        for label, count in result.distribution.items():
            lines.append(f"  - {label}: {count}")
    else:
        lines.append("  - (no rows)")
    return lines
