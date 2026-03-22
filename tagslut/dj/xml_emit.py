"""Deterministic Rekordbox XML emit and patch from dj_* DB state.

emit_rekordbox_xml()  — full emit from current active DJ admissions
patch_rekordbox_xml() — targeted re-emit that verifies a prior manifest exists first,
                        reusing stable TrackIDs from dj_track_id_map
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path_to_location(path: str) -> str:
    """Convert a filesystem path to a Rekordbox Location URI."""
    resolved_path = Path(path).resolve()
    # Rekordbox on macOS expects file://localhost/absolute/path
    encoded = quote(str(resolved_path), safe="/:")
    return f"file://localhost{encoded}"


def _build_track_element(
    *,
    track_id: int,
    path: str,
    title: str,
    artist: str,
    album: str | None,
    bpm: float | None,
    key_camelot: str | None,
    bitrate: int | None,
) -> ET.Element:
    attribs: dict[str, str] = {
        "TrackID": str(track_id),
        "Name": title,
        "Artist": artist,
        "Location": _path_to_location(path),
        "Kind": "MP3 File",
        "TotalTime": "0",
    }
    if album:
        attribs["Album"] = album
    if bpm is not None:
        attribs["AverageBpm"] = f"{bpm:.2f}"
    if key_camelot:
        attribs["Tonality"] = key_camelot
    if bitrate is not None:
        attribs["BitRate"] = str(bitrate)
    return ET.Element("TRACK", attribs)


def _build_playlist_node(
    *,
    name: str,
    track_ids: list[int],
) -> ET.Element:
    node = ET.Element(
        "NODE",
        {
            "Name": name,
            "Type": "1",
            "KeyType": "0",
            "Entries": str(len(track_ids)),
        },
    )
    for track_id in track_ids:
        ET.SubElement(node, "TRACK", {"Key": str(track_id)})
    return node


def _fetch_active_admissions(
    conn: sqlite3.Connection,
) -> list[tuple]:
    """Return rows: (da_id, rekordbox_id|None, mp3_path, bitrate,
                     title, artist, album, bpm, key_camelot)"""
    return conn.execute(
        """
        SELECT
            da.id,
            dmap.rekordbox_track_id,
            ma.path,
            ma.bitrate,
            ti.title_norm,
            ti.artist_norm,
            NULL AS album,
            f.bpm,
            f.key_camelot
        FROM dj_admission da
        JOIN mp3_asset      ma   ON ma.id  = da.mp3_asset_id
        JOIN track_identity ti   ON ti.id  = da.identity_id
        LEFT JOIN dj_track_id_map dmap ON dmap.dj_admission_id = da.id
        LEFT JOIN files f ON f.isrc = ti.isrc
        WHERE da.status = 'admitted'
        ORDER BY COALESCE(dmap.rekordbox_track_id, 0) ASC, da.id ASC
        """
    ).fetchall()


def _fetch_playlist_rows(
    conn: sqlite3.Connection,
    playlist_scope: list[int] | None,
) -> list[tuple[int, str, str | None]]:
    if playlist_scope:
        placeholders = ", ".join("?" * len(playlist_scope))
        return conn.execute(
            f"""
            SELECT id, name, sort_key
            FROM dj_playlist
            WHERE id IN ({placeholders})
            ORDER BY COALESCE(sort_key, '') ASC, name ASC, id ASC
            """,
            playlist_scope,
        ).fetchall()
    return conn.execute(
        """
        SELECT id, name, sort_key
        FROM dj_playlist
        ORDER BY COALESCE(sort_key, '') ASC, name ASC, id ASC
        """
    ).fetchall()


def _fetch_playlist_members(
    conn: sqlite3.Connection,
    playlist_id: int,
) -> list[tuple[int, int]]:
    return conn.execute(
        """
        SELECT pt.dj_admission_id, pt.ordinal
        FROM dj_playlist_track pt
        JOIN dj_admission da ON da.id = pt.dj_admission_id
        WHERE pt.playlist_id = ? AND da.status = 'admitted'
        ORDER BY pt.ordinal ASC, pt.dj_admission_id ASC
        """,
        (playlist_id,),
    ).fetchall()


def _build_export_scope(
    conn: sqlite3.Connection,
    *,
    playlist_scope: list[int] | None,
) -> tuple[dict[str, object], str]:
    admissions = conn.execute(
        """
        SELECT
            da.id,
            da.identity_id,
            da.mp3_asset_id,
            COALESCE(dmap.rekordbox_track_id, 0),
            ma.path,
            COALESCE(ma.bitrate, 0),
            COALESCE(ti.title_norm, ''),
            COALESCE(ti.artist_norm, ''),
            COALESCE(f.bpm, 0),
            COALESCE(f.key_camelot, '')
        FROM dj_admission da
        JOIN mp3_asset ma ON ma.id = da.mp3_asset_id
        JOIN track_identity ti ON ti.id = da.identity_id
        LEFT JOIN dj_track_id_map dmap ON dmap.dj_admission_id = da.id
        LEFT JOIN files f ON f.isrc = ti.isrc
        WHERE da.status = 'admitted'
        ORDER BY da.id ASC
        """
    ).fetchall()

    playlist_rows = _fetch_playlist_rows(conn, playlist_scope)
    playlists: list[dict[str, object]] = []
    for playlist_id, name, sort_key in playlist_rows:
        members = _fetch_playlist_members(conn, playlist_id)
        playlists.append(
            {
                "playlist_id": playlist_id,
                "name": name,
                "sort_key": sort_key or "",
                "tracks": [
                    {
                        "dj_admission_id": dj_admission_id,
                        "ordinal": ordinal,
                    }
                    for dj_admission_id, ordinal in members
                ],
            }
        )

    payload: dict[str, object] = {
        "playlist_scope": sorted(playlist_scope) if playlist_scope else None,
        "track_count": len(admissions),
        "playlist_count": len(playlists),
        "admissions": [
            {
                "dj_admission_id": row[0],
                "identity_id": row[1],
                "mp3_asset_id": row[2],
                "rekordbox_track_id": row[3],
                "path": row[4],
                "bitrate": row[5],
                "title": row[6],
                "artist": row[7],
                "bpm": row[8],
                "key_camelot": row[9],
            }
            for row in admissions
        ],
        "playlists": playlists,
    }
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return payload, hashlib.sha256(payload_json.encode("utf-8")).hexdigest()


def _assign_track_ids(
    conn: sqlite3.Connection,
    rows: list[tuple],
) -> dict[int, int]:
    """Assign stable rekordbox_track_id values for all admissions.

    Existing assignments are honoured from dj_track_id_map.
    New assignments are written back to dj_track_id_map.
    Returns da_id -> track_id mapping.
    """
    assigned: dict[int, int] = {}
    next_id = 1

    # First pass: collect existing IDs so next_id starts above them
    for da_id, rekordbox_id, *_ in rows:
        if rekordbox_id is not None:
            assigned[da_id] = rekordbox_id
            next_id = max(next_id, rekordbox_id + 1)

    # Second pass: assign new IDs sequentially
    for da_id, rekordbox_id, *_ in rows:
        if da_id not in assigned:
            assigned[da_id] = next_id
            next_id += 1

    # Persist new assignments
    for da_id, track_id in assigned.items():
        existing = conn.execute(
            "SELECT id FROM dj_track_id_map WHERE dj_admission_id = ?", (da_id,)
        ).fetchone()
        if existing is None:
            conn.execute(
                """
                INSERT INTO dj_track_id_map (dj_admission_id, rekordbox_track_id, assigned_at)
                VALUES (?, ?, ?)
                """,
                (da_id, track_id, _now_iso()),
            )

    return assigned


def _run_pre_emit_validation(conn: sqlite3.Connection) -> None:
    """Raise ValueError if any blocking validation issues are found."""
    from tagslut.dj.admission import validate_dj_library

    report = validate_dj_library(conn)
    blocking = [i for i in report.issues if i.kind in (
        "MISSING_MP3_FILE", "DUPLICATE_MP3_PATH", "MISSING_METADATA"
    )]
    if blocking:
        from tagslut.dj.admission import DjValidationReport
        partial = DjValidationReport(issues=blocking)
        raise ValueError(f"Pre-emit validation failed:\n{partial.summary()}")


def emit_rekordbox_xml(
    conn: sqlite3.Connection,
    *,
    output_path: Path,
    playlist_scope: list[int] | None = None,
    skip_validation: bool = False,
) -> str:
    """Emit a full Rekordbox-compatible XML from dj_* tables.

    Runs pre-emit validation unless skip_validation=True.
    Persists stable TrackIDs in dj_track_id_map.
    Records export manifest in dj_export_state.

    Returns the SHA-256 manifest hash of the written file.
    Raises ValueError if validation fails or no active admissions exist.
    """
    if not skip_validation:
        _run_pre_emit_validation(conn)

    rows = _fetch_active_admissions(conn)
    if not rows:
        raise ValueError(
            "No active DJ admissions found. "
            "Admit tracks with 'tagslut dj admit' or 'tagslut dj backfill' before emitting XML."
        )

    assigned = _assign_track_ids(conn, rows)
    scope_payload, state_hash = _build_export_scope(conn, playlist_scope=playlist_scope)

    # Build XML tree
    root = ET.Element("DJ_PLAYLISTS", {"Version": "1.0.0"})
    ET.SubElement(root, "PRODUCT", {
        "Name": "tagslut",
        "Version": "3.0.0",
        "Company": "tagslut",
    })

    collection = ET.SubElement(root, "COLLECTION", {"Entries": str(len(rows))})
    for da_id, _, path, bitrate, title, artist, album, bpm, key_camelot in rows:
        collection.append(
            _build_track_element(
                track_id=assigned[da_id],
                path=path,
                title=title or "",
                artist=artist or "",
                album=album,
                bpm=bpm,
                key_camelot=key_camelot,
                bitrate=bitrate,
            )
        )

    # Playlists
    playlists_root = ET.SubElement(root, "PLAYLISTS")
    root_node = ET.SubElement(
        playlists_root, "NODE", {"Name": "ROOT", "Type": "0", "Count": "0"}
    )
    pl_rows = _fetch_playlist_rows(conn, playlist_scope)

    for pl_id, pl_name, _sort_key in pl_rows:
        member_rows = _fetch_playlist_members(conn, pl_id)
        track_ids = [assigned[r[0]] for r in member_rows if r[0] in assigned]
        root_node.append(_build_playlist_node(name=pl_name, track_ids=track_ids))

    # Write file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(str(output_path), encoding="UTF-8", xml_declaration=True)

    manifest_hash = hashlib.sha256(output_path.read_bytes()).hexdigest()
    prior = conn.execute(
        """
        SELECT manifest_hash, scope_json
        FROM dj_export_state
        WHERE kind = 'rekordbox_xml'
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    if prior is not None:
        prior_hash, prior_scope_json = prior
        try:
            prior_scope = json.loads(prior_scope_json or "{}")
        except json.JSONDecodeError:
            prior_scope = {}
        if prior_scope.get("state_hash") == state_hash and prior_hash != manifest_hash:
            raise ValueError(
                "Determinism violation: Rekordbox XML changed without a DJ DB state change."
            )

    conn.execute(
        """
        INSERT INTO dj_export_state (kind, output_path, manifest_hash, emitted_at, scope_json)
        VALUES ('rekordbox_xml', ?, ?, ?, ?)
        """,
        (
            str(output_path),
            manifest_hash,
            _now_iso(),
            json.dumps(
                {
                    "track_count": len(rows),
                    "playlist_count": len(pl_rows),
                    "state_hash": state_hash,
                    "playlist_scope": sorted(playlist_scope) if playlist_scope else None,
                    "scope": scope_payload,
                },
                sort_keys=True,
            ),
        ),
    )
    conn.commit()

    return manifest_hash


