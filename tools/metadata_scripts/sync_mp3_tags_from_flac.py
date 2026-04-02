#!/usr/bin/env python3
"""
Sync DJ-relevant and core tags from master FLAC library to MP3 files.

Matching:
  - direct `flac_path` from a manifest/report row
  - exact `files.dj_pool_path` match when --match-source includes db_dj_pool_path
  - normalized title + artist, preferring exact album and close duration, when
    --match-source includes master

Default is dry-run; use --execute to write tags.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from mutagen.flac import FLAC
from mutagen.id3 import ID3, ID3NoHeaderError, TALB, TBPM, TCON, TDRC, TKEY, TIT2, TPE1, TPE2, TRCK, TSRC, TXXX

from tagslut.exec.dj_library_normalize import (
    load_db_dj_pool_lookup,
    load_master_index,
    pick_best_master_match,
    read_audio_metadata,
)
from tagslut.storage.v3 import resolve_dj_tag_snapshot_for_path
from tagslut.utils.db import DbResolutionError, resolve_cli_env_db_path

DEFAULT_JOBS = min(16, max(1, os.cpu_count() or 4))


@dataclass(frozen=True)
class Mp3WorkItem:
    path: Path
    manifest_flac_path: Path | None
    report_status: str
    report_reason: str


def _norm(s: str) -> str:
    return " ".join((s or "").strip().casefold().split())


def _get_id3(path: Path) -> Optional[ID3]:
    try:
        return ID3(path)
    except ID3NoHeaderError:
        return ID3()
    except Exception:
        return None


def _first_text_id3(tags: ID3, key: str) -> str:
    if key in tags:
        val = tags.get(key)
        if hasattr(val, "text") and val.text:
            return str(val.text[0]).strip()
    return ""


def _first_text_flac(tags: dict[str, list[str]], key: str) -> str:
    vals = tags.get(key.lower())
    if vals:
        return str(vals[0]).strip()
    return ""


def _resolve_report_path(value: str, report_path: Path) -> Path:
    candidate = Path(value).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (report_path.parent / candidate).resolve()


def _read_mp3_work_items(report: Optional[Path], root: Path, statuses: set[str]) -> list[Mp3WorkItem]:
    if report:
        items: list[Mp3WorkItem] = []
        with report.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                path_text = str(row.get("path") or row.get("source_path") or "").strip()
                if not path_text:
                    continue
                flac_text = str(row.get("flac_path") or row.get("db_path") or "").strip()
                status_text = str(row.get("status") or "").strip()
                reason_text = str(row.get("reason") or "").strip()
                if flac_text:
                    include = True
                else:
                    include = not statuses or status_text in statuses or reason_text in statuses
                if not include:
                    continue
                items.append(
                    Mp3WorkItem(
                        path=_resolve_report_path(path_text, report),
                        manifest_flac_path=_resolve_report_path(flac_text, report) if flac_text else None,
                        report_status=status_text,
                        report_reason=reason_text,
                    )
                )
        return items

    return [Mp3WorkItem(path=path, manifest_flac_path=None, report_status="", report_reason="") for path in root.rglob("*.mp3")]


def _backup_frames(tags: ID3) -> dict[str, str]:
    return {
        "TIT2": _first_text_id3(tags, "TIT2"),
        "TPE1": _first_text_id3(tags, "TPE1"),
        "TPE2": _first_text_id3(tags, "TPE2"),
        "TALB": _first_text_id3(tags, "TALB"),
        "TRCK": _first_text_id3(tags, "TRCK"),
        "TDRC": _first_text_id3(tags, "TDRC"),
        "TBPM": _first_text_id3(tags, "TBPM"),
        "TKEY": _first_text_id3(tags, "TKEY"),
        "TXXX:INITIALKEY": _first_text_id3(tags, "TXXX:INITIALKEY"),
        "TCON": _first_text_id3(tags, "TCON"),
        "TXXX:LABEL": _first_text_id3(tags, "TXXX:LABEL"),
        "TXXX:ENERGY": _first_text_id3(tags, "TXXX:ENERGY"),
        "TSRC": _first_text_id3(tags, "TSRC"),
    }


def _set_if_missing(tags: ID3, frame_id: str, frame: object) -> None:
    if frame_id in tags and _first_text_id3(tags, frame_id):
        return
    tags[frame_id] = frame


def _apply_selected_tags_from_flac(
    id3: ID3,
    flac_tags: dict[str, list[str]],
    *,
    copy_core_tags: bool,
    copy_dj_tags: bool,
) -> None:
    if copy_core_tags:
        title = _first_text_flac(flac_tags, "title")
        artist = _first_text_flac(flac_tags, "artist")
        album = _first_text_flac(flac_tags, "album")
        albumartist = _first_text_flac(flac_tags, "albumartist")
        tracknumber = _first_text_flac(flac_tags, "tracknumber") or _first_text_flac(flac_tags, "track")
        date = (
            _first_text_flac(flac_tags, "date")
            or _first_text_flac(flac_tags, "originaldate")
            or _first_text_flac(flac_tags, "year")
        )

        if title:
            _set_if_missing(id3, "TIT2", TIT2(encoding=3, text=title))
        if artist:
            _set_if_missing(id3, "TPE1", TPE1(encoding=3, text=artist))
        if album:
            _set_if_missing(id3, "TALB", TALB(encoding=3, text=album))
        if albumartist:
            _set_if_missing(id3, "TPE2", TPE2(encoding=3, text=albumartist))
        if tracknumber:
            _set_if_missing(id3, "TRCK", TRCK(encoding=3, text=tracknumber))
        if date:
            _set_if_missing(id3, "TDRC", TDRC(encoding=3, text=date))

    if copy_dj_tags:
        bpm = _first_text_flac(flac_tags, "bpm") or _first_text_flac(flac_tags, "TBPM")
        key = (
            _first_text_flac(flac_tags, "initialkey")
            or _first_text_flac(flac_tags, "INITIALKEY")
            or _first_text_flac(flac_tags, "key")
            or _first_text_flac(flac_tags, "KEY")
            or _first_text_flac(flac_tags, "key_camelot")
            or _first_text_flac(flac_tags, "KEY_CAMELOT")
        )
        genre = _first_text_flac(flac_tags, "genre") or _first_text_flac(flac_tags, "GENRE")
        label = _first_text_flac(flac_tags, "label") or _first_text_flac(flac_tags, "LABEL")
        energy = _first_text_flac(flac_tags, "energy") or _first_text_flac(flac_tags, "ENERGY")
        isrc = _first_text_flac(flac_tags, "isrc") or _first_text_flac(flac_tags, "ISRC")

        if bpm:
            id3["TBPM"] = TBPM(encoding=3, text=bpm)
        if key:
            id3["TKEY"] = TKEY(encoding=3, text=key)
            id3["TXXX:INITIALKEY"] = TXXX(encoding=3, desc="INITIALKEY", text=key)
        if genre:
            id3["TCON"] = TCON(encoding=3, text=genre)
        if label:
            id3["TXXX:LABEL"] = TXXX(encoding=3, desc="LABEL", text=label)
        if energy:
            id3["TXXX:ENERGY"] = TXXX(encoding=3, desc="ENERGY", text=energy)
        if isrc:
            id3["TSRC"] = TSRC(encoding=3, text=isrc)


def _apply_selected_tags_from_snapshot(
    id3: ID3,
    snapshot: object,
    *,
    copy_core_tags: bool,
    copy_dj_tags: bool,
) -> None:
    if copy_core_tags:
        title = str(getattr(snapshot, "title", "") or "").strip()
        artist = str(getattr(snapshot, "artist", "") or "").strip()
        album = str(getattr(snapshot, "album", "") or "").strip()
        year = getattr(snapshot, "year", None)

        if title:
            _set_if_missing(id3, "TIT2", TIT2(encoding=3, text=title))
        if artist:
            _set_if_missing(id3, "TPE1", TPE1(encoding=3, text=artist))
            _set_if_missing(id3, "TPE2", TPE2(encoding=3, text=artist))
        if album:
            _set_if_missing(id3, "TALB", TALB(encoding=3, text=album))
        if year is not None:
            _set_if_missing(id3, "TDRC", TDRC(encoding=3, text=str(year)))

    if copy_dj_tags:
        genre = str(getattr(snapshot, "genre", "") or "").strip()
        bpm = str(getattr(snapshot, "bpm", "") or "").strip()
        key = str(getattr(snapshot, "musical_key", "") or "").strip()
        label = str(getattr(snapshot, "label", "") or "").strip()
        isrc = str(getattr(snapshot, "isrc", "") or "").strip()
        energy = getattr(snapshot, "energy_1_10", None)

        if genre:
            id3["TCON"] = TCON(encoding=3, text=genre)
        if bpm:
            id3["TBPM"] = TBPM(encoding=3, text=bpm)
        if key:
            id3["TKEY"] = TKEY(encoding=3, text=key)
            id3["TXXX:INITIALKEY"] = TXXX(encoding=3, desc="INITIALKEY", text=key)
        if label:
            id3["TXXX:LABEL"] = TXXX(encoding=3, desc="LABEL", text=label)
        if isrc:
            id3["TSRC"] = TSRC(encoding=3, text=isrc)
        if energy is not None:
            id3["TXXX:ENERGY"] = TXXX(encoding=3, desc="ENERGY", text=str(energy))


def main() -> int:
    default_mp3_root = Path(os.environ.get("DJ_MP3_ROOT") or os.environ.get("MP3_LIBRARY", ".")).expanduser()
    default_flac_root = Path(os.environ.get("MASTER_LIBRARY") or os.environ.get("LIBRARY_ROOT", ".")).expanduser()

    ap = argparse.ArgumentParser(description="Sync MP3 tags from master FLAC library.")
    ap.add_argument("--db", help="SQLite DB path (used for db_dj_pool_path matching)")
    ap.add_argument(
        "--mp3-root",
        type=Path,
        default=default_mp3_root,
        help="MP3 library root (default: DJ_MP3_ROOT or MP3_LIBRARY)",
    )
    ap.add_argument(
        "--flac-root",
        type=Path,
        default=default_flac_root,
        help="FLAC master library root (default: MASTER_LIBRARY or LIBRARY_ROOT)",
    )
    ap.add_argument("--mp3-report", type=Path, help="Optional repair/report CSV")
    ap.add_argument(
        "--statuses",
        default="no_match,ambiguous",
        help="Comma-separated report status/reason selectors (ignored for rows with flac_path)",
    )
    ap.add_argument(
        "--match-source",
        choices=["auto", "master", "db_dj_pool_path"],
        default="auto",
        help="How to resolve source FLACs for MP3 repair",
    )
    ap.add_argument(
        "--copy-core-tags",
        dest="copy_core_tags",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Copy missing core ID3 tags (title/artist/album/albumartist/track/date)",
    )
    ap.add_argument(
        "--copy-dj-tags",
        dest="copy_dj_tags",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Copy DJ tags (BPM/key/genre/label/energy/ISRC)",
    )
    ap.add_argument(
        "--dj-snapshot",
        dest="dj_snapshot",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Overlay DJ snapshot metadata from the DB when a FLAC match exists",
    )
    ap.add_argument("--tol", type=float, default=2.0, help="Duration tolerance in seconds")
    ap.add_argument("--jobs", type=int, default=DEFAULT_JOBS, help="Reserved compatibility flag")
    ap.add_argument("--out", type=Path, default=Path("artifacts/mp3_sync_from_flac_report.csv"))
    ap.add_argument("--backup", type=Path, default=Path("artifacts/mp3_sync_from_flac_backup.jsonl"))
    ap.add_argument("--execute", action="store_true", help="Write tags to MP3 files")
    args = ap.parse_args()

    mp3_root = args.mp3_root.expanduser().resolve()
    flac_root = args.flac_root.expanduser().resolve()
    report_path = args.mp3_report.expanduser().resolve() if args.mp3_report else None
    statuses = {s.strip() for s in args.statuses.split(",") if s.strip()}
    work_items = _read_mp3_work_items(report_path, mp3_root, statuses)

    if not work_items:
        print("applied=0 no_match=0 missing_mp3=0")
        print(f"report={args.out}")
        print(f"backup={args.backup}")
        return 0

    db_lookup = {}
    db_resolution = None
    if args.match_source in {"auto", "db_dj_pool_path"}:
        try:
            db_resolution = resolve_cli_env_db_path(
                Path(args.db) if args.db else None,
                purpose="read",
                source_label="--db",
            )
        except DbResolutionError:
            db_resolution = None
        if db_resolution is not None:
            with sqlite3.connect(str(db_resolution.path)) as conn:
                db_lookup = load_db_dj_pool_lookup(conn, mp3_root)
    elif args.dj_snapshot:
        try:
            db_resolution = resolve_cli_env_db_path(
                Path(args.db) if args.db else None,
                purpose="read",
                source_label="--db",
            )
        except DbResolutionError:
            db_resolution = None

    mp3_meta_by_path = {}
    wanted_master_keys: set[tuple[str, str]] = set()
    for item in work_items:
        metadata = read_audio_metadata(item.path)
        mp3_meta_by_path[item.path] = metadata
        if metadata is None:
            continue
        if item.manifest_flac_path is not None:
            continue
        if args.match_source == "db_dj_pool_path" and item.path in db_lookup:
            continue
        if args.match_source in {"auto", "master"} and metadata.title and metadata.artist:
            wanted_master_keys.add((_norm(metadata.title), _norm(metadata.artist)))

    master_index = load_master_index(flac_root, wanted_master_keys) if args.match_source in {"auto", "master"} else {}

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.backup.parent.mkdir(parents=True, exist_ok=True)

    applied = 0
    no_match = 0
    missing_mp3 = 0
    snapshot_conn = sqlite3.connect(str(db_resolution.path)) if db_resolution is not None and args.dj_snapshot else None

    try:
        with args.out.open("w", newline="", encoding="utf-8") as fr, args.backup.open("w", encoding="utf-8") as fb:
            writer = csv.DictWriter(
                fr,
                fieldnames=["path", "status", "reason", "flac_path", "match_source"],
            )
            writer.writeheader()

            for item in work_items:
                if not item.path.exists():
                    missing_mp3 += 1
                    writer.writerow({"path": str(item.path), "status": "skip", "reason": "missing_mp3"})
                    continue

                metadata = mp3_meta_by_path.get(item.path)
                if metadata is None:
                    writer.writerow({"path": str(item.path), "status": "skip", "reason": "tag_read_error"})
                    continue

                chosen_flac: Path | None = item.manifest_flac_path if item.manifest_flac_path is not None else None
                match_source = "manifest_flac_path" if chosen_flac is not None else ""

                if chosen_flac is None and args.match_source in {"auto", "db_dj_pool_path"}:
                    lookup = db_lookup.get(item.path)
                    if lookup is not None:
                        chosen_flac = lookup.source_path
                        match_source = "db_dj_pool_path"

                if chosen_flac is None and args.match_source in {"auto", "master"}:
                    matches = master_index.get((_norm(metadata.title), _norm(metadata.artist)), [])
                    best = pick_best_master_match(metadata, matches, duration_tol=float(args.tol))
                    if best is not None:
                        chosen_flac = best.path
                        match_source = "master"

                if chosen_flac is None or not chosen_flac.exists():
                    no_match += 1
                    writer.writerow(
                        {
                            "path": str(item.path),
                            "status": "skip",
                            "reason": "no_flac_match",
                            "flac_path": str(chosen_flac) if chosen_flac is not None else "",
                            "match_source": match_source,
                        }
                    )
                    continue

                tags = _get_id3(item.path)
                if tags is None:
                    writer.writerow({"path": str(item.path), "status": "skip", "reason": "tag_read_error"})
                    continue

                try:
                    flac = FLAC(chosen_flac)
                except Exception:
                    writer.writerow(
                        {
                            "path": str(item.path),
                            "status": "skip",
                            "reason": "flac_read_error",
                            "flac_path": str(chosen_flac),
                            "match_source": match_source,
                        }
                    )
                    continue

                snapshot = None
                if snapshot_conn is not None:
                    try:
                        snapshot = resolve_dj_tag_snapshot_for_path(
                            snapshot_conn,
                            chosen_flac,
                            run_essentia=False,
                            dry_run=True,
                        )
                    except Exception:
                        snapshot = None

                backup = {"path": str(item.path), "tags": _backup_frames(tags)}
                fb.write(json.dumps(backup, ensure_ascii=False) + "\n")

                if args.execute:
                    flac_tags = {str(key).lower(): list(value) for key, value in (flac.tags or {}).items()}
                    _apply_selected_tags_from_flac(
                        tags,
                        flac_tags,
                        copy_core_tags=bool(args.copy_core_tags),
                        copy_dj_tags=bool(args.copy_dj_tags),
                    )
                    if snapshot is not None:
                        _apply_selected_tags_from_snapshot(
                            tags,
                            snapshot,
                            copy_core_tags=bool(args.copy_core_tags),
                            copy_dj_tags=bool(args.copy_dj_tags),
                        )
                    tags.save(item.path, v2_version=3)

                applied += 1
                writer.writerow(
                    {
                        "path": str(item.path),
                        "status": "applied",
                        "reason": "",
                        "flac_path": str(chosen_flac),
                        "match_source": match_source,
                    }
                )
    finally:
        if snapshot_conn is not None:
            snapshot_conn.close()

    print(f"applied={applied} no_match={no_match} missing_mp3={missing_mp3}")
    print(f"report={args.out}")
    print(f"backup={args.backup}")
    if not args.execute:
        print("DRY-RUN: use --execute to write tags")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
