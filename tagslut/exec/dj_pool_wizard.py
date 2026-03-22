from __future__ import annotations

import csv
import json
import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path
import re
import shutil

import click
from tagslut.exec.transcoder import transcode_to_mp3_from_snapshot
from tagslut.storage.models import DJ_SET_ROLES
from tagslut.storage.v3 import record_provenance_event, resolve_asset_id_by_path
from tagslut.storage.v3.analysis_service import resolve_dj_tag_snapshot

WIZARD_VERSION = "0.1.0"
logger = logging.getLogger(__name__)
_ROLE_PLAYLIST_PRIORITY = ("groove", "prime", "bridge", "club")
_ROLE_PLAYLIST_ORDER = tuple(role for role in _ROLE_PLAYLIST_PRIORITY if role in DJ_SET_ROLES) + tuple(
    sorted(DJ_SET_ROLES.difference(_ROLE_PLAYLIST_PRIORITY))
)
_ROLE_PLAYLIST_FILENAMES = {
    role: f"{index * 10}_{role.upper()}.m3u"
    for index, role in enumerate(_ROLE_PLAYLIST_ORDER, start=1)
}
_INTERACTIVE_VALUE_PREVIEW_LIMIT = 12


def sanitize_component(value: str | None) -> str:
    sanitized = re.sub(r'[\/\\:*?"<>|]', "", str(value or ""))
    sanitized = re.sub(r"\s+", "_", sanitized)
    sanitized = sanitized.strip("._")
    sanitized = sanitized[:120]
    return sanitized or "_"


def _track_value(track: dict, *keys: str) -> object | None:
    for key in keys:
        value = track.get(key)
        if value is not None:
            return value
    return None


def _track_text(track: dict, *keys: str) -> str:
    value = _track_value(track, *keys)
    if value is None:
        return ""
    return str(value).strip()


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(str(row[1]) == column for row in rows)


def _optional_column_expr(
    conn: sqlite3.Connection,
    table: str,
    alias: str,
    column: str,
    *,
    treat_blank_as_null: bool = False,
) -> str | None:
    if not _column_exists(conn, table, column):
        return None
    expr = f"{alias}.{column}"
    if treat_blank_as_null:
        return f"NULLIF(TRIM({expr}), '')"
    return expr


def _coalesce_expr(*exprs: str | None) -> str:
    present = [expr for expr in exprs if expr]
    if not present:
        return "NULL"
    if len(present) == 1:
        return present[0]
    return f"COALESCE({', '.join(present)})"


def _locked_cohort_terms(
    conn: sqlite3.Connection,
    *,
    alias: str,
) -> list[str]:
    terms: list[str] = []
    if _column_exists(conn, "files", "is_dj_material"):
        terms.append(f"{alias}.is_dj_material = 1")
    if _column_exists(conn, "files", "dj_flag"):
        terms.append(f"{alias}.dj_flag = 1")
    if _column_exists(conn, "files", "dj_pool_path"):
        terms.append(
            f"({alias}.dj_pool_path IS NOT NULL AND TRIM({alias}.dj_pool_path) <> '')"
        )
    return terms


def _locked_cohort_clause(
    conn: sqlite3.Connection,
    *,
    alias: str,
) -> str:
    terms = _locked_cohort_terms(conn, alias=alias)
    if not terms:
        return "0"
    return "(" + " OR ".join(terms) + ")"


def _locked_cohort_definition(conn: sqlite3.Connection) -> str:
    return _locked_cohort_clause(conn, alias="files")


def _iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _failure(row: dict, error_type: str, message: str) -> dict:
    return {
        "identity_id": row.get("identity_id"),
        "master_path": row.get("master_path"),
        "final_dest_path": row.get("final_dest_path"),
        "error_type": error_type,
        "error_message": message,
        "timestamp": _iso_now(),
    }


def _normalize_dj_set_role(value: object) -> str | None:
    role = str(value or "").strip().lower()
    if not role:
        return None
    if role not in DJ_SET_ROLES:
        return None
    return role


def _validated_only_roles(profile: dict) -> tuple[bool, list[str]]:
    raw_roles = profile.get("only_roles")
    if raw_roles is None:
        return False, []
    if isinstance(raw_roles, str) or not isinstance(raw_roles, (list, tuple, set, frozenset)):
        raise ValueError(
            f"only_roles must be a list of DJ set roles: {sorted(DJ_SET_ROLES)}"
        )

    normalized: list[str] = []
    for value in raw_roles:
        role = str(value).strip().lower()
        if not role:
            continue
        if role not in DJ_SET_ROLES:
            raise ValueError(
                f"Invalid only_roles value {role!r}. Allowed: {sorted(DJ_SET_ROLES)}"
            )
        if role not in normalized:
            normalized.append(role)
    return True, normalized


def _role_subfolder(track: dict) -> Path:
    role = _normalize_dj_set_role(track.get("dj_set_role"))
    if role is not None:
        return Path("pool") / role

    logger.warning(
        "Track %s has invalid or missing dj_set_role %r; routing to _unassigned",
        track.get("master_path")
        or _track_value(track, "canonical_title", "title")
        or "<unknown>",
        track.get("dj_set_role"),
    )
    return Path("pool") / "_unassigned"


def _build_cache_dest(run_dir: Path, row: dict, profile: dict) -> Path:
    """Cache dest inside run_dir/cache/ for transcoded files."""
    identity_id = row["identity_id"]
    artist = sanitize_component(_track_text(row, "canonical_artist", "artist") or "Unknown_Artist")
    title = sanitize_component(_track_text(row, "canonical_title", "title") or "Unknown_Title")
    bitrate = profile.get("bitrate", 320)
    fname = f"{artist}__{title}__{identity_id}_{bitrate}k.mp3"
    return run_dir / "cache" / fname


def _sha256_file(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def validate_schema_and_views(conn: sqlite3.Connection) -> None:
    required_tables = {
        "files",
        "asset_file",
        "asset_link",
        "track_identity",
        "provenance_event",
        "dj_track_profile",
    }
    required_views = {
        "v_dj_pool_candidates_v3",
        "v_dj_export_metadata_v1",
    }

    table_rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    view_rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='view'"
    ).fetchall()
    existing_tables = {str(row["name"]) for row in table_rows}
    existing_views = {str(row["name"]) for row in view_rows}

    missing_tables = sorted(required_tables - existing_tables)
    missing_views = sorted(required_views - existing_views)
    if missing_tables or missing_views:
        missing = sorted(missing_tables + missing_views)
        raise ValueError(
            f"Missing required schema objects: {missing}\n"
            "Run: tagslut db apply-migration --schema v3"
        )


