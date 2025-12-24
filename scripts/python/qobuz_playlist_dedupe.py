#!/usr/bin/env python3
"""
Bulk Qobuz playlist deduper (standalone).

- Authenticates against Qobuz's public API using app_id + email + password (MD5).
- Fetches all user playlists.
- Fetches tracks for each playlist.
- Deduplicates tracks within each playlist using:
    1) ISRC (if present)
    2) normalized (artist, title)
    3) track_id as last resort
- Writes:
    - JSON per playlist (deduped)
    - CSV per playlist (deduped)
    - summary.csv for all playlists

NOTE:
Qobuz does not publish stable API docs. Endpoints used here are based on
reverse-engineered usage in clients such as Roon and 3rd-party tools.
You may need to adjust paths or parameters if Qobuz changes them.
"""

import argparse
import csv
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

# -----------------------------
# Configuration defaults
# -----------------------------

QOBUZ_BASE_URL = "https://www.qobuz.com/api.json/0.2"

DEFAULT_LIMIT = 200  # used for pagination in playlist listing


# -----------------------------
# HTTP helper
# -----------------------------

class QobuzAPIError(Exception):
    """Custom exception for Qobuz API errors."""


def qobuz_get(path: str, params: Dict[str, Any], headers: Optional[Dict[str, str]] = None,
              retries: int = 3, backoff: float = 1.0) -> Dict[str, Any]:
    """
    Perform a GET request to Qobuz and return parsed JSON.
    Raises QobuzAPIError on error.
    """
    if headers is None:
        headers = {}

    url = f"{QOBUZ_BASE_URL.rstrip('/')}/{path.lstrip('/')}"
    query = urllib.parse.urlencode(params)
    full_url = f"{url}?{query}"

    last_exc: Optional[Exception] = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(full_url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
            try:
                data = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError as e:
                raise QobuzAPIError(f"Invalid JSON response from {full_url}: {e}") from e

            # Qobuz error format: {"status": "error", "code": ..., "message": "..."}
            if isinstance(data, dict) and data.get("status") == "error":
                code = data.get("code")
                msg = data.get("message", "Unknown error")
                raise QobuzAPIError(f"Qobuz API error {code}: {msg} (URL: {full_url})")

            return data

        except (urllib.error.URLError, urllib.error.HTTPError, QobuzAPIError) as e:
            last_exc = e
            if attempt < retries - 1:
                time.sleep(backoff * (2 ** attempt))
                continue
            raise QobuzAPIError(f"Failed request to {full_url}: {e}") from e

    # Should not reach here
    if last_exc:
        raise QobuzAPIError(str(last_exc))
    raise QobuzAPIError(f"Unknown error in qobuz_get({full_url})")


# -----------------------------
# Authentication
# -----------------------------

def md5_hex(s: str) -> str:
    """Return MD5 hex digest of a string."""
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def qobuz_login(app_id: str, email: str, password: str, password_is_md5: bool = False) -> str:
    """
    Login to Qobuz using email + password (MD5 or plain).

    According to widely used examples, Qobuz accepts:
      GET /user/login?email=...&password=<md5(password)>&app_id=...

    Returns: user_auth_token string.
    """
    if not password_is_md5:
        password_md5 = md5_hex(password)
    else:
        password_md5 = password

    params = {
        "email": email,
        "password": password_md5,
        "app_id": app_id,
    }

    data = qobuz_get("user/login", params)
    user_auth_token = data.get("user_auth_token")
    if not user_auth_token:
        raise QobuzAPIError("Login succeeded but user_auth_token missing in response")
    return user_auth_token


# -----------------------------
# Playlist fetching
# -----------------------------

def get_user_playlists(app_id: str, user_auth_token: str, limit: int = DEFAULT_LIMIT) -> List[Dict[str, Any]]:
    """
    Fetch all user's playlists using pagination.

    Endpoint (reverse-engineered):
      GET /playlist/getUserPlaylists?app_id=...&user_auth_token=...&limit=...&offset=...

    Returns: list of playlist dicts (raw from Qobuz).
    """
    playlists: List[Dict[str, Any]] = []
    offset = 0

    while True:
        params = {
            "app_id": app_id,
            "user_auth_token": user_auth_token,
            "limit": limit,
            "offset": offset,
        }
        data = qobuz_get("playlist/getUserPlaylists", params)

        # Expected shape (based on common clients):
        # { "playlists": { "items": [...], "total": N } }
        container = data.get("playlists") or data
        items = container.get("items") if isinstance(container, dict) else None
        if not items:
            break

        playlists.extend(items)
        total = container.get("total", len(playlists))
        offset += len(items)
        if offset >= total:
            break

    return playlists


def get_playlist_with_tracks(app_id: str, user_auth_token: str, playlist_id: str,
                             track_limit: int = 500) -> Dict[str, Any]:
    """
    Fetch playlist metadata and tracks.

    Endpoint (typical pattern):
      GET /playlist/get?playlist_id=...&app_id=...&user_auth_token=...&extra=tracks&limit=...

    Returns: playlist dict including "tracks" key.
    """
    params = {
        "playlist_id": playlist_id,
        "app_id": app_id,
        "user_auth_token": user_auth_token,
        "extra": "tracks",
        "limit": track_limit,
        "offset": 0,
    }
    data = qobuz_get("playlist/get", params)
    return data


# -----------------------------
# Deduplication logic
# -----------------------------

def normalize_text(s: Optional[str]) -> str:
    if not s:
        return ""
    s = s.strip().lower()
    # basic normalization; you can extend if needed
    return " ".join(s.split())


def build_track_key(track: Dict[str, Any]) -> Tuple[Optional[str], Optional[Tuple[str, str]], str]:
    """
    Build dedupe keys for a track:
      - primary: ISRC (if present)
      - secondary: (artist, title) normalized
      - tertiary: track_id
    """
    isrc = track.get("isrc")
    if isrc:
        isrc = isrc.strip().upper()

    title = normalize_text(track.get("title") or track.get("track_title"))
    # Artist: try nested artist object first, then 'artist' string
    artist_name = ""
    if isinstance(track.get("performer"), dict) and track["performer"].get("name"):
        artist_name = track["performer"]["name"]
    elif isinstance(track.get("artist"), dict) and track["artist"].get("name"):
        artist_name = track["artist"]["name"]
    elif isinstance(track.get("artist"), str):
        artist_name = track["artist"]
    artist_norm = normalize_text(artist_name)

    secondary = (artist_norm, title) if artist_norm or title else None

    track_id = str(track.get("id") or track.get("track_id") or "")
    return isrc, secondary, track_id


def dedupe_playlist_tracks(tracks: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    """
    Deduplicate tracks in a playlist.

    Returns:
      (deduped_tracks, duplicates_removed)
    """
    seen_isrc: set = set()
    seen_artist_title: set = set()
    seen_track_id: set = set()

    deduped: List[Dict[str, Any]] = []
    duplicates_removed = 0

    for track in tracks:
        isrc, secondary, track_id = build_track_key(track)

        duplicate = False

        if isrc and isrc in seen_isrc:
            duplicate = True
        elif secondary and secondary in seen_artist_title:
            duplicate = True
        elif track_id and track_id in seen_track_id:
            duplicate = True

        if duplicate:
            duplicates_removed += 1
            continue

        if isrc:
            seen_isrc.add(isrc)
        if secondary:
            seen_artist_title.add(secondary)
        if track_id:
            seen_track_id.add(track_id)

        deduped.append(track)

    return deduped, duplicates_removed


# -----------------------------
# Output helpers
# -----------------------------

def safe_filename(name: str) -> str:
    name = name.strip()
    forbidden = '<>:"/\\|?*'
    for ch in forbidden:
        name = name.replace(ch, "_")
    if not name:
        name = "unnamed_playlist"
    return name


def write_playlist_json(out_dir: str, playlist_name: str, playlist_payload: Dict[str, Any]) -> str:
    os.makedirs(out_dir, exist_ok=True)
    filename = safe_filename(playlist_name) + ".json"
    path = os.path.join(out_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(playlist_payload, f, ensure_ascii=False, indent=2)
    return path


def write_playlist_csv(out_dir: str, playlist_name: str, playlist_id: str,
                       tracks: List[Dict[str, Any]]) -> str:
    os.makedirs(out_dir, exist_ok=True)
    filename = safe_filename(playlist_name) + ".csv"
    path = os.path.join(out_dir, filename)

    fieldnames = [
        "playlist_name",
        "playlist_id",
        "position",
        "track_id",
        "isrc",
        "artist",
        "title",
        "album",
        "duration_seconds",
        "qobuz_url",
    ]

    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for idx, track in enumerate(tracks, start=1):
            track_id = track.get("id") or track.get("track_id")
            isrc = track.get("isrc")
            title = track.get("title") or track.get("track_title")
            duration = track.get("duration") or track.get("duration_ms", 0) // 1000

            artist_name = ""
            if isinstance(track.get("performer"), dict) and track["performer"].get("name"):
                artist_name = track["performer"]["name"]
            elif isinstance(track.get("artist"), dict) and track["artist"].get("name"):
                artist_name = track["artist"]["name"]
            elif isinstance(track.get("artist"), str):
                artist_name = track["artist"]

            album_title = ""
            if isinstance(track.get("album"), dict) and track["album"].get("title"):
                album_title = track["album"]["title"]
            elif isinstance(track.get("release"), dict) and track["release"].get("title"):
                album_title = track["release"]["title"]

            url = track.get("url") or track.get("permalink") or ""

            writer.writerow({
                "playlist_name": playlist_name,
                "playlist_id": playlist_id,
                "position": idx,
                "track_id": track_id,
                "isrc": isrc,
                "artist": artist_name,
                "title": title,
                "album": album_title,
                "duration_seconds": duration,
                "qobuz_url": url,
            })

    return path


def write_summary_csv(out_dir: str, summary_rows: List[Dict[str, Any]]) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "summary.csv")
    fieldnames = [
        "playlist_id",
        "playlist_name",
        "track_count_original",
        "track_count_deduped",
        "duplicates_removed",
    ]
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in summary_rows:
            writer.writerow(row)
    return path


# -----------------------------
# Main workflow
# -----------------------------

def process_all_playlists(app_id: str,
                          email: str,
                          password: str,
                          password_is_md5: bool,
                          output_dir: str,
                          include_empty: bool = False) -> None:
    """
    Main pipeline:
      - login
      - fetch playlists
      - fetch tracks per playlist
      - dedupe
      - write outputs
    """
    print("Logging into Qobuz...")
    token = qobuz_login(app_id, email, password, password_is_md5=password_is_md5)
    print("Login successful.")

    print("Fetching user playlists...")
    playlists = get_user_playlists(app_id, token)
    print(f"Found {len(playlists)} playlists.")

    if not playlists:
        print("No playlists found. Exiting.")
        return

    json_dir = os.path.join(output_dir, "json")
    csv_dir = os.path.join(output_dir, "csv")

    summary_rows: List[Dict[str, Any]] = []

    for idx, pl in enumerate(playlists, start=1):
        playlist_id = str(pl.get("id") or pl.get("playlist_id") or "")
        playlist_name = pl.get("name") or pl.get("title") or f"playlist_{playlist_id or idx}"

        print(f"[{idx}/{len(playlists)}] Fetching playlist '{playlist_name}' (id={playlist_id})...")

        pl_full = get_playlist_with_tracks(app_id, token, playlist_id)
        tracks_container = pl_full.get("tracks") or {}
        tracks_items = tracks_container.get("items") if isinstance(tracks_container, dict) else None
        if tracks_items is None:
            # some variants may use "tracks" directly as list
            if isinstance(tracks_container, list):
                tracks_items = tracks_container
            else:
                tracks_items = []

        original_count = len(tracks_items)
        if original_count == 0 and not include_empty:
            print(f"  - Playlist has 0 tracks, skipping outputs.")
            continue

        deduped_tracks, removed = dedupe_playlist_tracks(tracks_items)
        deduped_count = len(deduped_tracks)

        print(f"  - Original: {original_count} tracks, deduped: {deduped_count}, removed: {removed}")

        # replace tracks in payload for JSON output (keep structure)
        if isinstance(pl_full.get("tracks"), dict):
            pl_full["tracks"]["items"] = deduped_tracks
        elif isinstance(pl_full.get("tracks"), list):
            pl_full["tracks"] = deduped_tracks
        else:
            pl_full["tracks"] = {"items": deduped_tracks}

        json_path = write_playlist_json(json_dir, playlist_name, pl_full)
        csv_path = write_playlist_csv(csv_dir, playlist_name, playlist_id, deduped_tracks)

        print(f"  - Wrote JSON: {json_path}")
        print(f"  - Wrote CSV:  {csv_path}")

        summary_rows.append({
            "playlist_id": playlist_id,
            "playlist_name": playlist_name,
            "track_count_original": original_count,
            "track_count_deduped": deduped_count,
            "duplicates_removed": removed,
        })

    summary_path = write_summary_csv(output_dir, summary_rows)
    print(f"\nSummary written to: {summary_path}")
    print("Done.")


# -----------------------------
# CLI
# -----------------------------

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bulk Qobuz playlist deduper (standalone)."
    )

    parser.add_argument(
        "--app-id",
        required=True,
        help="Qobuz application ID (APP_ID)."
    )
    parser.add_argument(
        "--email",
        required=True,
        help="Qobuz account email/username."
    )
    parser.add_argument(
        "--password",
        required=True,
        help="Qobuz account password (plain text or MD5, see --password-is-md5)."
    )
    parser.add_argument(
        "--password-is-md5",
        action="store_true",
        help="Treat --password as an MD5 hex digest instead of plain text."
    )
    parser.add_argument(
        "--output-dir",
        default="qobuz_playlists_deduped",
        help="Directory to write outputs (JSON, CSV, summary). Default: %(default)s"
    )
    parser.add_argument(
        "--include-empty",
        action="store_true",
        help="Also write outputs for empty playlists (default: skip them)."
    )

    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    try:
        process_all_playlists(
            app_id=args.app_id,
            email=args.email,
            password=args.password,
            password_is_md5=args.password_is_md5,
            output_dir=args.output_dir,
            include_empty=args.include_empty,
        )
        return 0
    except QobuzAPIError as e:
        sys.stderr.write(f"Qobuz API error: {e}\n")
        return 1
    except KeyboardInterrupt:
        sys.stderr.write("Interrupted by user.\n")
        return 2


if __name__ == "__main__":
    sys.exit(main())
