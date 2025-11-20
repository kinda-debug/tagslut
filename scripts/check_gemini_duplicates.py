#!/usr/bin/env python3
import os
import sys
import csv
import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Tuple

DB_PATH = "artifacts/db/library.db"
GEMINI_LIST = "/Volumes/dotad/duplicates selected by gemini.txt"
OUT_CSV = "artifacts/reports/gemini_dupe_analysis.csv"


@dataclass
class FileRow:
    path: str
    checksum: str
    bit_rate: int
    sample_rate: int
    bit_depth: int
    duration: float


def load_music_rows(db_path: str) -> Tuple[Dict[str, FileRow], Dict[str, List[FileRow]]]:
    """
    Load all rows for /Volumes/dotad/MUSIC/* from library_files into:
      - path_index: path -> FileRow
      - checksum_index: checksum -> [FileRow,...]
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Verify the table exists
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='library_files';"
    )
    if cur.fetchone() is None:
        print("ERROR: table 'library_files' not found in DB.", file=sys.stderr)
        sys.exit(1)

    query = """
        SELECT path, checksum,
               COALESCE(bit_rate, 0),
               COALESCE(sample_rate, 0),
               COALESCE(bit_depth, 0),
               COALESCE(duration, 0.0)
        FROM library_files
        WHERE path LIKE '/Volumes/dotad/MUSIC/%'
          AND checksum IS NOT NULL
    """

    rows = cur.execute(query).fetchall()
    conn.close()

    path_index: Dict[str, FileRow] = {}
    checksum_index: Dict[str, List[FileRow]] = {}

    for path, checksum, br, sr, bd, dur in rows:
        fr = FileRow(
            path=path,
            checksum=checksum,
            bit_rate=int(br) if br is not None else 0,
            sample_rate=int(sr) if sr is not None else 0,
            bit_depth=int(bd) if bd is not None else 0,
            duration=float(dur) if dur is not None else 0.0,
        )
        path_index[path] = fr
        checksum_index.setdefault(checksum, []).append(fr)

    print(f"Loaded {len(rows)} rows from library_files under /Volumes/dotad/MUSIC")
    print(f"Unique checksums in MUSIC: {len(checksum_index)}")

    if not rows:
        print(
            "WARNING: No rows for /Volumes/dotad/MUSIC in DB. "
            "Check that DB_PATH is correct and MUSIC was scanned.",
            file=sys.stderr,
        )

    return path_index, checksum_index


def read_gemini_paths(txt_path: str) -> List[str]:
    """
    Read Gemini's duplicate list: assume one path per line.
    Ignore blank lines and comment-like lines starting with '#'.
    """
    paths: List[str] = []
    with open(txt_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            paths.append(line)
    print(f"Gemini paths loaded: {len(paths)}")
    return paths


def quality_key(fr: FileRow) -> Tuple[int, int, int, float]:
    """
    Higher is better on all fields.
    """
    return (fr.bit_depth, fr.sample_rate, fr.bit_rate, fr.duration)


def analyze_gemini_duplicates(
    db_path: str, gemini_list: str, out_csv: str
) -> None:
    # Load DB view of MUSIC
    print("=== ANALYZING GEMINI DUPLICATE LIST ===")
    path_index, checksum_index = load_music_rows(db_path)

    # If nothing loaded, stop here
    if not path_index:
        print("No MUSIC rows available in DB; aborting.")
        return

    # Load Gemini paths
    gemini_paths = read_gemini_paths(gemini_list)

    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    out_f = open(out_csv, "w", newline="", encoding="utf-8")
    writer = csv.writer(out_f)
    writer.writerow(
        [
            "gemini_path",
            "exists_on_disk",
            "in_db",
            "checksum",
            "n_same_checksum_in_music",
            "best_path_in_music",
            "bit_depth",
            "sample_rate",
            "bit_rate",
            "duration",
            "decision",  # KEEP / DELETE_LOWER_QUALITY / NOT_IN_DB / NO_DUPES
            "reason",
        ]
    )

    n_missing_disk = 0
    n_not_in_db = 0
    n_unique = 0
    n_keep = 0
    n_delete_lower = 0

    for p in gemini_paths:
        exists = os.path.isfile(p)
        if not exists:
            n_missing_disk += 1
            writer.writerow(
                [
                    p,
                    "0",
                    "0",
                    "",
                    0,
                    "",
                    "",
                    "",
                    "",
                    "",
                    "MISSING_ON_DISK",
                    "Gemini path does not exist on disk",
                ]
            )
            continue

        fr = path_index.get(p)
        if fr is None:
            # file exists but is not in DB under /Volumes/dotad/MUSIC
            n_not_in_db += 1
            writer.writerow(
                [
                    p,
                    "1",
                    "0",
                    "",
                    0,
                    "",
                    "",
                    "",
                    "",
                    "",
                    "NOT_IN_DB",
                    "File exists on disk but not in library_files for /Volumes/dotad/MUSIC",
                ]
            )
            continue

        # We have a DB row for this Gemini file
        same = checksum_index.get(fr.checksum, [])
        # Exclude itself from the other copies list
        others = [x for x in same if x.path != fr.path]

        if not others:
            # No other copy in MUSIC with same checksum
            n_unique += 1
            writer.writerow(
                [
                    p,
                    "1",
                    "1",
                    fr.checksum,
                    1,
                    fr.path,
                    fr.bit_depth,
                    fr.sample_rate,
                    fr.bit_rate,
                    fr.duration,
                    "NO_DUPES",
                    "No other file in /Volumes/dotad/MUSIC with the same checksum",
                ]
            )
            continue

        # There are other copies in MUSIC with the same checksum
        # Find best-quality among *all* copies (including this one)
        candidates = same
        best = max(candidates, key=quality_key)

        if best.path == fr.path:
            # This Gemini file is the best version
            n_keep += 1
            decision = "KEEP"
            reason = "This Gemini file has the best quality among all same-checksum copies in /Volumes/dotad/MUSIC"
        else:
            # This Gemini file is a lower-quality duplicate
            n_delete_lower += 1
            decision = "DELETE_LOWER_QUALITY"
            reason = f"Better quality copy exists in MUSIC: {best.path}"

        writer.writerow(
            [
                p,
                "1",
                "1",
                fr.checksum,
                len(same),
                best.path,
                fr.bit_depth,
                fr.sample_rate,
                fr.bit_rate,
                fr.duration,
                decision,
                reason,
            ]
        )

    out_f.close()

    print("=== DONE ===")
    print(f"Report written to: {out_csv}")
    print("----- STATS -----")
    print(f"Missing on disk:       {n_missing_disk}")
    print(f"Exists but NOT in DB:  {n_not_in_db}")
    print(f"No dupes in MUSIC:     {n_unique}")
    print(f"KEEP (best quality):   {n_keep}")
    print(f"DELETE_LOWER_QUALITY:  {n_delete_lower}")


def main():
    analyze_gemini_duplicates(DB_PATH, GEMINI_LIST, OUT_CSV)


if __name__ == "__main__":
    main()
