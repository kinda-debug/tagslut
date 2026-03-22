from __future__ import annotations

import csv
import logging
import sqlite3
import sys
from pathlib import Path
from typing import TextIO

import click

from tagslut.storage.models import DJ_SET_ROLES, DJ_SUBROLES
from tagslut.storage.queries import query_dj_candidates
from tagslut.utils.db import DbResolutionError, resolve_cli_env_db_path

logger = logging.getLogger(__name__)

EXPORT_COLUMNS = [
    "path",
    "artist",
    "title",
    "bpm",
    "key_camelot",
    "genre",
    "dj_set_role",
    "dj_subrole",
]
_FORBIDDEN_ROLE_VALUE = "emergency"


def _normalize_value(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _validate_choice(value: str | None, *, field_name: str, allowed: frozenset[str]) -> str | None:
    normalized = _normalize_value(value)
    if normalized is None:
        return None
    if normalized == _FORBIDDEN_ROLE_VALUE:
        raise ValueError(
            f"Invalid {field_name} {normalized!r}. "
            f"{_FORBIDDEN_ROLE_VALUE!r} is reserved and may not be assigned."
        )
    if normalized not in allowed:
        raise ValueError(
            f"Invalid {field_name} {normalized!r}. "
            f"Allowed: {sorted(allowed)}"
        )
    return normalized


def _validate_role(value: str | None) -> str:
    normalized = _validate_choice(value, field_name="dj_set_role", allowed=DJ_SET_ROLES)
    if normalized is None:
        raise ValueError("Invalid dj_set_role None. Allowed values are required.")
    return normalized


def _validate_subrole(value: str | None) -> str | None:
    return _validate_choice(value, field_name="dj_subrole", allowed=DJ_SUBROLES)


def _resolve_db_path(db_path: str | None, *, purpose: str) -> Path:
    cli_value = Path(db_path) if db_path is not None else None
    try:
        return resolve_cli_env_db_path(
            cli_value,
            purpose=purpose,
            source_label="--db",
        ).path
    except DbResolutionError as exc:
        raise click.ClickException(str(exc)) from exc


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _update_role_target(
    conn: sqlite3.Connection,
    target: str,
    role: str,
    subrole: str | None,
    *,
    replace_subrole: bool,
) -> list[str]:
    paths = [
        str(row["path"])
        for row in conn.execute(
            "SELECT DISTINCT path FROM files WHERE path = ? OR checksum = ? ORDER BY path",
            (target, target),
        ).fetchall()
    ]
    if not paths:
        return []

    if replace_subrole:
        conn.execute(
            "UPDATE files SET dj_set_role = ?, dj_subrole = ? WHERE path = ? OR checksum = ?",
            (role, subrole, target, target),
        )
    else:
        conn.execute(
            "UPDATE files SET dj_set_role = ? WHERE path = ? OR checksum = ?",
            (role, target, target),
        )
    return paths


def _update_role_path(
    conn: sqlite3.Connection,
    path: str,
    role: str,
    subrole: str | None,
    *,
    replace_subrole: bool,
) -> int:
    if replace_subrole:
        cursor = conn.execute(
            "UPDATE files SET dj_set_role = ?, dj_subrole = ? WHERE path = ?",
            (role, subrole, path),
        )
    else:
        cursor = conn.execute(
            "UPDATE files SET dj_set_role = ? WHERE path = ?",
            (role, path),
        )
    return int(cursor.rowcount or 0)


def _write_export_rows(handle: TextIO, rows: list[sqlite3.Row]) -> None:
    writer = csv.DictWriter(handle, fieldnames=EXPORT_COLUMNS)
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row[column] for column in EXPORT_COLUMNS})


@click.group("role")
def role_group() -> None:
    """Manage DJ set roles."""


