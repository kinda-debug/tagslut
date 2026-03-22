from __future__ import annotations

import csv
import io
import json
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from tagslut.dj.key_utils import camelot_to_classical, classical_to_camelot
from tagslut.storage.models import DJ_SET_ROLES

_ROLE_PRIORITY = ("groove", "prime", "bridge", "club")
ROLE_ORDER = tuple(role for role in _ROLE_PRIORITY if role in DJ_SET_ROLES) + tuple(
    sorted(DJ_SET_ROLES.difference(_ROLE_PRIORITY))
)
_UNASSIGNED_ROLE = "_unassigned"
EXPORT_COLUMNS = [
    "role",
    "subrole",
    "bpm",
    "key_camelot",
    "canonical_key",
    "artist",
    "title",
    "genre",
    "path",
    "energy",
    "dj_flag",
    "is_dj_material",
]


@dataclass(frozen=True)
class GigPrepTrack:
    role: str
    subrole: str | None
    bpm: float | None
    key_camelot: str | None
    canonical_key: str | None
    artist: str | None
    title: str | None
    genre: str | None
    path: str
    energy: int | None
    dj_flag: int
    is_dj_material: int


def parse_roles_filter(raw_value: str | None) -> list[str]:
    if raw_value is None:
        return list(ROLE_ORDER)

    normalized: list[str] = []
    for item in raw_value.split(","):
        role = str(item).strip().lower()
        if not role:
            continue
        if role not in DJ_SET_ROLES:
            raise ValueError(f"Invalid dj_set_role {role!r}. Allowed: {sorted(DJ_SET_ROLES)}")
        if role not in normalized:
            normalized.append(role)

    if not normalized:
        raise ValueError("At least one dj_set_role must be provided when using --roles.")

    return [role for role in ROLE_ORDER if role in normalized]


def _normalize_role(value: object) -> str | None:
    role = str(value or "").strip().lower()
    if not role:
        return None
    if role not in DJ_SET_ROLES:
        return None
    return role


def _normalize_key_camelot(value: object) -> str | None:
    text = str(value or "").strip().upper()
    if not text:
        return None
    return text if camelot_to_classical(text) is not None else None


def _derive_key_fields(row: sqlite3.Row) -> tuple[str | None, str | None]:
    key_camelot = _normalize_key_camelot(row["key_camelot"])
    canonical_key = str(row["canonical_key"]).strip() if row["canonical_key"] else None

    if key_camelot is None and canonical_key:
        key_camelot = classical_to_camelot(canonical_key)
    if canonical_key is None and key_camelot is not None:
        canonical_key = camelot_to_classical(key_camelot)

    return key_camelot, canonical_key


def _query_candidate_rows(
    conn: sqlite3.Connection,
    *,
    bpm_min: int,
    bpm_max: int,
) -> list[GigPrepTrack]:
    rows = conn.execute(
        """
        SELECT
            path,
            dj_set_role,
            dj_subrole,
            COALESCE(bpm, canonical_bpm) AS export_bpm,
            key_camelot,
            canonical_key,
            canonical_artist AS artist,
            canonical_title AS title,
            COALESCE(canonical_genre, genre) AS export_genre,
            energy,
            COALESCE(dj_flag, 0) AS dj_flag,
            COALESCE(is_dj_material, 0) AS is_dj_material
        FROM files
        WHERE (COALESCE(dj_flag, 0) = 1 OR COALESCE(is_dj_material, 0) = 1)
          AND COALESCE(bpm, canonical_bpm) >= ?
          AND COALESCE(bpm, canonical_bpm) <= ?
        ORDER BY path
        """,
        (int(bpm_min), int(bpm_max)),
    ).fetchall()

    tracks: list[GigPrepTrack] = []
    for row in rows:
        key_camelot, canonical_key = _derive_key_fields(row)
        bpm = float(row["export_bpm"]) if row["export_bpm"] is not None else None
        energy = int(row["energy"]) if row["energy"] is not None else None
        tracks.append(
            GigPrepTrack(
                role=_normalize_role(row["dj_set_role"]) or _UNASSIGNED_ROLE,
                subrole=str(row["dj_subrole"]).strip() if row["dj_subrole"] else None,
                bpm=bpm,
                key_camelot=key_camelot,
                canonical_key=canonical_key,
                artist=str(row["artist"]).strip() if row["artist"] else None,
                title=str(row["title"]).strip() if row["title"] else None,
                genre=str(row["export_genre"]).strip() if row["export_genre"] else None,
                path=str(row["path"]),
                energy=energy,
                dj_flag=int(row["dj_flag"] or 0),
                is_dj_material=int(row["is_dj_material"] or 0),
            )
        )
    return tracks


def _track_sort_key(track: GigPrepTrack) -> tuple[float, str, str, str]:
    bpm = track.bpm if track.bpm is not None else float("inf")
    artist = (track.artist or "").casefold()
    title = (track.title or "").casefold()
    return (bpm, artist, title, track.path.casefold())


def group_tracks_by_role(
    tracks: list[GigPrepTrack],
    *,
    selected_roles: list[str],
) -> dict[str, list[GigPrepTrack]]:
    grouped: dict[str, list[GigPrepTrack]] = {role: [] for role in selected_roles}
    grouped[_UNASSIGNED_ROLE] = []
    selected_role_set = set(selected_roles)

    for track in tracks:
        if track.role == _UNASSIGNED_ROLE:
            grouped[_UNASSIGNED_ROLE].append(track)
            continue
        if track.role in selected_role_set:
            grouped[track.role].append(track)

    for role, role_tracks in grouped.items():
        grouped[role] = sorted(role_tracks, key=_track_sort_key)
    return grouped


