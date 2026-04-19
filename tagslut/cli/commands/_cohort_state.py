from __future__ import annotations

import json
import os
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from tagslut.cli.commands._index_helpers import run_report_m3u
from tagslut.exec.canonical_writeback import write_canonical_tags
from tagslut.exec.dj_pool_m3u import write_dj_pool_m3u
from tagslut.exec.mp3_build import (
    _mp3_asset_dest_for_flac_path,
    build_full_tag_mp3_assets_from_flac_paths,
)
from tagslut.metadata.auth import TokenManager
from tagslut.metadata.enricher import Enricher
from tagslut.storage.v3 import create_schema_v3, resolve_asset_id_by_path, run_pending_v3
from tagslut.utils.env_paths import get_artifacts_dir, get_staging_volume, get_volume
from tagslut.utils.paths import list_files

EARLY_BLOCKED_STAGES = frozenset({"resolve", "precheck", "download", "acquisition"})


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_cohort_support(conn: sqlite3.Connection) -> None:
    create_schema_v3(conn)
    run_pending_v3(conn)


def resolve_stage_root() -> Path:
    root = get_staging_volume() or (get_artifacts_dir() / "cohorts")
    return root.expanduser().resolve()


def cohort_stage_dir(cohort_id: int) -> Path:
    return (resolve_stage_root() / str(int(cohort_id))).resolve()


def drop_stage_dir(cohort_id: int) -> None:
    stage_dir = cohort_stage_dir(cohort_id)
    if stage_dir.exists():
        shutil.rmtree(stage_dir)


def encode_flags(flags: dict[str, Any] | None) -> str:
    return json.dumps(flags or {}, sort_keys=True, ensure_ascii=True)