def compute_cohort_health(
    conn: sqlite3.Connection,
    master_root: Path,
) -> dict:
    prefix = str(master_root).rstrip("/") + "/%"
    cohort_clause = _locked_cohort_clause(conn, alias="f")
    cohort_definition = _locked_cohort_definition(conn)
    files_has_is_dj_material = _column_exists(conn, "files", "is_dj_material")
    files_has_dj_flag = _column_exists(conn, "files", "dj_flag")
    files_has_dj_pool_path = _column_exists(conn, "files", "dj_pool_path")

    flagged_row = conn.execute(
        f"""
        SELECT
          SUM(CASE WHEN {'is_dj_material = 1' if files_has_is_dj_material else '0'} THEN 1 ELSE 0 END)
            AS is_dj_material_count,
          SUM(CASE WHEN {'dj_flag = 1' if files_has_dj_flag else '0'} THEN 1 ELSE 0 END)
            AS dj_flag_count,
          SUM(CASE WHEN {'(dj_pool_path IS NOT NULL AND TRIM(dj_pool_path) <> \'\')' if files_has_dj_pool_path else '0'} THEN 1 ELSE 0 END)
            AS dj_pool_path_count,
          SUM(CASE WHEN {cohort_definition} THEN 1 ELSE 0 END)
            AS flagged_union_count
        FROM files
        WHERE path LIKE :prefix
        """,
        {"prefix": prefix},
    ).fetchone()

    coverage_row = conn.execute(
        f"""
        SELECT
          COUNT(*) AS cohort_total,
          SUM(CASE WHEN al.identity_id IS NOT NULL THEN 1 ELSE 0 END)
            AS cohort_with_identity,
          SUM(CASE WHEN al.identity_id IS NULL THEN 1 ELSE 0 END)
            AS cohort_without_identity
        FROM files f
        LEFT JOIN asset_file af ON af.path = f.path
        LEFT JOIN asset_link al
          ON al.asset_id = af.id AND al.active = 1
        WHERE {cohort_clause}
          AND f.path LIKE :prefix
        """,
        {"prefix": prefix},
    ).fetchone()

    relink_row = conn.execute(
        f"""
        SELECT COUNT(DISTINCT f.path) AS cohort_with_dj_pool_relink
        FROM files f
        JOIN asset_file af ON af.path = f.path
        JOIN asset_link al ON al.asset_id = af.id AND al.active = 1
        JOIN provenance_event pe
          ON pe.identity_id = al.identity_id
         AND pe.event_type = 'dj_pool_relink'
         AND pe.status = 'success'
        WHERE {cohort_clause}
          AND f.path LIKE :prefix
        """,
        {"prefix": prefix},
    ).fetchone()

    export_row = conn.execute(
        f"""
        SELECT COUNT(DISTINCT f.path) AS cohort_with_dj_export
        FROM files f
        JOIN asset_file af ON af.path = f.path
        JOIN asset_link al ON al.asset_id = af.id AND al.active = 1
        JOIN provenance_event pe
          ON pe.identity_id = al.identity_id
         AND pe.event_type = 'dj_export'
         AND pe.status = 'success'
        WHERE {cohort_clause}
          AND f.path LIKE :prefix
        """,
        {"prefix": prefix},
    ).fetchone()

    is_dj_material_count = int(flagged_row["is_dj_material_count"] or 0)
    dj_flag_count = int(flagged_row["dj_flag_count"] or 0)
    dj_pool_path_count = int(flagged_row["dj_pool_path_count"] or 0)
    flagged_union_count = int(flagged_row["flagged_union_count"] or 0)
    cohort_total = int(coverage_row["cohort_total"] or 0)
    cohort_with_identity = int(coverage_row["cohort_with_identity"] or 0)
    cohort_without_identity = int(coverage_row["cohort_without_identity"] or 0)
    cohort_with_dj_pool_relink = int(relink_row["cohort_with_dj_pool_relink"] or 0)
    cohort_with_dj_export = int(export_row["cohort_with_dj_export"] or 0)

    identity_coverage_pct = (
        cohort_with_identity / cohort_total * 100 if cohort_total else 0.0
    )
    legacy_cache_only_rows = max(
        dj_pool_path_count - cohort_with_dj_pool_relink,
        0,
    )
    transcode_required_rows = max(
        cohort_with_identity - cohort_with_dj_pool_relink - legacy_cache_only_rows,
        0,
    )

    notes: list[str] = []
    if is_dj_material_count == 0 and dj_flag_count == 0 and dj_pool_path_count > 0:
        notes.append("Cohort is export-backed (dj_pool_path only); is_dj_material = 0 for all rows")
    elif is_dj_material_count == 0 and dj_flag_count > 0:
        notes.append("Cohort is legacy-flag-backed (dj_flag); is_dj_material = 0 for all rows")
    if identity_coverage_pct == 100.0:
        notes.append("Cohort is fully identity-backed (100% coverage)")
    if cohort_with_dj_pool_relink == cohort_total:
        notes.append("Cohort is fully relink-backed — this will be a pure-copy run (0 transcodes)")
    elif transcode_required_rows > 0:
        notes.append(f"{transcode_required_rows} row(s) will require transcode")
    if legacy_cache_only_rows > 0:
        notes.append(f"{legacy_cache_only_rows} row(s) have legacy dj_pool_path cache only (no relink event)")

    return {
        "cohort_definition": cohort_definition,
        "master_restricted": True,
        "master_root": str(master_root),
        "flagged_union_count": flagged_union_count,
        "is_dj_material_count": is_dj_material_count,
        "dj_flag_count": dj_flag_count,
        "dj_pool_path_count": dj_pool_path_count,
        "cohort_total": cohort_total,
        "cohort_with_identity": cohort_with_identity,
        "cohort_without_identity": cohort_without_identity,
        "identity_coverage_pct": round(identity_coverage_pct, 2),
        "cohort_with_dj_pool_relink": cohort_with_dj_pool_relink,
        "cohort_with_dj_export": cohort_with_dj_export,
        "legacy_cache_only_rows": legacy_cache_only_rows,
        "transcode_required_rows": transcode_required_rows,
        "notes": notes,
    }


def compute_cohort_duplicates(
    conn: sqlite3.Connection,
    master_root: Path,
) -> dict:
    prefix = str(master_root).rstrip("/") + "/%"
    cohort_clause = _locked_cohort_clause(conn, alias="f")

    rows = conn.execute(
        f"""
        SELECT
          al.identity_id,
          COUNT(*) AS row_count,
          GROUP_CONCAT(f.path, '||') AS master_paths
        FROM files f
        JOIN asset_file af ON af.path = f.path
        JOIN asset_link al ON al.asset_id = af.id AND al.active = 1
        WHERE {cohort_clause}
          AND f.path LIKE :prefix
        GROUP BY al.identity_id
        HAVING COUNT(*) > 1
        ORDER BY row_count DESC, al.identity_id
        """,
        {"prefix": prefix},
    ).fetchall()

    duplicate_rows = [
        {
            "identity_id": int(row["identity_id"]),
            "row_count": int(row["row_count"]),
            "master_paths": str(row["master_paths"]).split("||"),
        }
        for row in rows
    ]

    return {
        "duplicate_identity_count": len(duplicate_rows),
        "duplicate_master_path_count": sum(row["row_count"] for row in duplicate_rows),
        "duplicate_rows": duplicate_rows,
    }


def _collect_available_value_counts(
    conn: sqlite3.Connection,
    master_root: Path,
    profile: dict,
    *,
    field: str,
) -> list[tuple[str, int]]:
    rows = select_flagged_master_paths(conn, master_root, profile)
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(field) or "").strip()
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    return sorted(
        counts.items(),
        key=lambda item: (-item[1], item[0].casefold()),
    )


def _prompt_available_value_filter(
    conn: sqlite3.Connection,
    master_root: Path,
    profile: dict,
    *,
    field: str,
    label: str,
    value_label: str,
) -> list[str] | None:
    value_counts = _collect_available_value_counts(
        conn,
        master_root,
        profile,
        field=field,
    )
    if not value_counts:
        click.echo(f"  No {value_label} values found in current cohort")
        return None

    displayed = value_counts[:_INTERACTIVE_VALUE_PREVIEW_LIMIT]
    search_term: str | None = None
    exact_lookup = {
        value.casefold(): value
        for value, _ in value_counts
    }

    while True:
        if search_term:
            click.echo(
                f"  Available {value_label} values matching {search_term!r} "
                f"({len(displayed)} of {len(value_counts)}):"
            )
        else:
            click.echo(
                f"  Available {value_label} values in current cohort "
                f"({len(value_counts)}):"
            )
        for index, (value, count) in enumerate(displayed, start=1):
            click.echo(f"    {index}. {value} ({count})")
        remaining = len(value_counts) - len(displayed)
        if remaining > 0:
            click.echo(f"    ... {remaining} more")
        click.echo(
            "  Enter numbers or exact values, comma-separated; "
            "`/text` searches; `?` shows all; blank skips."
        )

        raw = click.prompt(label, default="").strip()
        if not raw:
            return None

        if raw == "?":
            displayed = value_counts
            search_term = None
            continue

        if raw.startswith("/"):
            term = raw[1:].strip()
            if not term:
                displayed = value_counts[:_INTERACTIVE_VALUE_PREVIEW_LIMIT]
                search_term = None
                continue
            filtered = [
                item
                for item in value_counts
                if term.casefold() in item[0].casefold()
            ]
            if not filtered:
                click.echo(f"  No {value_label} values match {term!r}")
                continue
            displayed = filtered
            search_term = term
            continue

        selected: list[str] = []
        invalid: list[str] = []
        for token in [part.strip() for part in raw.split(",") if part.strip()]:
            selected_value = None
            if token.isdigit():
                index = int(token)
                if 1 <= index <= len(displayed):
                    selected_value = displayed[index - 1][0]
            else:
                selected_value = exact_lookup.get(token.casefold())

            if selected_value is None:
                invalid.append(token)
                continue
            if selected_value not in selected:
                selected.append(selected_value)

        if invalid:
            click.echo(
                f"  Unknown {value_label} selection(s): {', '.join(invalid)}"
            )
            click.echo(
                "  Use numbered options, exact values, `?`, or `/text`."
            )
            continue

        return selected or None


