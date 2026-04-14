#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import shutil
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator

from mutagen.id3 import ID3, ID3NoHeaderError
from mutagen.mp3 import MP3

from tagslut.exec.mp3_reconcile import normalize_isrc


MP3_SOURCES = (
    Path("/Volumes/MUSIC/MP3_LIBRARY/_spotiflac_next"),
    Path("/Volumes/MUSIC/mp3_leftorvers"),
)
MASTER_ROOT = Path("/Volumes/MUSIC/MASTER_LIBRARY")
MP3_ROOT = Path("/Volumes/MUSIC/MP3_LIBRARY")
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


def _id3_text(tags: ID3, key: str) -> str:
    frame = tags.get(key)
    if frame is None:
        return ""
    return _decode_first(getattr(frame, "text", ""))


def _id3_user_text(tags: ID3, desc: str) -> str:
    for frame in tags.getall("TXXX"):
        frame_desc = str(getattr(frame, "desc", "")).strip()
        if frame_desc.upper() == desc.upper():
            return _decode_first(getattr(frame, "text", ""))
    return ""


def _read_mp3_isrc(path: Path) -> str:
    try:
        MP3(str(path))
        try:
            tags = ID3(str(path))
        except ID3NoHeaderError:
            return ""
        isrc_raw = _id3_text(tags, "TSRC")
        if not isrc_raw:
            isrc_raw = _id3_user_text(tags, "ISRC")
        if not isrc_raw:
            isrc_raw = _id3_user_text(tags, "----:com.apple.iTunes:ISRC")
        return normalize_isrc(isrc_raw)
    except Exception as exc:
        _eprint(f"[tag-error] {path}: {exc}")
        return ""


def _iter_mp3_files(root: Path) -> Iterator[Path]:
    if not root.exists():
        _eprint(f"[missing-source] {root}")
        return
    for path in sorted(root.rglob("*.mp3"), key=lambda p: str(p).lower()):
        if path.is_file():
            yield path.resolve()


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(r[1]) for r in rows if r and r[1]}


def _col_exists(conn: sqlite3.Connection, table: str, col: str) -> bool:
    return col in _columns(conn, table)


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


def _active_link_where(conn: sqlite3.Connection) -> str:
    return "al.active = 1" if _col_exists(conn, "asset_link", "active") else "1=1"


def _merged_where(conn: sqlite3.Connection) -> str:
    return "ti.merged_into_id IS NULL" if _col_exists(conn, "track_identity", "merged_into_id") else "1=1"


def _master_where(conn: sqlite3.Connection, path_col: str) -> tuple[str, tuple[object, ...]]:
    if _col_exists(conn, "asset_file", "zone"):
        return "af.zone = 'MASTER_LIBRARY'", tuple()
    like = str(MASTER_ROOT).rstrip("/") + "/%"
    return f"af.{path_col} LIKE ?", (like,)


@dataclass(frozen=True)
class MasterMatch:
    identity_id: int
    asset_id: int
    flac_path: str


def _find_master_flacs(conn: sqlite3.Connection, *, isrc: str) -> list[MasterMatch]:
    path_col = _asset_file_path_col(conn)
    where_active = _active_link_where(conn)
    where_merged = _merged_where(conn)
    where_master, master_params = _master_where(conn, path_col)

    rows = conn.execute(
        f"""
        SELECT ti.id AS identity_id, af.id AS asset_id, af.{path_col} AS p
        FROM track_identity ti
        JOIN asset_link al ON al.identity_id = ti.id
        JOIN asset_file af ON af.id = al.asset_id
        WHERE ({where_merged})
          AND ({where_active})
          AND ti.isrc = ?
          AND ({where_master})
          AND lower(af.{path_col}) LIKE '%.flac'
        ORDER BY af.id ASC
        """,
        (isrc, *master_params),
    ).fetchall()

    out: list[MasterMatch] = []
    for r in rows:
        p = str(r["p"] or "").strip()
        if not p:
            continue
        out.append(MasterMatch(identity_id=int(r["identity_id"]), asset_id=int(r["asset_id"]), flac_path=p))
    return out


def _derive_target_mp3_path(*, flac_path: str) -> Path:
    p = Path(flac_path)
    try:
        rel = p.resolve().relative_to(MASTER_ROOT.resolve())
    except Exception:
        rel = Path(p.name)
    return (MP3_ROOT / rel).with_suffix(".mp3")


def _within_one_percent(a: int, b: int) -> bool:
    if a == b:
        return True
    base = max(a, b)
    if base <= 0:
        return False
    return abs(a - b) / base <= 0.01


