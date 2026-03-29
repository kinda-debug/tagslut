"""Read/write helpers for v3 DJ track profiles."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from tagslut.storage.v3.schema import V3_SCHEMA_NAME, V3_SCHEMA_VERSION_DJ_PROFILE

_ALLOWED_SET_ROLES = {
    "warmup",
    "builder",
    "peak",
    "tool",
    "closer",
    "ambient",
    "break",
    "unknown",
}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except sqlite3.OperationalError:
        return False
    return any(str(row[1]) == column for row in rows)


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS dj_track_profile (
            identity_id INTEGER PRIMARY KEY REFERENCES track_identity(id),
            rating INTEGER NULL CHECK(rating BETWEEN 0 AND 5),
            energy INTEGER NULL CHECK(energy BETWEEN 0 AND 10),
            set_role TEXT NULL CHECK(
                set_role IN ('warmup','builder','peak','tool','closer','ambient','break','unknown')
            ),
            dj_tags_json TEXT NOT NULL DEFAULT '[]',
            notes TEXT NULL,
            last_played_at TEXT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_dj_track_profile_set_role ON dj_track_profile(set_role);
        CREATE INDEX IF NOT EXISTS idx_dj_track_profile_energy ON dj_track_profile(energy);
        CREATE INDEX IF NOT EXISTS idx_dj_track_profile_last_played_at ON dj_track_profile(last_played_at);
        """
    )
    if _table_exists(conn, "schema_migrations"):
        conn.execute(
            """
            INSERT OR IGNORE INTO schema_migrations (schema_name, version, note)
            VALUES (?, ?, ?)
            """,
            (V3_SCHEMA_NAME, V3_SCHEMA_VERSION_DJ_PROFILE, "dj profile support"),
        )
    conn.commit()


def _validate_profile_fields(fields_dict: dict[str, Any]) -> None:
    if "rating" in fields_dict and fields_dict["rating"] is not None:
        rating = int(fields_dict["rating"])
        if rating < 0 or rating > 5:
            raise ValueError("rating must be between 0 and 5")
    if "energy" in fields_dict and fields_dict["energy"] is not None:
        energy = int(fields_dict["energy"])
        if energy < 0 or energy > 10:
            raise ValueError("energy must be between 0 and 10")
    if "set_role" in fields_dict and fields_dict["set_role"] is not None:
        set_role = str(fields_dict["set_role"]).strip().lower()
        if set_role not in _ALLOWED_SET_ROLES:
            raise ValueError(f"set_role must be one of: {', '.join(sorted(_ALLOWED_SET_ROLES))}")
    if "dj_tags_json" in fields_dict and fields_dict["dj_tags_json"] is not None:
        tags = json.loads(str(fields_dict["dj_tags_json"]))
        if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
            raise ValueError("dj_tags_json must encode a JSON array of strings")


def _identity_is_editable(conn: sqlite3.Connection, identity_id: int, *, allow_archived: bool) -> bool:
    if not _table_exists(conn, "track_identity"):
        return False
    where = ["ti.id = ?"]
    if _column_exists(conn, "track_identity", "merged_into_id"):
        where.append("ti.merged_into_id IS NULL")
    params: list[object] = [int(identity_id)]
    if _table_exists(conn, "identity_status") and not allow_archived:
        where.append("COALESCE(ist.status, 'unknown') != 'archived'")
        row = conn.execute(
            f"""
            SELECT 1
            FROM track_identity ti
            LEFT JOIN identity_status ist ON ist.identity_id = ti.id
            WHERE {' AND '.join(where)}
            LIMIT 1
            """,
            tuple(params),
        ).fetchone()
        return row is not None
    row = conn.execute(
        f"SELECT 1 FROM track_identity ti WHERE {' AND '.join(where)} LIMIT 1",
        tuple(params),
    ).fetchone()
    return row is not None


