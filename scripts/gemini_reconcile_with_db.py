#!/usr/bin/env python3
"""
Reconcile Gemini duplicate list against library_final.db.

- Reads a plain-text Gemini list: one full file path per line
- Computes SHA-1 checksums for each existing file
- Optionally probes audio metadata via ffprobe (if available)
- Stores Gemini entries in a gemini_files table in the SQLite DB
- Compares Gemini checksums against library_files
- Flags only those Gemini files that are SAFE to delete:
    * File exists on disk
    * Has a checksum
    * Same checksum exists in library_files under MUSIC_ROOT
    * The Gemini file itself is NOT under MUSIC_ROOT
- Outputs a CSV with a delete_path column for downstream deletion.

Defaults are set for your environment but can be overridden with CLI args.
"""

import argparse
import csv
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

DEFAULT_DB_PATH = "artifacts/db/library_final.db"
DEFAULT_GEMINI_LIST = "/Volumes/dotad/duplicates selected by gemini.txt"
DEFAULT_MUSIC_ROOT = "/Volumes/dotad/MUSIC"
DEFAULT_OUT_CSV = "artifacts/reports/gemini_safe_to_delete_from_db.csv"


@dataclass
class FileInfo:
    path: str
    checksum: Optional[str]
    bit_rate: Optional[int]
    sample_rate: Optional[int]
    bit_depth: Optional[int]
    duration: Optional[float]
    exists_on_disk: bool


def sha1_for_file(path: str, block_size: int = 1024 * 1024) -> Optional[str]:
    """Compute SHA-1 checksum for a file. Returns None on error."""
    h = hashlib.sha1()
    try:
        with open(path, "rb") as f:
            while True:
                chunk = f.read(block_size)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
    except (OSError, IOError):
        return None


