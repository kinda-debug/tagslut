#!/usr/bin/env python3
import argparse
import csv
import os
import sqlite3

def load_music_checksums(db_path, music_root, verbose=False):
    if verbose:
        print(f"[INFO] Loading MUSIC rows from DB: {db_path}")
        print(f"[INFO] MUSIC root = {music_root}")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    # DEBUG: show first 5 DB paths
    dbg = cur.execute("SELECT path FROM library_files LIMIT 5;").fetchall()
    print("[DEBUG] First DB paths:", [d[0] for d in dbg])

    q = """
        SELECT path, checksum
        FROM library_files
        WHERE path LIKE ?;
    """

    rows = cur.execute(q, (music_root.rstrip("/") + "/%",)).fetchall()
    conn.close()

    if verbose:
        print(f"[INFO] Loaded {len(rows)} rows for MUSIC root")

    return rows


def load_gemini_list(gemini_path, verbose=False):
    if verbose:
        print(f"[INFO] Reading Gemini list: {gemini_path}")
    paths = []
    with open(gemini_path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                paths.append(line)
    if verbose:
        print(f"[INFO] Loaded {len(paths)} Gemini paths")
    return paths


def analyze(db_path, gemini_list, music_root, out_csv, verbose=False):

    if verbose:
        print("=== ANALYZING GEMINI DUPLICATE LIST ===")

    # load DB rows
    music_rows = load_music_checksums(db_path, music_root, verbose=verbose)
    if not music_rows:
        print("[ERROR] No rows for MUSIC found in the DB. Aborting.")
        return

    # checksum index
    checksum_map = {}
    for p, ch in music_rows:
        checksum_map.setdefault(ch, []).append(p)

    if verbose:
        print(f"[INFO] Unique checksums in MUSIC: {len(checksum_map)}")

    # load Gemini paths
    gemini_paths = load_gemini_list(gemini_list, verbose=verbose)

    # open DB again to fetch checksums for GEMINI paths
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    results = []

    for gpath in gemini_paths:
        if verbose:
            print(f"[CHECK] {gpath}")

        q = """
            SELECT checksum
            FROM library_files
            WHERE path = ?;
        """
        row = cur.execute(q, (gpath,)).fetchone()

        if row is None:
            results.append([gpath, "", "NOT_IN_DB", ""])
            continue

        checksum = row[0]
        matches = checksum_map.get(checksum, [])

        if len(matches) == 0:
            results.append([gpath, checksum, "UNIQUE", ""])
        elif len(matches) == 1:
            results.append([gpath, checksum, "SINGLE_MATCH", matches[0]])
        else:
            # multiple matches → duplicates
            targets = ";".join(matches)
            results.append([gpath, checksum, "MULTI_MATCH", targets])

    conn.close()

    # write CSV
    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    with open(out_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["gemini_path", "checksum", "status", "matches"])
        w.writerows(results)

    print(f"[DONE] Wrote report to: {out_csv}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--gemini-list", required=True)
    parser.add_argument("--music-root", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    analyze(
        args.db,
        args.gemini_list,
        args.music_root,
        args.out,
        verbose=args.verbose
    )


if __name__ == "__main__":
    main()