def resolve_mp3_source(
    conn: sqlite3.Connection,
    master_path: str | Path,
    identity_id: int,
) -> tuple[str, Path | None, int | None, str | None]:
    master_path_text = str(Path(master_path).expanduser().resolve())

    row = conn.execute(
        """
        SELECT pe.id, pe.dest_path
        FROM provenance_event pe
        JOIN asset_file af ON af.path = :master_path
        JOIN asset_link al ON al.asset_id = af.id AND al.active = 1
        WHERE pe.identity_id = al.identity_id
          AND pe.event_type = 'dj_pool_relink'
          AND pe.status = 'success'
        ORDER BY pe.event_time DESC
        LIMIT 1
        """,
        {"master_path": master_path_text},
    ).fetchone()
    if row is not None and row["dest_path"]:
        dest_path = Path(str(row["dest_path"])).expanduser().resolve()
        if dest_path.exists():
            return ("relink", dest_path, int(row["id"]), None)

    row = conn.execute(
        "SELECT dj_pool_path FROM files WHERE path = :master_path",
        {"master_path": master_path_text},
    ).fetchone()
    if row is not None:
        dj_pool_path = str(row["dj_pool_path"] or "").strip()
        if dj_pool_path:
            dest_path = Path(dj_pool_path).expanduser().resolve()
            if dest_path.exists():
                return ("legacy", dest_path, None, "legacy_cache_fallback")

    row = conn.execute(
        """
        SELECT pe.id, pe.dest_path
        FROM provenance_event pe
        WHERE pe.identity_id = :identity_id
          AND pe.event_type = 'dj_export'
          AND pe.status = 'success'
        ORDER BY pe.event_time DESC
        LIMIT 1
        """,
        {"identity_id": int(identity_id)},
    ).fetchone()
    if row is not None and row["dest_path"]:
        dest_path = Path(str(row["dest_path"])).expanduser().resolve()
        if dest_path.exists():
            return ("export", dest_path, int(row["id"]), "export_path_fallback")

    return ("none", None, None, None)


def select_flagged_master_paths(
    conn: sqlite3.Connection,
    master_root: Path,
    profile: dict,
) -> list[dict]:
    only_roles_supplied, only_roles = _validated_only_roles(profile)
    prefix = str(master_root).rstrip("/") + "/%"
    cohort_clause = _locked_cohort_clause(conn, alias="f")
    files_has_dj_flag = _column_exists(conn, "files", "dj_flag")
    files_has_dj_set_role = _column_exists(conn, "files", "dj_set_role")
    files_has_duration_status = _column_exists(conn, "files", "duration_status")
    files_has_quality_rank = _column_exists(conn, "files", "quality_rank")
    files_has_download_source = _column_exists(conn, "files", "download_source")
    files_has_download_date = _column_exists(conn, "files", "download_date")
    asset_file_has_first_seen_at = _column_exists(conn, "asset_file", "first_seen_at")
    files_has_mtime = _column_exists(conn, "files", "mtime")
    files_has_canonical_artist = _column_exists(conn, "files", "canonical_artist")
    files_has_canonical_title = _column_exists(conn, "files", "canonical_title")
    files_has_canonical_genre = _column_exists(conn, "files", "canonical_genre")
    files_has_genre = _column_exists(conn, "files", "genre")
    files_has_canonical_label = _column_exists(conn, "files", "canonical_label")
    files_has_canonical_bpm = _column_exists(conn, "files", "canonical_bpm")
    files_has_bpm = _column_exists(conn, "files", "bpm")
    files_has_canonical_key = _column_exists(conn, "files", "canonical_key")
    files_has_key_camelot = _column_exists(conn, "files", "key_camelot")
    files_has_canonical_year = _column_exists(conn, "files", "canonical_year")

    flac_ok_expr = _coalesce_expr(
        _optional_column_expr(conn, "asset_file", "af", "flac_ok"),
        _optional_column_expr(conn, "files", "f", "flac_ok"),
    )
    integrity_state_expr = _coalesce_expr(
        _optional_column_expr(conn, "asset_file", "af", "integrity_state", treat_blank_as_null=True),
        _optional_column_expr(conn, "files", "f", "integrity_state", treat_blank_as_null=True),
    )
    download_source_expr = _coalesce_expr(
        _optional_column_expr(conn, "asset_file", "af", "download_source", treat_blank_as_null=True),
        _optional_column_expr(conn, "files", "f", "download_source", treat_blank_as_null=True)
        if files_has_download_source else None,
    )
    download_date_expr = _coalesce_expr(
        _optional_column_expr(conn, "asset_file", "af", "download_date", treat_blank_as_null=True),
        _optional_column_expr(conn, "files", "f", "download_date", treat_blank_as_null=True)
        if files_has_download_date else None,
        _optional_column_expr(conn, "asset_file", "af", "first_seen_at", treat_blank_as_null=True)
        if asset_file_has_first_seen_at else None,
        "datetime(f.mtime, 'unixepoch')"
        if files_has_mtime else None,
    )
    artist_expr = _coalesce_expr(
        "NULLIF(TRIM(ti.canonical_artist), '')",
        _optional_column_expr(conn, "files", "f", "canonical_artist", treat_blank_as_null=True)
        if files_has_canonical_artist else None,
    )
    title_expr = _coalesce_expr(
        "NULLIF(TRIM(ti.canonical_title), '')",
        _optional_column_expr(conn, "files", "f", "canonical_title", treat_blank_as_null=True)
        if files_has_canonical_title else None,
    )
    genre_expr = _coalesce_expr(
        "NULLIF(TRIM(ti.canonical_genre), '')",
        _optional_column_expr(conn, "files", "f", "canonical_genre", treat_blank_as_null=True)
        if files_has_canonical_genre else None,
        _optional_column_expr(conn, "files", "f", "genre", treat_blank_as_null=True)
        if files_has_genre else None,
    )
    label_expr = _coalesce_expr(
        "NULLIF(TRIM(ti.canonical_label), '')",
        _optional_column_expr(conn, "files", "f", "canonical_label", treat_blank_as_null=True)
        if files_has_canonical_label else None,
    )
    bpm_expr = _coalesce_expr(
        "ti.canonical_bpm",
        _optional_column_expr(conn, "files", "f", "canonical_bpm")
        if files_has_canonical_bpm else None,
        _optional_column_expr(conn, "files", "f", "bpm")
        if files_has_bpm else None,
    )
    key_expr = _coalesce_expr(
        "NULLIF(TRIM(ti.canonical_key), '')",
        _optional_column_expr(conn, "files", "f", "canonical_key", treat_blank_as_null=True)
        if files_has_canonical_key else None,
        _optional_column_expr(conn, "files", "f", "key_camelot", treat_blank_as_null=True)
        if files_has_key_camelot else None,
    )
    year_expr = _coalesce_expr(
        "ti.canonical_year",
        _optional_column_expr(conn, "files", "f", "canonical_year")
        if files_has_canonical_year else None,
    )

    select_columns = [
        "f.path AS master_path",
        "f.is_dj_material" if _column_exists(conn, "files", "is_dj_material") else "0 AS is_dj_material",
        "f.dj_flag" if files_has_dj_flag else "0 AS dj_flag",
        "f.dj_pool_path" if _column_exists(conn, "files", "dj_pool_path") else "NULL AS dj_pool_path",
    ]
    if files_has_dj_set_role:
        select_columns.append("f.dj_set_role")
    else:
        select_columns.append("NULL AS dj_set_role")
    if files_has_duration_status:
        select_columns.append("f.duration_status")
    if files_has_quality_rank:
        select_columns.append("f.quality_rank")
    select_columns.extend(
        [
            f"{flac_ok_expr} AS flac_ok",
            f"{integrity_state_expr} AS integrity_state",
            f"{download_source_expr} AS download_source",
            f"{download_date_expr} AS download_date",
            "al.identity_id",
            f"{artist_expr} AS artist",
            f"{title_expr} AS title",
            f"{genre_expr} AS genre",
            f"{label_expr} AS label",
            f"{bpm_expr} AS bpm",
            f"{key_expr} AS musical_key",
            f"{year_expr} AS year",
            "dj.rating AS dj_rating",
            "dj.energy AS dj_energy",
            "dj.set_role AS profile_set_role",
        ]
    )

    query = [
        "SELECT",
        "  " + ",\n  ".join(select_columns),
        "FROM files f",
        "LEFT JOIN asset_file af ON af.path = f.path",
        "LEFT JOIN asset_link al ON al.asset_id = af.id AND al.active = 1",
        "LEFT JOIN track_identity ti ON ti.id = al.identity_id",
        "LEFT JOIN dj_track_profile dj ON dj.identity_id = al.identity_id",
        f"WHERE {cohort_clause}",
        "  AND f.path LIKE ?",
    ]
    params: list[object] = [prefix]

    if bool(profile.get("require_flac_ok", False)):
        query.append(f"  AND {flac_ok_expr} = 1")

    integrity_states = [str(value) for value in (profile.get("integrity_states") or []) if str(value).strip()]
    if integrity_states:
        placeholders = ", ".join("?" for _ in integrity_states)
        query.append(f"  AND {integrity_state_expr} IN ({placeholders})")
        params.extend(integrity_states)

    if bool(profile.get("require_duration_ok", False)) and files_has_duration_status:
        query.append("  AND f.duration_status = 'ok'")

    if profile.get("require_artist_title") is True:
        query.extend(
            [
                f"  AND {artist_expr} IS NOT NULL",
                f"  AND {title_expr} IS NOT NULL",
                f"  AND TRIM({artist_expr}) <> ''",
                f"  AND TRIM({title_expr}) <> ''",
            ]
        )

    if profile.get("require_bpm") is True:
        query.append(f"  AND {bpm_expr} IS NOT NULL")

    if profile.get("require_key") is True:
        query.extend(
            [
                f"  AND {key_expr} IS NOT NULL",
                f"  AND TRIM({key_expr}) <> ''",
            ]
        )

    if profile.get("require_genre") is True:
        query.extend(
            [
                f"  AND {genre_expr} IS NOT NULL",
                f"  AND TRIM({genre_expr}) <> ''",
            ]
        )

    download_source_include = [
        str(value)
        for value in (profile.get("download_source_include") or [])
        if str(value).strip()
    ]
    if download_source_include:
        placeholders = ", ".join("?" for _ in download_source_include)
        query.append(f"  AND {download_source_expr} IN ({placeholders})")
        params.extend(download_source_include)

    download_date_since = str(profile.get("download_date_since") or "").strip()
    if download_date_since:
        query.append(f"  AND {download_date_expr} IS NOT NULL")
        query.append(f"  AND SUBSTR({download_date_expr}, 1, 10) >= ?")
        params.append(download_date_since)

    download_date_until = str(profile.get("download_date_until") or "").strip()
    if download_date_until:
        query.append(f"  AND {download_date_expr} IS NOT NULL")
        query.append(f"  AND SUBSTR({download_date_expr}, 1, 10) <= ?")
        params.append(download_date_until)

    genre_include = [str(value) for value in (profile.get("genre_include") or []) if str(value).strip()]
    if genre_include:
        placeholders = ", ".join("?" for _ in genre_include)
        query.append(f"  AND {genre_expr} IN ({placeholders})")
        params.extend(genre_include)

    genre_exclude = [str(value) for value in (profile.get("genre_exclude") or []) if str(value).strip()]
    if genre_exclude:
        placeholders = ", ".join("?" for _ in genre_exclude)
        query.append(f"  AND ({genre_expr} IS NULL OR {genre_expr} NOT IN ({placeholders}))")
        params.extend(genre_exclude)

    bpm_min = profile.get("bpm_min")
    if bpm_min is not None:
        query.append(f"  AND {bpm_expr} >= ?")
        params.append(float(bpm_min))

    bpm_max = profile.get("bpm_max")
    if bpm_max is not None:
        query.append(f"  AND {bpm_expr} <= ?")
        params.append(float(bpm_max))

    key_include = [str(value) for value in (profile.get("key_include") or []) if str(value).strip()]
    if key_include:
        placeholders = ", ".join("?" for _ in key_include)
        query.append(f"  AND {key_expr} IN ({placeholders})")
        params.extend(key_include)

    key_exclude = [str(value) for value in (profile.get("key_exclude") or []) if str(value).strip()]
    if key_exclude:
        placeholders = ", ".join("?" for _ in key_exclude)
        query.append(f"  AND ({key_expr} IS NULL OR {key_expr} NOT IN ({placeholders}))")
        params.extend(key_exclude)

    label_include = [str(value) for value in (profile.get("label_include") or []) if str(value).strip()]
    if label_include:
        placeholders = ", ".join("?" for _ in label_include)
        query.append(f"  AND {label_expr} IN ({placeholders})")
        params.extend(label_include)

    label_exclude = [str(value) for value in (profile.get("label_exclude") or []) if str(value).strip()]
    if label_exclude:
        placeholders = ", ".join("?" for _ in label_exclude)
        query.append(f"  AND ({label_expr} IS NULL OR {label_expr} NOT IN ({placeholders}))")
        params.extend(label_exclude)

    year_min = profile.get("year_min")
    if year_min is not None:
        query.append(f"  AND {year_expr} >= ?")
        params.append(int(year_min))

    year_max = profile.get("year_max")
    if year_max is not None:
        query.append(f"  AND {year_expr} <= ?")
        params.append(int(year_max))

    quality_rank_max = profile.get("quality_rank_max")
    if quality_rank_max is not None and files_has_quality_rank:
        query.append("  AND f.quality_rank <= ?")
        params.append(int(quality_rank_max))

    min_rating = profile.get("min_rating")
    if min_rating is not None:
        query.append("  AND dj.rating >= ?")
        params.append(int(min_rating))

    min_energy = profile.get("min_energy")
    if min_energy is not None:
        query.append("  AND dj.energy >= ?")
        params.append(int(min_energy))

    if only_roles_supplied:
        if not files_has_dj_set_role:
            query.append("  AND 0")
        elif only_roles:
            placeholders = ", ".join("?" for _ in only_roles)
            query.append(f"  AND f.dj_set_role IN ({placeholders})")
            params.extend(only_roles)
        else:
            query.append("  AND 0")

    set_role_include = [str(value) for value in (profile.get("set_role_include") or []) if str(value).strip()]
    if set_role_include:
        placeholders = ", ".join("?" for _ in set_role_include)
        query.append(f"  AND dj.set_role IN ({placeholders})")
        params.extend(set_role_include)

    if bool(profile.get("only_profiled", False)):
        query.append("  AND dj.identity_id IS NOT NULL")

    query.append("ORDER BY f.path ASC")

    rows = conn.execute("\n".join(query), tuple(params)).fetchall()
    return [dict(row) for row in rows]