def ffprobe_available() -> bool:
    """Check if ffprobe is available in PATH."""
    try:
        subprocess.run(
            ["ffprobe", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return True
    except OSError:
        return False


def probe_audio(path: str) -> Tuple[Optional[int], Optional[int], Optional[int], Optional[float]]:
    """
    Use ffprobe to extract bit_rate, sample_rate, bit_depth, duration.
    Returns (bit_rate, sample_rate, bit_depth, duration) or (None, None, None, None) on failure.
    """
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-select_streams", "a",
        path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            return None, None, None, None
        data = json.loads(result.stdout or "{}")
        streams = data.get("streams") or []
        if not streams:
            return None, None, None, None
        s = streams[0]
        # Some containers use bits_per_sample, others bits_per_raw_sample
        br = s.get("bit_rate")
        sr = s.get("sample_rate")
        bd = s.get("bits_per_sample") or s.get("bits_per_raw_sample")
        dur = s.get("duration") or s.get("tags", {}).get("DURATION")
        bit_rate = int(br) if br is not None else None
        sample_rate = int(sr) if sr is not None else None
        bit_depth = int(bd) if bd is not None else None
        try:
            duration = float(dur) if dur is not None else None
        except (TypeError, ValueError):
            duration = None
        return bit_rate, sample_rate, bit_depth, duration
    except Exception:
        return None, None, None, None


def read_gemini_list(txt_path: str) -> List[str]:
    """Read Gemini's duplicate list: one path per line, ignore empty and comment lines."""
    paths: List[str] = []
    with open(txt_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Handle accidental surrounding quotes
            if (line.startswith('"') and line.endswith('"')) or (
                line.startswith("'") and line.endswith("'")
            ):
                line = line[1:-1]
            paths.append(line)
    return paths


def ensure_library_files_exists(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='library_files';"
    )
    if cur.fetchone() is None:
        print("ERROR: table 'library_files' not found in DB.", file=sys.stderr)
        sys.exit(1)


def init_gemini_table(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS gemini_files (
            path TEXT PRIMARY KEY,
            checksum TEXT,
            bit_rate INTEGER,
            sample_rate INTEGER,
            bit_depth INTEGER,
            duration REAL
        );
        """
    )
    conn.commit()


def load_library_by_checksum(
    conn: sqlite3.Connection, music_root: str
) -> Tuple[Dict[str, List[FileInfo]], Dict[str, List[FileInfo]]]:
    """
    Load all rows from library_files into:
      - by_checksum: checksum -> [FileInfo,...] (all paths)
      - by_checksum_music: checksum -> [FileInfo,...] (only paths under music_root)
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT path, checksum,
               bit_rate,
               sample_rate,
               bit_depth,
               duration
        FROM library_files
        """
    )
    rows = cur.fetchall()
    by_checksum: Dict[str, List[FileInfo]] = {}
    by_checksum_music: Dict[str, List[FileInfo]] = {}

    total = 0
    for path, checksum, br, sr, bd, dur in rows:
        total += 1
        if not checksum:
            continue
        fi = FileInfo(
            path=path,
            checksum=checksum,
            bit_rate=int(br) if br is not None else None,
            sample_rate=int(sr) if sr is not None else None,
            bit_depth=int(bd) if bd is not None else None,
            duration=float(dur) if dur is not None else None,
            exists_on_disk=True,  # DB says it existed when scanned
        )
        by_checksum.setdefault(checksum, []).append(fi)
        if path.startswith(music_root):
            by_checksum_music.setdefault(checksum, []).append(fi)

    print(f"Loaded {total} rows from library_files")
    print(f"Unique checksums in DB: {len(by_checksum)}")
    print(f"Unique checksums in MUSIC_ROOT ({music_root}): {len(by_checksum_music)}")
    return by_checksum, by_checksum_music


def insert_gemini_entries(
    conn: sqlite3.Connection, gemini_infos: List[FileInfo]
) -> None:
    cur = conn.cursor()
    rows = [
        (
            gi.path,
            gi.checksum,
            gi.bit_rate,
            gi.sample_rate,
            gi.bit_depth,
            gi.duration,
        )
        for gi in gemini_infos
    ]
    cur.executemany(
        """
        INSERT OR REPLACE INTO gemini_files
            (path, checksum, bit_rate, sample_rate, bit_depth, duration)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()


def reconcile(
    db_path: str,
    gemini_list_path: str,
    music_root: str,
    out_csv: str,
) -> None:
    print("=== GEMINI / DB RECONCILIATION ===")
    print(f"DB:           {db_path}")
    print(f"Gemini list:  {gemini_list_path}")
    print(f"MUSIC_ROOT:   {music_root}")
    print(f"Out CSV:      {out_csv}")

    if not os.path.isfile(db_path):
        print(f"ERROR: DB file not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    if not os.path.isfile(gemini_list_path):
        print(f"ERROR: Gemini list not found: {gemini_list_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    try:
        ensure_library_files_exists(conn)
        init_gemini_table(conn)

        # Load library checksums
        by_checksum, by_checksum_music = load_library_by_checksum(conn, music_root)

        # Read Gemini paths
        gemini_paths = read_gemini_list(gemini_list_path)
        print(f"Gemini paths loaded: {len(gemini_paths)}")

        use_ffprobe = ffprobe_available()
        if use_ffprobe:
            print("ffprobe detected: audio metadata will be collected.")
        else:
            print("ffprobe not found: audio metadata will be skipped.")

        gemini_infos: List[FileInfo] = []

        # Scan Gemini files: existence, checksum, optional metadata
        for p in gemini_paths:
            exists = os.path.isfile(p)
            checksum: Optional[str] = None
            bit_rate: Optional[int] = None
            sample_rate: Optional[int] = None
            bit_depth: Optional[int] = None
            duration: Optional[float] = None

            if exists:
                checksum = sha1_for_file(p)
                if use_ffprobe and checksum is not None:
                    bit_rate, sample_rate, bit_depth, duration = probe_audio(p)
            else:
                # Nothing more we can do
                pass

            gemini_infos.append(
                FileInfo(
                    path=p,
                    checksum=checksum,
                    bit_rate=bit_rate,
                    sample_rate=sample_rate,
                    bit_depth=bit_depth,
                    duration=duration,
                    exists_on_disk=exists,
                )
            )

        # Store Gemini entries in DB for future reference
        insert_gemini_entries(conn, gemini_infos)
    finally:
        conn.close()

    # Now reconcile in Python using in-memory DB view (we already built by_checksum/by_checksum_music)
    # Note: we need them outside the try/finally, so reload quickly without closing; easier is to reopen
    conn = sqlite3.connect(db_path)
    try:
        by_checksum, by_checksum_music = load_library_by_checksum(conn, music_root)
    finally:
        conn.close()

    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8") as f_out:
        writer = csv.writer(f_out)
        writer.writerow(
            [
                "gemini_path",
                "exists_on_disk",
                "checksum",
                "decision",
                "reason",
                "music_match_count",
                "example_music_path",
                "delete_path",
            ]
        )

        total = 0
        n_missing = 0
        n_no_checksum = 0
        n_safe_delete = 0
        n_in_music_root = 0
        n_unique = 0
        n_dupes_no_music = 0

        for gi in gemini_infos:
            total += 1
            exists_str = "1" if gi.exists_on_disk else "0"
            checksum = gi.checksum

            if not gi.exists_on_disk:
                decision = "MISSING_ON_DISK"
                reason = "Gemini path does not exist on disk"
                music_match_count = 0
                example_music_path = ""
                delete_path = ""  # nothing to delete
            elif checksum is None:
                n_no_checksum += 1
                decision = "KEEP_NO_CHECKSUM"
                reason = "Checksum could not be computed"
                music_match_count = 0
                example_music_path = ""
                delete_path = ""
            else:
                music_matches = by_checksum_music.get(checksum, [])
                all_matches = by_checksum.get(checksum, [])

                if music_matches:
                    music_match_count = len(music_matches)
                    example_music_path = music_matches[0].path
                    if gi.path.startswith(music_root):
                        # Gemini file itself is within MUSIC_ROOT:
                        # Do NOT auto-delete. This is a library file.
                        n_in_music_root += 1
                        decision = "IN_MUSIC_ROOT"
                        reason = (
                            "File is under MUSIC_ROOT; duplicates exist but script only "
                            "auto-flags external copies for deletion"
                        )
                        delete_path = ""
                    else:
                        # This is an external duplicate; safe to delete
                        n_safe_delete += 1
                        decision = "SAFE_TO_DELETE"
                        reason = (
                            f"Checksum matches {music_match_count} file(s) under MUSIC_ROOT; "
                            f"example: {example_music_path}"
                        )
                        delete_path = gi.path
                else:
                    music_match_count = 0
                    example_music_path = ""
                    # No copy in MUSIC_ROOT with same checksum
                    if len(all_matches) > 1:
                        n_dupes_no_music += 1
                        decision = "KEEP_DUPES_NO_MUSIC"
                        reason = (
                            f"{len(all_matches)} duplicate(s) in DB share this checksum, "
                            "but none are under MUSIC_ROOT"
                        )
                    else:
                        n_unique += 1
                        decision = "KEEP_UNIQUE"
                        reason = "No other file in DB has this checksum"
                    delete_path = ""

            if not gi.exists_on_disk:
                n_missing += 1

            writer.writerow(
                [
                    gi.path,
                    exists_str,
                    checksum or "",
                    decision,
                    reason,
                    music_match_count,
                    example_music_path,
                    delete_path,
                ]
            )

    print("=== RECONCILIATION COMPLETE ===")
    print(f"Output CSV:               {out_csv}")
    print(f"Total Gemini entries:     {total}")
    print(f"  Missing on disk:        {n_missing}")
    print(f"  No checksum:            {n_no_checksum}")
    print(f"  SAFE_TO_DELETE:         {n_safe_delete}")
    print(f"  IN_MUSIC_ROOT:          {n_in_music_root}")
    print(f"  KEEP_UNIQUE:            {n_unique}")
    print(f"  KEEP_DUPES_NO_MUSIC:    {n_dupes_no_music}")
    print("")
    print("Rows with decision = SAFE_TO_DELETE have delete_path populated.")
    print("You can feed this CSV to your delete_gemini_dupes.py script if it")
    print("expects a delete_path column.")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Reconcile Gemini duplicate list against library_final.db "
        "and generate a safe-to-delete CSV."
    )
    p.add_argument(
        "--db",
        dest="db_path",
        default=DEFAULT_DB_PATH,
        help=f"Path to SQLite DB (default: {DEFAULT_DB_PATH})",
    )
    p.add_argument(
        "--gemini-list",
        dest="gemini_list",
        default=DEFAULT_GEMINI_LIST,
        help=f"Path to Gemini duplicates list (default: {DEFAULT_GEMINI_LIST})",
    )
    p.add_argument(
        "--music-root",
        dest="music_root",
        default=DEFAULT_MUSIC_ROOT,
        help=f"Canonical MUSIC root (default: {DEFAULT_MUSIC_ROOT})",
    )
    p.add_argument(
        "--out",
        dest="out_csv",
        default=DEFAULT_OUT_CSV,
        help=f"Output CSV path (default: {DEFAULT_OUT_CSV})",
    )
    return p.parse_args(argv)


def main() -> None:
    args = parse_args()
    reconcile(
        db_path=args.db_path,
        gemini_list_path=args.gemini_list,
        music_root=args.music_root,
        out_csv=args.out_csv,
    )


if __name__ == "__main__":
    main()
