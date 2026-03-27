from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

import click

from tagslut.storage.v3 import resolve_asset_id_by_path


_ISRC_RE = re.compile(r"\b[A-Z]{2}[A-Z0-9]{3}[0-9]{2}[0-9]{5}\b")


def _normalize_isrc(value: str | None) -> str:
    text = (value or "").strip().upper()
    if not text:
        return ""
    text = re.sub(r"[\s-]+", "", text)
    m = _ISRC_RE.search(text)
    return m.group(0) if m else ""


def _has_active_column(conn: sqlite3.Connection) -> bool:
    cols = [str(row[1]) for row in conn.execute("PRAGMA table_info(asset_link)").fetchall()]
    return "active" in cols


def _resolve_identity_for_asset(conn: sqlite3.Connection, asset_id: int) -> int | None:
    active_where = "AND al.active = 1" if _has_active_column(conn) else ""
    row = conn.execute(
        f"""
        SELECT al.identity_id
        FROM asset_link al
        WHERE al.asset_id = ?
        {active_where}
        ORDER BY al.confidence DESC, al.id ASC
        LIMIT 1
        """,
        (int(asset_id),),
    ).fetchone()
    return int(row[0]) if row and row[0] is not None else None


def _load_identity_row(conn: sqlite3.Connection, identity_id: int) -> sqlite3.Row | None:
    conn.row_factory = sqlite3.Row
    return conn.execute(
        """
        SELECT
            id,
            isrc,
            beatport_id,
            tidal_id,
            artist_norm,
            title_norm,
            ingested_at,
            ingestion_method,
            ingestion_source,
            ingestion_confidence
        FROM track_identity
        WHERE id = ?
        """,
        (int(identity_id),),
    ).fetchone()


def _recent_provenance_events(
    conn: sqlite3.Connection,
    *,
    identity_id: int | None,
    asset_id: int | None,
    limit: int = 40,
) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    clauses: list[str] = []
    params: list[Any] = []
    if identity_id is not None:
        clauses.append("identity_id = ?")
        params.append(int(identity_id))
    if asset_id is not None:
        clauses.append("asset_id = ?")
        params.append(int(asset_id))
    if not clauses:
        return []
    where = " OR ".join(clauses)
    return list(
        conn.execute(
            f"""
            SELECT event_type, status, event_time, asset_id, identity_id, details_json
            FROM provenance_event
            WHERE {where}
            ORDER BY event_time DESC, id DESC
            LIMIT ?
            """,
            (*params, int(limit)),
        ).fetchall()
    )


def register_v3_group(cli: click.Group) -> None:
    @cli.group()
    def v3():  # type: ignore  # TODO: mypy-strict
        """V3 database utilities."""

    @v3.group("provenance")
    def provenance_group():  # type: ignore  # TODO: mypy-strict
        """Query v3 provenance and ingestion attribution."""

    @provenance_group.command("show")
    @click.option("--db", "db_path", required=True, type=click.Path(exists=True), help="tagslut v3 DB path")
    @click.option("--path", "asset_path", type=click.Path(exists=True), help="Asset path to resolve")
    @click.option("--identity-id", type=int, default=None, help="track_identity.id")
    @click.option("--isrc", default=None, help="ISRC to resolve")
    @click.option("--limit", type=int, default=40, show_default=True, help="Max provenance_event rows")
    def provenance_show(  # type: ignore  # TODO: mypy-strict
        db_path: str,
        asset_path: str | None,
        identity_id: int | None,
        isrc: str | None,
        limit: int,
    ) -> None:
        """Show ingestion fields + recent provenance_event rows."""
        if sum(bool(x) for x in (asset_path, identity_id is not None, isrc)) != 1:
            raise click.ClickException("Provide exactly one of --path, --identity-id, or --isrc")

        resolved_db = Path(db_path).expanduser().resolve()
        conn = sqlite3.connect(str(resolved_db))
        try:
            asset_id: int | None = None
            resolved_identity_id: int | None = identity_id

            if asset_path:
                p = Path(asset_path).expanduser().resolve()
                asset_id = resolve_asset_id_by_path(conn, str(p))
                if asset_id is None:
                    raise click.ClickException(f"asset_file not found for path: {p}")
                resolved_identity_id = _resolve_identity_for_asset(conn, asset_id)

            if isrc is not None:
                norm = _normalize_isrc(isrc)
                if not norm:
                    raise click.ClickException("Invalid ISRC")
                row = conn.execute(
                    """
                    SELECT id
                    FROM track_identity
                    WHERE upper(replace(replace(isrc, '-', ''), ' ', '')) = ?
                    LIMIT 1
                    """,
                    (norm,),
                ).fetchone()
                if not row:
                    raise click.ClickException(f"No track_identity found for ISRC={norm}")
                resolved_identity_id = int(row[0])

            if resolved_identity_id is None:
                raise click.ClickException("Could not resolve identity_id for the requested input")

            identity_row = _load_identity_row(conn, resolved_identity_id)
            if identity_row is None:
                raise click.ClickException(f"track_identity not found: id={resolved_identity_id}")

            click.echo(f"identity_id: {identity_row['id']}")
            click.echo(f"isrc: {identity_row['isrc']}")
            click.echo(f"beatport_id: {identity_row['beatport_id']}")
            click.echo(f"tidal_id: {identity_row['tidal_id']}")
            click.echo(f"artist_norm: {identity_row['artist_norm']}")
            click.echo(f"title_norm: {identity_row['title_norm']}")
            click.echo(f"ingested_at: {identity_row['ingested_at']}")
            click.echo(f"ingestion_method: {identity_row['ingestion_method']}")
            click.echo(f"ingestion_source: {identity_row['ingestion_source']}")
            click.echo(f"ingestion_confidence: {identity_row['ingestion_confidence']}")

            if asset_id is not None:
                click.echo(f"asset_id: {asset_id}")

            rows = _recent_provenance_events(
                conn,
                identity_id=int(resolved_identity_id),
                asset_id=asset_id,
                limit=int(limit),
            )
            if not rows:
                click.echo("provenance_event: (none)")
                return

            click.echo("provenance_event:")
            for r in rows:
                details = {}
                try:
                    details = json.loads(r["details_json"] or "{}")
                except Exception:
                    details = {"raw": r["details_json"]}
                click.echo(
                    json.dumps(
                        {
                            "event_time": r["event_time"],
                            "event_type": r["event_type"],
                            "status": r["status"],
                            "asset_id": r["asset_id"],
                            "identity_id": r["identity_id"],
                            "details": details,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                )
        finally:
            conn.close()

