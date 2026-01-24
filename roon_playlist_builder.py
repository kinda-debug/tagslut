#!/usr/bin/env python3
"""
Roon Playlist Builder (Deterministic, ID-first)

What this does:
- Loads a FULL library index from an XLSX (your entire library).
- Reads SongShift-style TXT playlists (Spotify/Deezer/Tidal).
- Matches tracks by EXTERNAL ID first (spotify/deezer/tidal), then by exact tag path,
  then by conservative fuzzy fallback (title + artist).
- Emits non-empty UTF-8 M3U8 playlists suitable for Roon.
- Emits unmatched reports per-playlist.
- VERBOSE BY DEFAULT.

No hardcoding. No guessing the library is the playlist. The TXT files ARE the playlist.
"""

import argparse
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pandas as pd

try:
    from rapidfuzz import fuzz
except Exception:
    fuzz = None


# ----------------------------- Data Models ----------------------------- #

@dataclass
class LibTrack:
    title: str
    artist: str
    album: str
    path: str
    source: Optional[str]
    external_id: Optional[str]


@dataclass
class PlaylistItem:
    title: str
    artist: str
    album: Optional[str]
    source: Optional[str]
    external_id: Optional[str]


# ----------------------------- Utilities ----------------------------- #

def vprint(msg: str, quiet: bool):
    if not quiet:
        print(msg)


