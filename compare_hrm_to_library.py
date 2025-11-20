#!/usr/bin/env python3
import os
import json
import sqlite3
import argparse
import csv
from pathlib import Path

def load_hrm_flacs(json_path):
    with open(json_path, "r") as f:
        tree = json.load(f)

    hrm_files = []

    def walk(node, prefix=""):
        path = os.path.join(prefix, node["name"])
        if node["type"] == "file" and node["name"].lower().endswith(".flac"):
            hrm_files.append(path)
        for child in node.get("children", []):
            walk(child, path)

    walk(tree)
    return hrm_files


def load_music_flacs(music_root):
    flacs = []
    for root, dirs, files in os.walk(music_root):
        for f in files:
            if f.lower().endswith(".flac"):
                flacs.append(os.path.join(root, f))
    return flacs


def load_db_paths(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        rows = cur.execute("SELECT path FROM library_files").fetchall()
        conn.close()
        return set(r[0] for r in rows)
    except Exception as e:
        conn.close()
        raise e


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hrm-json", required=True)
    ap.add_argument("--db", required=True)
    ap.add_argument("--music-root", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    print("Loading HRM JSON…")
    hrm_files = load_hrm_flacs(args.hrm_json)
    print(f"HRM FLAC count: {len(hrm_files)}")

    print("Loading MUSIC…")
    music_files = load_music_flacs(args.music_root)
    music_basenames = set(os.path.basename(p) for p in music_files)
    print(f"MUSIC FLAC count: {len(music_basenames)}")

    print("Loading DB…")
    db_paths = load_db_paths(args.db)
    db_basenames = set(os.path.basename(p) for p in db_paths)
    print(f"DB FLAC count: {len(db_basenames)}")

    print("Comparing…")

    missing = []
    for f in hrm_files:
        bn = os.path.basename(f)
        if bn not in music_basenames and bn not in db_basenames:
            missing.append(f)

    print(f"Missing files: {len(missing)}")

    with open(args.out, "w", newline="", encoding="utf-8") as csvfile:
        w = csv.writer(csvfile)
        w.writerow(["hrm_path"])
        for m in missing:
            w.writerow([m])

    print(f"Written: {args.out}")


if __name__ == "__main__":
    main()