def build_pool_dest_path(
    run_dir: Path,
    track: dict,
    profile: dict,
) -> Path:
    layout = str(profile.get("layout", "by_genre") or "by_genre")
    template = str(profile.get("filename_template", "{artist} - {title}.mp3") or "{artist} - {title}.mp3")

    artist = sanitize_component(_track_text(track, "canonical_artist", "artist") or "Unknown Artist")
    title = sanitize_component(_track_text(track, "canonical_title", "title") or "Unknown Title")
    genre = sanitize_component(_track_text(track, "canonical_genre", "genre") or "Unknown Genre")
    label = sanitize_component(_track_text(track, "canonical_label", "label") or "Unknown Label")

    filename = template.format(artist=artist, title=title)
    if not filename.endswith(".mp3"):
        filename += ".mp3"
    filename = sanitize_component(filename)

    if layout == "flat":
        subfolder = Path("pool")
    elif layout == "by_genre":
        subfolder = Path("pool") / genre
    elif layout == "by_role":
        subfolder = _role_subfolder(track)
    elif layout == "by_label":
        subfolder = Path("pool") / label
    else:
        subfolder = Path("pool")

    dest = run_dir / subfolder / filename
    if not dest.resolve().is_relative_to(run_dir.resolve()):
        raise ValueError(
            f"Computed destination path escapes run directory: {dest}"
        )
    return dest


