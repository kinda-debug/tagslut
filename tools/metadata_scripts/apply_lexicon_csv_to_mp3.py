#!/usr/bin/env python3
"""
Apply Lexicon DJ CSV tags to matching MP3 files in the DJ library.

Matching priority:
  1) title + artist + album
  2) title + artist
  Tie-breaker: closest duration (if provided in CSV)

Writes:
  - BPM -> TBPM
  - Key -> TKEY + TXXX:INITIALKEY
  - Genre -> TCON
  - Label -> TXXX:LABEL
  - Energy -> TXXX:ENERGY

Default is dry-run; use --execute to write tags.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Optional

from mutagen.id3 import ID3, ID3NoHeaderError, TBPM, TCON, TKEY, TIT2, TALB, TPE1, TXXX
from mutagen.mp3 import MP3


def _norm(s: str) -> str:
    return " ".join((s or "").strip().casefold().split())


def _parse_duration(val: str) -> Optional[float]:
    val = (val or "").strip()
    if not val:
        return None
    if ":" in val:
        parts = val.split(":")
        try:
            if len(parts) == 2:
                return float(parts[0]) * 60 + float(parts[1])
            if len(parts) == 3:
                return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        except Exception:
            return None
    try:
        return float(val)
    except Exception:
        return None


def _read_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def _index_rows(rows: list[dict]) -> tuple[dict, dict]:
    by_title_artist = defaultdict(list)
    by_title_artist_album = defaultdict(list)
    for row in rows:
        title = _norm(row.get("title") or "")
        artist = _norm(row.get("artist") or "")
        album = _norm(row.get("albumTitle") or "")
        if title and artist:
            by_title_artist[(title, artist)].append(row)
        if title and artist and album:
            by_title_artist_album[(title, artist, album)].append(row)
    return by_title_artist, by_title_artist_album


def _pick_best(rows: list[dict], duration_s: Optional[float]) -> Optional[dict]:
    if not rows:
        return None
    if duration_s is None:
        return rows[0]
    best = None
    best_diff = None
    for row in rows:
        d = _parse_duration(row.get("duration", ""))
        if d is None:
            continue
        diff = abs(d - duration_s)
        if best is None or diff < best_diff:
            best = row
            best_diff = diff
    return best or rows[0]


def _get_id3(path: Path) -> Optional[ID3]:
    try:
        return ID3(path)
    except ID3NoHeaderError:
        return ID3()
    except Exception:
        return None


def _first_text(tags: ID3, key: str) -> str:
    if key in tags:
        val = tags.get(key)
        if hasattr(val, "text") and val.text:
            return str(val.text[0]).strip()
    return ""


def _apply_tags(tags: ID3, row: dict) -> None:
    bpm = (row.get("bpm") or "").strip()
    key = (row.get("key") or "").strip()
    genre = (row.get("genre") or "").strip()
    label = (row.get("label") or "").strip()
    energy = (row.get("energy") or "").strip()
    title = (row.get("title") or "").strip()
    artist = (row.get("artist") or "").strip()
    album = (row.get("albumTitle") or "").strip()

    if title:
        tags["TIT2"] = TIT2(encoding=3, text=title)
    if artist:
        tags["TPE1"] = TPE1(encoding=3, text=artist)
    if album:
        tags["TALB"] = TALB(encoding=3, text=album)
    if bpm:
        tags["TBPM"] = TBPM(encoding=3, text=bpm)
    if key:
        tags["TKEY"] = TKEY(encoding=3, text=key)
        tags["TXXX:INITIALKEY"] = TXXX(encoding=3, desc="INITIALKEY", text=key)
    if genre:
        tags["TCON"] = TCON(encoding=3, text=genre)
    if label:
        tags["TXXX:LABEL"] = TXXX(encoding=3, desc="LABEL", text=label)
    if energy:
        tags["TXXX:ENERGY"] = TXXX(encoding=3, desc="ENERGY", text=energy)


def main() -> int:
    ap = argparse.ArgumentParser(description="Apply Lexicon CSV tags to MP3 files.")
    ap.add_argument("--csv", type=Path, required=True, help="Lexicon CSV export")
    ap.add_argument("--root", type=Path, required=True, help="Library root to scan")
    ap.add_argument("--out", type=Path, default=Path("artifacts/lexicon_apply_mp3_report.csv"))
    ap.add_argument("--backup", type=Path, default=Path("artifacts/lexicon_apply_mp3_backup.jsonl"))
    ap.add_argument("--execute", action="store_true", help="Write tags to files")
    args = ap.parse_args()

    rows = _read_rows(args.csv)
    by_title_artist, by_title_artist_album = _index_rows(rows)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.backup.parent.mkdir(parents=True, exist_ok=True)

    applied = 0
    no_match = 0
    ambiguous = 0

    with args.out.open("w", newline="", encoding="utf-8") as fr, args.backup.open(
        "w", encoding="utf-8"
    ) as fb:
        writer = csv.DictWriter(
            fr,
            fieldnames=["path", "status", "reason"],
        )
        writer.writeheader()

        for mp3_path in args.root.rglob("*.mp3"):
            try:
                audio = MP3(mp3_path)
            except Exception:
                writer.writerow({"path": str(mp3_path), "status": "skip", "reason": "read_error"})
                continue

            tags = _get_id3(mp3_path)
            if tags is None:
                writer.writerow({"path": str(mp3_path), "status": "skip", "reason": "tag_read_error"})
                continue

            title = _norm(_first_text(tags, "TIT2"))
            artist = _norm(_first_text(tags, "TPE1"))
            album = _norm(_first_text(tags, "TALB"))
            duration_s = float(getattr(audio.info, "length", 0.0) or 0.0) or None

            candidates = []
            if title and artist and album:
                candidates = by_title_artist_album.get((title, artist, album), [])
            if not candidates and title and artist:
                candidates = by_title_artist.get((title, artist), [])

            if not candidates:
                no_match += 1
                writer.writerow({"path": str(mp3_path), "status": "skip", "reason": "no_match"})
                continue

            if len(candidates) > 1:
                ambiguous += 1

            row = _pick_best(candidates, duration_s)
            if row is None:
                writer.writerow({"path": str(mp3_path), "status": "skip", "reason": "ambiguous_no_choice"})
                continue

            backup = {
                "path": str(mp3_path),
                "tags": {
                    "TIT2": _first_text(tags, "TIT2"),
                    "TPE1": _first_text(tags, "TPE1"),
                    "TALB": _first_text(tags, "TALB"),
                    "TBPM": _first_text(tags, "TBPM"),
                    "TKEY": _first_text(tags, "TKEY"),
                    "TXXX:INITIALKEY": _first_text(tags, "TXXX:INITIALKEY"),
                    "TCON": _first_text(tags, "TCON"),
                    "TXXX:LABEL": _first_text(tags, "TXXX:LABEL"),
                    "TXXX:ENERGY": _first_text(tags, "TXXX:ENERGY"),
                },
            }
            fb.write(json.dumps(backup, ensure_ascii=False) + "\n")

            if args.execute:
                _apply_tags(tags, row)
                tags.save(mp3_path, v2_version=3)

            applied += 1
            writer.writerow({"path": str(mp3_path), "status": "applied", "reason": ""})

    print(f"applied={applied} no_match={no_match} ambiguous={ambiguous}")
    print(f"report={args.out}")
    print(f"backup={args.backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
