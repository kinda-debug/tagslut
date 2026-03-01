from __future__ import annotations

import sqlite3
from typing import Optional

import click

from tagslut.cli.runtime import run_tagslut_wrapper, WRAPPER_CONTEXT
from tagslut.storage.schema import init_db


def register_index_group(cli: click.Group) -> None:
    @cli.group()
    def index():  # type: ignore  # TODO: mypy-strict
        """Canonical indexing and metadata registration commands."""

    @index.command("register", context_settings=WRAPPER_CONTEXT)
    @click.argument("args", nargs=-1, type=click.UNPROCESSED)
    def index_register(args):  # type: ignore  # TODO: mypy-strict
        """Register files in inventory."""
        run_tagslut_wrapper(["_mgmt", "register", *list(args)])

    @index.command("check", context_settings=WRAPPER_CONTEXT)
    @click.argument("args", nargs=-1, type=click.UNPROCESSED)
    def index_check(args):  # type: ignore  # TODO: mypy-strict
        """Check for duplicates before downloading."""
        run_tagslut_wrapper(["_mgmt", "check", *list(args)])

    @index.command("duration-check", context_settings=WRAPPER_CONTEXT)
    @click.argument("args", nargs=-1, type=click.UNPROCESSED)
    def index_duration_check(args):  # type: ignore  # TODO: mypy-strict
        """Measure durations and compute duration status."""
        run_tagslut_wrapper(["_mgmt", "check-duration", *list(args)])

    @index.command("duration-audit", context_settings=WRAPPER_CONTEXT)
    @click.argument("args", nargs=-1, type=click.UNPROCESSED)
    def index_duration_audit(args):  # type: ignore  # TODO: mypy-strict
        """Audit duration anomalies from inventory."""
        run_tagslut_wrapper(["_mgmt", "audit-duration", *list(args)])

    @index.command("set-duration-ref", context_settings=WRAPPER_CONTEXT)
    @click.argument("args", nargs=-1, type=click.UNPROCESSED)
    def index_set_duration_ref(args):  # type: ignore  # TODO: mypy-strict
        """Set manual duration reference from a known-good file."""
        run_tagslut_wrapper(["_mgmt", "set-duration-ref", *list(args)])

    @index.command("enrich", context_settings=WRAPPER_CONTEXT)
    @click.argument("args", nargs=-1, type=click.UNPROCESSED)
    def index_enrich(args):  # type: ignore  # TODO: mypy-strict
        """Run metadata enrichment for indexed files."""
        run_tagslut_wrapper(["_metadata", "enrich", *list(args)])

    # ------------------------------------------------------------------
    # DJ flag commands
    # ------------------------------------------------------------------

    @index.command("dj-flag")
    @click.argument("target")
    @click.option(
        "--set",
        "flag_value",
        default="true",
        show_default=True,
        type=click.Choice(["true", "false"], case_sensitive=False),
        help="Set dj_flag to true or false.",
    )
    @click.option(
        "--db",
        "db_path",
        required=True,
        type=click.Path(exists=True),
        help="Path to the inventory SQLite database.",
    )
    def index_dj_flag(target: str, flag_value: str, db_path: str) -> None:
        """Flag a track (or batch by ISRC) as DJ material.

        TARGET may be a file path or an ISRC string.
        """
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        init_db(conn)
        value = 1 if flag_value.lower() == "true" else 0
        with conn:
            cur = conn.execute(
                "UPDATE files SET dj_flag = ? WHERE path = ? OR isrc = ?",
                (value, target, target),
            )
        click.echo(f"dj_flag set to {value} for {cur.rowcount} row(s) matching '{target}'.")
        conn.close()

    @index.command("dj-autoflag")
    @click.option("--genre", default=None, help="Filter by genre (case-insensitive substring).")
    @click.option("--bpm", "bpm_range", default=None, help="BPM range, e.g. '125-145'.")
    @click.option("--label", default=None, help="Filter by label (case-insensitive substring).")
    @click.option(
        "--set",
        "flag_value",
        default="true",
        show_default=True,
        type=click.Choice(["true", "false"], case_sensitive=False),
        help="Set dj_flag to true or false.",
    )
    @click.option(
        "--db",
        "db_path",
        required=True,
        type=click.Path(exists=True),
        help="Path to the inventory SQLite database.",
    )
    def index_dj_autoflag(
        genre: Optional[str],
        bpm_range: Optional[str],
        label: Optional[str],
        flag_value: str,
        db_path: str,
    ) -> None:
        """Bulk-flag tracks by genre, BPM range, or label.

        Example: tagslut index dj-autoflag --genre techno --bpm 125-145 --db inventory.db
        """
        value = 1 if flag_value.lower() == "true" else 0

        clauses: list[str] = []
        params: list[object] = []

        if genre:
            clauses.append(
                "(LOWER(genre) LIKE ? OR LOWER(canonical_genre) LIKE ?)"
            )
            pattern = f"%{genre.lower()}%"
            params.extend([pattern, pattern])

        if bpm_range:
            try:
                lo_str, hi_str = bpm_range.split("-", 1)
                lo, hi = float(lo_str), float(hi_str)
            except ValueError:
                click.echo(
                    f"Invalid BPM range '{bpm_range}'. Expected format: '125-145'.",
                    err=True,
                )
                return
            clauses.append("(bpm BETWEEN ? AND ? OR canonical_bpm BETWEEN ? AND ?)")
            params.extend([lo, hi, lo, hi])

        if label:
            clauses.append("LOWER(canonical_label) LIKE ?")
            params.append(f"%{label.lower()}%")

        if not clauses:
            click.echo("Provide at least one filter (--genre, --bpm, --label).", err=True)
            return

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        init_db(conn)

        where = " AND ".join(clauses)
        params.insert(0, value)
        with conn:
            cur = conn.execute(f"UPDATE files SET dj_flag = ? WHERE {where}", params)
        click.echo(f"dj_flag set to {value} for {cur.rowcount} row(s).")
        conn.close()

    @index.command("dj-status")
    @click.option(
        "--db",
        "db_path",
        required=True,
        type=click.Path(exists=True),
        help="Path to the inventory SQLite database.",
    )
    def index_dj_status(db_path: str) -> None:
        """Show DJ pool status: flagged tracks, export state, and field coverage."""
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            total = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            flagged = conn.execute(
                "SELECT COUNT(*) FROM files WHERE dj_flag = 1"
            ).fetchone()[0]
            exported = conn.execute(
                "SELECT COUNT(*) FROM files WHERE last_exported_usb IS NOT NULL"
            ).fetchone()[0]
            has_bpm = conn.execute(
                "SELECT COUNT(*) FROM files WHERE bpm IS NOT NULL"
            ).fetchone()[0]
            has_key = conn.execute(
                "SELECT COUNT(*) FROM files WHERE key_camelot IS NOT NULL"
            ).fetchone()[0]
            has_isrc = conn.execute(
                "SELECT COUNT(*) FROM files WHERE isrc IS NOT NULL"
            ).fetchone()[0]
            in_pool = conn.execute(
                "SELECT COUNT(*) FROM files WHERE dj_pool_path IS NOT NULL"
            ).fetchone()[0]
        finally:
            conn.close()

        click.echo(f"Total tracks:         {total}")
        click.echo(f"DJ-flagged:           {flagged}")
        click.echo(f"In DJ pool (MP3):     {in_pool}")
        click.echo(f"Exported to USB:      {exported}")
        click.echo(f"Have BPM:             {has_bpm}")
        click.echo(f"Have Camelot key:     {has_key}")
        click.echo(f"Have ISRC:            {has_isrc}")
