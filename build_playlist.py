#!/usr/bin/env python3

import pandas as pd
import subprocess
from pathlib import Path
from rapidfuzz import process, fuzz

# ----------------------------
# CONFIG
# ----------------------------

POOL = Path("/Volumes/MUSIC/_work/gig_runs/gig_2026_03_13/special_pool_from_playlists_20260312_184742/pool")
XLSX = Path("/Users/georgeskhawam/Desktop/Happy.xlsx")

PLAYLIST = POOL / "HAPPY_FROM_XLSX.m3u"

DOWNLOAD_MISSING = False
FUZZ_THRESHOLD = 80


# ----------------------------
# BUILD FILE INDEX
# ----------------------------

def index_pool():

    files = []

    for p in POOL.rglob("*.mp3"):
        files.append(str(p))

    return files


# ----------------------------
# FIND BEST MATCH
# ----------------------------

def find_track(title, artist, files):

    query = f"{artist} {title}".lower()

    match = process.extractOne(
        query,
        files,
        scorer=fuzz.token_set_ratio
    )

    if match and match[1] >= FUZZ_THRESHOLD:
        return Path(match[0])

    return None


# ----------------------------
# DOWNLOAD
# ----------------------------

def download_track(title, artist):

    query = f"{artist} - {title}"

    print("DOWNLOADING:", query)

    subprocess.run([
        "spotdl",
        query,
        "--output",
        str(POOL / "{artist} - {title}.{output-ext}")
    ])


# ----------------------------
# MAIN
# ----------------------------

def main():

    print("Reading XLSX...")

    df = pd.read_excel(XLSX)

    files = index_pool()

    playlist = []

    missing = []

    for _, row in df.iterrows():

        title = str(row["Title"]).strip()
        artist = str(row["Track Artist(s)"]).strip()

        file = find_track(title, artist, files)

        if file:

            print("MATCH", file)

            playlist.append(file)

        else:

            print("MISSING", artist, "-", title)

            missing.append((title, artist))

            if DOWNLOAD_MISSING:
                download_track(title, artist)

    print("\nWriting playlist...")

    with open(PLAYLIST, "w", encoding="utf-8") as f:

        f.write("#EXTM3U\n")

        for p in playlist:
            f.write(str(p) + "\n")

    print("\nPlaylist created:", PLAYLIST)

    print("\nSummary")
    print("Matched:", len(playlist))
    print("Missing:", len(missing))


if __name__ == "__main__":
    main()