def plan_actions(
    conn: sqlite3.Connection,
    selected_tracks: list[dict],
    run_dir: Path,
    profile: dict,
) -> list[dict]:
    selected_tracks = sorted(selected_tracks, key=lambda row: row["master_path"])
    seen_identities: dict[str, str] = {}
    plan_rows: list[dict] = []

    for track in selected_tracks:
        identity_id = track["identity_id"]
        has_identity = identity_id is not None

        if has_identity:
            source_info = resolve_mp3_source(
                conn,
                track["master_path"],
                int(identity_id),
            )
            source_type, source_path, source_warning = (
                source_info[0],
                source_info[1],
                source_info[3],
            )
        else:
            source_type, source_path, source_warning = ("none", None, None)

        identity_key = str(identity_id) if identity_id is not None else None
        if identity_key is not None and identity_key in seen_identities:
            selected = False
            cache_action = "skip"
            pool_action = "skip"
            reason = "duplicate_identity"
            warning = f"kept: {seen_identities[identity_key]}"
        elif source_type == "relink":
            selected = True
            cache_action = "use_relink"
            pool_action = "copy"
            reason = None
            warning = None
        elif source_type == "legacy":
            selected = True
            cache_action = "use_legacy"
            pool_action = "copy"
            reason = None
            warning = "legacy_cache_fallback"
        elif source_type == "export":
            selected = True
            cache_action = "use_export"
            pool_action = "copy"
            reason = None
            warning = "export_path_fallback"
        elif source_type == "none" and has_identity:
            selected = True
            cache_action = "transcode"
            pool_action = "copy_after_transcode"
            reason = None
            warning = None
        else:
            selected = False
            cache_action = "skip"
            pool_action = "skip"
            reason = "no_v3_identity"
            warning = None

        if selected:
            try:
                final_dest_path = str(build_pool_dest_path(run_dir, track, profile))
            except ValueError as exc:
                selected = False
                cache_action = "skip"
                pool_action = "skip"
                reason = "path_escape"
                warning = str(exc)
                final_dest_path = None
        else:
            final_dest_path = None

        if cache_action == "transcode":
            transcode_ready = has_identity
            transcode_blocker = None if transcode_ready else "no_v3_identity"
        else:
            transcode_ready = None
            transcode_blocker = None

        if selected and identity_key is not None:
            seen_identities[identity_key] = str(track["master_path"])

        artist = _track_value(track, "canonical_artist", "artist")
        title = _track_value(track, "canonical_title", "title")
        genre = _track_value(track, "canonical_genre", "genre")
        label = _track_value(track, "canonical_label", "label")
        bpm = _track_value(track, "canonical_bpm", "bpm")
        musical_key = _track_value(track, "canonical_key", "musical_key")
        row = {
            "master_path": track["master_path"],
            "identity_id": identity_id,
            "v3_identity": has_identity,
            "selected": selected,
            "cache_source_type": source_type,
            "cache_source_path": str(source_path) if source_path else None,
            "cache_source_warning": source_warning,
            "cache_action": cache_action,
            "pool_action": pool_action,
            "transcode_ready": transcode_ready,
            "transcode_blocker": transcode_blocker,
            "final_dest_path": final_dest_path,
            "reason": reason,
            "warning": warning,
            "artist": artist,
            "title": title,
            "genre": genre,
            "label": label,
            "bpm": bpm,
            "musical_key": musical_key,
            "dj_set_role": track.get("dj_set_role"),
        }
        plan_rows.append(row)

    seen_dest: dict[str, int] = {}
    for i, row in enumerate(plan_rows):
        if not row["selected"] or row["final_dest_path"] is None:
            continue
        norm = str(Path(row["final_dest_path"]).resolve()).lower()
        if norm in seen_dest:
            base = Path(row["final_dest_path"])
            stem = base.stem
            suffix = base.suffix
            uid = str(row["identity_id"] or i)
            new_name = f"{stem}__{uid}{suffix}"
            new_path = base.parent / new_name
            if new_path.resolve().is_relative_to(
                base.parent.parent.resolve()
            ):
                row["final_dest_path"] = str(new_path)
                row["warning"] = (
                    ((row["warning"] or "") + " filename_collision_resolved").strip()
                )
                norm = str(new_path.resolve()).lower()
        seen_dest[norm] = i

    return plan_rows


def execute_plan(
    conn: sqlite3.Connection,
    plan_rows: list[dict],
    profile: dict,
    run_dir: Path,
) -> tuple[list[dict], list[dict]]:
    receipts: list[dict] = []
    failures: list[dict] = []
    bitrate = int(profile.get("bitrate", 320))
    ffmpeg_path = profile.get("ffmpeg_path") or None
    cache_overwrite_policy = profile.get("cache_overwrite_policy", "never")
    pool_overwrite_policy = profile.get("pool_overwrite_policy", "never")

    rows = sorted(
        plan_rows,
        key=lambda r: (
            0 if r["selected"] else 1,
            r.get("identity_id") or 0,
            r.get("final_dest_path") or "",
        )
    )

    for row in rows:
        if not row["selected"]:
            continue

        if row["cache_action"] == "transcode":
            if not row["identity_id"]:
                failures.append(_failure(row, "no_v3_identity", "identity_id is None"))
                continue

            try:
                snapshot = resolve_dj_tag_snapshot(
                    conn, int(row["identity_id"]),
                    run_essentia=True, dry_run=False
                )
            except Exception as exc:
                failures.append(_failure(row, "transcode_failed", f"snapshot failed: {exc}"))
                continue

            partial_metadata = any(
                value is None for value in (
                    snapshot.bpm,
                    snapshot.musical_key,
                    snapshot.energy_1_10,
                )
            )

            cache_dest = _build_cache_dest(run_dir, row, profile)
            cache_dest.parent.mkdir(parents=True, exist_ok=True)

            try:
                transcode_to_mp3_from_snapshot(
                    Path(row["master_path"]),
                    cache_dest.parent,
                    snapshot,
                    bitrate=bitrate,
                    overwrite=(cache_overwrite_policy == "always"),
                    ffmpeg_path=ffmpeg_path,
                    dest_path=cache_dest,
                )
            except Exception as exc:
                failures.append(_failure(row, "transcode_failed", str(exc)))
                continue

            try:
                asset_id = resolve_asset_id_by_path(
                    conn, Path(row["master_path"])
                )
                conn.execute("BEGIN")
                conn.execute(
                    "UPDATE files SET dj_pool_path = ? WHERE path = ?",
                    (str(cache_dest), row["master_path"]),
                )
                prov_id = record_provenance_event(
                    conn,
                    event_type="dj_export",
                    status="success",
                    asset_id=asset_id,
                    identity_id=int(row["identity_id"]),
                    source_path=row["master_path"],
                    dest_path=str(cache_dest),
                    details={
                        "tag_snapshot": snapshot.as_dict(),
                        "bpm_source": snapshot.bpm_source,
                        "key_source": snapshot.key_source,
                        "energy_source": snapshot.energy_source,
                        "format": "mp3",
                        "bitrate": bitrate,
                        "tool_version": f"dj_pool_wizard:{WIZARD_VERSION}",
                        "partial_metadata": partial_metadata,
                    },
                )
                conn.execute("COMMIT")
                row["cache_source_path"] = str(cache_dest)
                row["_provenance_event_id"] = prov_id
                row["_snapshot"] = {
                    "energy_1_10": snapshot.energy_1_10,
                    "bpm_source": snapshot.bpm_source,
                    "key_source": snapshot.key_source,
                    "energy_source": snapshot.energy_source,
                }
                if partial_metadata:
                    row["warning"] = (
                        ((row.get("warning") or "") + " partial_metadata").strip()
                    )
            except Exception as exc:
                try:
                    conn.execute("ROLLBACK")
                except Exception:
                    pass
                failures.append(_failure(row, "db_write_failed", str(exc)))
                continue

        if row["pool_action"] not in ("copy", "copy_after_transcode"):
            continue

        source = Path(row["cache_source_path"]) if row["cache_source_path"] else None
        dest = Path(row["final_dest_path"])

        if source is None or not source.exists():
            failures.append(_failure(row, "copy_failed", "cache source missing on disk"))
            continue

        dest.parent.mkdir(parents=True, exist_ok=True)

        previous_hash = None
        if dest.exists():
            if pool_overwrite_policy == "never":
                failures.append(_failure(row, "pool_path_exists", f"dest exists: {dest}"))
                continue
            elif pool_overwrite_policy == "if_same_hash":
                previous_hash = _sha256_file(dest)
                source_hash = _sha256_file(source)
                if previous_hash != source_hash:
                    failures.append(_failure(row, "pool_hash_mismatch", "dest exists with different hash"))
                    continue

        shutil.copy2(source, dest)
        new_hash = _sha256_file(dest)
        snapshot_meta = row.get("_snapshot") or {}
        receipts.append({
            "identity_id": row["identity_id"],
            "master_path": row["master_path"],
            "cache_source_type": row["cache_source_type"],
            "cache_source_path": row["cache_source_path"],
            "final_dest_path": str(dest),
            "cache_action": row["cache_action"],
            "pool_action": row["pool_action"],
            "provenance_event_id": row.get("_provenance_event_id"),
            "overwrite": previous_hash is not None,
            "overwrite_policy": pool_overwrite_policy,
            "previous_hash": previous_hash,
            "new_hash": new_hash,
            "partial_metadata": "partial_metadata" in (row.get("warning") or ""),
            "warning": row.get("warning"),
            "timestamp": _iso_now(),
            "energy_1_10": snapshot_meta.get("energy_1_10"),
            "bpm_source": snapshot_meta.get("bpm_source"),
            "key_source": snapshot_meta.get("key_source"),
            "energy_source": snapshot_meta.get("energy_source"),
        })

    return receipts, failures