def _camelot_sort_key(value: str) -> tuple[int, str]:
    normalized = _normalize_key_camelot(value)
    if normalized is None:
        return (99, str(value))
    return (int(normalized[:-1]), normalized[-1])


def _format_bpm(value: float | None) -> str:
    if value is None:
        return "?"
    if value.is_integer():
        return str(int(value))
    return f"{value:.1f}".rstrip("0").rstrip(".")


def _format_key_summary(tracks: list[GigPrepTrack]) -> str:
    counts = Counter(track.key_camelot for track in tracks if track.key_camelot)
    if not counts:
        return "Keys: none"
    parts = [f"{key}×{counts[key]}" for key in sorted(counts, key=_camelot_sort_key)]
    return "Keys: " + "  ".join(parts)


def _section_header(role: str, count: int) -> str:
    return f"── {role.upper()} ({count} tracks) " + ("─" * 38)


def _format_text_track(track: GigPrepTrack) -> str:
    line = (
        f"{_format_bpm(track.bpm):>3}  "
        f"{(track.key_camelot or '?'): <3} "
        f" {track.artist or '<unknown artist>'} – {track.title or '<unknown title>'}"
    )
    if track.subrole:
        line += f"  [{track.subrole}]"
    if track.genre:
        line += f" [{track.genre}]"
    return line


def render_text_report(
    grouped_tracks: dict[str, list[GigPrepTrack]],
    *,
    gig_date: date,
    venue: str | None,
) -> str:
    lines = [f"Gig Prep: {gig_date.isoformat()}"]
    if venue:
        lines[-1] += f" @ {venue}"
    lines.append("")

    for role in ROLE_ORDER:
        role_tracks = grouped_tracks.get(role) or []
        if not role_tracks:
            continue
        lines.append(_section_header(role, len(role_tracks)))
        lines.append(_format_key_summary(role_tracks))
        for track in role_tracks:
            lines.append(_format_text_track(track))
        lines.append("")

    unassigned_tracks = grouped_tracks.get(_UNASSIGNED_ROLE) or []
    if unassigned_tracks:
        lines.append(_section_header(_UNASSIGNED_ROLE, len(unassigned_tracks)))
        lines.append(_format_key_summary(unassigned_tracks))
        for track in unassigned_tracks:
            lines.append(_format_text_track(track))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _export_row(track: GigPrepTrack) -> dict[str, Any]:
    return {
        "role": track.role,
        "subrole": track.subrole,
        "bpm": track.bpm,
        "key_camelot": track.key_camelot,
        "canonical_key": track.canonical_key,
        "artist": track.artist,
        "title": track.title,
        "genre": track.genre,
        "path": track.path,
        "energy": track.energy,
        "dj_flag": track.dj_flag,
        "is_dj_material": track.is_dj_material,
    }


def flatten_tracks(grouped_tracks: dict[str, list[GigPrepTrack]]) -> list[GigPrepTrack]:
    ordered: list[GigPrepTrack] = []
    for role in ROLE_ORDER:
        ordered.extend(grouped_tracks.get(role) or [])
    ordered.extend(grouped_tracks.get(_UNASSIGNED_ROLE) or [])
    return ordered


def render_csv_report(grouped_tracks: dict[str, list[GigPrepTrack]]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=EXPORT_COLUMNS)
    writer.writeheader()
    for track in flatten_tracks(grouped_tracks):
        writer.writerow(_export_row(track))
    return output.getvalue()


def render_json_report(grouped_tracks: dict[str, list[GigPrepTrack]]) -> str:
    rows = [_export_row(track) for track in flatten_tracks(grouped_tracks)]
    return json.dumps(rows, indent=2) + "\n"


def render_report(
    grouped_tracks: dict[str, list[GigPrepTrack]],
    *,
    gig_date: date,
    venue: str | None,
    output_format: str,
) -> str:
    if output_format == "csv":
        return render_csv_report(grouped_tracks)
    if output_format == "json":
        return render_json_report(grouped_tracks)
    return render_text_report(grouped_tracks, gig_date=gig_date, venue=venue)


def record_gig_run(
    conn: sqlite3.Connection,
    *,
    gig_date: date,
    venue: str | None,
    bpm_min: int,
    bpm_max: int,
    roles_filter: list[str],
    track_count: int,
    output_path: Path | None,
) -> None:
    conn.execute(
        """
        INSERT INTO gigs (
            date,
            venue,
            bpm_min,
            bpm_max,
            roles_filter,
            track_count,
            output_path
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            gig_date.isoformat(),
            venue,
            int(bpm_min),
            int(bpm_max),
            ",".join(roles_filter),
            int(track_count),
            str(output_path) if output_path is not None else None,
        ),
    )


def run_gig_prep(
    conn: sqlite3.Connection,
    *,
    gig_date: date,
    venue: str | None,
    bpm_min: int,
    bpm_max: int,
    roles_filter: list[str],
    output_format: str,
    output_path: Path | None,
) -> str:
    tracks = _query_candidate_rows(conn, bpm_min=bpm_min, bpm_max=bpm_max)
    grouped_tracks = group_tracks_by_role(tracks, selected_roles=roles_filter)
    rendered = render_report(
        grouped_tracks,
        gig_date=gig_date,
        venue=venue,
        output_format=output_format,
    )

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")

    record_gig_run(
        conn,
        gig_date=gig_date,
        venue=venue,
        bpm_min=bpm_min,
        bpm_max=bpm_max,
        roles_filter=roles_filter,
        track_count=len(flatten_tracks(grouped_tracks)),
        output_path=output_path,
    )
    return rendered
