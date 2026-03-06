#!/usr/bin/env python3
"""
Apply Lexicon DJ CSV tags to matching FLAC files in the master library.

Matching priority:
  1) title + artist + album
  2) title + artist
  Tie-breaker: closest duration (if provided in CSV and readable from file)

Writes:
  - BPM -> BPM tag
  - Key -> INITIALKEY + KEY (Lexicon key) + KEY_CAMELOT (camelot)
  - Genre -> GENRE
  - Label -> LABEL
  - Energy -> ENERGY

Default is dry-run; use --execute to write tags.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Optional

from mutagen.flac import FLAC


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


def _apply_tags(audio: FLAC, row: dict) -> None:
    bpm = (row.get("bpm") or "").strip()
    key = (row.get("key") or "").strip()
    genre = (row.get("genre") or "").strip()
    label = (row.get("label") or "").strip()
    energy = (row.get("energy") or "").strip()

    if bpm:
        audio["BPM"] = bpm
    if key:
        audio["INITIALKEY"] = key
        audio["KEY"] = key
        audio["KEY_CAMELOT"] = key
    if genre:
        audio["GENRE"] = genre
    if label:
        audio["LABEL"] = label
    if energy:
        audio["ENERGY"] = energy


def main() -> int:
    ap = argparse.ArgumentParser(description="Apply Lexicon CSV tags to FLAC files.")
    ap.add_argument("--csv", type=Path, required=True, help="Lexicon CSV export")
    ap.add_argument("--root", type=Path, required=True, help="Library root to scan")
    ap.add_argument("--out", type=Path, default=Path("artifacts/lexicon_apply_report.csv"))
    ap.add_argument("--backup", type=Path, default=Path("artifacts/lexicon_apply_backup.jsonl"))
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

        for flac_path in args.root.rglob("*.flac"):
            try:
                audio = FLAC(flac_path)
            except Exception:
                writer.writerow({"path": str(flac_path), "status": "skip", "reason": "read_error"})
                continue

            title = _norm((audio.get("title") or [""])[0])
            artist = _norm((audio.get("artist") or [""])[0])
            album = _norm((audio.get("album") or [""])[0])
            duration_s = float(getattr(audio.info, "length", 0.0) or 0.0) or None

            candidates = []
            if title and artist and album:
                candidates = by_title_artist_album.get((title, artist, album), [])
            if not candidates and title and artist:
                candidates = by_title_artist.get((title, artist), [])

            if not candidates:
                no_match += 1
                writer.writerow({"path": str(flac_path), "status": "skip", "reason": "no_match"})
                continue

            if len(candidates) > 1:
                ambiguous += 1

            row = _pick_best(candidates, duration_s)
            if row is None:
                writer.writerow({"path": str(flac_path), "status": "skip", "reason": "ambiguous_no_choice"})
                continue

            backup = {
                "path": str(flac_path),
                "tags": {
                    "BPM": audio.get("BPM"),
                    "INITIALKEY": audio.get("INITIALKEY"),
                    "KEY": audio.get("KEY"),
                    "KEY_CAMELOT": audio.get("KEY_CAMELOT"),
                    "GENRE": audio.get("GENRE"),
                    "LABEL": audio.get("LABEL"),
                    "ENERGY": audio.get("ENERGY"),
                },
            }
            fb.write(json.dumps(backup, ensure_ascii=False) + "\n")

            if args.execute:
                _apply_tags(audio, row)
                audio.save()

            applied += 1
            writer.writerow({"path": str(flac_path), "status": "applied", "reason": ""})

    print(f"applied={applied} no_match={no_match} ambiguous={ambiguous}")
    print(f"report={args.out}")
    print(f"backup={args.backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
