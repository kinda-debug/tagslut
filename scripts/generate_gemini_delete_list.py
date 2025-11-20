#!/usr/bin/env python3
import argparse
import csv
import os
import sqlite3
import sys

"""
Input:
  --db path/to/library_final.db
  --analysis gemini_dupe_analysis.csv
  --music-root /Volumes/dotad/MUSIC
  --out gemini_safe_to_delete.csv

Output:
  CSV with files that are safe to delete.
Rules:
  • Gemini file must exist.
  • Must have a checksum match in MUSIC.
  • MUSIC file must exist on disk.
  • MUSIC file must not be corrupt (checksum present in DB).
  • Prefer MUSIC version by default.
"""

def load_music_checksums(db_path, music_root):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    q = """
        SELECT path, checksum, bit_rate, duration
        FROM library_files
        WHERE path LIKE ? || '%';
    """
    rows = cur.execute(q, (music_root,)).fetchall()
    conn.close()

    music_by_checksum = {}
    for path, checksum, bit_rate, duration in rows:
        if checksum not in music_by_checksum:
            music_by_checksum[checksum] = []
        music_by_checksum[checksum].append({
            "path": path,
            "bit_rate": bit_rate,
            "duration": duration
        })
    return music_by_checksum


def read_analysis_csv(path):
    results = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            results.append(row)
    return results


def file_exists(path):
    return os.path.isfile(path)


def evaluate_entry(entry, music_by_checksum):
    """
    entry fields from gemini_dupe_analysis.csv:
      gemini_path
      checksum
      status
      reason
      music_match_path
      music_bitrate
      gemini_bitrate
    """
    gemini_path = entry["gemini_path"]
    checksum = entry["checksum"]

    # Must have real checksum
    if not checksum:
        return False, "no checksum in gemini entry"

    # Gemini file must exist
    if not file_exists(gemini_path):
        return False, "gemini file missing"

    # Must have checksum match in MUSIC DB
    if checksum not in music_by_checksum:
        return False, "no matching checksum in MUSIC"

    # MUSIC file(s) must exist
    music_candidates = music_by_checksum[checksum]
    existing_targets = [c for c in music_candidates if file_exists(c["path"])]

    if not existing_targets:
        return False, "matching checksum in DB but no actual file in MUSIC"

    # If we reach here: safe to delete gemini copy
    return True, "duplicate found in MUSIC"


def generate_delete_list(db_path, analysis_csv, music_root, out_csv):
    music_by_checksum = load_music_checksums(db_path, music_root)
    analysis = read_analysis_csv(analysis_csv)

    safe = []
    rejected = []

    for row in analysis:
        ok, reason = evaluate_entry(row, music_by_checksum)
        result_row = {
            "gemini_path": row["gemini_path"],
            "checksum": row["checksum"],
            "decision": "delete" if ok else "keep",
            "reason": reason,
            "music_match_path": row.get("music_match_path", "")
        }
        if ok:
            safe.append(result_row)
        else:
            rejected.append(result_row)

    # Write output CSV
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        fieldnames = ["gemini_path", "checksum", "decision", "reason", "music_match_path"]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in safe + rejected:
            w.writerow(r)

    print(f"[DONE] Safe-to-delete list written to: {out_csv}")
    print(f"  Safe: {len(safe)}")
    print(f"  Keep: {len(rejected)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--analysis", required=True)
    ap.add_argument("--music-root", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    generate_delete_list(
        db_path=args.db,
        analysis_csv=args.analysis,
        music_root=args.music_root,
        out_csv=args.out
    )


if __name__ == "__main__":
    main()