def upsert_profile(
    conn: sqlite3.Connection,
    identity_id: int,
    rating: int | None = None,
    energy: int | None = None,
    set_role: str | None = None,
    notes: str | None = None,
    add_tags: list[str] | None = None,
    remove_tags: list[str] | None = None,
    last_played_at: str | None = None,
    *,
    allow_archived: bool = False,
    fields_dict: dict[str, Any] | None = None,
) -> None:
    ensure_schema(conn)
    if not _identity_is_editable(conn, int(identity_id), allow_archived=allow_archived):
        raise RuntimeError("identity is missing, merged, or archived")

    if fields_dict is None:
        fields_dict = {}
    # Backwards-compatible bridge for existing callers that set fields directly.
    if rating is not None:
        fields_dict["rating"] = rating
    if energy is not None:
        fields_dict["energy"] = energy
    if set_role is not None:
        fields_dict["set_role"] = set_role
    if notes is not None:
        fields_dict["notes"] = notes
    if last_played_at is not None:
        fields_dict["last_played_at"] = last_played_at

    add_tags = add_tags or []
    remove_tags = remove_tags or []
    if add_tags or remove_tags:
        existing = get_profile(conn, int(identity_id))
        existing_tags: list[str] = []
        if existing and existing.get("dj_tags_json"):
            try:
                parsed = json.loads(str(existing["dj_tags_json"]))
                if isinstance(parsed, list):
                    existing_tags = [str(item).strip() for item in parsed if str(item).strip()]
            except json.JSONDecodeError:
                existing_tags = []
        merged = {tag for tag in existing_tags if tag}
        for tag in add_tags:
            clean = str(tag).strip()
            if clean:
                merged.add(clean)
        for tag in remove_tags:
            merged.discard(str(tag).strip())
        fields_dict["dj_tags_json"] = json.dumps(sorted(merged), separators=(",", ":"))

    allowed_fields = {"rating", "energy", "set_role", "dj_tags_json", "notes", "last_played_at"}
    unknown = sorted(set(fields_dict) - allowed_fields)
    if unknown:
        raise ValueError(f"unknown fields: {', '.join(unknown)}")
    _validate_profile_fields(fields_dict)

    conn.execute(
        "INSERT OR IGNORE INTO dj_track_profile (identity_id) VALUES (?)",
        (int(identity_id),),
    )

    assignments: list[str] = []
    params: list[object] = []
    for key in ("rating", "energy", "set_role", "dj_tags_json", "notes", "last_played_at"):
        if key not in fields_dict:
            continue
        value = fields_dict[key]
        if key in {"rating", "energy"} and value is not None:
            value = int(value)
        if key == "set_role" and value is not None:
            value = str(value).strip().lower()
        assignments.append(f"{key} = ?")
        params.append(value)

    if assignments:
        assignments.append("updated_at = CURRENT_TIMESTAMP")
        params.append(int(identity_id))
        conn.execute(
            f"UPDATE dj_track_profile SET {', '.join(assignments)} WHERE identity_id = ?",
            tuple(params),
        )
        conn.commit()


def get_profile(conn: sqlite3.Connection, identity_id: int) -> dict[str, Any] | None:
    if not _table_exists(conn, "dj_track_profile"):
        return None
    row = conn.execute(
        """
        SELECT identity_id, rating, energy, set_role, dj_tags_json, notes, last_played_at, updated_at
        FROM dj_track_profile
        WHERE identity_id = ?
        """,
        (int(identity_id),),
    ).fetchone()
    if row is None:
        return None
    return {
        "identity_id": int(row[0]),
        "rating": row[1],
        "energy": row[2],
        "set_role": row[3],
        "dj_tags_json": row[4],
        "notes": row[5],
        "last_played_at": row[6],
        "updated_at": row[7],
    }


def list_profiles(
    conn: sqlite3.Connection,
    *,
    min_rating: int | None = None,
    set_role: str | None = None,
    set_roles: list[str] | None = None,
    min_energy: int | None = None,
    only_profiled: bool = True,
) -> list[sqlite3.Row]:
    if not _table_exists(conn, "dj_track_profile"):
        return []

    where: list[str] = []
    params: list[object] = []
    if min_rating is not None:
        where.append("rating >= ?")
        params.append(int(min_rating))
    roles = list(set_roles or [])
    if set_role:
        roles.append(set_role)
    clean_roles = [str(role).strip().lower() for role in roles if str(role).strip()]
    if clean_roles:
        placeholders = ",".join("?" for _ in clean_roles)
        where.append(f"set_role IN ({placeholders})")
        params.extend(clean_roles)
    if min_energy is not None:
        where.append("energy >= ?")
        params.append(int(min_energy))
    if only_profiled:
        where.append("1=1")

    where_sql = ""
    if where:
        where_sql = "WHERE " + " AND ".join(where)

    return conn.execute(
        f"""
        SELECT identity_id, rating, energy, set_role, dj_tags_json, notes, last_played_at, updated_at
        FROM dj_track_profile
        {where_sql}
        ORDER BY identity_id ASC
        """,
        tuple(params),
    ).fetchall()