def build_pool_manifest(
    run_dir: Path,
    plan: list[dict],
    receipts: list[dict],
    failures: list[dict],
    profile: dict,
    plan_mode: bool,
) -> dict:
    executed = {row["final_dest_path"]: row for row in receipts}
    failed_paths = {row["final_dest_path"] for row in failures}

    selected_n = sum(1 for row in plan if row["selected"])
    executed_n = len(receipts)
    skipped_n = sum(1 for row in plan if not row["selected"])
    failed_n = len(failures)
    no_v3_n = sum(1 for row in failures if row["error_type"] == "no_v3_identity")
    legacy_n = sum(
        1 for row in plan
        if row.get("cache_source_type") == "legacy" and row["selected"]
    )

    manifest_rows: list[dict] = []
    for row in plan:
        if plan_mode:
            status = "planned"
        elif not row["selected"]:
            status = "skipped"
        elif row["final_dest_path"] in executed:
            status = "executed"
        elif row["final_dest_path"] in failed_paths:
            status = "failed"
        else:
            status = "planned"

        receipt = executed.get(row["final_dest_path"], {})
        manifest_rows.append({
            "identity_id": row["identity_id"],
            "master_path": row["master_path"],
            "cache_source_type": row["cache_source_type"],
            "cache_source_path": row["cache_source_path"],
            "final_dest_path": row["final_dest_path"],
            "playlist_rel_path": None,
            "bpm": row.get("bpm"),
            "musical_key": row.get("musical_key"),
            "dj_set_role": row.get("dj_set_role"),
            "energy_1_10": receipt.get("energy_1_10"),
            "bpm_source": receipt.get("bpm_source"),
            "key_source": receipt.get("key_source"),
            "energy_source": receipt.get("energy_source"),
            "provenance_event_id": receipt.get("provenance_event_id"),
            "status": status,
            "reason": row.get("reason"),
            "warning": row.get("warning"),
        })

    return {
        "pool_name": profile.get("pool_name", "pool"),
        "run_timestamp": _iso_now(),
        "wizard_version": WIZARD_VERSION,
        "plan_mode": plan_mode,
        "profile": profile,
        "execution_summary": {
            "selected": selected_n,
            "executed": executed_n,
            "skipped": skipped_n,
            "failed": failed_n,
            "no_v3_identity": no_v3_n,
            "legacy_cache_fallback": legacy_n,
        },
        "rows": manifest_rows,
    }


def generate_playlist(
    manifest: dict,
    playlist_path: Path,
    mode: str,
) -> None:
    playlist_path.parent.mkdir(parents=True, exist_ok=True)

    lines = ["#EXTM3U"]
    for row in manifest["rows"]:
        if row["status"] != "executed":
            continue
        dest = row["final_dest_path"]
        if dest is None:
            continue
        if mode == "relative":
            path_str = os.path.relpath(dest, str(playlist_path.parent))
        else:
            path_str = str(Path(dest).resolve())
        lines.append(path_str)
        row["playlist_rel_path"] = path_str

    playlist_path.write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def generate_role_playlists(
    manifest: dict,
    pool_root: Path,
    mode: str,
) -> list[Path]:
    written: list[Path] = []
    rows_by_role = {role: [] for role in _ROLE_PLAYLIST_ORDER}

    for row in manifest["rows"]:
        if row["status"] != "executed":
            continue
        if row.get("final_dest_path") is None:
            continue
        role = _normalize_dj_set_role(row.get("dj_set_role"))
        if role is None:
            continue
        rows_by_role.setdefault(role, []).append(row)

    for role in _ROLE_PLAYLIST_ORDER:
        role_rows = rows_by_role.get(role) or []
        if not role_rows:
            continue

        role_manifest = {"rows": role_rows}
        playlist_path = pool_root / _ROLE_PLAYLIST_FILENAMES[role]
        generate_playlist(role_manifest, playlist_path, mode=mode)
        written.append(playlist_path)

    return written