def decode_flags(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def create_cohort(
    conn: sqlite3.Connection,
    *,
    source_url: str,
    source_kind: str,
    flags: dict[str, Any] | None = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO cohort (source_url, source_kind, status, blocked_reason, created_at, flags)
        VALUES (?, ?, 'running', NULL, ?, ?)
        """,
        (source_url, source_kind, utcnow_iso(), encode_flags(flags)),
    )
    return int(cur.lastrowid)


def get_cohort(conn: sqlite3.Connection, cohort_id: int) -> sqlite3.Row | tuple[Any, ...] | None:
    return conn.execute(
        """
        SELECT id, source_url, source_kind, status, blocked_reason, created_at, completed_at, flags
        FROM cohort
        WHERE id = ?
        """,
        (int(cohort_id),),
    ).fetchone()


def find_cohort_by_source(
    conn: sqlite3.Connection,
    *,
    source_url: str,
    blocked_only: bool = False,
) -> list[sqlite3.Row | tuple[Any, ...]]:
    sql = [
        """
        SELECT id, source_url, source_kind, status, blocked_reason, created_at, completed_at, flags
        FROM cohort
        WHERE source_url = ?
        """
    ]
    params: list[Any] = [source_url]
    if blocked_only:
        sql.append("AND status = 'blocked'")
    sql.append("ORDER BY datetime(created_at) DESC, id DESC")
    return list(conn.execute("\n".join(sql), tuple(params)).fetchall())


def find_latest_blocked_cohort_for_source(
    conn: sqlite3.Connection,
    *,
    source_url: str,
) -> tuple[sqlite3.Row | tuple[Any, ...] | None, bool]:
    rows = find_cohort_by_source(conn, source_url=source_url, blocked_only=True)
    if not rows:
        return None, False
    latest = rows[0]
    latest_created_at = latest[5]
    ambiguous = any(row[5] == latest_created_at and row[0] != latest[0] for row in rows[1:])
    return latest, ambiguous


def upsert_cohort_file(
    conn: sqlite3.Connection,
    *,
    cohort_id: int,
    source_path: str | None = None,
    asset_file_id: int | None = None,
    status: str = "pending",
) -> int:
    row = conn.execute(
        """
        SELECT id
        FROM cohort_file
        WHERE cohort_id = ?
          AND COALESCE(source_path, '') = COALESCE(?, '')
          AND COALESCE(asset_file_id, -1) = COALESCE(?, -1)
        ORDER BY id ASC
        LIMIT 1
        """,
        (int(cohort_id), source_path, asset_file_id),
    ).fetchone()
    if row is not None:
        row_id = int(row[0])
        if asset_file_id is not None:
            conn.execute(
                "UPDATE cohort_file SET asset_file_id = COALESCE(asset_file_id, ?) WHERE id = ?",
                (int(asset_file_id), row_id),
            )
        return row_id

    cur = conn.execute(
        """
        INSERT INTO cohort_file (cohort_id, asset_file_id, source_path, status, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (int(cohort_id), asset_file_id, source_path, status, utcnow_iso()),
    )
    return int(cur.lastrowid)


def bind_asset_paths(
    conn: sqlite3.Connection,
    *,
    cohort_id: int,
    paths: Iterable[Path],
) -> list[int]:
    row_ids: list[int] = []
    for path in paths:
        resolved = path.expanduser().resolve()
        asset_id = resolve_asset_id_by_path(conn, resolved)
        row_ids.append(
            upsert_cohort_file(
                conn,
                cohort_id=cohort_id,
                source_path=str(resolved),
                asset_file_id=asset_id,
                status="pending",
            )
        )
    return row_ids


def _update_asset_status(
    conn: sqlite3.Connection,
    *,
    asset_file_id: int | None,
    status: str,
    blocked_reason: str | None,
) -> None:
    if asset_file_id is None:
        return
    conn.execute(
        """
        UPDATE asset_file
        SET status = ?, blocked_reason = ?
        WHERE id = ?
        """,
        (status, blocked_reason, int(asset_file_id)),
    )


def mark_cohort_file_blocked(
    conn: sqlite3.Connection,
    *,
    cohort_id: int,
    stage: str,
    reason: str,
    source_path: str | None = None,
    asset_file_id: int | None = None,
) -> int:
    row_id = upsert_cohort_file(
        conn,
        cohort_id=cohort_id,
        source_path=source_path,
        asset_file_id=asset_file_id,
        status="blocked",
    )
    conn.execute(
        """
        UPDATE cohort_file
        SET status = 'blocked',
            blocked_stage = ?,
            blocked_reason = ?,
            asset_file_id = COALESCE(asset_file_id, ?)
        WHERE id = ?
        """,
        (stage, reason, asset_file_id, row_id),
    )
    _update_asset_status(
        conn,
        asset_file_id=asset_file_id,
        status="blocked",
        blocked_reason=f"{stage}:{reason}",
    )
    return row_id


def clear_cohort_file_blocked(
    conn: sqlite3.Connection,
    *,
    cohort_file_id: int,
) -> None:
    row = conn.execute(
        "SELECT asset_file_id FROM cohort_file WHERE id = ?",
        (int(cohort_file_id),),
    ).fetchone()
    asset_file_id = int(row[0]) if row is not None and row[0] is not None else None
    conn.execute(
        """
        UPDATE cohort_file
        SET status = 'ok',
            blocked_stage = NULL,
            blocked_reason = NULL
        WHERE id = ?
        """,
        (int(cohort_file_id),),
    )
    _update_asset_status(conn, asset_file_id=asset_file_id, status="ok", blocked_reason=None)


def clear_blocked_rows_for_paths(
    conn: sqlite3.Connection,
    *,
    cohort_id: int,
    paths: Iterable[Path],
) -> None:
    for path in paths:
        resolved = str(path.expanduser().resolve())
        rows = conn.execute(
            """
            SELECT id
            FROM cohort_file
            WHERE cohort_id = ?
              AND (source_path = ? OR asset_file_id = (
                    SELECT id FROM asset_file WHERE path = ? LIMIT 1
                  ))
            ORDER BY id ASC
            """,
            (int(cohort_id), resolved, resolved),
        ).fetchall()
        for row in rows:
            clear_cohort_file_blocked(conn, cohort_file_id=int(row[0]))


def mark_paths_ok(
    conn: sqlite3.Connection,
    *,
    cohort_id: int,
    paths: Iterable[Path],
) -> None:
    clear_blocked_rows_for_paths(conn, cohort_id=cohort_id, paths=paths)
    for path in paths:
        resolved = Path(path).expanduser().resolve()
        asset_row = conn.execute(
            "SELECT id FROM asset_file WHERE path = ? LIMIT 1",
            (str(resolved),),
        ).fetchone()
        asset_file_id = int(asset_row[0]) if asset_row is not None and asset_row[0] is not None else None
        row = conn.execute(
            """
            SELECT id
            FROM cohort_file
            WHERE cohort_id = ?
              AND (source_path = ? OR asset_file_id = COALESCE(?, asset_file_id))
            ORDER BY id ASC
            LIMIT 1
            """,
            (int(cohort_id), str(resolved), asset_file_id),
        ).fetchone()
        if row is None:
            row_id = bind_asset_paths(conn, cohort_id=cohort_id, paths=[resolved])[0]
        else:
            row_id = int(row[0])
        conn.execute(
            """
            UPDATE cohort_file
            SET status = 'ok',
                blocked_stage = NULL,
                blocked_reason = NULL,
                asset_file_id = COALESCE(asset_file_id, ?)
            WHERE id = ?
            """,
            (asset_file_id, row_id),
        )
        if asset_file_id is not None:
            conn.execute(
                "UPDATE asset_file SET status = 'ok', blocked_reason = NULL WHERE id = ?",
                (asset_file_id,),
            )


def mark_source_placeholder_ok(
    conn: sqlite3.Connection,
    *,
    cohort_id: int,
    source_path: str,
) -> None:
    conn.execute(
        """
        UPDATE cohort_file
        SET status = 'ok',
            blocked_stage = NULL,
            blocked_reason = NULL
        WHERE cohort_id = ?
          AND asset_file_id IS NULL
          AND source_path = ?
          AND status = 'blocked'
        """,
        (int(cohort_id), source_path),
    )


def record_blocked_paths(
    conn: sqlite3.Connection,
    *,
    cohort_id: int,
    stage: str,
    reason: str,
    paths: Sequence[Path],
    placeholder_source: str,
) -> None:
    if paths:
        bind_asset_paths(conn, cohort_id=cohort_id, paths=paths)
        for path in paths:
            asset_row = conn.execute(
                "SELECT id FROM asset_file WHERE path = ? LIMIT 1",
                (str(path.expanduser().resolve()),),
            ).fetchone()
            asset_file_id = int(asset_row[0]) if asset_row is not None and asset_row[0] is not None else None
            mark_cohort_file_blocked(
                conn,
                cohort_id=cohort_id,
                stage=stage,
                reason=reason,
                source_path=str(path.expanduser().resolve()),
                asset_file_id=asset_file_id,
            )
    else:
        mark_cohort_file_blocked(
            conn,
            cohort_id=cohort_id,
            stage=stage,
            reason=reason,
            source_path=placeholder_source,
            asset_file_id=None,
        )
    set_cohort_blocked(conn, cohort_id=cohort_id, reason=f"{stage}: {reason}")


def set_cohort_blocked(
    conn: sqlite3.Connection,
    *,
    cohort_id: int,
    reason: str,
) -> None:
    conn.execute(
        """
        UPDATE cohort
        SET status = 'blocked',
            blocked_reason = ?,
            completed_at = NULL
        WHERE id = ?
        """,
        (reason, int(cohort_id)),
    )


def set_cohort_running(conn: sqlite3.Connection, *, cohort_id: int) -> None:
    conn.execute(
        """
        UPDATE cohort
        SET status = 'running',
            blocked_reason = NULL,
            completed_at = NULL
        WHERE id = ?
        """,
        (int(cohort_id),),
    )


def refresh_cohort_status(
    conn: sqlite3.Connection,
    *,
    cohort_id: int,
    blocked_summary: str | None = None,
) -> str:
    counts = conn.execute(
        """
        SELECT
            SUM(CASE WHEN status = 'blocked' THEN 1 ELSE 0 END) AS blocked_count,
            SUM(CASE WHEN status = 'ok' THEN 1 ELSE 0 END) AS ok_count,
            COUNT(*) AS total_count
        FROM cohort_file
        WHERE cohort_id = ?
        """,
        (int(cohort_id),),
    ).fetchone()
    blocked_count = int(counts[0] or 0) if counts is not None else 0
    ok_count = int(counts[1] or 0) if counts is not None else 0
    total_count = int(counts[2] or 0) if counts is not None else 0

    if blocked_count > 0:
        summary = blocked_summary or f"{blocked_count} file(s) remain blocked"
        set_cohort_blocked(conn, cohort_id=cohort_id, reason=summary)
        return "blocked"

    conn.execute(
        """
        UPDATE cohort
        SET status = ?,
            blocked_reason = NULL,
            completed_at = ?
        WHERE id = ?
        """,
        ("complete", utcnow_iso(), int(cohort_id)),
    )
    return "complete"


def blocked_rows_for_cohort(conn: sqlite3.Connection, *, cohort_id: int) -> list[sqlite3.Row | tuple[Any, ...]]:
    return list(
        conn.execute(
            """
            SELECT id, cohort_id, asset_file_id, source_path, status, blocked_reason, blocked_stage, created_at
            FROM cohort_file
            WHERE cohort_id = ? AND status = 'blocked'
            ORDER BY id ASC
            """,
            (int(cohort_id),),
        ).fetchall()
    )


def cohort_paths(conn: sqlite3.Connection, *, cohort_id: int) -> list[Path]:
    rows = conn.execute(
        """
        SELECT COALESCE(af.path, cf.source_path) AS path_value
        FROM cohort_file cf
        LEFT JOIN asset_file af ON af.id = cf.asset_file_id
        WHERE cf.cohort_id = ?
        ORDER BY cf.id ASC
        """,
        (int(cohort_id),),
    ).fetchall()
    out: list[Path] = []
    seen: set[str] = set()
    for row in rows:
        raw = row[0]
        if raw is None:
            continue
        resolved = str(Path(str(raw)).expanduser().resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        out.append(Path(resolved))
    return out


def list_blocked_cohorts(conn: sqlite3.Connection) -> list[sqlite3.Row | tuple[Any, ...]]:
    return list(
        conn.execute(
            """
            SELECT
                c.id,
                c.source_url,
                c.source_kind,
                c.status,
                c.blocked_reason,
                c.created_at,
                SUM(CASE WHEN cf.status = 'blocked' THEN 1 ELSE 0 END) AS blocked_file_count
            FROM cohort c
            LEFT JOIN cohort_file cf ON cf.cohort_id = c.id
            WHERE c.status = 'blocked'
            GROUP BY c.id, c.source_url, c.source_kind, c.status, c.blocked_reason, c.created_at
            ORDER BY datetime(c.created_at) DESC, c.id DESC
            """
        ).fetchall()
    )


def cohort_requires_fix_message(
    *,
    cohort_id: int,
    source_url: str | None,
) -> str:
    source = source_url or "(unknown source)"
    return (
        f"Blocked cohort reminder: cohort {cohort_id} for {source}. "
        f"Use `tagslut fix {cohort_id}` to resume it."
    )


@dataclass(frozen=True)
class RetagResult:
    ok_paths: list[Path]
    blocked: dict[Path, str]


@dataclass(frozen=True)
class OutputResult:
    ok: bool
    stage: str | None
    reason: str | None
    mp3_paths: list[Path]
    playlist_paths: list[Path]


def resolve_flac_paths(target: Path | str) -> list[Path]:
    path = Path(target).expanduser().resolve()
    if path.is_dir():
        files = sorted(list_files(path, {".flac"}), key=lambda item: str(item))
        return [item.expanduser().resolve() for item in files]
    if not path.is_file():
        return []
    if path.suffix.lower() == ".flac":
        return [path]
    sibling_flac = path.with_suffix(".flac")
    if sibling_flac.exists():
        return [sibling_flac.expanduser().resolve()]
    return []


def retag_flac_paths(
    *,
    db_path: Path,
    flac_paths: Sequence[Path],
    force: bool = False,
) -> RetagResult:
    blocked: dict[Path, str] = {}
    ok_paths: list[Path] = []
    if not flac_paths:
        return RetagResult(ok_paths=[], blocked={})

    providers = ["beatport", "tidal", "qobuz"]
    token_manager = TokenManager()
    with Enricher(
        db_path=db_path,
        token_manager=token_manager,
        providers=providers,
        dry_run=False,
        mode="hoarding",
    ) as enricher:
        for path in flac_paths:
            resolved = path.expanduser().resolve()
            _result, status = enricher.enrich_file(str(resolved), force=force, retry_no_match=False)
            if status in {"enriched", "not_eligible"}:
                ok_paths.append(resolved)
            elif status == "no_match":
                blocked[resolved] = "no provider match"
            elif status == "not_found":
                blocked[resolved] = "file not found in database"
            elif status == "not_flac_ok":
                blocked[resolved] = "file failed integrity checks"
            else:
                blocked[resolved] = status.replace("_", " ")

    if ok_paths:
        with sqlite3.connect(str(db_path)) as conn:
            write_canonical_tags(
                conn,
                ok_paths,
                force=force,
                execute=True,
                progress_interval=0,
                echo=None,
            )
    return RetagResult(ok_paths=ok_paths, blocked=blocked)


def _common_parent_dir(paths: Sequence[Path]) -> Path:
    if not paths:
        raise ValueError("paths must not be empty")
    if len(paths) == 1:
        return paths[0].expanduser().resolve().parent
    return Path(os.path.commonpath([str(path.expanduser().resolve()) for path in paths])).resolve()


def _remove_new_mp3_rows(conn: sqlite3.Connection, paths: Sequence[Path]) -> None:
    for path in paths:
        conn.execute("DELETE FROM mp3_asset WHERE path = ?", (str(path.expanduser().resolve()),))


def promote_staged_mp3s(
    conn: sqlite3.Connection,
    *,
    staged_root: Path,
    final_root: Path,
) -> list[Path]:
    moved: list[Path] = []
    if not staged_root.exists():
        return moved
    for staged_path in sorted(staged_root.rglob("*.mp3"), key=lambda path: str(path)):
        rel_path = staged_path.relative_to(staged_root)
        final_path = (final_root / rel_path).resolve()
        existing_row = conn.execute(
            "SELECT id FROM mp3_asset WHERE path = ?",
            (str(final_path),),
        ).fetchone()
        if existing_row is not None:
            conn.execute("DELETE FROM mp3_asset WHERE path = ?", (str(staged_path.resolve()),))
            staged_path.unlink(missing_ok=True)
            continue

        final_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staged_path), str(final_path))
        conn.execute(
            "UPDATE mp3_asset SET path = ? WHERE path = ?",
            (str(final_path), str(staged_path.resolve())),
        )
        moved.append(final_path)
    return moved


def build_output_artifacts(
    *,
    db_path: Path,
    cohort_id: int,
    flac_paths: Sequence[Path],
    dj: bool,
    playlist_only: bool,
    playlist_name: str | None = None,
) -> OutputResult:
    if not flac_paths or (not dj and not playlist_only):
        return OutputResult(ok=True, stage=None, reason=None, mp3_paths=[], playlist_paths=[])

    stage_dir = cohort_stage_dir(cohort_id)
    drop_stage_dir(cohort_id)
    stage_dir.mkdir(parents=True, exist_ok=True)

    moved_mp3_paths: list[Path] = []
    playlist_paths: list[Path] = []

    try:
        if dj:
            mp3_root_value = os.environ.get("MP3_LIBRARY")
            if not mp3_root_value:
                return OutputResult(
                    ok=False,
                    stage="mp3",
                    reason="Missing MP3_LIBRARY environment variable for DJ output",
                    mp3_paths=[],
                    playlist_paths=[],
                )

            final_mp3_root = Path(mp3_root_value).expanduser().resolve()
            staged_mp3_root = (stage_dir / "mp3").resolve()
            library_root = get_volume("library", required=False)
            with sqlite3.connect(str(db_path)) as conn:
                build_result = build_full_tag_mp3_assets_from_flac_paths(
                    conn,
                    flac_paths=list(flac_paths),
                    mp3_root=staged_mp3_root,
                    dry_run=False,
                    overwrite=False,
                )
                if build_result.failed > 0:
                    return OutputResult(
                        ok=False,
                        stage="mp3",
                        reason="; ".join(build_result.errors[:5]) or build_result.summary(),
                        mp3_paths=[],
                        playlist_paths=[],
                    )

                moved_mp3_paths = promote_staged_mp3s(
                    conn,
                    staged_root=staged_mp3_root,
                    final_root=final_mp3_root,
                )
                final_mp3_paths = [
                    _mp3_asset_dest_for_flac_path(
                        flac_path=path.expanduser().resolve(),
                        mp3_root=final_mp3_root,
                        library_root=library_root,
                    ).resolve()
                    for path in flac_paths
                ]

                try:
                    batch_path, global_path = write_dj_pool_m3u(
                        mp3_paths=final_mp3_paths,
                        mp3_root=final_mp3_root,
                        playlist_name=playlist_name,
                    )
                except Exception as exc:
                    for path in moved_mp3_paths:
                        path.unlink(missing_ok=True)
                    _remove_new_mp3_rows(conn, moved_mp3_paths)
                    conn.commit()
                    return OutputResult(
                        ok=False,
                        stage="playlist",
                        reason=str(exc),
                        mp3_paths=[],
                        playlist_paths=[],
                    )

                conn.commit()
                playlist_paths.extend([batch_path.resolve(), global_path.resolve()])

        if playlist_only and not dj:
            staged_playlist_dir = (stage_dir / "m3u").resolve()
            staged_playlist_dir.mkdir(parents=True, exist_ok=True)
            run_report_m3u(
                paths=tuple(str(path.expanduser().resolve()) for path in flac_paths),
                merge=True,
                m3u_dir=str(staged_playlist_dir),
                db=str(db_path),
                source=f"cohort-{cohort_id}",
                path_mode="absolute",
                name_prefix="",
                name_suffix="",
                verbose=False,
            )
            staged_playlists = sorted(staged_playlist_dir.glob("*.m3u"), key=lambda path: str(path))
            final_playlist_dir = _common_parent_dir(flac_paths)
            for staged_playlist in staged_playlists:
                final_playlist = (final_playlist_dir / staged_playlist.name).resolve()
                shutil.move(str(staged_playlist), str(final_playlist))
                playlist_paths.append(final_playlist)

        return OutputResult(
            ok=True,
            stage=None,
            reason=None,
            mp3_paths=moved_mp3_paths,
            playlist_paths=playlist_paths,
        )
    finally:
        drop_stage_dir(cohort_id)
