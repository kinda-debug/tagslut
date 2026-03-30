"""Stage 3 DJ backfill (bulk admission).

Implements the `tagslut dj backfill` admission loop:
- Select eligible `mp3_asset` rows (status written by mp3 reconcile on success)
- Insert `dj_admission` rows idempotently
- Ensure a stable `dj_track_id_map` TrackID exists per admitted row
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from tagslut.cli._progress import ProgressCallback


MP3_RECONCILE_SUCCESS_STATUS = "verified"
DJ_COPY_PROFILES = ("dj_copy_320_cbr",)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_db_path(db_path: str | Path | None) -> Path:
    """Resolve DB path from CLI `--db` or $TAGSLUT_DB with a clear error message."""
    if db_path:
        return Path(db_path).expanduser().resolve()
    env_value = (os.environ.get("TAGSLUT_DB") or "").strip()
    if env_value:
        return Path(env_value).expanduser().resolve()
    raise ValueError(
        "Missing database path. Pass --db /path/to/music.db or set TAGSLUT_DB=/path/to/music.db."
    )


def _ensure_track_id_map(conn: sqlite3.Connection, *, admission_id: int) -> None:
    existing = conn.execute(
        "SELECT rekordbox_track_id FROM dj_track_id_map WHERE dj_admission_id = ?",
        (admission_id,),
    ).fetchone()
    if existing is not None:
        return

    for _attempt in range(5):
        next_id = int(
            conn.execute(
                "SELECT COALESCE(MAX(rekordbox_track_id), 0) + 1 FROM dj_track_id_map"
            ).fetchone()[0]
        )
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO dj_track_id_map (dj_admission_id, rekordbox_track_id, assigned_at)
            VALUES (?, ?, ?)
            """,
            (admission_id, next_id, _now_iso()),
        )
        if cur.rowcount == 1:
            return
        existing = conn.execute(
            "SELECT rekordbox_track_id FROM dj_track_id_map WHERE dj_admission_id = ?",
            (admission_id,),
        ).fetchone()
        if existing is not None:
            return

    raise RuntimeError(
        f"Failed to assign Rekordbox TrackID for dj_admission.id={admission_id} "
        "(unexpected uniqueness conflict)."
    )


def backfill_dj_admissions(
    conn: sqlite3.Connection,
    *,
    progress_cb: ProgressCallback | None = None,
) -> tuple[int, int]:
    """Backfill dj_admission + dj_track_id_map for reconciled MP3 assets.

    Returns (admitted_new, skipped_existing).
    """
    rows = conn.execute(
        """
        SELECT ma.id, ma.identity_id, ma.profile
        FROM mp3_asset ma
        WHERE ma.status = ?
          AND ma.identity_id IS NOT NULL
        ORDER BY
          ma.identity_id,
          CASE WHEN ma.profile IN (?) THEN 0 ELSE 1 END,
          ma.id
        """,
        (MP3_RECONCILE_SUCCESS_STATUS, DJ_COPY_PROFILES[0]),
    ).fetchall()

    admitted = 0
    skipped = 0

    selected: list[tuple[int, int]] = []
    seen_identities: set[int] = set()
    for mp3_asset_id, identity_id, _profile in rows:
        identity_id_int = int(identity_id)
        if identity_id_int in seen_identities:
            continue
        seen_identities.add(identity_id_int)
        selected.append((int(mp3_asset_id), identity_id_int))

    total = len(selected)

    for idx, (mp3_asset_id, identity_id_int) in enumerate(selected, start=1):
        label = f"identity_id={identity_id_int}"

        existing = conn.execute(
            "SELECT id, status FROM dj_admission WHERE identity_id = ?",
            (identity_id_int,),
        ).fetchone()
        if existing and existing[1] == "admitted":
            skipped += 1
            _ensure_track_id_map(conn, admission_id=int(existing[0]))
            if progress_cb is not None:
                progress_cb(label, idx, total)
            continue

        cur = conn.execute(
            """
            INSERT OR IGNORE INTO dj_admission
              (identity_id, mp3_asset_id, status, admitted_at, notes)
            VALUES (?, ?, 'admitted', ?, NULL)
            """,
            (identity_id_int, int(mp3_asset_id), _now_iso()),
        )
        if cur.rowcount == 1:
            admitted += 1
            admission_id = int(cur.lastrowid)  # type: ignore[arg-type]
            _ensure_track_id_map(conn, admission_id=admission_id)
            if progress_cb is not None:
                progress_cb(label, idx, total)
            continue

        # Existing row but not admitted: re-admit in-place.
        if existing:
            admission_id = int(existing[0])
            conn.execute(
                """
                UPDATE dj_admission
                SET mp3_asset_id = ?,
                    status      = 'admitted',
                    admitted_at = ?
                WHERE id = ?
                """,
                (int(mp3_asset_id), _now_iso(), admission_id),
            )
            admitted += 1
            _ensure_track_id_map(conn, admission_id=admission_id)
            if progress_cb is not None:
                progress_cb(label, idx, total)
            continue

        # A concurrent insert likely happened; treat as skipped if now admitted.
        existing = conn.execute(
            "SELECT id, status FROM dj_admission WHERE identity_id = ?",
            (identity_id_int,),
        ).fetchone()
        if existing and existing[1] == "admitted":
            skipped += 1
            _ensure_track_id_map(conn, admission_id=int(existing[0]))
            if progress_cb is not None:
                progress_cb(label, idx, total)
            continue
        raise RuntimeError(f"Failed to backfill dj_admission for identity_id={identity_id_int}.")

    return admitted, skipped


def run_backfill(*, db_path: str | Path | None) -> tuple[int, int]:
    """Convenience entrypoint: open DB, backfill, commit, and return counts."""
    resolved = resolve_db_path(db_path)
    conn = sqlite3.connect(str(resolved))
    try:
        admitted, skipped = backfill_dj_admissions(conn)
        conn.commit()
        return admitted, skipped
    finally:
        conn.close()
