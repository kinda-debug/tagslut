from __future__ import annotations

import sqlite3

from tagslut.download.models import DownloadResult


def register_downloaded_asset(conn: sqlite3.Connection, result: DownloadResult) -> None:
    """
    Persist the acquisition provider into asset_file.download_source for a downloaded file path.

    This is intentionally minimal and does not perform full intake registration.
    """
    conn.execute(
        """
        INSERT INTO asset_file (path, download_source)
        VALUES (?, ?)
        ON CONFLICT(path) DO UPDATE SET
            download_source = excluded.download_source,
            last_seen_at = CURRENT_TIMESTAMP
        """,
        (str(result.file_path), result.download_source),
    )

