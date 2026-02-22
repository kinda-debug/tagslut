from __future__ import annotations

import csv
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from tagslut.dj.transcode import TrackRow, build_output_path, make_dedupe_key

log = logging.getLogger(__name__)


@dataclass
class LexiconTrack:
    path: str
    artist: str
    title: str
    verdict: str
    reason: str
    crate: str
    bpm: float | None = None
    key: str | None = None
    genre: str | None = None
    duration_sec: float | None = None


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def _detect_columns(rows: list[dict[str, Any]]) -> dict[str, str | None]:
    if not rows:
        return {"path": None, "artist": None, "title": None, "bpm": None, "key": None, "genre": None, "duration": None, "album": None}
    keys = [k for k in rows[0].keys()]
    norm_map = {k: _normalize(k) for k in keys}

    def find_key(candidates: list[str]) -> str | None:
        for key, norm in norm_map.items():
            for cand in candidates:
                if cand in norm:
                    return key
        return None

    return {
        "path": find_key(["path", "source_path", "file_path"]),
        "artist": find_key(["artist", "track_artist", "trackartist", "performer"]),
        "title": find_key(["title", "track", "name"]),
        "bpm": find_key(["bpm", "tempo", "canonical_bpm"]),
        "key": find_key(["key", "camelot", "canonical_key"]),
        "genre": find_key(["genre", "genre_raw", "canonical_genre", "track_genre", "big_genre"]),
        "duration": find_key(["duration", "duration_s", "duration_sec", "duration_seconds", "length"]),
        "album": find_key(["album", "release", "album_name"]),
    }


def _latest_scan_report() -> Path | None:
    candidates = list(Path("output/spreadsheet").glob("dj*scan_report*.csv"))
    if not candidates:
        return None

    def extract_ts(name: str) -> tuple[int, str]:
        m = re.search(r"(\d{8}_\d{6})", name)
        if m:
            return (0, m.group(1))
        m = re.search(r"(\d{8})", name)
        if m:
            return (1, m.group(1))
        return (2, "")

    def key(p: Path):
        kind, ts = extract_ts(p.name)
        if ts:
            return (kind, ts)
        return (3, f"{p.stat().st_mtime:.0f}")

    return sorted(candidates, key=key)[-1]


def load_scan_report() -> tuple[list[dict[str, Any]], dict[str, str | None]]:
    path = _latest_scan_report()
    if path is None:
        return [], {"path": None, "artist": None, "title": None, "bpm": None, "key": None, "genre": None, "duration": None, "album": None}
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append({k.strip(): v for k, v in row.items()})
    columns = _detect_columns(rows)
    return rows, columns


def load_track_overrides(path: Path) -> list[LexiconTrack]:
    tracks: list[LexiconTrack] = []
    if not path.exists():
        return tracks
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.reader(handle)
        for row in reader:
            if not row:
                continue
            if row[0].strip().startswith("#"):
                continue
            while len(row) < 6:
                row.append("")
            path_value, artist, title, verdict, reason, crate = [cell.strip() for cell in row[:6]]
            if verdict.lower() != "safe":
                continue
            tracks.append(
                LexiconTrack(
                    path=path_value,
                    artist=artist,
                    title=title,
                    verdict=verdict,
                    reason=reason,
                    crate=crate,
                )
            )
    return tracks


def _scan_index(rows: list[dict[str, Any]], columns: dict[str, str | None]) -> dict[str, dict[str, Any]]:
    by_path: dict[str, dict[str, Any]] = {}
    by_artist_title: dict[str, dict[str, Any]] = {}

    path_col = columns.get("path")
    artist_col = columns.get("artist")
    title_col = columns.get("title")

    for row in rows:
        if path_col and row.get(path_col):
            by_path[str(row[path_col]).strip().lower()] = row
        if artist_col and title_col and row.get(artist_col) and row.get(title_col):
            key = f"{_normalize(str(row[artist_col]))}|{_normalize(str(row[title_col]))}"
            by_artist_title[key] = row

    return {"by_path": by_path, "by_artist_title": by_artist_title}


