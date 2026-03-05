#!/usr/bin/env python3
"""
Fetch ISRCs from MusicBrainz for local MP3 files and optionally write TSRC tags.

Inputs:
  - M3U/M3U8 playlist of file paths, OR
  - a CSV with a 'path' column

Matching strategy:
  1) Query MusicBrainz recording search using title + artist (+ album if present).
  2) If no ISRC found, retry with relaxed query (drop album, normalize remix/feat).
  3) Pick best match by highest score and closest duration (if available).

Safety:
  - Default is dry-run (no writes).
  - Writes only TSRC (ISRC) tag when --execute is used.
  - Respects MusicBrainz rate limit (1 request/sec) and requires a User-Agent.

Example:
  python tools/metadata_scripts/fetch_isrcs_musicbrainz.py \\
    --playlist /path/to/isrc_missing.m3u8 \\
    --user-agent "tagslut/1.0 (contact: you@example.com)" \\
    --out artifacts/isrc_fetch_report.csv \\
    --execute
"""
from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path
from typing import Iterable, Optional

import httpx
from mutagen.id3 import ID3, ID3NoHeaderError, TSRC


MB_BASE = "https://musicbrainz.org/ws/2"


def _read_paths_from_playlist(path: Path) -> list[Path]:
    paths: list[Path] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        paths.append(Path(line))
    return paths


def _read_paths_from_csv(path: Path) -> list[Path]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if "path" not in reader.fieldnames:
            raise SystemExit("CSV must contain a 'path' column.")
        return [Path(row["path"]) for row in reader if row.get("path")]


def _get_id3(path: Path) -> Optional[ID3]:
    try:
        return ID3(path)
    except ID3NoHeaderError:
        return ID3()
    except Exception:
        return None


def _first_text(tags: ID3, key: str) -> str:
    if key in tags:
        val = tags.get(key)
        if hasattr(val, "text") and val.text:
            return str(val.text[0]).strip()
    return ""


def _norm(s: str) -> str:
    return " ".join((s or "").strip().split())


def _normalize_title(title: str) -> str:
    # Remove common remix/feat decorations for relaxed search
    s = _norm(title)
    s = s.replace("feat.", "").replace("featuring", "").replace("ft.", "")
    s = s.replace("remix", "").replace("mix", "")
    return _norm(s)


def _build_query(title: str, artist: str, album: str) -> str:
    # MusicBrainz Lucene query: field:"value"
    parts = []
    if title:
        parts.append(f'recording:"{title}"')
    if artist:
        parts.append(f'artist:"{artist}"')
    if album:
        parts.append(f'release:"{album}"')
    return " AND ".join(parts)


def _pick_best(recordings: list[dict], duration_ms: Optional[int]) -> Optional[dict]:
    if not recordings:
        return None
    # Prefer higher score, then closest duration
    def score_key(r: dict) -> tuple[int, int]:
        score = int(r.get("score") or 0)
        if duration_ms is None or r.get("length") is None:
            return (score, 0)
        diff = abs(int(r["length"]) - duration_ms)
        # smaller diff should rank higher -> invert
        return (score, -diff)

    return max(recordings, key=score_key)


def _duration_ms_from_ffprobe(path: Path) -> Optional[int]:
    # Use ffprobe to get duration if available
    import subprocess
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=duration",
        "-of",
        "default=nk=1:nw=1",
        str(path),
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            return None
        val = (res.stdout or "").strip()
        if not val:
            return None
        return int(float(val) * 1000)
    except Exception:
        return None


def fetch_isrc_for_track(
    client: httpx.Client,
    *,
    title: str,
    artist: str,
    album: str,
    duration_ms: Optional[int],
) -> Optional[str]:
    # Full query
    query = _build_query(title, artist, album)
    if not query:
        return None
    params = {"query": query, "fmt": "json", "limit": 5}
    resp = client.get(f"{MB_BASE}/recording", params=params, timeout=30.0)
    resp.raise_for_status()
    data = resp.json()
    recordings = data.get("recordings") or []
    best = _pick_best(recordings, duration_ms)
    if best and (best.get("isrcs") or []):
        return best["isrcs"][0]

    # Relaxed query (drop album, normalize title)
    relaxed_title = _normalize_title(title)
    relaxed_query = _build_query(relaxed_title, artist, "")
    if not relaxed_query:
        return None
    params = {"query": relaxed_query, "fmt": "json", "limit": 5}
    resp = client.get(f"{MB_BASE}/recording", params=params, timeout=30.0)
    resp.raise_for_status()
    data = resp.json()
    recordings = data.get("recordings") or []
    best = _pick_best(recordings, duration_ms)
    if not best:
        return None
    isrcs = best.get("isrcs") or []
    return isrcs[0] if isrcs else None


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch ISRCs from MusicBrainz for MP3 files.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--playlist", type=Path, help="M3U/M3U8 file with absolute paths")
    src.add_argument("--csv", type=Path, help="CSV with a 'path' column")
    ap.add_argument("--user-agent", required=True, help="User-Agent per MusicBrainz policy")
    ap.add_argument("--out", type=Path, default=Path("artifacts/isrc_fetch_report.csv"))
    ap.add_argument("--limit", type=int, help="Limit number of files")
    ap.add_argument("--sleep", type=float, default=1.1, help="Seconds between requests (default 1.1)")
    ap.add_argument("--execute", action="store_true", help="Write TSRC tags to files")
    args = ap.parse_args()

    if args.playlist:
        paths = _read_paths_from_playlist(args.playlist)
    else:
        paths = _read_paths_from_csv(args.csv)

    if args.limit:
        paths = paths[: args.limit]

    args.out.parent.mkdir(parents=True, exist_ok=True)

    with httpx.Client(headers={"User-Agent": args.user_agent}) as client, args.out.open(
        "w", newline="", encoding="utf-8"
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["path", "status", "title", "artist", "album", "isrc"],
        )
        writer.writeheader()

        for idx, path in enumerate(paths, start=1):
            if not path.exists():
                writer.writerow({"path": str(path), "status": "missing"})
                continue

            tags = _get_id3(path)
            if tags is None:
                writer.writerow({"path": str(path), "status": "tag_read_error"})
                continue

            title = _norm(_first_text(tags, "TIT2"))
            artist = _norm(_first_text(tags, "TPE1"))
            album = _norm(_first_text(tags, "TALB"))
            duration_ms = _duration_ms_from_ffprobe(path)

            try:
                isrc = fetch_isrc_for_track(
                    client,
                    title=title,
                    artist=artist,
                    album=album,
                    duration_ms=duration_ms,
                )
            except Exception:
                writer.writerow(
                    {
                        "path": str(path),
                        "status": "mb_error",
                        "title": title,
                        "artist": artist,
                        "album": album,
                        "isrc": "",
                    }
                )
                time.sleep(args.sleep)
                continue

            if isrc and args.execute:
                tags["TSRC"] = TSRC(encoding=3, text=isrc)
                tags.save(path, v2_version=3)

            writer.writerow(
                {
                    "path": str(path),
                    "status": "found" if isrc else "not_found",
                    "title": title,
                    "artist": artist,
                    "album": album,
                    "isrc": isrc or "",
                }
            )

            if idx < len(paths):
                time.sleep(args.sleep)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
