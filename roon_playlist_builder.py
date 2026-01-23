#!/usr/bin/env python3

import os
import csv

import pandas as pd
from mutagen import File
from rapidfuzz import fuzz
from unidecode import unidecode


# ==========================
# CONFIG
# ==========================

SPREADSHEET_PRIMARY = "/Users/georgeskhawam/M.xlsx"
MUSIC_ROOT_FALLBACK = "/Volumes/SAD/MU"

OUTPUT_M3U = "Osteria_Dance.m3u8"
OUTPUT_SONGSHIFT = "Osteria_Dance_unmatched_songshift.csv"

AUDIO_EXTENSIONS = (".flac", ".mp3", ".aiff", ".aif", ".wav", ".m4a")
MATCH_THRESHOLD = 85

ENABLE_ROON_API = False
ROON_PLAYLIST_NAME = "Osteria Dance"


# ==========================
# NORMALIZATION
# ==========================

def norm(value):
    if not value:
        return ""
    return unidecode(str(value)).lower().strip()


# ==========================
# COLUMN DETECTION
# ==========================

TITLE_ALIASES = {
    "title",
    "song",
    "track",
    "track title",
    "song title",
    "name",
}

ARTIST_ALIASES = {
    "artist",
    "artist name",
    "primary artist",
    "performer",
    "album artist",
    "track artist(s)",
}

ALBUM_ALIASES = {
    "album",
    "album title",
    "release",
    "collection",
}


def detect_column(columns, aliases):
    for column in columns:
        if column in aliases:
            return column
    return None


# ==========================
# PLAYLIST INGEST
# ==========================

def load_playlist():
    if not os.path.exists(SPREADSHEET_PRIMARY):
        print("Spreadsheet not found, falling back to directory scan")
        return []

    print("Using spreadsheet source")

    df = pd.read_excel(SPREADSHEET_PRIMARY)
    df.columns = [c.lower().strip() for c in df.columns]

    title_col = detect_column(df.columns, TITLE_ALIASES)
    artist_col = detect_column(df.columns, ARTIST_ALIASES)
    album_col = detect_column(df.columns, ALBUM_ALIASES)

    if not title_col or not artist_col:
        raise ValueError(
            "Could not infer Title/Artist columns.\n"
            f"Detected columns: {list(df.columns)}"
        )

    print(
        f"Mapped columns → title: '{title_col}', "
        f"artist: '{artist_col}', "
        f"album: '{album_col}'"
    )

    tracks = []

    for _, row in df.iterrows():
        tracks.append(
            {
                "title": norm(row.get(title_col)),
                "artist": norm(row.get(artist_col)),
                "album": norm(row.get(album_col)) if album_col else "",
                "raw_title": row.get(title_col),
                "raw_artist": row.get(artist_col),
                "raw_album": row.get(album_col) if album_col else "",
            }
        )

    return tracks


# ==========================
# LIBRARY SCAN
# ==========================

def scan_library(root):
    library = []

    for dirpath, _, filenames in os.walk(root):
        for filename in filenames:
            if not filename.lower().endswith(AUDIO_EXTENSIONS):
                continue

            full_path = os.path.join(dirpath, filename)

            title = artist = album = ""

            try:
                audio = File(full_path, easy=True)
                if audio:
                    title = audio.get("title", [""])[0]
                    artist = audio.get("artist", [""])[0]
                    album = audio.get("album", [""])[0]
            except Exception:
                pass

            library.append(
                {
                    "path": full_path,
                    "title": norm(title) or norm(os.path.splitext(filename)[0]),
                    "artist": norm(artist),
                    "album": norm(album),
                }
            )

    return library


# ==========================
# MATCHING
# ==========================

def match_track(target, library):
    best_match = None
    best_score = 0

    for track in library:
        score_title = fuzz.token_set_ratio(target["title"], track["title"])
        score_artist = fuzz.token_set_ratio(target["artist"], track["artist"])
        score_album = (
            fuzz.token_set_ratio(target["album"], track["album"])
            if target["album"]
            else 0
        )

        score = (0.5 * score_title) + (0.4 * score_artist) + (0.1 * score_album)

        if score > best_score:
            best_score = score
            best_match = track

    if best_score >= MATCH_THRESHOLD:
        return best_match["path"], int(best_score)

    return None, int(best_score)


# ==========================
# EXPORTS
# ==========================

def write_m3u(paths):
    with open(OUTPUT_M3U, "w", encoding="utf-8") as file:
        file.write("#EXTM3U\n")
        for path in paths:
            file.write(f"{path}\n")


def write_songshift_csv(unmatched):
    with open(
        OUTPUT_SONGSHIFT,
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.writer(file)
        writer.writerow(["Title", "Artist", "Album"])

        for track in unmatched:
            writer.writerow(
                [
                    track["raw_title"] or "",
                    track["raw_artist"] or "",
                    track["raw_album"] or "",
                ]
            )


# ==========================
# OPTIONAL ROON API
# ==========================

def create_roon_playlist(file_paths):
    from roonapi import RoonApi, RoonDiscovery

    appinfo = {
        "extension_id": "local.playlist.builder",
        "display_name": "Local Playlist Builder",
        "display_version": "1.0",
        "publisher": "local",
        "email": "local@localhost",
    }

    discovery = RoonDiscovery(None)
    server = discovery.first()

    if not server:
        raise RuntimeError("No Roon Core found")

    roon = RoonApi(appinfo, None, server)
    roon.register_extension()

    playlist = roon.playlist.create(ROON_PLAYLIST_NAME)
    library = roon.mylibrary

    for path in file_paths:
        results = library.search(path)
        if results:
            roon.playlist.add_tracks(playlist, results)

    roon.unregister_extension()


# ==========================
# MAIN
# ==========================

def main():
    playlist = load_playlist()
    library = scan_library(MUSIC_ROOT_FALLBACK)

    matched_paths = []
    unmatched = []

    for track in playlist:
        path, _score = match_track(track, library)
        if path:
            matched_paths.append(path)
        else:
            unmatched.append(track)

    write_m3u(matched_paths)
    write_songshift_csv(unmatched)

    print(f"Matched: {len(matched_paths)}")
    print(f"Unmatched: {len(unmatched)}")
    print(f"M3U written: {OUTPUT_M3U}")
    print(f"SongShift CSV written: {OUTPUT_SONGSHIFT}")

    if ENABLE_ROON_API:
        create_roon_playlist(matched_paths)


if __name__ == "__main__":
    main()
