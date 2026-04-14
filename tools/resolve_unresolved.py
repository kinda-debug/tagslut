#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from mutagen.flac import FLAC
from mutagen.mp4 import MP4
from rapidfuzz import fuzz

from tagslut.exec.mp3_reconcile import (
    normalize_artist_title_pair,
    normalize_isrc,
)
from tagslut.utils.final_library_layout import sanitize_component, strip_audio_extension


UNRESOLVED_DIRS = (
    Path("/Volumes/MUSIC/MASTER_LIBRARY/_UNRESOLVED"),
    Path("/Volumes/MUSIC/MASTER_LIBRARY/_UNRESOLVED_FROM_LIBRARY"),
)
MASTER_ROOT = Path("/Volumes/MUSIC/MASTER_LIBRARY")
LOGS_ROOT = Path("/Volumes/MUSIC/logs")
DEFAULT_DB_PATH = Path("/Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db")

FUZZY_THRESHOLD = 0.92

REPORT_HEADER = [
    "source_path",
    "result",
    "match_method",
    "target_path",
    "identity_id",
    "isrc",
    "notes",
]


def _eprint(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _latest_tsv(logs_root: Path, glob_pat: str) -> Path:
    candidates = sorted(
        logs_root.glob(glob_pat),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(f"Missing prerequisite: {logs_root}/{glob_pat}")
    return candidates[0]


def _report_path(now: datetime) -> Path:
    return LOGS_ROOT / f"resolve_unresolved_{now.strftime('%Y%m%d_%H%M%S')}.tsv"


def _decode_first(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        for item in value:
            s = _decode_first(item)
            if s:
                return s
        return ""
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="strict").strip()
        except UnicodeDecodeError:
            return value.decode("latin-1", errors="ignore").strip()
    return str(value).strip()


def _parse_int_token(value: str) -> int | None:
    text = (value or "").strip()
    if not text:
        return None
    head = text.split("/", 1)[0].strip()
    if not head:
        return None
    try:
        return int(head)
    except ValueError:
        return None


def _extract_year(value: str) -> str:
    text = (value or "").strip()
    if len(text) >= 4 and text[:4].isdigit():
        return text[:4]
    return ""


@dataclass(frozen=True)
class FileTags:
    isrc: str
    artist: str
    title: str
    album: str
    year: str
    disc: int | None
    track: int | None

    @property
    def norm_pair(self) -> tuple[str, str]:
        return normalize_artist_title_pair(self.artist, self.title)


class MissingRequiredFieldError(RuntimeError):
    def __init__(self, field: str) -> None:
        super().__init__(f"missing_required_fields:{field}")
        self.field = field


def _read_flac_tags(path: Path) -> FileTags:
    audio = FLAC(str(path))
    isrc_raw = _decode_first(audio.get("isrc") or audio.get("ISRC"))
    artist = _decode_first(audio.get("artist") or audio.get("ARTIST"))
    title = _decode_first(audio.get("title") or audio.get("TITLE"))
    album = _decode_first(audio.get("album") or audio.get("ALBUM"))
    date_raw = _decode_first(audio.get("date") or audio.get("DATE") or audio.get("year") or audio.get("YEAR"))
    disc_raw = _decode_first(audio.get("discnumber") or audio.get("DISCNUMBER") or audio.get("disc") or audio.get("DISC"))
    track_raw = _decode_first(audio.get("tracknumber") or audio.get("TRACKNUMBER") or audio.get("track") or audio.get("TRACK"))
    return FileTags(
        isrc=normalize_isrc(isrc_raw),
        artist=artist,
        title=title,
        album=album,
        year=_extract_year(date_raw),
        disc=_parse_int_token(disc_raw),
        track=_parse_int_token(track_raw),
    )


def _mp4_int_pair(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, list) and value:
        return _mp4_int_pair(value[0])
    if isinstance(value, tuple) and value:
        try:
            return int(value[0])
        except Exception:
            return None
    return None


def _read_m4a_tags(path: Path) -> FileTags:
    audio = MP4(str(path))
    tags: dict[str, Any] = getattr(audio, "tags", None) or {}
    isrc_raw = _decode_first(
        tags.get("----:com.apple.iTunes:ISRC") or tags.get("----:com.apple.iTunes:TSRC")
    )
    artist = _decode_first(tags.get("\xa9ART"))
    title = _decode_first(tags.get("\xa9nam"))
    album = _decode_first(tags.get("\xa9alb"))
    date_raw = _decode_first(tags.get("\xa9day"))
    disc = _mp4_int_pair(tags.get("disk"))
    track = _mp4_int_pair(tags.get("trkn"))
    return FileTags(
        isrc=normalize_isrc(isrc_raw),
        artist=artist,
        title=title,
        album=album,
        year=_extract_year(date_raw),
        disc=disc,
        track=track,
    )


def _read_file_tags(path: Path) -> FileTags:
    suffix = path.suffix.lower()
    if suffix == ".flac":
        return _read_flac_tags(path)
    if suffix == ".m4a":
        return _read_m4a_tags(path)
    raise RuntimeError(f"unsupported_extension:{suffix}")


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (name,)
    ).fetchone()
    return row is not None


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    out: set[str] = set()
    for r in rows:
        try:
            out.add(str(r["name"]))
        except Exception:
            out.add(str(r[1]))
    return out


def _col_exists(conn: sqlite3.Connection, table: str, col: str) -> bool:
    try:
        return col in _columns(conn, table)
    except sqlite3.OperationalError:
        return False


def _merged_where(conn: sqlite3.Connection) -> str:
    return "merged_into_id IS NULL" if _col_exists(conn, "track_identity", "merged_into_id") else "1=1"


def _connect_db(db_path: Path, *, readonly: bool) -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")
    if readonly:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _asset_file_path_col(conn: sqlite3.Connection) -> str:
    cols = _columns(conn, "asset_file")
    if "path" in cols:
        return "path"
    if "file_path" in cols:
        return "file_path"
    raise RuntimeError("asset_file missing path column (expected path or file_path)")


def _identity_row_for_isrc(conn: sqlite3.Connection, isrc: str) -> list[sqlite3.Row]:
    where_merged = _merged_where(conn)
    return conn.execute(
        f"SELECT * FROM track_identity WHERE ({where_merged}) AND isrc = ?",
        (isrc,),
    ).fetchall()


def _load_fuzzy_pool(conn: sqlite3.Connection) -> list[tuple[int, str, str]]:
    where_merged = _merged_where(conn)
    rows = conn.execute(
        f"""
        SELECT id, COALESCE(artist_norm, ''), COALESCE(title_norm, '')
        FROM track_identity
        WHERE ({where_merged})
          AND COALESCE(TRIM(artist_norm), '') != ''
          AND COALESCE(TRIM(title_norm), '') != ''
        """,
    ).fetchall()
    out: list[tuple[int, str, str]] = []
    for r in rows:
        out.append((int(r[0]), str(r[1]), str(r[2])))
    return out


def _best_fuzzy_match(
    pool: Iterable[tuple[int, str, str]],
    *,
    artist_norm: str,
    title_norm: str,
) -> tuple[int | None, float, bool]:
    best_id: int | None = None
    best_score = 0.0
    best_tied = False

    if not artist_norm or not title_norm:
        return None, 0.0, False

    for identity_id, a_norm, t_norm in pool:
        if not a_norm or not t_norm:
            continue
        a_score = fuzz.ratio(artist_norm, a_norm) / 100.0
        t_score = fuzz.ratio(title_norm, t_norm) / 100.0
        score = (a_score + t_score) / 2.0
        if score > best_score + 1e-9:
            best_id = identity_id
            best_score = score
            best_tied = False
        elif abs(score - best_score) <= 1e-9 and score >= FUZZY_THRESHOLD:
            best_tied = True

    return best_id, best_score, best_tied


def _first_nonempty(row: sqlite3.Row, keys: list[str]) -> str:
    for k in keys:
        if k not in row.keys():
            continue
        v = row[k]
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return ""


def _first_int(row: sqlite3.Row, keys: list[str]) -> int | None:
    for k in keys:
        if k not in row.keys():
            continue
        v = row[k]
        if v is None:
            continue
        try:
            return int(str(v).strip())
        except Exception:
            continue
    return None


def _payload_int(payload_json: str, keys: list[str]) -> int | None:
    if not payload_json.strip():
        return None
    try:
        payload = json.loads(payload_json)
    except Exception:
        return None

    def _walk(obj: Any) -> Iterable[Any]:
        yield obj
        if isinstance(obj, dict):
            for v in obj.values():
                yield from _walk(v)
        elif isinstance(obj, list):
            for v in obj:
                yield from _walk(v)

    for obj in _walk(payload):
        if not isinstance(obj, dict):
            continue
        for k in keys:
            if k not in obj:
                continue
            try:
                return int(str(obj[k]).strip())
            except Exception:
                continue
    return None


def _payload_str(payload_json: str, keys: list[str]) -> str:
    if not payload_json.strip():
        return ""
    try:
        payload = json.loads(payload_json)
    except Exception:
        return ""

    def _walk(obj: Any) -> Iterable[Any]:
        yield obj
        if isinstance(obj, dict):
            for v in obj.values():
                yield from _walk(v)
        elif isinstance(obj, list):
            for v in obj:
                yield from _walk(v)

    for obj in _walk(payload):
        if not isinstance(obj, dict):
            continue
        for k in keys:
            if k not in obj:
                continue
            val = obj[k]
            if val is None:
                continue
            s = str(val).strip()
            if s:
                return s
    return ""


def _row_get(row: sqlite3.Row, key: str, default: Any = "") -> Any:
    if key in row.keys():
        return row[key]
    return default


def _active_link_where(conn: sqlite3.Connection) -> str:
    return "al.active = 1" if _col_exists(conn, "asset_link", "active") else "1=1"


def _master_path_prefix_where(conn: sqlite3.Connection, path_col: str) -> str:
    if _col_exists(conn, "asset_file", "zone"):
        return "af.zone = 'MASTER_LIBRARY'"
    return f"af.{path_col} LIKE ?"


def _hint_master_path_for_identity(conn: sqlite3.Connection, identity_id: int) -> str | None:
    path_col = _asset_file_path_col(conn)
    where_active = _active_link_where(conn)
    where_master = _master_path_prefix_where(conn, path_col)
    params: list[object] = [identity_id]
    like_param: str | None = None
    if where_master.endswith("?"):
        like_param = str(MASTER_ROOT).rstrip("/") + "/%"
        params.append(like_param)
    row = conn.execute(
        f"""
        SELECT af.{path_col} AS p
        FROM asset_link al
        JOIN asset_file af ON af.id = al.asset_id
        WHERE ({where_active})
          AND al.identity_id = ?
          AND ({where_master})
        ORDER BY af.id ASC
        LIMIT 1
        """,
        tuple(params),
    ).fetchone()
    if not row:
        return None
    return str(row[0] or "").strip() or None


def _derive_master_destination_from_master_hint(master_asset_path: str, tags: FileTags) -> Path:
    """
    Use an existing MASTER_LIBRARY asset path linked to this identity to infer:
    - artist folder name
    - album folder name (and year)
    """
    p = Path(master_asset_path)
    try:
        rel = p.resolve().relative_to(MASTER_ROOT)
    except Exception as exc:
        raise RuntimeError(f"master_hint_not_under_master_root: {exc}") from exc

    if len(rel.parts) < 3:
        raise RuntimeError("master_hint_too_shallow")

    artist_folder = rel.parts[0]
    album_folder = rel.parts[1]
    if not album_folder.startswith("(") or len(album_folder) < 6 or not album_folder[1:5].isdigit():
        raise RuntimeError("master_hint_album_folder_unparseable")
    year = album_folder[1:5]

    disc = tags.disc if tags.disc is not None else 1
    track = tags.track
    if track is None:
        raise RuntimeError("file tags missing required fields: track")

    artist_for_filename = tags.artist.strip() or artist_folder
    title_for_filename = tags.title.strip()
    if not title_for_filename:
        raise RuntimeError("file tags missing required fields: title")

    artist_s = sanitize_component(strip_audio_extension(artist_for_filename))
    title_s = sanitize_component(strip_audio_extension(title_for_filename))
    track_filename = sanitize_component(f"{int(disc)}-{int(track):02d}. {title_s} - {artist_s}.flac")
    return MASTER_ROOT / artist_folder / album_folder.replace(album_folder[1:5], year) / track_filename


def _derive_master_destination(identity_row: sqlite3.Row, tags: FileTags) -> tuple[Path, str, bool]:
    artist = (_first_nonempty(identity_row, ["canonical_artist", "artist_norm"]) or "").strip()
    if not artist:
        artist = (tags.artist or "").strip()
    if not artist:
        raise MissingRequiredFieldError("artist")

    payload_json = str(_row_get(identity_row, "canonical_payload_json") or "")

    year_fallback = False
    year_int = _first_int(identity_row, ["canonical_year"])
    year = str(year_int).strip() if year_int else ""
    if not year:
        year = _extract_year(_first_nonempty(identity_row, ["canonical_release_date"]))
    if not year:
        year = _payload_str(payload_json, ["year", "release_year", "releaseYear"])[:4].strip()
    if not year:
        year = (tags.year or "").strip()
    if not year:
        year = "0000"
        year_fallback = True

    album = (_first_nonempty(identity_row, ["canonical_album", "album_norm"]) or "").strip()
    if not album:
        album = (tags.album or "").strip()
    if not album:
        raise MissingRequiredFieldError("album")

    disc = tags.disc if tags.disc is not None else 1
    track = tags.track
    if track is None:
        raise MissingRequiredFieldError("track")

    title = (_first_nonempty(identity_row, ["canonical_title", "title_norm"]) or "").strip()
    if not title:
        title = (tags.title or "").strip()
    if not title:
        raise MissingRequiredFieldError("title")

    artist_s = sanitize_component(strip_audio_extension(artist))
    title_s = sanitize_component(strip_audio_extension(title))
    album_s = sanitize_component(strip_audio_extension(album))

    album_folder = sanitize_component(f"({year}) {album_s}")
    track_filename = sanitize_component(f"{int(disc)}-{int(track):02d}. {title_s} - {artist_s}.flac")
    return MASTER_ROOT / artist_s / album_folder / track_filename, year, year_fallback


def _derive_master_destination_from_file_tags(tags: FileTags) -> Path:
    missing: list[str] = []
    if not tags.artist.strip():
        missing.append("artist")
    if not tags.title.strip():
        missing.append("title")
    if not tags.album.strip():
        missing.append("album")
    if not tags.year.strip():
        missing.append("year")
    disc = tags.disc if tags.disc is not None else 1
    track = tags.track
    if track is None:
        missing.append("track")
    if missing:
        raise RuntimeError(f"file tags missing required fields: {', '.join(missing)}")

    artist_s = sanitize_component(strip_audio_extension(tags.artist))
    title_s = sanitize_component(strip_audio_extension(tags.title))
    album_s = sanitize_component(strip_audio_extension(tags.album))
    album_folder = sanitize_component(f"({tags.year}) {album_s}")
    track_filename = sanitize_component(f"{int(disc)}-{int(track):02d}. {title_s} - {artist_s}.flac")
    return MASTER_ROOT / artist_s / album_folder / track_filename


def _move_file(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        src.rename(dest)
    except OSError:
        shutil.move(str(src), str(dest))


def _ensure_db_prereqs(conn: sqlite3.Connection) -> None:
    required = {"asset_file", "track_identity", "asset_link", "provenance_event"}
    missing = [t for t in sorted(required) if not _table_exists(conn, t)]
    if missing:
        raise RuntimeError(f"DB missing required tables: {', '.join(missing)}")


def _upsert_asset_file(
    conn: sqlite3.Connection,
    *,
    src_path: str,
    dest_path: str,
    zone: str,
    library: str,
) -> int:
    path_col = _asset_file_path_col(conn)
    cols = _columns(conn, "asset_file")

    existing = conn.execute(
        f"SELECT id FROM asset_file WHERE {path_col} = ? LIMIT 1",
        (src_path,),
    ).fetchone()

    if existing is not None:
        asset_id = int(existing[0])
        updates: list[str] = [f"{path_col} = ?"]
        params: list[object] = [dest_path]
        if "zone" in cols:
            updates.append("zone = ?")
            params.append(zone)
        if "library" in cols:
            updates.append("library = ?")
            params.append(library)
        if "last_seen_at" in cols:
            updates.append("last_seen_at = CURRENT_TIMESTAMP")
        params.append(asset_id)
        conn.execute(
            f"UPDATE asset_file SET {', '.join(updates)} WHERE id = ?",
            tuple(params),
        )
        return asset_id

    insert_cols: list[str] = [path_col]
    insert_vals: list[object] = [dest_path]
    if "zone" in cols:
        insert_cols.append("zone")
        insert_vals.append(zone)
    if "library" in cols:
        insert_cols.append("library")
        insert_vals.append(library)
    if "first_seen_at" in cols:
        insert_cols.append("first_seen_at")
        insert_vals.append("CURRENT_TIMESTAMP")
    if "last_seen_at" in cols:
        insert_cols.append("last_seen_at")
        insert_vals.append("CURRENT_TIMESTAMP")

    placeholders: list[str] = []
    params: list[object] = []
    for v in insert_vals:
        if isinstance(v, str) and v == "CURRENT_TIMESTAMP":
            placeholders.append(v)
        else:
            placeholders.append("?")
            params.append(v)

    conn.execute(
        f"INSERT INTO asset_file ({', '.join(insert_cols)}) VALUES ({', '.join(placeholders)})",
        tuple(params),
    )
    row = conn.execute(
        f"SELECT id FROM asset_file WHERE {path_col} = ? LIMIT 1",
        (dest_path,),
    ).fetchone()
    if row is None:
        raise RuntimeError("failed to resolve asset_file id after insert")
    return int(row[0])


def _upsert_asset_link(conn: sqlite3.Connection, *, asset_id: int, identity_id: int) -> None:
    cols = _columns(conn, "asset_link")

    set_bits: list[str] = ["identity_id = ?"]
    params: list[object] = [identity_id]
    if "link_source" in cols:
        set_bits.append("link_source = ?")
        params.append("resolve_unresolved")
    if "confidence" in cols:
        params.append(1.0)
        set_bits.append("confidence = ?")
    if "active" in cols:
        params.append(1)
        set_bits.append("active = ?")
    if "updated_at" in cols:
        set_bits.append("updated_at = CURRENT_TIMESTAMP")

    params.append(asset_id)
    updated = conn.execute(
        f"UPDATE asset_link SET {', '.join(set_bits)} WHERE asset_id = ?",
        tuple(params),
    ).rowcount
    if updated and updated > 0:
        return

    insert_cols = ["asset_id", "identity_id"]
    insert_vals: list[object] = [asset_id, identity_id]
    if "confidence" in cols:
        insert_cols.append("confidence")
        insert_vals.append(1.0)
    if "link_source" in cols:
        insert_cols.append("link_source")
        insert_vals.append("resolve_unresolved")
    if "active" in cols:
        insert_cols.append("active")
        insert_vals.append(1)

    placeholders = ",".join("?" for _ in insert_vals)
    conn.execute(
        f"INSERT OR IGNORE INTO asset_link ({', '.join(insert_cols)}) VALUES ({placeholders})",
        tuple(insert_vals),
    )


def _insert_provenance_event(
    conn: sqlite3.Connection,
    *,
    asset_id: int,
    identity_id: int,
    source_path: str,
    dest_path: str,
) -> None:
    cols = _columns(conn, "provenance_event")
    insert_cols: list[str] = []
    insert_vals: list[object] = []

    if "event_type" in cols:
        insert_cols.append("event_type")
        insert_vals.append("resolve_unresolved")
    if "asset_id" in cols:
        insert_cols.append("asset_id")
        insert_vals.append(asset_id)
    if "identity_id" in cols:
        insert_cols.append("identity_id")
        insert_vals.append(identity_id)
    if "source_path" in cols:
        insert_cols.append("source_path")
        insert_vals.append(source_path)
    if "dest_path" in cols:
        insert_cols.append("dest_path")
        insert_vals.append(dest_path)
    if "status" in cols:
        insert_cols.append("status")
        insert_vals.append("moved")
    if "ingestion_method" in cols:
        insert_cols.append("ingestion_method")
        insert_vals.append("resolve_unresolved")
    if "details_json" in cols:
        insert_cols.append("details_json")
        insert_vals.append(json.dumps({"ingestion_method": "resolve_unresolved"}))

    if not insert_cols:
        return

    placeholders = ",".join("?" for _ in insert_vals)
    conn.execute(
        f"INSERT INTO provenance_event ({', '.join(insert_cols)}) VALUES ({placeholders})",
        tuple(insert_vals),
    )


def _iter_unresolved_flacs() -> list[Path]:
    files: list[Path] = []
    for root in UNRESOLVED_DIRS:
        if not root.exists():
            continue
        files.extend([p for p in root.rglob("*.flac") if p.is_file()])
    return sorted({p.resolve() for p in files}, key=lambda p: str(p).lower())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve MASTER_LIBRARY _UNRESOLVED FLACs by ISRC (and report fuzzy candidates)."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path(os.environ.get("TAGSLUT_DB") or DEFAULT_DB_PATH),
        help="SQLite DB path (default: $TAGSLUT_DB or built-in default)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print/report actions without moving files or writing to DB",
    )
    args = parser.parse_args()

    try:
        inventory_tsv = _latest_tsv(LOGS_ROOT, "inventory_*.tsv")
        intake_tsv = _latest_tsv(LOGS_ROOT, "intake_sweep_*.tsv")
    except Exception as exc:
        _eprint(str(exc))
        return 2

    now = datetime.now()
    out_path = _report_path(now)
    LOGS_ROOT.mkdir(parents=True, exist_ok=True)

    conn = _connect_db(args.db, readonly=args.dry_run)
    try:
        _ensure_db_prereqs(conn)
        fuzzy_pool = _load_fuzzy_pool(conn)

        files = _iter_unresolved_flacs()
        total = len(files)

        counts = {
            "moved": 0,
            "fuzzy_match_pending_review": 0,
            "unmatched": 0,
            "ambiguous": 0,
            "duplicate_on_disk": 0,
            "error": 0,
        }

        with out_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
            writer.writerow(REPORT_HEADER)

            for src in files:
                src_s = str(src)
                target_s = ""
                match_method = ""
                identity_id: int | None = None
                isrc = ""
                notes = ""
                year_fallback = False
                result = "error"

                try:
                    tags = _read_file_tags(src)
                    isrc = tags.isrc

                    if isrc:
                        match_method = "isrc"
                        matches = _identity_row_for_isrc(conn, isrc)
                        if len(matches) == 1:
                            identity_row = matches[0]
                            identity_id = int(identity_row["id"])

                            dest_path: Path | None = None
                            try:
                                dest_path, _year, year_fallback = _derive_master_destination(identity_row, tags)
                            except MissingRequiredFieldError as exc:
                                hint = _hint_master_path_for_identity(conn, identity_id)
                                if hint:
                                    dest_path = _derive_master_destination_from_master_hint(hint, tags)
                                    notes = f"dest_from_master_hint ({exc})"
                                else:
                                    result = "unmatched"
                                    notes = str(exc)
                                    dest_path = None
                            except Exception as exc:
                                hint = _hint_master_path_for_identity(conn, identity_id)
                                if hint:
                                    dest_path = _derive_master_destination_from_master_hint(hint, tags)
                                    notes = f"dest_from_master_hint (identity_error: {type(exc).__name__})"
                                else:
                                    result = "unmatched"
                                    notes = f"matched_isrc_but_no_destination: {type(exc).__name__}: {exc}"
                                    dest_path = None
                            if dest_path is not None and result != "unmatched":
                                target_s = str(dest_path)

                                if dest_path.exists():
                                    result = "duplicate_on_disk"
                                    notes = notes or "target_exists"
                                else:
                                    path_col = _asset_file_path_col(conn)
                                    db_has_target = conn.execute(
                                        f"SELECT 1 FROM asset_file WHERE {path_col} = ? LIMIT 1",
                                        (target_s,),
                                    ).fetchone()
                                    if db_has_target:
                                        result = "duplicate_on_disk"
                                        notes = notes or "asset_file_has_target"
                                    else:
                                        if not args.dry_run:
                                            _move_file(src, dest_path)
                                            try:
                                                conn.execute("BEGIN")
                                                asset_id = _upsert_asset_file(
                                                    conn,
                                                    src_path=src_s,
                                                    dest_path=target_s,
                                                    zone="MASTER_LIBRARY",
                                                    library="master",
                                                )
                                                _upsert_asset_link(conn, asset_id=asset_id, identity_id=identity_id)
                                                _insert_provenance_event(
                                                    conn,
                                                    asset_id=asset_id,
                                                    identity_id=identity_id,
                                                    source_path=src_s,
                                                    dest_path=target_s,
                                                )
                                                conn.commit()
                                            except Exception:
                                                conn.rollback()
                                                try:
                                                    if dest_path.exists() and not src.exists():
                                                        _move_file(dest_path, src)
                                                except Exception:
                                                    pass
                                                raise
                                        result = "moved"
                                        if args.dry_run:
                                            notes = "dry_run; " + notes if notes else "dry_run"
                        elif len(matches) > 1:
                            result = "ambiguous"
                            identity_id = None
                            notes = f"isrc_multiple_matches={len(matches)}"
                        else:
                            result = "unmatched"
                            notes = "isrc_not_found"
                    else:
                        match_method = "fuzzy"
                        a_norm, t_norm = tags.norm_pair
                        best_id, best_score, best_tied = _best_fuzzy_match(
                            fuzzy_pool, artist_norm=a_norm, title_norm=t_norm
                        )
                        if best_id is not None and best_score >= FUZZY_THRESHOLD and not best_tied:
                            result = "fuzzy_match_pending_review"
                            identity_id = int(best_id)
                            notes = f"score={best_score:.3f}"
                        elif best_tied and best_score >= FUZZY_THRESHOLD:
                            result = "ambiguous"
                            notes = f"fuzzy_tied_best score={best_score:.3f}"
                        else:
                            result = "unmatched"
                            notes = f"no_isrc; fuzzy_best={best_score:.3f}"

                except Exception as exc:
                    result = "error"
                    notes = f"{type(exc).__name__}: {exc}"

                if result in counts:
                    counts[result] += 1
                else:
                    counts["error"] += 1

                if year_fallback:
                    notes = f"{notes}; year_fallback=True" if notes else "year_fallback=True"

                writer.writerow(
                    [
                        src_s,
                        result,
                        match_method,
                        target_s,
                        str(identity_id or ""),
                        isrc,
                        notes,
                    ]
                )

        skipped = counts["ambiguous"] + counts["duplicate_on_disk"]
        _eprint(f"Using inventory TSV: {inventory_tsv}")
        _eprint(f"Using intake sweep TSV: {intake_tsv}")
        print(f"Total files: {total}")
        print(
            "Moved: {moved}  |  Fuzzy pending review: {fuzzy_match_pending_review}  |  "
            "Unmatched: {unmatched}  |  Skipped: {skipped}  |  Errors: {error}".format(
                moved=counts["moved"],
                fuzzy_match_pending_review=counts["fuzzy_match_pending_review"],
                unmatched=counts["unmatched"],
                skipped=skipped,
                error=counts["error"],
            )
        )
        print(f"Output: {out_path}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
