"""HTTP Inspect API for the track hub.

A minimal FastAPI server that exposes read-only endpoints for inspecting
the track hub (library_tracks, library_track_sources, files).

Usage:
    # Via environment variable:
    DEDUPE_DB_PATH=/path/to/music.db python -m tools.inspect_api

    # Via CLI argument (overrides env var):
    python -m tools.inspect_api --db /path/to/music.db

    # With custom host/port:
    python -m tools.inspect_api --db /path/to/music.db --host 0.0.0.0 --port 8080

Endpoints:
    GET /health                              - Health check
    GET /track-hub/by-isrc/{isrc}            - Find track by ISRC
    GET /track-hub/by-provider/{service}/{track_id} - Find track by provider ID

Requirements:
    pip install fastapi uvicorn

    If uvicorn is not installed, the server will not start. Install it with:
        pip install uvicorn[standard]
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

# FastAPI is optional; guard the import
try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import JSONResponse

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    FastAPI = None  # type: ignore
    HTTPException = Exception  # type: ignore


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def _get_db_path() -> str:
    """Resolve the database path from CLI arg or environment variable."""
    # This will be set by the main block when running as a script
    db_path = getattr(_get_db_path, "_db_path", None)
    if db_path:
        return db_path

    # Fallback to environment variable
    env_path = os.environ.get("DEDUPE_DB_PATH")
    if env_path:
        return env_path

    raise RuntimeError(
        "Database path not configured. Set DEDUPE_DB_PATH environment variable "
        "or pass --db argument when running the server."
    )


def _connect_db() -> sqlite3.Connection:
    """Open a read-only connection to the SQLite database."""
    db_path = _get_db_path()
    if not Path(db_path).exists():
        raise RuntimeError(f"Database not found at {db_path}")

    # Use URI mode for read-only access
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    """Convert a sqlite3.Row to a dictionary, or None if row is None."""
    if row is None:
        return None
    return dict(row)


def _rows_to_list(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    """Convert a list of sqlite3.Row to a list of dictionaries."""
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Track hub query helpers
# ---------------------------------------------------------------------------


def _fetch_track_hub_data(conn: sqlite3.Connection, key: str) -> dict[str, Any]:
    """Fetch all track hub data for a given library_track_key.

    Returns a dict with:
        - library_track_key: str
        - track: dict | None (from library_tracks)
        - sources: list[dict] (from library_track_sources)
        - files: list[dict] (from files)
    """
    # Fetch canonical track
    cursor = conn.execute(
        """
        SELECT library_track_key, title, artist, album, duration_ms, isrc,
               release_date, explicit, best_cover_url, genre, bpm, musical_key,
               label, updated_at
        FROM library_tracks
        WHERE library_track_key = ?
        """,
        (key,),
    )
    track_row = cursor.fetchone()

    # Fetch provider sources
    cursor = conn.execute(
        """
        SELECT service, service_track_id, url, duration_ms, isrc, album_art_url,
               genre, bpm, musical_key, album_title, artist_name, track_number,
               disc_number, match_confidence, fetched_at
        FROM library_track_sources
        WHERE library_track_key = ?
        ORDER BY service, service_track_id
        """,
        (key,),
    )
    source_rows = cursor.fetchall()

    # Fetch linked files
    cursor = conn.execute(
        """
        SELECT path, canonical_duration, canonical_duration_source,
               metadata_health, metadata_health_reason, enrichment_providers,
               enrichment_confidence
        FROM files
        WHERE library_track_key = ?
        ORDER BY path
        """,
        (key,),
    )
    file_rows = cursor.fetchall()

    return {
        "library_track_key": key,
        "track": _row_to_dict(track_row),
        "sources": _rows_to_list(source_rows),
        "files": _rows_to_list(file_rows),
    }


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

if FASTAPI_AVAILABLE:
    app = FastAPI(
        title="Dedupe Track Hub Inspect API",
        description="Read-only API for inspecting the track hub database.",
        version="1.0.0",
    )

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "ok"}

    @app.get("/track-hub/by-isrc/{isrc}")
    async def get_track_by_isrc(isrc: str) -> dict[str, Any]:
        """Find a track by ISRC.

        Normalizes the ISRC (uppercase, stripped) and derives the library_track_key.
        Returns the canonical track, provider sources, and linked files.
        """
        # Normalize ISRC
        normalized_isrc = isrc.strip().upper()
        key = f"isrc:{normalized_isrc}"

        try:
            conn = _connect_db()
        except RuntimeError as e:
            raise HTTPException(status_code=500, detail=str(e))

        try:
            data = _fetch_track_hub_data(conn, key)

            # Check if we found anything
            if data["track"] is None and not data["sources"] and not data["files"]:
                raise HTTPException(
                    status_code=404,
                    detail=f"No track found for ISRC: {normalized_isrc}",
                )

            return data
        finally:
            conn.close()

    @app.get("/track-hub/by-provider/{service}/{track_id}")
    async def get_track_by_provider(service: str, track_id: str) -> dict[str, Any]:
        """Find tracks by provider service and track ID.

        Looks up all library_track_key values associated with the given
        (service, track_id) pair and returns full track hub data for each.
        """
        normalized_service = service.lower()
        normalized_track_id = track_id.strip()

        try:
            conn = _connect_db()
        except RuntimeError as e:
            raise HTTPException(status_code=500, detail=str(e))

        try:
            # Find all distinct keys for this provider/track_id
            cursor = conn.execute(
                """
                SELECT DISTINCT library_track_key
                FROM library_track_sources
                WHERE service = ? AND service_track_id = ?
                """,
                (normalized_service, normalized_track_id),
            )
            key_rows = cursor.fetchall()

            if not key_rows:
                raise HTTPException(
                    status_code=404,
                    detail=f"No track found for service={normalized_service}, track_id={normalized_track_id}",
                )

            # Fetch full data for each key
            results = []
            for row in key_rows:
                key = row["library_track_key"]
                if key:
                    results.append(_fetch_track_hub_data(conn, key))

            return {
                "service": normalized_service,
                "track_id": normalized_track_id,
                "results": results,
            }
        finally:
            conn.close()

else:
    # Placeholder app when FastAPI is not available
    app = None  # type: ignore


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the inspect API server."""
    if not FASTAPI_AVAILABLE:
        print("Error: FastAPI is not installed.", file=sys.stderr)
        print("Install it with: pip install fastapi uvicorn[standard]", file=sys.stderr)
        sys.exit(1)

    parser = argparse.ArgumentParser(
        prog="tools.inspect_api",
        description="Run the track hub inspect API server.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m tools.inspect_api --db ./music.db
    python -m tools.inspect_api --db ./music.db --host 0.0.0.0 --port 8080
    DEDUPE_DB_PATH=./music.db python -m tools.inspect_api

Endpoints:
    GET /health                              - Health check
    GET /track-hub/by-isrc/{isrc}            - Find track by ISRC
    GET /track-hub/by-provider/{service}/{track_id} - Find track by provider ID
        """,
    )
    parser.add_argument(
        "--db",
        help="Path to the SQLite database file. Overrides DEDUPE_DB_PATH env var.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind the server to (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind the server to (default: 8000).",
    )

    args = parser.parse_args()

    # Set the database path
    if args.db:
        _get_db_path._db_path = args.db  # type: ignore
    elif not os.environ.get("DEDUPE_DB_PATH"):
        print("Error: Database path required.", file=sys.stderr)
        print("Set DEDUPE_DB_PATH environment variable or pass --db argument.", file=sys.stderr)
        sys.exit(1)

    # Verify database exists before starting server
    try:
        db_path = _get_db_path()
        if not Path(db_path).exists():
            print(f"Error: Database not found at {db_path}", file=sys.stderr)
            sys.exit(1)
        print(f"Using database: {db_path}")
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Try to import and run uvicorn
    try:
        import uvicorn
    except ImportError:
        print("Error: uvicorn is not installed.", file=sys.stderr)
        print("Install it with: pip install uvicorn[standard]", file=sys.stderr)
        sys.exit(1)

    print(f"Starting server at http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop.")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