# Role decision rubric:
# groove : value mainly musical, backbone of the bar night
# prime  : raises the room while staying true to your sound
# bridge : value mainly recognitional, civilians light up
# club   : reserve pressure, would not want the whole night to sound like this
#
# Hesitating between prime and bridge?
#   mainly musical       -> prime
#   mainly recognitional -> bridge
@role_group.command("set")
@click.argument("target")
@click.argument("role")
@click.option("--subrole", default=None, help="Optional DJ subrole")
@click.option("--db", "db_path", type=click.Path(), help="SQLite DB path (or TAGSLUT_DB)")
def set_role(target: str, role: str, subrole: str | None, db_path: str | None) -> None:
    """Set DJ set role by file path or checksum."""
    try:
        validated_role = _validate_role(role)
        validated_subrole = _validate_subrole(subrole) if subrole is not None else None
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    conn = _connect(_resolve_db_path(db_path, purpose="write"))
    try:
        with conn:
            matched_paths = _update_role_target(
                conn,
                target,
                validated_role,
                validated_subrole,
                replace_subrole=subrole is not None,
            )
        if not matched_paths:
            raise click.ClickException(f"No matching file found for {target!r}.")
    except sqlite3.Error as exc:
        raise click.ClickException(f"Failed to update DJ role: {exc}") from exc
    finally:
        conn.close()

    for path in matched_paths:
        click.echo(f"SET  {path}  dj_set_role={validated_role}")


@role_group.command("bulk")
@click.argument("csv_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--db", "db_path", type=click.Path(), help="SQLite DB path (or TAGSLUT_DB)")
def bulk_set_roles(csv_file: str, db_path: str | None) -> None:
    """Bulk-apply DJ set roles from CSV."""
    csv_path = Path(csv_file)
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        required_columns = {"path", "dj_set_role"}
        missing_columns = sorted(required_columns.difference(fieldnames))
        if missing_columns:
            raise click.ClickException(
                f"CSV must include columns: {', '.join(sorted(required_columns))}. "
                f"Missing: {', '.join(missing_columns)}"
            )

        subrole_present = "dj_subrole" in fieldnames
        updated = 0
        skipped = 0
        errors = 0

        conn = _connect(_resolve_db_path(db_path, purpose="write"))
        try:
            try:
                with conn:
                    for row_number, row in enumerate(reader, start=2):
                        path = _normalize_value(row.get("path"))
                        if path is None:
                            logger.warning("Row %s: missing path", row_number)
                            errors += 1
                            continue

                        try:
                            validated_role = _validate_role(row.get("dj_set_role"))
                        except ValueError as exc:
                            logger.warning("Row %s (%s): %s", row_number, path, exc)
                            skipped += 1
                            continue

                        replace_subrole = subrole_present
                        validated_subrole: str | None = None
                        if subrole_present:
                            try:
                                validated_subrole = _validate_subrole(row.get("dj_subrole"))
                            except ValueError as exc:
                                logger.warning(
                                    "Row %s (%s): %s Clearing dj_subrole.",
                                    row_number,
                                    path,
                                    exc,
                                )
                                validated_subrole = None

                        rowcount = _update_role_path(
                            conn,
                            path,
                            validated_role,
                            validated_subrole,
                            replace_subrole=replace_subrole,
                        )
                        if rowcount == 0:
                            logger.warning("Row %s (%s): no matching file found", row_number, path)
                            errors += 1
                            continue

                        updated += rowcount
            except Exception as exc:
                raise click.ClickException(f"Bulk role update failed: {exc}") from exc
        finally:
            conn.close()

    click.echo(f"Bulk role set: {updated} updated, {skipped} skipped, {errors} errors")


@role_group.command("export")
@click.option("--unassigned-only", is_flag=True, help="Only export rows without dj_set_role")
@click.option("--bpm-min", type=float, default=None, help="Minimum BPM filter")
@click.option("--bpm-max", type=float, default=None, help="Maximum BPM filter")
@click.option("--output", type=click.Path(dir_okay=False), default=None, help="Write CSV to file")
@click.option("--db", "db_path", type=click.Path(), help="SQLite DB path (or TAGSLUT_DB)")
def export_roles(
    unassigned_only: bool,
    bpm_min: float | None,
    bpm_max: float | None,
    output: str | None,
    db_path: str | None,
) -> None:
    """Export DJ role candidates as CSV."""
    if bpm_min is not None and bpm_max is not None and bpm_min > bpm_max:
        raise click.ClickException("--bpm-min cannot be greater than --bpm-max")

    conn = _connect(_resolve_db_path(db_path, purpose="read"))
    try:
        rows = query_dj_candidates(
            conn,
            unassigned_only=unassigned_only,
            bpm_min=bpm_min,
            bpm_max=bpm_max,
        )
    finally:
        conn.close()

    if output is None:
        _write_export_rows(sys.stdout, rows)
        return

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        _write_export_rows(handle, rows)
