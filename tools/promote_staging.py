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

from tagslut.exec.mp3_reconcile import normalize_isrc
from tagslut.utils.final_library_layout import sanitize_component, strip_audio_extension


STAGING_ROOT = Path("/Volumes/MUSIC/staging/SpotiFLACnext")
MASTER_ROOT = Path("/Volumes/MUSIC/MASTER_LIBRARY")
LOGS_ROOT = Path("/Volumes/MUSIC/logs")
DEFAULT_DB_PATH = Path("/Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db")

REPORT_HEADER = [
    "source_path",
    "result",
    "target_path",
    "isrc",
    "identity_id",
    "notes",
]


def _eprint(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _report_path(now: datetime) -> Path:
    return LOGS_ROOT / f"promote_staging_{now.strftime('%Y%m%d_%H%M%S')}.tsv"


def _decode_first(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        for item in value:
            text = _decode_first(item)
            if text:
                return text
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


def _iter_originals(root: Path) -> list[Path]:
    if not root.exists():
        raise FileNotFoundError(f"missing staging root: {root}")
    files: list[Path] = []
    for suffix in (".flac", ".m4a"):
        files.extend([p.resolve() for p in root.rglob(f"*{suffix}") if p.is_file()])
        files.extend([p.resolve() for p in root.rglob(f"*{suffix.upper()}") if p.is_file()])
    return sorted(set(files), key=lambda p: str(p).lower())


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


def _ensure_db_prereqs(conn: sqlite3.Connection) -> None:
    required = {"asset_file", "track_identity"}
    missing = [t for t in sorted(required) if not _table_exists(conn, t)]
    if missing:
        raise RuntimeError(f"DB missing required tables: {', '.join(missing)}")
    cols = _columns(conn, "asset_file")
    if "zone" not in cols:
        raise RuntimeError("asset_file missing required column: zone")


def _identity_row_for_isrc(conn: sqlite3.Connection, isrc: str) -> list[sqlite3.Row]:
    where_merged = _merged_where(conn)
    return conn.execute(
        f"SELECT * FROM track_identity WHERE ({where_merged}) AND isrc = ?",
        (isrc,),
    ).fetchall()


def _row_get(row: sqlite3.Row, key: str, default: Any = "") -> Any:
    if key in row.keys():
        return row[key]
    return default


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


def _derive_master_destination(
    identity_row: sqlite3.Row,
    tags: FileTags,
    *,
    dest_suffix: str,
) -> tuple[Path, bool]:
    if not dest_suffix.startswith("."):
        raise RuntimeError(f"invalid_dest_suffix:{dest_suffix}")

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
    track_filename = sanitize_component(
        f"{int(disc)}-{int(track):02d}. {title_s} - {artist_s}{dest_suffix.lower()}"
    )
    return MASTER_ROOT / artist_s / album_folder / track_filename, year_fallback


def _move_file(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        src.rename(dest)
    except OSError:
        shutil.move(str(src), str(dest))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Promote staging originals (FLAC/M4A) into MASTER_LIBRARY by ISRC and update existing DB rows."
    )
    parser.add_argument("--dry-run", action="store_true", help="Report-only; do not move files or update DB.")
    parser.add_argument(
        "--db",
        type=Path,
        help="SQLite DB path (defaults to $TAGSLUT_DB if set, else built-in default).",
    )
    args = parser.parse_args()

    now = datetime.now()
    out_path = _report_path(now)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    db_path = args.db or Path(os.environ.get("TAGSLUT_DB", "")).expanduser()
    if not str(db_path).strip():
        db_path = DEFAULT_DB_PATH

    originals = _iter_originals(STAGING_ROOT)

    counts = {
        "promoted": 0,
        "no_isrc": 0,
        "isrc_not_found": 0,
        "duplicate_on_disk": 0,
        "missing_required_fields": 0,
        "error": 0,
    }

    conn = _connect_db(db_path, readonly=bool(args.dry_run))
    try:
        _ensure_db_prereqs(conn)
        path_col = _asset_file_path_col(conn)

        with out_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
            writer.writerow(REPORT_HEADER)

            for src in originals:
                src_s = str(src)
                target_s = ""
                isrc = ""
                identity_id: int | None = None
                notes = ""
                year_fallback = False
                result = "error"

                try:
                    tags = _read_file_tags(src)
                    isrc = tags.isrc

                    if not isrc:
                        result = "no_isrc"
                    else:
                        matches = _identity_row_for_isrc(conn, isrc)
                        if len(matches) == 0:
                            result = "isrc_not_found"
                        elif len(matches) > 1:
                            result = "error"
                            notes = f"isrc_multiple_matches={len(matches)}"
                        else:
                            identity_row = matches[0]
                            identity_id = int(identity_row["id"])

                            try:
                                dest_path, year_fallback = _derive_master_destination(
                                    identity_row,
                                    tags,
                                    dest_suffix=src.suffix.lower(),
                                )
                            except MissingRequiredFieldError as exc:
                                result = "missing_required_fields"
                                notes = str(exc)
                                dest_path = None

                            if dest_path is not None:
                                target_s = str(dest_path)

                                if dest_path.exists():
                                    result = "duplicate_on_disk"
                                    notes = notes or "target_exists"
                                else:
                                    db_has_target = conn.execute(
                                        f"SELECT 1 FROM asset_file WHERE {path_col} = ? LIMIT 1",
                                        (target_s,),
                                    ).fetchone()
                                    if db_has_target:
                                        result = "duplicate_on_disk"
                                        notes = notes or "asset_file_has_target"
                                    else:
                                        row = conn.execute(
                                            f"SELECT id FROM asset_file WHERE {path_col} = ? LIMIT 1",
                                            (src_s,),
                                        ).fetchone()
                                        if not row:
                                            result = "error"
                                            notes = "asset_file_missing_for_source"
                                        else:
                                            asset_id = int(row[0])
                                            if not args.dry_run:
                                                try:
                                                    _move_file(src, dest_path)
                                                    conn.execute("BEGIN")
                                                    conn.execute(
                                                        f"UPDATE asset_file SET zone = ?, {path_col} = ? WHERE id = ?",
                                                        ("MASTER_LIBRARY", target_s, asset_id),
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
                                            result = "promoted"
                                            if args.dry_run:
                                                notes = notes or "dry_run"

                except Exception as exc:
                    result = "error"
                    notes = f"{type(exc).__name__}: {exc}"

                if year_fallback:
                    notes = f"{notes}; year_fallback=True" if notes else "year_fallback=True"

                counts[result] = counts.get(result, 0) + 1
                writer.writerow([src_s, result, target_s, isrc, str(identity_id or ""), notes])

    finally:
        conn.close()

    total = len(originals)
    print(f"Total originals: {total}")
    print(
        "Promoted: {p}  |  No ISRC: {n}  |  ISRC not found: {nf}  |  Duplicate: {d}  |  Errors: {e}".format(
            p=counts.get("promoted", 0),
            n=counts.get("no_isrc", 0),
            nf=counts.get("isrc_not_found", 0),
            d=counts.get("duplicate_on_disk", 0),
            e=(counts.get("missing_required_fields", 0) + counts.get("error", 0)),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

