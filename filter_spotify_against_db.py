#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


def _load_spotify_export(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
        raise ValueError(
            f"Unexpected JSON shape in {path}. Expected a list with exactly one object."
        )
    if "tracks" not in data[0] or not isinstance(data[0]["tracks"], list):
        raise ValueError(f"Unexpected JSON shape in {path}. Missing list field 'tracks'.")
    return data[0]


def _normalize_isrc(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    return value or None


_ISRC_RE = re.compile(r"\b[A-Z]{2}[A-Z0-9]{3}[0-9]{2}[0-9]{5}\b", re.IGNORECASE)

_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^a-z0-9\s]+")


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    text = value.strip().lower()
    if not text:
        return ""
    text = text.replace("&", " and ")
    text = text.replace("’", "'")
    text = _PUNCT_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    return text


def _track_key(artist: Any, title: Any) -> str:
    a = _normalize_text(artist)
    t = _normalize_text(title)
    if not a and not t:
        return ""
    return f"{a} | {t}".strip()


def _bucket_key(artist: str, title: str) -> str:
    a = _normalize_text(artist)
    t = _normalize_text(title)
    return f"{a[:4]}:{t[:4]}"


def _extract_isrc_from_filename(path: Path) -> str | None:
    m = _ISRC_RE.search(path.stem)
    if not m:
        return None
    return m.group(0).upper()


def _extract_artist_title_from_filename(path: Path) -> tuple[str | None, str | None]:
    stem = path.stem
    if " - " in stem:
        left, right = stem.split(" - ", 1)
        artist = left.strip() or None
        title = right.strip() or None
        return artist, title
    return None, None


def _extract_isrc_from_tags(path: Path) -> str | None:
    try:
        from mutagen import File as MutagenFile  # type: ignore
    except Exception:
        return None

    try:
        audio = MutagenFile(str(path), easy=False)
    except Exception:
        return None
    if audio is None:
        return None

    tags = getattr(audio, "tags", None)
    if tags is None:
        return None

    # ID3 (MP3, AIFF/WAV with ID3): TSRC frame
    getall = getattr(tags, "getall", None)
    if callable(getall):
        for frame_key in ("TSRC", "ISRC"):
            try:
                frames = tags.getall(frame_key)
            except Exception:
                frames = []
            for frame in frames or []:
                text = getattr(frame, "text", None)
                if isinstance(text, (list, tuple)) and text:
                    candidate = _normalize_isrc(text[0])
                    if candidate:
                        m = _ISRC_RE.search(candidate)
                        if m:
                            return m.group(0).upper()
                candidate = _normalize_isrc(frame)
                if candidate:
                    m = _ISRC_RE.search(candidate)
                    if m:
                        return m.group(0).upper()

    # MP4 (M4A): commonly stored as iTunes freeform atom
    for key in (
        "----:com.apple.iTunes:ISRC",
        "----:com.apple.iTunes:TSRC",
        "ISRC",
        "TSRC",
        "isrc",
        "tsrc",
    ):
        try:
            raw = tags.get(key)  # type: ignore[attr-defined]
        except Exception:
            raw = None
        if raw is None:
            continue
        values = raw if isinstance(raw, (list, tuple)) else [raw]
        for value in values:
            if isinstance(value, (bytes, bytearray)):
                try:
                    value = value.decode("utf-8", errors="ignore")
                except Exception:
                    value = ""
            candidate = _normalize_isrc(value)
            if not candidate:
                continue
            m = _ISRC_RE.search(candidate)
            if m:
                return m.group(0).upper()

    # Vorbis-style comments / generic mappings
    try:
        items = tags.items()  # type: ignore[attr-defined]
    except Exception:
        items = []
    lowered = {str(k).lower(): v for k, v in items}
    for k in ("isrc", "tsrc"):
        raw = lowered.get(k)
        if raw is None:
            continue
        values = raw if isinstance(raw, (list, tuple)) else [raw]
        for value in values:
            candidate = _normalize_isrc(value)
            if not candidate:
                continue
            m = _ISRC_RE.search(candidate)
            if m:
                return m.group(0).upper()

    return None


def _extract_isrc(path: Path) -> str | None:
    return _extract_isrc_from_tags(path) or _extract_isrc_from_filename(path)


def _extract_artist_title_from_tags(path: Path) -> tuple[str | None, str | None]:
    try:
        from mutagen import File as MutagenFile  # type: ignore
    except Exception:
        return None, None

    try:
        audio = MutagenFile(str(path), easy=False)
    except Exception:
        return None, None
    if audio is None:
        return None, None

    tags = getattr(audio, "tags", None)
    if tags is None:
        return None, None

    # Vorbis/MP4-style mappings
    try:
        items = tags.items()  # type: ignore[attr-defined]
    except Exception:
        items = []
    lowered = {str(k).lower(): v for k, v in items}

    def _first(v: Any) -> str | None:
        if v is None:
            return None
        values = v if isinstance(v, (list, tuple)) else [v]
        if not values:
            return None
        value = values[0]
        if isinstance(value, (bytes, bytearray)):
            try:
                value = value.decode("utf-8", errors="ignore")
            except Exception:
                value = ""
        s = str(value).strip()
        return s or None

    artist = _first(lowered.get("artist") or lowered.get("albumartist"))
    title = _first(lowered.get("title"))
    return artist, title


def _extract_artist_title(path: Path) -> tuple[str | None, str | None]:
    artist, title = _extract_artist_title_from_tags(path)
    if artist or title:
        return artist, title
    return _extract_artist_title_from_filename(path)


def _db_has_isrc(conn: sqlite3.Connection, isrc: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        WHERE
            EXISTS (SELECT 1 FROM track_identity WHERE isrc = ?)
            OR EXISTS (SELECT 1 FROM library_tracks WHERE isrc = ?)
            OR EXISTS (SELECT 1 FROM files WHERE isrc = ?)
        LIMIT 1
        """,
        (isrc, isrc, isrc),
    ).fetchone()
    return row is not None


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Filter a Spotify JSON export against a tagslut DB or a local music folder by ISRC."
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Path to Spotify JSON export (e.g. Indie_spotify.json).",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Path to tagslut SQLite DB (defaults to TAGSLUT_DB).",
    )
    parser.add_argument(
        "--music-root",
        type=Path,
        default=None,
        help="Scan this folder for non-FLAC audio files and match by embedded ISRC tags.",
    )
    parser.add_argument(
        "--fuzzy",
        action="store_true",
        help="Enable fuzzy artist/title matching against scanned files when ISRC isn't found.",
    )
    parser.add_argument(
        "--fuzzy-threshold",
        type=int,
        default=92,
        help="Fuzzy match threshold (0-100). Default: 92.",
    )
    parser.add_argument(
        "--removed-out",
        type=Path,
        default=None,
        help="Output path for removed (matched) tracks JSON.",
    )
    parser.add_argument(
        "--clean-out",
        type=Path,
        default=None,
        help="Output path for clean (unmatched) tracks JSON.",
    )
    args = parser.parse_args()

    input_path = args.input.expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    music_root = args.music_root.expanduser().resolve() if args.music_root is not None else None
    if music_root is not None and not music_root.exists():
        raise FileNotFoundError(f"Music root not found: {music_root}")

    removed_out = (
        args.removed_out
        or input_path.with_name(f"{input_path.stem}.removed{input_path.suffix}")
    )
    clean_out = (
        args.clean_out
        or input_path.with_name(f"{input_path.stem}.clean{input_path.suffix}")
    )
    removed_out = removed_out.expanduser().resolve()
    clean_out = clean_out.expanduser().resolve()

    playlist = _load_spotify_export(input_path)
    tracks: list[dict[str, Any]] = playlist["tracks"]

    removed_tracks: list[dict[str, Any]] = []
    clean_tracks: list[dict[str, Any]] = []

    if music_root is not None:
        threshold = int(args.fuzzy_threshold)
        if threshold < 0 or threshold > 100:
            raise SystemExit("--fuzzy-threshold must be between 0 and 100.")

        target_isrcs = {i for i in (_normalize_isrc(t.get("isrc")) for t in tracks) if i}
        target_isrcs = {i.upper() for i in target_isrcs if i}
        found_isrcs: set[str] = set()

        spotify_keys: list[str] = []
        bucket_to_indices: dict[str, list[int]] = {}
        if args.fuzzy:
            for idx, track in enumerate(tracks):
                key = _track_key(track.get("artist"), track.get("track"))
                spotify_keys.append(key)
                if not key:
                    continue
                b = _bucket_key(track.get("artist") or "", track.get("track") or "")
                bucket_to_indices.setdefault(b, []).append(idx)
        else:
            spotify_keys = [""] * len(tracks)

        matched_by_fuzzy: set[int] = set()

        audio_exts = {".mp3", ".m4a", ".aac", ".wav", ".aif", ".aiff"}
        for path in music_root.rglob("*"):
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            if suffix == ".flac":
                continue
            if suffix not in audio_exts:
                continue
            isrc = _extract_isrc(path)
            if not isrc:
                if not args.fuzzy:
                    continue
            if isrc:
                isrc = isrc.upper()
                if isrc in target_isrcs:
                    found_isrcs.add(isrc)

            if args.fuzzy:
                artist, title = _extract_artist_title(path)
                file_key = _track_key(artist, title)
                if file_key:
                    b = _bucket_key(artist or "", title or "")
                    candidates = bucket_to_indices.get(b, [])
                    best_idx: int | None = None
                    best_score = 0.0
                    for idx in candidates:
                        if idx in matched_by_fuzzy:
                            continue
                        s = _similarity(file_key, spotify_keys[idx])
                        if s > best_score:
                            best_score = s
                            best_idx = idx
                    if best_idx is not None and (best_score * 100.0) >= float(threshold):
                        matched_by_fuzzy.add(best_idx)

            if (len(found_isrcs) + len(matched_by_fuzzy)) >= len(tracks):
                break

        for idx, track in enumerate(tracks):
            isrc = _normalize_isrc(track.get("isrc"))
            if isrc and isrc.upper() in found_isrcs:
                removed_tracks.append(track)
            elif args.fuzzy and idx in matched_by_fuzzy:
                removed_tracks.append(track)
            else:
                clean_tracks.append(track)
    else:
        db_path = args.db
        if db_path is None:
            env_db = os.getenv("TAGSLUT_DB")
            if not env_db:
                raise SystemExit("Missing --db / --music-root and TAGSLUT_DB is not set.")
            db_path = Path(env_db)
        db_path = db_path.expanduser().resolve()
        if not db_path.exists():
            raise FileNotFoundError(f"DB file not found: {db_path}")

        conn = sqlite3.connect(str(db_path))
        try:
            conn.row_factory = sqlite3.Row
            for track in tracks:
                isrc = _normalize_isrc(track.get("isrc"))
                if isrc and _db_has_isrc(conn, isrc):
                    removed_tracks.append(track)
                else:
                    clean_tracks.append(track)
        finally:
            conn.close()

    removed_payload = dict(playlist)
    removed_payload["tracks"] = removed_tracks

    clean_payload = dict(playlist)
    clean_payload["tracks"] = clean_tracks

    removed_out.write_text(
        json.dumps([removed_payload], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    clean_out.write_text(
        json.dumps([clean_payload], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Input tracks:   {len(tracks)}")
    print(f"Removed tracks: {len(removed_tracks)} -> {removed_out}")
    print(f"Clean tracks:   {len(clean_tracks)} -> {clean_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
