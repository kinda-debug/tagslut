#!/usr/bin/env python3
import argparse
import csv
import os
import sqlite3

def load_db_checksums(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    query = """
        SELECT path, checksum
        FROM library_files
    """

    rows = cur.execute(query).fetchall()
    conn.close()

    db_map = {}
    for path, checksum in rows:
        db_map[path] = checksum

    return db_map


def scan_flac_files(root):
    flacs = []
    for dirpath, _, filenames in os.walk(root):
        for f in filenames:
            if f.lower().endswith(".flac"):
                full_path = os.path.join(dirpath, f)
                rel = os.path.relpath(full_path, root)
                flacs.append((full_path, rel))
    return flacs


def build_checksum_index(db_map, root_prefix):
    index = {}
    prefix_norm = os.path.normpath(root_prefix)

    for db_path, checksum in db_map.items():
        norm_path = os.path.normpath(db_path)

        if norm_path.startswith(prefix_norm):
            rel = os.path.relpath(norm_path, prefix_norm)
            index[rel] = checksum

    return index


def main():
    parser = argparse.ArgumentParser(description="Find files missing from MUSIC based on DB entries.")
    parser.add_argument("--db", required=True, help="Path to library.db")
    parser.add_argument("--music-root", required=True, help="Path to canonical MUSIC folder")
    parser.add_argument("--new-music-root", required=True, help="Path to folder to compare")
    parser.add_argument("--out", required=True, help="CSV output")

    args = parser.parse_args()

    print("Loading DB...")
    db_map = load_db_checksums(args.db)

    print("Indexing MUSIC checksums...")
    music_index = build_checksum_index(db_map, args.music_root)

    print("Scanning source folder:", args.new_music_root)
    src_files = scan_flac_files(args.new_music_root)

    missing = []

    for full_src, rel_src in src_files:
        if rel_src not in music_index:
            missing.append([rel_src, full_src])

    print("Writing CSV:", args.out)
    out_dir = os.path.dirname(args.out)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir)

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["relative_path", "full_path"])
        writer.writerows(missing)

    print("=== SUMMARY ===")
    print("Source FLACs scanned:", len(src_files))
    print("Missing from MUSIC:", len(missing))
    print("CSV written to:", args.out)
    print("================")


if __name__ == "__main__":
    main()
