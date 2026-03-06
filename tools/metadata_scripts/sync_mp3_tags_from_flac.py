#!/usr/bin/env python3
"""
Sync DJ-relevant tags from master FLAC library to MP3 files.

Matching:
  - title + artist, then closest duration within tolerance (default 2s)
  - if album is present on both, prefer exact album match

Tags copied from FLAC -> MP3:
  - BPM
  - INITIALKEY / KEY / KEY_CAMELOT
  - GENRE
  - LABEL
  - ENERGY
  - ISRC

Inputs:
  - MP3 report CSV with 'path' and 'status' columns (optional filter)
  - Or a direct MP3 root

Default is dry-run; use --execute to write tags.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Optional

from mutagen.flac import FLAC
from mutagen.id3 import ID3, ID3NoHeaderError, TBPM, TCON, TKEY, TSRC, TXXX
from mutagen.mp3 import MP3


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


def _first_text_flac(tags: dict, key: str) -> str:
    vals = tags.get(key)
    if vals:
        return str(vals[0]).strip()
    return ""


def _read_mp3_paths(report: Optional[Path], root: Path, statuses: set[str]) -> list[Path]:
    if report:
        paths = []
        with report.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if statuses and row.get("status") not in statuses:
                    continue
                p = row.get("path")
                if p:
                    paths.append(Path(p))
        return paths
    return list(root.rglob("*.mp3"))


def _index_flacs(flac_root: Path) -> dict[tuple[str, str], list[dict]]:
    index: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for path in flac_root.rglob("*.flac"):
        try:
            audio = FLAC(path)
        except Exception:
            continue
        title = _norm(_first_text_flac(audio.tags or {}, "title"))
        artist = _norm(_first_text_flac(audio.tags or {}, "artist"))
        album = _norm(_first_text_flac(audio.tags or {}, "album"))
        duration = float(getattr(audio.info, "length", 0.0) or 0.0)
        if not title or not artist:
            continue
        index[(title, artist)].append(
            {
                "path": path,
                "album": album,
                "duration": duration,
                "tags": audio.tags or {},
            }
        )
    return index


def _pick_best(candidates: list[dict], album: str, duration: Optional[float], tol: float) -> Optional[dict]:
    if not candidates:
        return None
    album = _norm(album)
    if album:
        album_matches = [c for c in candidates if _norm(c.get("album", "")) == album]
        if album_matches:
            candidates = album_matches
    if duration is None:
        return candidates[0]
    best = None
    best_diff = None
    for c in candidates:
        d = c.get("duration")
        if d is None:
            continue
        diff = abs(float(d) - duration)
        if diff <= tol and (best is None or diff < best_diff):
            best = c
            best_diff = diff
    return best or candidates[0]


def _apply_tags_from_flac(id3: ID3, flac_tags: dict) -> None:
    bpm = _first_text_flac(flac_tags, "bpm") or _first_text_flac(flac_tags, "BPM")
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


def _env_path(key: str) -> Optional[Path]:
    value = os.environ.get(key, "").strip()
    if not value:
        return None
    return Path(value)


def main() -> int:
    default_mp3_root = _env_path("DJ_MP3_ROOT")
    default_flac_root = _env_path("DJ_LIBRARY_ROOT") or _env_path("LIBRARY_ROOT") or _env_path("VOLUME_ARCHIVE")

    ap = argparse.ArgumentParser(description="Sync MP3 tags from master FLAC library.")
    ap.add_argument(
        "--mp3-root",
        type=Path,
        default=default_mp3_root,
        help="MP3 library root (default: DJ_MP3_ROOT)",
    )
    ap.add_argument(
        "--flac-root",
        type=Path,
        default=default_flac_root,
        help="FLAC master library root (default: DJ_LIBRARY_ROOT or LIBRARY_ROOT)",
    )
    ap.add_argument("--mp3-report", type=Path, help="Optional MP3 report CSV to filter")
    ap.add_argument(
        "--statuses",
        default="no_match,ambiguous",
        help="Comma-separated MP3 report statuses to include (default: no_match,ambiguous)",
    )
    ap.add_argument("--tol", type=float, default=2.0, help="Duration tolerance in seconds")
    ap.add_argument("--out", type=Path, default=Path("artifacts/mp3_sync_from_flac_report.csv"))
    ap.add_argument("--backup", type=Path, default=Path("artifacts/mp3_sync_from_flac_backup.jsonl"))
    ap.add_argument("--execute", action="store_true", help="Write tags to MP3 files")
    args = ap.parse_args()

    if not args.mp3_root:
        raise SystemExit("MP3 root missing. Provide --mp3-root or set DJ_MP3_ROOT in .env.")
    if not args.flac_root:
        raise SystemExit("FLAC root missing. Provide --flac-root or set DJ_LIBRARY_ROOT in .env.")

    args.mp3_root = args.mp3_root.expanduser().resolve()
    args.flac_root = args.flac_root.expanduser().resolve()

    statuses = {s.strip() for s in args.statuses.split(",") if s.strip()}
    mp3_paths = _read_mp3_paths(args.mp3_report, args.mp3_root, statuses)
    flac_index = _index_flacs(args.flac_root)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.backup.parent.mkdir(parents=True, exist_ok=True)

    applied = 0
    no_match = 0
    missing_mp3 = 0

    with args.out.open("w", newline="", encoding="utf-8") as fr, args.backup.open(
        "w", encoding="utf-8"
    ) as fb:
        writer = csv.DictWriter(fr, fieldnames=["path", "status", "reason", "flac_path"])
        writer.writeheader()

        for mp3_path in mp3_paths:
            if not mp3_path.exists():
                missing_mp3 += 1
                writer.writerow({"path": str(mp3_path), "status": "skip", "reason": "missing_mp3"})
                continue

            tags = _get_id3(mp3_path)
            if tags is None:
                writer.writerow({"path": str(mp3_path), "status": "skip", "reason": "tag_read_error"})
                continue

            title = _norm(_first_text_id3(tags, "TIT2"))
            artist = _norm(_first_text_id3(tags, "TPE1"))
            album = _norm(_first_text_id3(tags, "TALB"))
            duration_s = None
            try:
                duration_s = float(getattr(MP3(mp3_path).info, "length", 0.0) or 0.0) or None
            except Exception:
                duration_s = None

            candidates = flac_index.get((title, artist), [])
            if not candidates:
                no_match += 1
                writer.writerow({"path": str(mp3_path), "status": "skip", "reason": "no_flac_match"})
                continue

            flac = _pick_best(candidates, album, duration_s, args.tol)
            if flac is None:
                no_match += 1
                writer.writerow({"path": str(mp3_path), "status": "skip", "reason": "no_flac_choice"})
                continue

            backup = {
                "path": str(mp3_path),
                "tags": {
                    "TBPM": _first_text_id3(tags, "TBPM"),
                    "TKEY": _first_text_id3(tags, "TKEY"),
                    "TXXX:INITIALKEY": _first_text_id3(tags, "TXXX:INITIALKEY"),
                    "TCON": _first_text_id3(tags, "TCON"),
                    "TXXX:LABEL": _first_text_id3(tags, "TXXX:LABEL"),
                    "TXXX:ENERGY": _first_text_id3(tags, "TXXX:ENERGY"),
                    "TSRC": _first_text_id3(tags, "TSRC"),
                },
            }
            fb.write(json.dumps(backup, ensure_ascii=False) + "\n")

            if args.execute:
                _apply_tags_from_flac(tags, flac["tags"])
                tags.save(mp3_path, v2_version=3)

            applied += 1
            writer.writerow(
                {
                    "path": str(mp3_path),
                    "status": "applied",
                    "reason": "",
                    "flac_path": str(flac["path"]),
                }
            )

    print(f"applied={applied} no_match={no_match} missing_mp3={missing_mp3}")
    print(f"report={args.out}")
    print(f"backup={args.backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