def patch_rekordbox_xml(
    conn: sqlite3.Connection,
    *,
    output_path: Path,
    prior_export_id: int | None = None,
    playlist_scope: list[int] | None = None,
    skip_validation: bool = False,
) -> str:
    """Re-emit Rekordbox XML, verifying a prior export exists first.

    Requires that at least one prior dj_export_state row of kind='rekordbox_xml'
    exists (or a specific prior_export_id is provided). All existing TrackIDs
    from dj_track_id_map are preserved, so DJ hardware retains cue points.

    Returns the new manifest hash.
    Raises ValueError if no prior export is found or if the prior output file
    has been tampered with.
    """
    # Locate prior export
    if prior_export_id is not None:
        prior = conn.execute(
            "SELECT id, output_path, manifest_hash FROM dj_export_state WHERE id = ? AND kind = 'rekordbox_xml'",
            (prior_export_id,),
        ).fetchone()
        if prior is None:
            raise ValueError(
                f"No rekordbox_xml export found with id={prior_export_id}."
            )
    else:
        prior = conn.execute(
            "SELECT id, output_path, manifest_hash FROM dj_export_state"
            " WHERE kind = 'rekordbox_xml' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if prior is None:
            raise ValueError(
                "No prior Rekordbox XML export found in dj_export_state. "
                "Run 'tagslut dj xml emit' first."
            )

    prior_id, prior_path, prior_hash = prior

    # Verify prior file integrity if it still exists
    prior_file = Path(prior_path)
    if prior_file.exists():
        current_hash = hashlib.sha256(prior_file.read_bytes()).hexdigest()
        if current_hash != prior_hash:
            raise ValueError(
                f"Prior XML at {prior_path} does not match stored manifest hash. "
                "The file may have been manually edited. "
                "Use 'tagslut dj xml emit' for a clean full emit instead."
            )

    # Delegate to emit (TrackIDs are stable because they're in dj_track_id_map)
    return emit_rekordbox_xml(
        conn,
        output_path=output_path,
        playlist_scope=playlist_scope,
        skip_validation=skip_validation,
    )