def run_interactive_wizard(
    conn: sqlite3.Connection,
    master_root: Path,
    health: dict,
    dups: dict,
) -> dict:
    def _prompt_float_or_none(label: str) -> float | None:
        raw = click.prompt(f"{label} (blank = no limit)", default="").strip()
        try:
            return float(raw) if raw else None
        except ValueError:
            click.echo(f"  Invalid number, skipping {label}")
            return None

    def _prompt_int_or_none(label: str) -> int | None:
        raw = click.prompt(f"{label} (blank = no limit)", default="").strip()
        try:
            return int(raw) if raw else None
        except ValueError:
            click.echo(f"  Invalid number, skipping {label}")
            return None

    files_has_duration_status = _column_exists(conn, "files", "duration_status")
    files_has_quality_rank = _column_exists(conn, "files", "quality_rank")
    preview_profile: dict[str, object] = {}

    def _set_preview_value(key: str, value: object) -> None:
        if value is None or value == [] or value == "":
            preview_profile.pop(key, None)
            return
        preview_profile[key] = value

    def _echo_value_counts(
        field: str,
        value_label: str,
        *,
        max_items: int = 12,
    ) -> None:
        value_counts = _collect_available_value_counts(
            conn,
            master_root,
            preview_profile,
            field=field,
        )
        if not value_counts:
            click.echo(f"  No {value_label} values found in current cohort")
            return

        shown = value_counts[:max_items]
        rendered = ", ".join(
            f"{value} ({count})"
            for value, count in shown
        )
        click.echo(f"  Available {value_label} values: {rendered}")
        remaining = len(value_counts) - len(shown)
        if remaining > 0:
            click.echo(
                f"  ... {remaining} more. Use `?` or `/text` in the prompt to explore."
            )

    def _echo_numeric_range(
        field: str,
        value_label: str,
        *,
        integer: bool = False,
    ) -> None:
        values: list[float] = []
        for row in select_flagged_master_paths(conn, master_root, preview_profile):
            value = row.get(field)
            if value is None or value == "":
                continue
            try:
                values.append(float(value))
            except (TypeError, ValueError):
                continue

        if not values:
            click.echo(f"  No {value_label} values found in current cohort")
            return

        if integer:
            distinct = sorted({int(value) for value in values})
            if len(distinct) <= 12:
                click.echo(
                    f"  Available {value_label} values: "
                    f"{', '.join(str(value) for value in distinct)}"
                )
                return
            click.echo(
                f"  Available {value_label} range: "
                f"{int(min(values))} to {int(max(values))}"
            )
            return

        click.echo(
            f"  Available {value_label} range: "
            f"{min(values):.1f} to {max(values):.1f}"
        )

    def _echo_date_range(field: str, value_label: str) -> None:
        dates = sorted(
            {
                str(row.get(field) or "").strip()[:10]
                for row in select_flagged_master_paths(conn, master_root, preview_profile)
                if str(row.get(field) or "").strip()
            }
        )
        if not dates:
            click.echo(f"  No {value_label} values found in current cohort")
            return
        click.echo(
            f"  Available {value_label} range: {dates[0]} to {dates[-1]}"
        )

    pool_name = click.prompt("Pool name", default="DJ Pool").strip()
    if not pool_name:
        pool_name = "DJ Pool"

    click.echo("\n── Locked cohort ──────────────────────────────────")
    click.echo(f"  {health['cohort_definition']}")
    click.echo(f"  Restricted to: {master_root}")
    click.echo(f"  Total flagged: {health['flagged_union_count']}")
    for note in health.get("notes", []):
        click.echo(f"  ↳ {note}")
    if dups["duplicate_identity_count"] > 0:
        click.echo(
            f"  ⚠  {dups['duplicate_identity_count']} duplicate "
            f"identit(ies) detected — first-path wins at plan time"
        )
    click.echo("────────────────────────────────────────────────────")

    if not click.confirm("Continue with this cohort?", default=True):
        raise ValueError("Aborted by user at cohort confirmation")

    click.echo(f"\nAll source assets must be under: {master_root}")
    if not click.confirm("Confirm MASTER_LIBRARY restriction?", default=True):
        raise ValueError("Aborted by user at MASTER_LIBRARY confirmation")

    click.echo("\n── Integrity gates ─────────────────────────────────")
    require_flac_ok = click.confirm("Require flac_ok = 1?", default=False)
    _set_preview_value("require_flac_ok", require_flac_ok)

    integrity_states = _prompt_available_value_filter(
        conn,
        master_root,
        preview_profile,
        field="integrity_state",
        label="integrity_state include",
        value_label="integrity_state",
    )
    _set_preview_value("integrity_states", integrity_states)

    require_duration_ok = False
    if files_has_duration_status:
        _echo_value_counts("duration_status", "duration_status")
        require_duration_ok = click.confirm(
            "Require duration_status = 'ok'?", default=False
        )
    else:
        click.echo(
            "  duration_status column not found in files — duration gate skipped"
        )
    _set_preview_value("require_duration_ok", require_duration_ok)

    click.echo("\n── Metadata gates ──────────────────────────────────")
    require_artist_title = click.confirm(
        "Require artist + title?", default=False
    )
    require_bpm = click.confirm("Require BPM?", default=False)
    require_key = click.confirm("Require musical key?", default=False)
    require_genre = click.confirm("Require genre?", default=False)
    _set_preview_value("require_artist_title", require_artist_title)
    _set_preview_value("require_bpm", require_bpm)
    _set_preview_value("require_key", require_key)
    _set_preview_value("require_genre", require_genre)

    click.echo("\n── Source / date filters ────────────────────────────")
    download_source_include = _prompt_available_value_filter(
        conn,
        master_root,
        preview_profile,
        field="download_source",
        label="download_source include",
        value_label="download_source",
    )
    _set_preview_value("download_source_include", download_source_include)

    _echo_date_range("download_date", "download_date")
    since_input = click.prompt(
        "download_date since (YYYY-MM-DD, blank = none)",
        default="",
    ).strip()
    download_date_since = since_input if since_input else None
    _set_preview_value("download_date_since", download_date_since)

    _echo_date_range("download_date", "download_date")
    until_input = click.prompt(
        "download_date until (YYYY-MM-DD, blank = none)",
        default="",
    ).strip()
    download_date_until = until_input if until_input else None
    _set_preview_value("download_date_until", download_date_until)

    click.echo("\n── Musical filters ─────────────────────────────────")
    genre_include = _prompt_available_value_filter(
        conn,
        master_root,
        preview_profile,
        field="genre",
        label="genre include",
        value_label="genre",
    )
    _set_preview_value("genre_include", genre_include)
    genre_exclude = _prompt_available_value_filter(
        conn,
        master_root,
        preview_profile,
        field="genre",
        label="genre exclude",
        value_label="genre",
    )
    _set_preview_value("genre_exclude", genre_exclude)
    _echo_numeric_range("bpm", "BPM")
    bpm_min = _prompt_float_or_none("BPM min")
    _set_preview_value("bpm_min", bpm_min)
    _echo_numeric_range("bpm", "BPM")
    bpm_max = _prompt_float_or_none("BPM max")
    _set_preview_value("bpm_max", bpm_max)
    key_include = _prompt_available_value_filter(
        conn,
        master_root,
        preview_profile,
        field="musical_key",
        label="musical key include",
        value_label="musical key",
    )
    _set_preview_value("key_include", key_include)
    key_exclude = _prompt_available_value_filter(
        conn,
        master_root,
        preview_profile,
        field="musical_key",
        label="musical key exclude",
        value_label="musical key",
    )
    _set_preview_value("key_exclude", key_exclude)
    label_include = _prompt_available_value_filter(
        conn,
        master_root,
        preview_profile,
        field="label",
        label="label include",
        value_label="label",
    )
    _set_preview_value("label_include", label_include)
    label_exclude = _prompt_available_value_filter(
        conn,
        master_root,
        preview_profile,
        field="label",
        label="label exclude",
        value_label="label",
    )
    _set_preview_value("label_exclude", label_exclude)
    quality_rank_max = None
    if files_has_quality_rank:
        click.echo(
            "  quality_rank is the legacy source-quality score "
            "(1 = best, 7 = worst)"
        )
        _echo_numeric_range("quality_rank", "quality_rank", integer=True)
        quality_rank_max = _prompt_int_or_none("quality_rank max")
        _set_preview_value("quality_rank_max", quality_rank_max)
    else:
        click.echo(
            "  quality_rank column not found in files — quality_rank filter skipped"
        )
    _echo_numeric_range("year", "year", integer=True)
    year_min = _prompt_int_or_none("year min")
    _set_preview_value("year_min", year_min)
    _echo_numeric_range("year", "year", integer=True)
    year_max = _prompt_int_or_none("year max")
    _set_preview_value("year_max", year_max)

    click.echo("\n── DJ profile filters ──────────────────────────────")
    profile_count = conn.execute(
        "SELECT COUNT(*) FROM dj_track_profile"
    ).fetchone()[0]

    profile_filter_active = False
    min_rating = None
    min_energy = None
    set_role_include = None
    only_profiled = False

    if profile_count == 0:
        click.echo(
            "  No dj_track_profile rows found — profile filters skipped"
        )
    else:
        click.echo(f"  {profile_count} profiled track(s) available")

        if click.confirm("  Enable DJ profile filters?", default=False):
            profile_filter_active = True

            _echo_numeric_range("dj_rating", "DJ rating", integer=True)
            min_rating = _prompt_int_or_none("  min rating (0–5)")
            if min_rating is not None:
                min_rating = max(0, min(5, min_rating))
            _set_preview_value("min_rating", min_rating)

            _echo_numeric_range("dj_energy", "DJ energy", integer=True)
            min_energy = _prompt_int_or_none("  min energy (0–10)")
            if min_energy is not None:
                min_energy = max(0, min(10, min_energy))
            _set_preview_value("min_energy", min_energy)

            set_role_include = _prompt_available_value_filter(
                conn,
                master_root,
                preview_profile,
                field="profile_set_role",
                label="  set_role include",
                value_label="set_role",
            )
            _set_preview_value("set_role_include", set_role_include)

            only_profiled = click.confirm(
                "  Only include profiled tracks?", default=False
            )
            _set_preview_value("only_profiled", only_profiled)

    default_layout = "by_role" if profile_filter_active else "by_genre"

    click.echo("\n── Output shaping ──────────────────────────────────")
    layout = click.prompt(
        "Layout",
        type=click.Choice(["flat", "by_genre", "by_role", "by_label"]),
        default=default_layout,
    )

    filename_template = click.prompt(
        "Filename template",
        default="{artist} - {title}.mp3",
    ).strip()
    if not filename_template:
        filename_template = "{artist} - {title}.mp3"

    create_playlist = click.confirm("Generate playlist?", default=True)
    playlist_mode = "relative"
    if create_playlist:
        playlist_mode = click.prompt(
            "Playlist path mode",
            type=click.Choice(["relative", "absolute"]),
            default="relative",
        )

    click.echo("\n── Execution controls ──────────────────────────────")
    execute = click.confirm("Execute now? (no = plan only)", default=False)

    bitrate = 320
    ffmpeg_path = None
    cache_overwrite_policy = "never"
    pool_overwrite_policy = "never"

    if execute:
        bitrate_raw = click.prompt(
            "MP3 bitrate (kbps)", default="320"
        ).strip()
        try:
            bitrate = int(bitrate_raw)
        except ValueError:
            bitrate = 320

        ffmpeg_raw = click.prompt(
            "ffmpeg path (blank = auto)", default=""
        ).strip()
        ffmpeg_path = ffmpeg_raw if ffmpeg_raw else None

        cache_overwrite_policy = click.prompt(
            "Cache overwrite policy",
            type=click.Choice(["never", "if_same_hash", "always"]),
            default="never",
        )
        pool_overwrite_policy = click.prompt(
            "Pool overwrite policy",
            type=click.Choice(["never", "if_same_hash", "always"]),
            default="never",
        )

    return {
        "pool_name": pool_name,
        "layout": layout,
        "filename_template": filename_template,
        "create_playlist": create_playlist,
        "playlist_mode": playlist_mode,
        "require_flac_ok": require_flac_ok,
        "integrity_states": integrity_states,
        "require_duration_ok": require_duration_ok,
        "require_artist_title": require_artist_title,
        "require_bpm": require_bpm,
        "require_key": require_key,
        "require_genre": require_genre,
        "download_source_include": download_source_include,
        "download_date_since": download_date_since,
        "download_date_until": download_date_until,
        "genre_include": genre_include,
        "genre_exclude": genre_exclude,
        "bpm_min": bpm_min,
        "bpm_max": bpm_max,
        "key_include": key_include,
        "key_exclude": key_exclude,
        "label_include": label_include,
        "label_exclude": label_exclude,
        "quality_rank_max": quality_rank_max,
        "year_min": year_min,
        "year_max": year_max,
        "min_rating": min_rating,
        "min_energy": min_energy,
        "set_role_include": set_role_include,
        "only_profiled": only_profiled,
        "bitrate": bitrate,
        "ffmpeg_path": ffmpeg_path,
        "cache_overwrite_policy": cache_overwrite_policy,
        "pool_overwrite_policy": pool_overwrite_policy,
        "execute": execute,
    }