def _enrich(track: LexiconTrack, scan_index: dict[str, dict[str, Any]], columns: dict[str, str | None]) -> None:
    row = None
    if track.path:
        row = scan_index["by_path"].get(track.path.lower())
    if row is None:
        key = f"{_normalize(track.artist)}|{_normalize(track.title)}"
        row = scan_index["by_artist_title"].get(key)
    if row is None:
        return

    bpm_col = columns.get("bpm")
    key_col = columns.get("key")
    genre_col = columns.get("genre")
    duration_col = columns.get("duration")
    if bpm_col:
        track.bpm = _parse_float(row.get(bpm_col))
    if key_col:
        key_val = str(row.get(key_col) or "").strip()
        track.key = key_val if key_val else None
    if genre_col:
        genre_val = str(row.get(genre_col) or "").strip()
        track.genre = genre_val if genre_val else None
    if duration_col:
        track.duration_sec = _parse_float(row.get(duration_col))


def load_lexicon_tracks(overrides_path: Path) -> list[LexiconTrack]:
    tracks = load_track_overrides(overrides_path)
    rows, columns = load_scan_report()
    if rows:
        index = _scan_index(rows, columns)
        for track in tracks:
            _enrich(track, index, columns)
    return tracks


def _clamp(value: int, low: int = 1, high: int = 10) -> int:
    return max(low, min(high, value))


def estimate_tags(track: dict[str, Any]) -> dict[str, Any]:
    bpm = track.get("bpm")
    key = track.get("key")
    genre = track.get("genre") or ""
    genre_lower = str(genre).lower()

    energy = 5
    if isinstance(bpm, (int, float)):
        if bpm < 110:
            energy = 3
        elif 110 <= bpm <= 119:
            energy = 5
        elif 120 <= bpm <= 124:
            energy = 6
        elif 125 <= bpm <= 129:
            energy = 7
        elif 130 <= bpm <= 135:
            energy = 8
        elif 136 <= bpm <= 145:
            energy = 9
        else:
            energy = 10

    if "ambient" in genre_lower or "downtempo" in genre_lower:
        energy = min(energy, 4)
    if "melodic" in genre_lower:
        energy -= 1
    if "hard" in genre_lower or "acid" in genre_lower or "peak" in genre_lower:
        energy += 1

    energy = _clamp(int(round(energy)))

    danceability = energy
    if any(g in genre_lower for g in ["techno", "house", "disco", "funk"]):
        danceability += 1
    if any(g in genre_lower for g in ["ambient", "electronica"]):
        danceability -= 2
    danceability = _clamp(int(round(danceability)))

    happiness = 5
    if isinstance(key, str) and key.strip():
        if key.strip().upper().endswith("A"):
            happiness = 4
        elif key.strip().upper().endswith("B"):
            happiness = 7
    if any(g in genre_lower for g in ["disco", "funk", "soul"]):
        happiness += 1
    if any(g in genre_lower for g in ["dark", "acid", "industrial"]):
        happiness -= 1
    happiness = _clamp(int(round(happiness)))

    comment_parts = []
    if key:
        comment_parts.append(str(key))
    if bpm is not None:
        comment_parts.append(f"{int(round(bpm))} BPM")
    crate = track.get("crate")
    if crate:
        comment_parts.append(str(crate))
    comment = " | ".join(comment_parts)

    if energy <= 2:
        rating = 1
    elif energy <= 4:
        rating = 2
    elif energy <= 6:
        rating = 3
    elif energy <= 8:
        rating = 4
    else:
        rating = 5

    confidence = "low"
    if bpm is not None:
        confidence = "medium"
        if key and genre:
            confidence = "high"

    return {
        "Energy": energy,
        "Danceability": danceability,
        "Happiness": happiness,
        "Comment": comment,
        "Rating": rating,
        "Key": key or "",
        "confidence": confidence,
    }