def _upsert_mp3_asset(
    conn: sqlite3.Connection,
    *,
    identity_id: int,
    asset_id: int,
    path: Path,
) -> None:
    cols = _columns(conn, "mp3_asset")
    required = {"identity_id", "asset_id", "path"}
    missing = sorted(required - cols)
    if missing:
        raise RuntimeError(f"mp3_asset missing required columns: {', '.join(missing)}")

    insert_cols: list[str] = ["identity_id", "asset_id", "path"]
    insert_vals: list[object] = [int(identity_id), int(asset_id), str(path)]

    update_sets: list[str] = ["identity_id = excluded.identity_id", "asset_id = excluded.asset_id"]

    if "zone" in cols:
        insert_cols.append("zone")
        insert_vals.append("MP3_LIBRARY")
        update_sets.append("zone = excluded.zone")
    if "status" in cols:
        insert_cols.append("status")
        insert_vals.append("verified")
        update_sets.append("status = excluded.status")
    if "source" in cols:
        insert_cols.append("source")
        insert_vals.append("mp3_consolidation")
        update_sets.append("source = excluded.source")
    if "reconciled_at" in cols:
        insert_cols.append("reconciled_at")
        insert_vals.append(datetime.now().isoformat(timespec="seconds"))
        update_sets.append("reconciled_at = excluded.reconciled_at")
    if "updated_at" in cols:
        update_sets.append("updated_at = CURRENT_TIMESTAMP")

    placeholders = ", ".join(["?"] * len(insert_cols))
    conn.execute(
        f"""
        INSERT INTO mp3_asset ({', '.join(insert_cols)})
        VALUES ({placeholders})
        ON CONFLICT(path) DO UPDATE SET {', '.join(update_sets)}
        """,
        tuple(insert_vals),
    )


def _report_path(now: datetime) -> Path:
    return LOGS_ROOT / f"mp3_consolidation_{now.strftime('%Y%m%d_%H%M%S')}.tsv"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Consolidate MP3 leftovers into MP3_LIBRARY using ISRC->MASTER_LIBRARY FLAC.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--dry-run", action="store_true", default=False)
    args = parser.parse_args(argv)

    LOGS_ROOT.mkdir(parents=True, exist_ok=True)
    report_path = _report_path(datetime.now())

    total = 0
    moved = 0
    no_master = 0
    ambiguous = 0
    duplicate = 0
    conflict = 0
    errors = 0

    conn = _connect_db(args.db, readonly=args.dry_run)
    try:
        with report_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
            writer.writerow(REPORT_HEADER)

            for src_root in MP3_SOURCES:
                for src_path in _iter_mp3_files(src_root):
                    total += 1
                    target_path: str = ""
                    isrc = ""
                    identity_id_str = ""
                    notes = ""

                    try:
                        isrc = _read_mp3_isrc(src_path)
                        if not isrc:
                            errors += 1
                            writer.writerow([str(src_path), "error", "", "", "", "missing_isrc"])
                            continue

                        matches = _find_master_flacs(conn, isrc=isrc)
                        if not matches:
                            no_master += 1
                            writer.writerow([str(src_path), "no_master_flac", "", isrc, "", ""])
                            continue

                        unique_flacs = {m.flac_path for m in matches}
                        if len(unique_flacs) != 1:
                            ambiguous += 1
                            writer.writerow(
                                [str(src_path), "ambiguous", "", isrc, "", f"master_flacs={len(unique_flacs)}"]
                            )
                            continue

                        match = matches[0]
                        identity_id_str = str(match.identity_id)
                        target = _derive_target_mp3_path(flac_path=match.flac_path)
                        target_path = str(target)

                        if target.exists():
                            src_size = src_path.stat().st_size
                            dst_size = target.stat().st_size
                            if _within_one_percent(src_size, dst_size):
                                duplicate += 1
                                if not args.dry_run:
                                    src_path.unlink(missing_ok=True)
                                writer.writerow([str(src_path), "duplicate", str(target), isrc, identity_id_str, ""])
                            else:
                                conflict += 1
                                writer.writerow(
                                    [str(src_path), "conflict", str(target), isrc, identity_id_str, "target_exists_size_mismatch"]
                                )
                            continue

                        if args.dry_run:
                            moved += 1
                            writer.writerow([str(src_path), "moved", str(target), isrc, identity_id_str, "dry_run"])
                            continue

                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(src_path), str(target))
                        _upsert_mp3_asset(conn, identity_id=match.identity_id, asset_id=match.asset_id, path=target)
                        conn.commit()

                        moved += 1
                        writer.writerow([str(src_path), "moved", str(target), isrc, identity_id_str, ""])
                    except Exception as exc:
                        errors += 1
                        if not isrc:
                            try:
                                isrc = _read_mp3_isrc(src_path)
                            except Exception:
                                isrc = ""
                        notes = str(exc)
                        writer.writerow([str(src_path), "error", target_path, isrc, identity_id_str, notes])
    finally:
        conn.close()

    print(f"Total MP3s: {total}")
    print(
        f"Moved: {moved}  |  No master FLAC: {no_master}  |  Duplicate removed: {duplicate}  |  Conflicts: {conflict}  |  Errors: {errors}"
    )
    print(f"Output: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