def validate_wizard_environment(
    db_path: Path,
    master_root: Path,
    dj_cache_root: Path,
    out_root: Path,
    pool_name: str,
    overwrite_run: bool,
) -> Path:
    db_path = Path(db_path).expanduser().resolve()
    master_root = Path(master_root).expanduser().resolve()
    dj_cache_root = Path(dj_cache_root).expanduser().resolve()
    out_root = Path(out_root).expanduser().resolve()

    sanitized_name = re.sub(r'[\/\\:*?"<>|]', "", str(pool_name))
    sanitized_name = re.sub(r"[\s_]+", "_", sanitized_name)
    sanitized_name = sanitized_name.strip(" .")
    sanitized_name = sanitized_name[:80]
    if not sanitized_name:
        sanitized_name = "pool"

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = out_root / f"{sanitized_name}_{timestamp}"

    if out_root == master_root:
        raise ValueError("out-root must not be MASTER_LIBRARY")

    if master_root in out_root.parents:
        raise ValueError("out-root must not be inside MASTER_LIBRARY")

    if out_root == dj_cache_root:
        raise ValueError("out-root must not be DJ_LIBRARY")

    if dj_cache_root in out_root.parents:
        raise ValueError("out-root must not be inside DJ_LIBRARY")

    if out_root == db_path.parent:
        raise ValueError("out-root must not be the DB parent directory")

    if run_dir.exists() and (run_dir / "pool_manifest.json").exists() and not overwrite_run:
        raise ValueError("Run directory already contains pool_manifest.json; use --overwrite-run")

    resolved_run_dir = run_dir.resolve()
    for path in (
        run_dir / "pool_manifest.json",
        run_dir / "plan.csv",
        run_dir / "answers.json",
    ):
        if not path.resolve().is_relative_to(resolved_run_dir):
            raise ValueError("Computed path escapes run directory")

    return run_dir


def run_pool_wizard(
    db_path: str | Path | None,
    master_root: str | Path,
    dj_cache_root: str | Path,
    out_root: str | Path | None,
    plan_mode: bool,
    profile_path: str | Path | None,
    non_interactive: bool,
    overwrite_run: bool,
) -> int:
    import sys

    db_path_resolved = Path(db_path).expanduser().resolve() if db_path is not None else None
    master_root_resolved = Path(master_root).expanduser().resolve()
    dj_cache_root_resolved = Path(dj_cache_root).expanduser().resolve()
    out_root_resolved = Path(out_root).expanduser().resolve() if out_root is not None else None
    profile_path_resolved = Path(profile_path).expanduser().resolve() if profile_path is not None else None

    if non_interactive and not out_root_resolved:
        click.echo("Error: --out-root is required in --non-interactive mode", err=True)
        return 2
    if non_interactive and not profile_path_resolved:
        click.echo("Error: --profile is required in --non-interactive mode", err=True)
        return 2
    if out_root_resolved is None:
        click.echo("Error: --out-root is required", err=True)
        return 2
    if db_path_resolved is None:
        click.echo("Error: database path is required", err=True)
        return 2

    conn = sqlite3.connect(str(db_path_resolved))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        try:
            validate_schema_and_views(conn)
        except ValueError as exc:
            click.echo(f"Error: {exc}", err=True)
            return 2

        health = compute_cohort_health(conn, master_root_resolved)
        dups = compute_cohort_duplicates(conn, master_root_resolved)

        is_tty = sys.stdin.isatty()

        if non_interactive:
            if not profile_path_resolved or not profile_path_resolved.exists():
                click.echo(
                    "Error: --profile file not found", err=True
                )
                return 2
            profile = json.loads(
                profile_path_resolved.read_text(encoding="utf-8")
            )
            required_fields = ["pool_name"]
            missing = [field for field in required_fields if not profile.get(field)]
            if missing:
                click.echo(
                    f"Error: profile missing required fields: {missing}",
                    err=True,
                )
                return 2
            pool_name = profile["pool_name"]
        elif is_tty:
            try:
                profile = run_interactive_wizard(
                    conn, master_root_resolved, health, dups
                )
            except ValueError as exc:
                click.echo(f"Aborted: {exc}", err=True)
                return 2
            pool_name = profile["pool_name"]
            plan_mode = not profile.get("execute", False)
        else:
            click.echo(
                "Warning: no TTY detected and --non-interactive not set. "
                "Running plan mode with empty profile.",
                err=True,
            )
            profile = {}
            pool_name = "pool"

        try:
            run_dir = validate_wizard_environment(
                db_path=db_path_resolved,
                master_root=master_root_resolved,
                dj_cache_root=dj_cache_root_resolved,
                out_root=out_root_resolved,
                pool_name=pool_name,
                overwrite_run=overwrite_run,
            )
        except ValueError as exc:
            click.echo(f"Error: {exc}", err=True)
            return 2

        run_dir.mkdir(parents=True, exist_ok=True)

        (run_dir / "answers.json").write_text(
            json.dumps(profile, indent=2), encoding="utf-8"
        )

        if profile_path_resolved:
            profile_path_resolved.write_text(
                json.dumps(profile, indent=2), encoding="utf-8"
            )

        (run_dir / "cohort_health.json").write_text(
            json.dumps(health, indent=2), encoding="utf-8"
        )
        (run_dir / "cohort_duplicates.json").write_text(
            json.dumps(dups, indent=2), encoding="utf-8"
        )

        try:
            selected = select_flagged_master_paths(conn, master_root_resolved, profile)
        except ValueError as exc:
            click.echo(f"Error: {exc}", err=True)
            return 2

        if not selected:
            if non_interactive:
                click.echo(
                    "Error: profile filter produces empty cohort", err=True
                )
                return 2
            if not click.confirm(
                "Filters produced zero candidates. Continue?",
                default=False,
            ):
                return 2

        if selected:
            selected_csv = run_dir / "selected.csv"
            with selected_csv.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=selected[0].keys())
                writer.writeheader()
                writer.writerows(selected)

        plan = plan_actions(conn, selected, run_dir, profile)

        plan_csv = run_dir / "plan.csv"
        if plan:
            with plan_csv.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=plan[0].keys())
                writer.writeheader()
                writer.writerows(plan)

        total = len(plan)
        selected_n = sum(1 for row in plan if row["selected"])
        skipped = sum(1 for row in plan if not row["selected"])
        by_action: dict[str, int] = {}
        for row in plan:
            if row["selected"]:
                by_action[row["cache_action"]] = by_action.get(row["cache_action"], 0) + 1

        click.echo(f"Plan: {total} rows | selected={selected_n} skipped={skipped}")
        for action, count in sorted(by_action.items()):
            click.echo(f"  {action}: {count}")

        manifest = build_pool_manifest(
            run_dir, plan, [], [], profile, plan_mode=plan_mode
        )
        (run_dir / "pool_manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )

        if not plan_mode:
            receipts, failures = execute_plan(conn, plan, profile, run_dir)

            _write_jsonl(run_dir / "receipts.jsonl", receipts)
            _write_jsonl(run_dir / "failures.jsonl", failures)

            manifest = build_pool_manifest(
                run_dir, plan, receipts, failures, profile, plan_mode=False
            )
            (run_dir / "pool_manifest.json").write_text(
                json.dumps(manifest, indent=2), encoding="utf-8"
            )

            if profile.get("create_playlist", False):
                playlist_mode = profile.get("playlist_mode", "relative")
                if str(profile.get("layout", "by_genre") or "by_genre") == "by_role":
                    generate_role_playlists(
                        manifest,
                        run_dir / "pool",
                        mode=playlist_mode,
                    )
                else:
                    generate_playlist(
                        manifest,
                        run_dir / "playlist.m3u8",
                        mode=playlist_mode,
                    )

        s = manifest["execution_summary"]
        click.echo(
            f"selected={s['selected']} executed={s['executed']} "
            f"skipped={s['skipped']} failed={s['failed']} "
            f"no_v3_identity={s['no_v3_identity']} "
            f"legacy_cache_fallback={s['legacy_cache_fallback']}"
        )
        click.echo(f"Run directory: {run_dir}")
        return 1 if (not plan_mode and failures) else 0
    finally:
        conn.close()
