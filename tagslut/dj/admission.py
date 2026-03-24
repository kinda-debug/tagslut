"""DJ admission layer.

Provides:
  admit_track()         — admit a single identity into the DJ library
  backfill_admissions() — auto-admit all un-admitted mp3_asset rows with status='verified'
  validate_dj_library() — run consistency checks over dj_* and mp3_asset tables
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DjAdmissionError(Exception):
    pass


def _ensure_track_id_map(conn: sqlite3.Connection, *, admission_id: int) -> None:
    """Ensure a stable Rekordbox TrackID exists for an admitted dj_admission row."""
    existing = conn.execute(
        "SELECT rekordbox_track_id FROM dj_track_id_map WHERE dj_admission_id = ?",
        (admission_id,),
    ).fetchone()
    if existing is not None:
        return

    next_id = int(
        conn.execute(
            "SELECT COALESCE(MAX(rekordbox_track_id), 0) + 1 FROM dj_track_id_map"
        ).fetchone()[0]
    )
    conn.execute(
        """
        INSERT INTO dj_track_id_map (dj_admission_id, rekordbox_track_id, assigned_at)
        VALUES (?, ?, ?)
        """,
        (admission_id, next_id, _now_iso()),
    )


def admit_track(
    conn: sqlite3.Connection,
    *,
    identity_id: int,
    mp3_asset_id: int,
    notes: dict | None = None,
) -> int:
    """Admit an identity into the DJ library.

    Returns the dj_admission.id.
    Raises DjAdmissionError if the identity is already admitted.
    """
    existing = conn.execute(
        "SELECT id, status FROM dj_admission WHERE identity_id = ?",
        (identity_id,),
    ).fetchone()
    if existing:
        admission_id, status = existing
        if status == "admitted":
            raise DjAdmissionError(
                f"Identity {identity_id} is already admitted "
                f"(dj_admission.id={admission_id}). "
                "To update, use 'tagslut dj backfill'."
            )
        # Re-admit a previously rejected/needs_review admission
        conn.execute(
            """
            UPDATE dj_admission
            SET mp3_asset_id = ?,
                status      = 'admitted',
                admitted_at = ?,
                notes       = ?
            WHERE id = ?
            """,
            (
                mp3_asset_id,
                _now_iso(),
                json.dumps(notes) if notes else None,
                admission_id,
            ),
        )
        _ensure_track_id_map(conn, admission_id=admission_id)
        return admission_id

    cur = conn.execute(
        """
        INSERT INTO dj_admission
          (identity_id, mp3_asset_id, status, admitted_at, notes)
        VALUES (?, ?, 'admitted', ?, ?)
        """,
        (
            identity_id,
            mp3_asset_id,
            _now_iso(),
            json.dumps(notes) if notes else None,
        ),
    )
    admission_id = int(cur.lastrowid)  # type: ignore[arg-type]
    _ensure_track_id_map(conn, admission_id=admission_id)
    return admission_id


def backfill_admissions(conn: sqlite3.Connection) -> tuple[int, int]:
    """Auto-admit all mp3_asset rows with status='verified' that have no dj_admission yet.

    Returns (admitted_count, skipped_count).
    Skips identities that already have an admitted admission.
    """
    dj_copy_profiles = ("dj_copy_320_cbr",)
    rows = conn.execute(
        """
        SELECT ma.id, ma.identity_id, ma.profile
        FROM mp3_asset ma
        WHERE ma.status = 'verified'
          AND ma.identity_id IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM dj_admission da
            WHERE da.identity_id = ma.identity_id AND da.status = 'admitted'
          )
        ORDER BY
          ma.identity_id,
          CASE WHEN ma.profile IN (?) THEN 0 ELSE 1 END,
          ma.id
        """
        ,
        (dj_copy_profiles[0],),
    ).fetchall()

    admitted = 0
    skipped = 0
    seen_identities: set[int] = set()
    for mp3_id, identity_id, _profile in rows:
        if identity_id in seen_identities:
            continue
        seen_identities.add(identity_id)
        try:
            admit_track(conn, identity_id=identity_id, mp3_asset_id=mp3_id)
            admitted += 1
        except DjAdmissionError:
            skipped += 1
    return admitted, skipped


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@dataclass
class DjValidationIssue:
    kind: str
    message: str
    identity_id: int | None = None
    mp3_asset_id: int | None = None
    dj_admission_id: int | None = None


@dataclass
class DjValidationReport:
    issues: list[DjValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    def add(self, kind: str, message: str, **kwargs: int | None) -> None:
        self.issues.append(DjValidationIssue(kind=kind, message=message, **kwargs))

    def summary(self) -> str:
        if self.ok:
            return "DJ library validation passed — no issues found."
        lines = [f"DJ library validation: {len(self.issues)} issue(s) found"]
        for issue in self.issues:
            lines.append(f"  [{issue.kind}] {issue.message}")
        return "\n".join(lines)


def validate_dj_library(conn: sqlite3.Connection) -> DjValidationReport:
    """Run consistency checks over dj_* and mp3_asset tables.

    Checks performed:
    1. Every admitted admission's MP3 asset has status='verified' and exists on disk.
    2. All dj_playlist_track entries reference admitted admissions.
    3. Every admitted admission's identity has non-empty title and artist.
    """
    report = DjValidationReport()

    # 1. MP3 asset status and path existence
    rows = conn.execute(
        """
        SELECT da.id, da.identity_id, ma.id, ma.path, ma.status
        FROM dj_admission da
        JOIN mp3_asset ma ON ma.id = da.mp3_asset_id
        WHERE da.status = 'admitted'
        """
    ).fetchall()
    for da_id, identity_id, ma_id, mp3_path, mp3_status in rows:
        if mp3_status != "verified":
            report.add(
                "BAD_MP3_STATUS",
                f"dj_admission {da_id}: mp3_asset {ma_id} has status={mp3_status!r}",
                identity_id=identity_id,
                mp3_asset_id=ma_id,
                dj_admission_id=da_id,
            )
        if not Path(mp3_path).exists():
            report.add(
                "MISSING_MP3_FILE",
                f"dj_admission {da_id}: MP3 not found on disk: {mp3_path}",
                identity_id=identity_id,
                mp3_asset_id=ma_id,
                dj_admission_id=da_id,
            )

    # 2. Playlist members must be admitted admissions
    orphan_rows = conn.execute(
        """
        SELECT pt.playlist_id, pt.dj_admission_id, da.status
        FROM dj_playlist_track pt
        JOIN dj_admission da ON da.id = pt.dj_admission_id
        WHERE da.status != 'admitted'
        """
    ).fetchall()
    for playlist_id, da_id, status in orphan_rows:
        report.add(
            "INACTIVE_PLAYLIST_MEMBER",
            f"dj_playlist_track in playlist {playlist_id} references "
            f"admission {da_id} with status={status!r}",
            dj_admission_id=da_id,
        )

    # 3. Required metadata: title and artist must be non-empty
    meta_rows = conn.execute(
        """
        SELECT da.id, da.identity_id, ti.title_norm, ti.artist_norm
        FROM dj_admission da
        JOIN track_identity ti ON ti.id = da.identity_id
        WHERE da.status = 'admitted'
          AND (
               ti.title_norm  IS NULL OR trim(ti.title_norm)  = ''
            OR ti.artist_norm IS NULL OR trim(ti.artist_norm) = ''
          )
        """
    ).fetchall()
    for da_id, identity_id, title, artist in meta_rows:
        report.add(
            "MISSING_METADATA",
            f"dj_admission {da_id}: identity {identity_id} missing required "
            f"title or artist (title_norm={title!r}, artist_norm={artist!r})",
            identity_id=identity_id,
            dj_admission_id=da_id,
        )

    return report


def record_validation_state(
    conn: sqlite3.Connection,
    *,
    state_hash: str,
    issue_count: int,
    passed: bool,
    summary: str | None = None,
) -> int:
    """Insert a dj_validation_state row and return its id."""
    cur = conn.execute(
        """
        INSERT INTO dj_validation_state
          (validated_at, state_hash, issue_count, passed, summary)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            _now_iso(),
            state_hash,
            issue_count,
            1 if passed else 0,
            summary,
        ),
    )
    return cur.lastrowid  # type: ignore[return-value]