def norm(s: Optional[str]) -> str:
    if not s:
        return ""
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[’']", "", s)
    return s


def parse_songshift_txt(path: str) -> List[PlaylistItem]:
    """
    SongShift TXT lines typically look like:
    Title | Artist | Album |  spotify | <id>
    Header lines starting with ***playlist*** are ignored.
    """
    items: List[PlaylistItem] = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("***"):
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 3:
                continue

            title = parts[0]
            artist = parts[1]
            album = parts[2] if len(parts) >= 3 else None

            source = None
            external_id = None
            if len(parts) >= 5:
                source = parts[-2].lower() if parts[-2] else None
                external_id = parts[-1] if parts[-1] else None

            items.append(
                PlaylistItem(
                    title=title,
                    artist=artist,
                    album=album,
                    source=source,
                    external_id=external_id,
                )
            )
    return items


# ----------------------------- Library Load ----------------------------- #

def load_library_xlsx(xlsx_path: str, quiet: bool) -> Tuple[
    Dict[Tuple[str, str], List[LibTrack]],
    Dict[Tuple[str, str], LibTrack],
    List[LibTrack]
]:
    """
    Builds:
    - id_index[(source, external_id)] -> LibTrack
    - title_artist_index[(title, artist)] -> [LibTrack, ...]
    """
    vprint(f"Loading library from spreadsheet: {xlsx_path}", quiet)
    df = pd.read_excel(xlsx_path)
    df.columns = [c.strip().lower() for c in df.columns]

    # map common alternative column names to canonical ones
    column_aliases = {
        "track title": "title",
        "song": "title",
        "name": "title",

        "artist": "album artist",
        "track artist": "album artist",
        "track artist(s)": "album artist",

        "file": "path",
        "filepath": "path",
        "file path": "path",
        "location": "path",
    }

    df = df.rename(columns={c: column_aliases[c] for c in df.columns if c in column_aliases})

    # --- auto-detect critical columns by heuristic ---
    def find_col(candidates):
        for c in df.columns:
            for k in candidates:
                if k in c:
                    return c
        return None

    col_title = find_col(["title", "track", "song", "name"])
    col_artist = find_col(["album artist", "artist"])
    col_path = find_col(["path", "file", "location"])

    if not col_title or not col_artist or not col_path:
        raise ValueError(
            "Could not auto-detect required columns.\n"
            f"Detected columns: {list(df.columns)}\n"
            f"title={col_title}, artist={col_artist}, path={col_path}"
        )

    id_index: Dict[Tuple[str, str], LibTrack] = {}
    ta_index: Dict[Tuple[str, str], List[LibTrack]] = defaultdict(list)
    all_tracks: List[LibTrack] = []

    for _, r in df.iterrows():
        t = LibTrack(
            title=str(r.get(col_title, "")).strip(),
            artist=str(r.get(col_artist, "")).strip(),
            album=str(r.get("album", "")).strip(),
            path=os.path.abspath(os.path.expanduser(str(r.get(col_path, "")).strip())),
            source=str(r.get("source", "")).lower().strip() if "source" in df.columns and pd.notna(r.get("source", "")) else None,
            external_id=str(r.get("external id", "")).strip() if "external id" in df.columns and pd.notna(r.get("external id", "")) else None,
        )
        if not os.path.isfile(t.path):
            continue
        all_tracks.append(t)

        if t.source and t.external_id:
            id_index[(t.source, t.external_id)] = t

        ta_index[(norm(t.title), norm(t.artist))].append(t)

    vprint(f"Indexed {len(all_tracks)} library tracks", quiet)
    return ta_index, id_index, all_tracks


# ----------------------------- Matching ----------------------------- #

def match_item(
    item: PlaylistItem,
    ta_index: Dict[Tuple[str, str], List[LibTrack]],
    id_index: Dict[Tuple[str, str], LibTrack],
    quiet: bool,
    fuzzy_threshold: int = 92,
) -> Optional[LibTrack]:
    # 1) External ID match (deterministic)
    if item.source and item.external_id:
        key = (item.source.lower(), item.external_id)
        if key in id_index:
            vprint(f"✔ ID match: {item.title}", quiet)
            return id_index[key]

    # 2) Exact title+artist
    key = (norm(item.title), norm(item.artist))
    if key in ta_index and ta_index[key]:
        vprint(f"✔ Exact tag match: {item.title}", quiet)
        return ta_index[key][0]

    # 3) Conservative fuzzy fallback (optional)
    if fuzz is not None:
        best = None
        best_score = 0
        for (t, a), tracks in ta_index.items():
            s1 = fuzz.token_set_ratio(norm(item.title), t)
            s2 = fuzz.token_set_ratio(norm(item.artist), a)
            score = (s1 + s2) // 2
            if score > best_score:
                best_score = score
                best = tracks[0]
        if best and best_score >= fuzzy_threshold:
            vprint(f"✔ Fuzzy match ({best_score}): {item.title}", quiet)
            return best

    vprint(f"✖ Unmatched: {item.title} – {item.artist}", quiet)
    return None


# ----------------------------- Output ----------------------------- #

def write_m3u8(out_path: str, tracks: List[LibTrack], quiet: bool):
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for t in tracks:
            f.write(f"{t.path}\n")
    vprint(f"Wrote M3U8: {out_path} ({len(tracks)} tracks)", quiet)


def write_unmatched(out_path: str, items: List[PlaylistItem], quiet: bool):
    with open(out_path, "w", encoding="utf-8") as f:
        for i in items:
            f.write(f"{i.title} | {i.artist} | {i.album or ''} | {i.source or ''} | {i.external_id or ''}\n")
    vprint(f"Wrote unmatched report: {out_path} ({len(items)} items)", quiet)


# ----------------------------- Main ----------------------------- #

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--txt-dir", help="Directory containing SongShift TXT playlists")
    ap.add_argument("--playlist", help="Single SongShift TXT playlist")
    ap.add_argument("--library-xlsx", required=True)
    ap.add_argument("--out-dir", default=".")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if not args.txt_dir and not args.playlist:
        ap.error("Provide --txt-dir or --playlist")

    ta_index, id_index, _ = load_library_xlsx(args.library_xlsx, args.quiet)

    playlists: List[str] = []
    if args.playlist:
        playlists.append(args.playlist)
    if args.txt_dir:
        for fn in os.listdir(args.txt_dir):
            if fn.lower().endswith(".txt"):
                playlists.append(os.path.join(args.txt_dir, fn))

    for pl in playlists:
        name = os.path.splitext(os.path.basename(pl))[0]
        vprint(f"\n=== Processing playlist: {name} ===", args.quiet)

        items = parse_songshift_txt(pl)
        matched: List[LibTrack] = []
        unmatched: List[PlaylistItem] = []

        for it in items:
            m = match_item(it, ta_index, id_index, args.quiet)
            if m:
                matched.append(m)
            else:
                unmatched.append(it)

        base_dir = os.path.dirname(os.path.abspath(pl))
        out_m3u = os.path.join(base_dir, f"{name}.m3u8")
        out_un = os.path.join(base_dir, f"{name}.unmatched.txt")

        if not matched:
            vprint(f"WARNING: playlist '{name}' produced 0 matched tracks", args.quiet)

        write_m3u8(out_m3u, matched, args.quiet)
        write_unmatched(out_un, unmatched, args.quiet)


if __name__ == "__main__":
    main()