def _load_export_manifest(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    mapping: dict[str, str] = {}
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            artist = str(row.get("artist") or "").strip()
            title = str(row.get("title") or "").strip()
            location = str(row.get("path") or "").strip()
            if artist and title and location:
                key = f"{_normalize(artist)}|{_normalize(title)}"
                mapping[key] = location
    return mapping


def build_location_map(output_root: Path) -> dict[str, str]:
    manifest_path = output_root / "export_manifest.jsonl"
    return _load_export_manifest(manifest_path)


def resolve_location(track: dict[str, Any], output_root: Path, manifest: dict[str, str]) -> str:
    key = f"{_normalize(track['artist'])}|{_normalize(track['title'])}"
    location = manifest.get(key)
    if location:
        return location

    source_path = Path(track["path"])
    track_row = TrackRow(
        row_num=0,
        album_artist=str(track.get("artist") or ""),
        album=str(track.get("album") or ""),
        track_number=None,
        title=str(track.get("title") or ""),
        track_artist=str(track.get("artist") or ""),
        external_id="",
        source="lexicon",
        source_path=source_path,
        dedupe_key=("",),
    )
    track_row.dedupe_key = make_dedupe_key(track_row)
    return str(build_output_path(output_root, track_row))


def write_lexicon_csv(tracks: list[dict[str, Any]], output_path: Path, output_root: Path) -> int:
    manifest = build_location_map(output_root)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "Location",
            "Title",
            "Artist",
            "Energy",
            "Danceability",
            "Happiness",
            "Comment",
            "Rating",
            "Key",
        ])

        for track in tracks:
            tags = estimate_tags(track)
            location = resolve_location(track, output_root, manifest)

            writer.writerow([
                location,
                track.get("title") or "",
                track.get("artist") or "",
                tags["Energy"],
                tags["Danceability"],
                tags["Happiness"],
                tags["Comment"],
                tags["Rating"],
                tags["Key"],
            ])
    return len(tracks)


def push_to_lexicon_api(tracks: list[dict[str, Any]], *, only_high: bool = False, dry_run: bool = False) -> dict[str, int]:
    url = "http://localhost:48624/v1/tracks"
    try:
        import requests  # type: ignore
    except Exception:
        requests = None

    if requests is None:
        print("lexicon-python/requests not available. Use CSV mode instead.")
        return {"pushed": 0, "skipped": len(tracks), "failed": 0}

    try:
        resp = requests.get(url, timeout=3)
    except Exception as exc:
        print(f"Lexicon API not reachable: {exc}. Use CSV mode instead.")
        return {"pushed": 0, "skipped": len(tracks), "failed": 0}

    if resp.status_code >= 400:
        print(f"Lexicon API returned {resp.status_code}. Use CSV mode instead.")
        return {"pushed": 0, "skipped": len(tracks), "failed": 0}

    pushed = 0
    skipped = 0
    failed = 0

    for idx, track in enumerate(tracks, start=1):
        tags = estimate_tags(track)
        if only_high and tags["confidence"] != "high":
            skipped += 1
            continue
        if dry_run:
            skipped += 1
            continue

        payload = {
            "location": track.get("location") or "",
            "artist": track.get("artist") or "",
            "title": track.get("title") or "",
            "Energy": tags["Energy"],
            "Danceability": tags["Danceability"],
            "Happiness": tags["Happiness"],
            "Comment": tags["Comment"],
            "Rating": tags["Rating"],
            "Key": tags["Key"],
        }

        try:
            r = requests.patch(url, json=payload, timeout=5)
        except Exception:
            failed += 1
            continue
        if r.status_code >= 400:
            failed += 1
        else:
            pushed += 1

        if idx % 50 == 0:
            print(f"Pushed {idx}/{len(tracks)} tracks")

    return {"pushed": pushed, "skipped": skipped, "failed": failed}
