from __future__ import annotations

import click
from pathlib import Path

from tagslut.cli.runtime import run_tagslut_wrapper, WRAPPER_CONTEXT


def register_index_group(cli: click.Group) -> None:
    @cli.group()
    def index():
        """Canonical indexing and metadata registration commands."""

    @index.command("register", context_settings=WRAPPER_CONTEXT)
    @click.argument("args", nargs=-1, type=click.UNPROCESSED)
    def index_register(args):
        """Register files in inventory."""
        run_tagslut_wrapper(["_mgmt", "register", *list(args)])

    @index.command("check", context_settings=WRAPPER_CONTEXT)
    @click.argument("args", nargs=-1, type=click.UNPROCESSED)
    def index_check(args):
        """Check for duplicates before downloading."""
        run_tagslut_wrapper(["_mgmt", "check", *list(args)])

    @index.command("duration-check", context_settings=WRAPPER_CONTEXT)
    @click.argument("args", nargs=-1, type=click.UNPROCESSED)
    def index_duration_check(args):
        """Measure durations and compute duration status."""
        run_tagslut_wrapper(["_mgmt", "check-duration", *list(args)])

    @index.command("duration-audit", context_settings=WRAPPER_CONTEXT)
    @click.argument("args", nargs=-1, type=click.UNPROCESSED)
    def index_duration_audit(args):
        """Audit duration anomalies from inventory."""
        run_tagslut_wrapper(["_mgmt", "audit-duration", *list(args)])

    @index.command("set-duration-ref", context_settings=WRAPPER_CONTEXT)
    @click.argument("args", nargs=-1, type=click.UNPROCESSED)
    def index_set_duration_ref(args):
        """Set manual duration reference from a known-good file."""
        run_tagslut_wrapper(["_mgmt", "set-duration-ref", *list(args)])

    @index.command("enrich", context_settings=WRAPPER_CONTEXT)
    @click.argument("args", nargs=-1, type=click.UNPROCESSED)
    def index_enrich(args):
        """Run metadata enrichment for indexed files."""
        run_tagslut_wrapper(["_metadata", "enrich", *list(args)])

    @index.command("rekordbox-sync")
    @click.option(
        "--usb",
        required=True,
        type=click.Path(exists=True, path_type=Path),
        help="USB mount point containing PIONEER/ database",
    )
    @click.option("--db", "db_path", required=True, type=click.Path())
    @click.option("--dry-run", is_flag=True)
    def rekordbox_sync(usb: Path, db_path: str, dry_run: bool) -> None:
        """Sync BPM, key, and Rekordbox IDs from USB back to master library."""
        from tagslut.metadata.rekordbox_sync import sync_from_usb
        from tagslut.storage.schema import get_connection

        with get_connection(db_path) as conn:
            summary = sync_from_usb(usb, conn, dry_run=dry_run)

        prefix = "[DRY RUN] " if dry_run else ""
        click.echo(
            f"{prefix}Rekordbox sync: {summary['updated']} updated, "
            f"{summary['not_found']} not found, {len(summary['errors'])} errors"
        )
        for err in summary["errors"]:
            click.echo(f"  • {err}")
