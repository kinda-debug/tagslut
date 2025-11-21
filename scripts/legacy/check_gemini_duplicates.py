#!/usr/bin/env python3
import argparse
import csv
import os
import sqlite3
from collections import defaultdict

"""
FULL RECONCILIATION SCRIPT
--------------------------
This script performs a complete checksum-based reconciliation between:
  • DB (library_final.db)
  • Gemini-selected duplicate paths
  • The canonical MUSIC root

It answers:
  • Is this Gemini file in the DB?
  • What is its checksum?
  • What other files share that checksum?
  • Are those copies inside MUSIC?
  • What is the safest action?

Outputs a CSV with:
  gemini_path, checksum, status, recommendation, num_total_copies,
  num_music_copies, num_outside_copies, music_paths, other_paths
"""


def load_db(db_path, verbose=False):
    if verbose:
        print(f"[INFO] Loading DB: {db_path}")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    rows = cur.execute("SELECT path, checksum FROM library_files;").fetchall()
    conn.close()

    path_to_checksum = {}
    checksum_to_paths = defaultdict(list)

    for p, ch in rows:
        path_to_checksum[p] = ch
        checksum_to_paths[ch].append(p)

    if verbose:
        print(f"[INFO] Loaded {len(rows)} DB rows")
        print(f"[INFO] Unique checksums: {len(checksum_to_paths)}")

    return path_to_checksum, checksum_to_paths


def load_gemini_list(path, verbose=False):
    if verbose:
        print(f"[INFO] Reading Gemini file: {path}")

    out = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(line)

    if verbose:
        print(f"[INFO] Gemini paths loaded: {len(out)}")
    return out


def classify(gpath, music_root, checksum, all_paths):
    """
    Classify a Gemini entry and produce an action recommendation.

    all_paths = all DB paths sharing this checksum.
    """
    music_root = music_root.rstrip("/") + "/"
    in_music = [p for p in all_paths if p.startswith(music_root)]
    outside = [p for p in all_paths if not p.startswith(music_root)]

    g_in_music = gpath.startswith(music_root)

    num_total = len(all_paths)
    num_music = len(in_music)
    num_outside = len(outside)

    # SAFE DECISION LOGIC
    if checksum == "":
        return (
            "NOT_IN_DB",
            "keep",
            num_total,
            num_music,
            num_outside,
            ";".join(in_music),
            ";".join([p for p in all_paths if p != gpath]),
        )

    if num_total == 1:
        if g_in_music:
            return (
                "UNIQUE_IN_MUSIC",
                "keep",
                num_total,
                num_music,
                num_outside,
                ";".join(in_music),
                "",
            )
        else:
            return (
                "UNIQUE_OUTSIDE_MUSIC",
                "move_to_music",
                num_total,
                num_music,
                num_outside,
                ";".join(in_music),
                "",
            )

    # Multiple copies
    if g_in_music:
        return (
            "DUPLICATE_IN_MUSIC",
            "remove_other_copies_only",
            num_total,
            num_music,
            num_outside,
            ";".join(in_music),
            ";".join([p for p in all_paths if p != gpath]),
        )
    else:
        # Gemini path is outside MUSIC
        if num_music >= 1:
            return (
                "DUPLICATE_OUTSIDE_MUSIC",
                "safe_to_delete",
                num_total,
                num_music,
                num_outside,
                ";".join(in_music),
                ";".join([p for p in all_paths if p != gpath]),
            )
        else:
            # duplicate outside music but no canonical copy exists
            return (
                "NO_MUSIC_COPY_EXISTS",
                "review",
                num_total,
                num_music,
                num_outside,
                "",
                ";".join([p for p in all_paths if p != gpath]),
            )


def analyze(db_path, gemini_path, music_root, out_csv, verbose=False):
    if verbose:
        print("=== FULL RECONCILIATION START ===")

    path_to_checksum, checksum_to_paths = load_db(db_path, verbose=verbose)
    gemini_paths = load_gemini_list(gemini_path, verbose=verbose)

    results = []

    for gpath in gemini_paths:
        if verbose:
            print(f"[CHECK] {gpath}")

        checksum = path_to_checksum.get(gpath, "")

        if checksum == "":
            # not in DB
            status, rec, nt, nm, no, mus, oth = classify(
                gpath, music_root, "", []
            )
        else:
            all_paths = checksum_to_paths[checksum]
            status, rec, nt, nm, no, mus, oth = classify(
                gpath, music_root, checksum, all_paths
            )

        results.append([
            gpath,
            checksum,
            status,
            rec,
            nt,
            nm,
            no,
            mus,
            oth
        ])

    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    with open(out_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "gemini_path",
            "checksum",
            "status",
            "recommendation",
            "num_total_copies",
            "num_music_copies",
            "num_outside_copies",
            "music_paths",
            "other_paths"
        ])
        w.writerows(results)

    print(f"[DONE] Reconciliation CSV written to: {out_csv}")
    print("=== FULL RECONCILIATION COMPLETE ===")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--gemini-list", required=True)
    ap.add_argument("--music-root", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    analyze(
        args.db,
        args.gemini_list,
        args.music_root,
        args.out,
        verbose=args.verbose
    )


if __name__ == "__main__":
    main()