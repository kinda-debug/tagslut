from __future__ import annotations

import csv
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from tagslut.dj.curation import (
    DjCurationConfig,
    DjScoreResult,
    calculate_dj_score,
    resolve_track_override,
)
from tagslut.dj.lexicon import _normalize, _parse_float, load_scan_report
from concurrent.futures import ThreadPoolExecutor, as_completed
from tagslut.dj.transcode import TrackRow, assign_output_paths, load_tracks, make_dedupe_key, transcode_one
from mutagen import File as MutagenFile  # type: ignore  # TODO: mypy-strict

logger = logging.getLogger(__name__)


@dataclass
class ClassifiedTrack:
    track: dict[str, Any]
    score: DjScoreResult


def _split_artists(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _extract_remixer(title: str) -> str | None:
    text = title.strip()
    if not text:
        return None
    patterns = [
        r"\(([^)]+)\)",
        r"\[([^\]]+)\]",
        r" - ([^-]+)$",
    ]
    remix_keywords = [
        "remix",
        "edit",
        "rework",
        "re-edit",
        "refix",
        "dub",
        "dub mix",
        "extended",
        "club mix",
        "instrumental",
        "version",
        "vip",
        "bootleg",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, text, flags=re.IGNORECASE):
            lower = match.lower()
            if any(kw in lower for kw in remix_keywords):
                for kw in remix_keywords:
                    if kw in lower:
                        name = lower.replace(kw, "").strip(" -–_")
                        return name.strip() if name.strip() else None
    return None


def _build_scan_index(rows: list[dict[str, Any]], columns: dict[str, str | None]) -> dict[str, dict[str, Any]]:
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


def _lookup_scan_row(
        track_path: str, artist: str, title: str, scan_index: dict[str, dict[str, Any]]
) -> dict[str, Any] | None:
    candidates = [track_path]
    if " – " in track_path:
        candidates.append(track_path.replace(" – ", " - "))
    if " - " in track_path:
        candidates.append(track_path.replace(" - ", " – "))
    candidates.append(f"{track_path}.flac")
    if track_path.endswith(".flac.flac"):
        candidates.append(track_path[:-5])

    for candidate in candidates:
        row = scan_index["by_path"].get(candidate.lower())
        if row is not None:
            return row  # type: ignore  # TODO: mypy-strict

    key = f"{_normalize(artist)}|{_normalize(title)}"
    return scan_index["by_artist_title"].get(key)


def _library_remixers_from_scan(rows: list[dict[str, Any]], columns: dict[str, str | None]) -> set[str]:
    artist_col = columns.get("artist")
    if not artist_col:
        return set()
    remixers: set[str] = set()
    for row in rows:
        artist = str(row.get(artist_col) or "")
        for part in _split_artists(artist):
            remixers.add(_normalize(part))
    return remixers


def _enrich_from_scan(
        track: dict[str, Any], scan_index: dict[str, dict[str, Any]], columns: dict[str, str | None]
) -> None:
    row = _lookup_scan_row(
        track_path=str(track.get("path") or ""),
        artist=str(track.get("artist") or ""),
        title=str(track.get("title") or ""),
        scan_index=scan_index,
    )
    if row is None:
        _enrich_from_file(track)
        return
    bpm_col = columns.get("bpm")
    key_col = columns.get("key")
    genre_col = columns.get("genre")
    duration_col = columns.get("duration")
    if bpm_col:
        track["bpm"] = _parse_float(row.get(bpm_col))
    if key_col:
        key_val = str(row.get(key_col) or "").strip()
        track["key"] = key_val if key_val else None
    if genre_col:
        genre_val = str(row.get(genre_col) or "").strip()
        track["genre"] = genre_val if genre_val else None
    if duration_col:
        track["duration_sec"] = _parse_float(row.get(duration_col))
    _enrich_from_file(track)


def _tag_value(tags: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        raw = tags.get(key)
        if raw is None:
            continue
        if isinstance(raw, (list, tuple)):
            if not raw:
                continue
            raw = raw[0]
        value = str(raw).strip()
        if value:
            return value
    return None


def _enrich_from_file(track: dict[str, Any]) -> None:
    path_value = str(track.get("path") or "").strip()
    if not path_value:
        return
    file_path = Path(path_value)
    if not file_path.exists():
        return
    try:
        audio = MutagenFile(file_path, easy=False)
    except Exception as e:
        logger.debug("Failed to read audio metadata for %s: %s", file_path, e)
        audio = None
    if audio is None or not hasattr(audio, "info") or audio.info is None:
        return
    tags = getattr(audio, "tags", None) or {}

    if not track.get("artist"):
        artist_raw = _tag_value(
            tags, ["ARTIST", "TPE1", "ALBUMARTIST", "TPE2", "artist", "albumartist"])
        if artist_raw:
            track["artist"] = artist_raw
    if not track.get("title"):
        title_raw = _tag_value(tags, ["TITLE", "TIT2", "title"])
        if title_raw:
            track["title"] = title_raw
    if track.get("bpm") is None:
        bpm_raw = _tag_value(tags, ["BPM", "TBPM", "bpm", "tbpm"])
        if bpm_raw:
            track["bpm"] = _parse_float(bpm_raw)
    if track.get("key") is None:
        key_raw = _tag_value(tags, ["INITIALKEY", "TKEY", "KEY", "initialkey", "tkey", "key"])
        if key_raw:
            track["key"] = key_raw
    if track.get("genre") is None:
        genre_raw = _tag_value(tags, ["GENRE", "genre", "TCON", "tcon"])
        if genre_raw:
            track["genre"] = genre_raw
    if track.get("duration_sec") is None:
        length = getattr(audio.info, "length", None)
        if length is not None:
            track["duration_sec"] = float(length)


def _load_m3u(path: Path) -> list[Path]:
    tracks = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        tracks.append(Path(line))
    return tracks


def _load_folder(root: Path) -> list[Path]:
    exts = {".mp3", ".flac", ".wav", ".aiff"}
    return [p for p in root.rglob("*") if p.suffix.lower() in exts and not p.name.startswith("._")]


def load_input_tracks(input_path: Path) -> list[dict[str, Any]]:
    if input_path.suffix.lower() in {".xlsx", ".xlsm", ".xls"}:
        tracks, _, _ = load_tracks(input_path, None)
        output = []
        for tr in tracks:
            output.append({
                "path": str(tr.source_path),
                "artist": tr.track_artist or tr.album_artist or "",
                "title": tr.title or "",
            })
        return output
    if input_path.suffix.lower() in {".m3u", ".m3u8"}:
        paths = _load_m3u(input_path)
    elif input_path.is_dir():
        paths = _load_folder(input_path)
    else:
        paths = [input_path]

    output = []
    for p in paths:
        output.append({
            "path": str(p),
            "artist": "",
            "title": p.stem,
        })
    return output


def classify_tracks(
    input_path: Path,
    config: DjCurationConfig,
) -> tuple[list[ClassifiedTrack], list[ClassifiedTrack], list[ClassifiedTrack]]:
    tracks = load_input_tracks(input_path)
    rows, columns = load_scan_report()
    scan_index = _build_scan_index(rows, columns)
    remixers = _library_remixers_from_scan(rows, columns)

    safe: list[ClassifiedTrack] = []
    block: list[ClassifiedTrack] = []
    review: list[ClassifiedTrack] = []

    for track in tracks:
        _enrich_from_scan(track, scan_index, columns)
        remixer = _extract_remixer(str(track.get("title") or ""))
        if remixer:
            track["remixer"] = remixer
        override = resolve_track_override(
            path=str(track.get("path") or ""),
            artist=str(track.get("artist") or ""),
            title=str(track.get("title") or ""),
        )
        if override:
            verdict = str(override.get("verdict") or "review").lower()
            reason = str(override.get("reason") or "").strip()
            reasons = [reason] if reason else ["track_override"]
            if verdict == "safe":
                score = DjScoreResult(track=track, score=999, reasons=reasons, decision="safe")
                safe.append(ClassifiedTrack(track=track, score=score))
            elif verdict == "block":
                score = DjScoreResult(track=track, score=-999, reasons=reasons, decision="block")
                block.append(ClassifiedTrack(track=track, score=score))
            else:
                score = DjScoreResult(track=track, score=0, reasons=reasons, decision="review")
                review.append(ClassifiedTrack(track=track, score=score))
            continue

        artist_value = str(track.get("artist") or "").strip()
        if artist_value:
            artist_norm = _normalize(artist_value)
            if artist_norm in config.artist_blocklist:
                score = DjScoreResult(
                    track=track,
                    score=-999,
                    reasons=["artist_blocklist"],
                    decision="block",
                )
                block.append(ClassifiedTrack(track=track, score=score))
                continue
            if artist_norm in config.artist_reviewlist:
                score = DjScoreResult(
                    track=track,
                    score=0,
                    reasons=["artist_reviewlist"],
                    decision="review",
                )
                review.append(ClassifiedTrack(track=track, score=score))
                continue

        score = calculate_dj_score(track, config, remixers)
        item = ClassifiedTrack(track=track, score=score)
        if score.decision == "safe":
            safe.append(item)
        elif score.decision == "block":
            block.append(item)
        else:
            review.append(item)

    return safe, block, review


def _existing_override_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    if not path.exists():
        return keys
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.reader(handle)
        for row in reader:
            if not row or row[0].startswith("#"):
                continue
            while len(row) < 6:
                row.append("")
            path_val = row[0].strip()
            artist = row[1].strip()
            title = row[2].strip()
            if path_val:
                keys.add(path_val.lower())
            if artist and title:
                keys.add(f"{_normalize(artist)}|{_normalize(title)}")
    return keys


def append_overrides(path: Path, items: Iterable[ClassifiedTrack]) -> int:
    existing = _existing_override_keys(path)
    appended = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        for item in items:
            track = item.track
            score = item.score
            path_val = str(track.get("path") or "")
            artist = str(track.get("artist") or "")
            title = str(track.get("title") or "")
            key1 = path_val.lower() if path_val else ""
            key2 = f"{_normalize(artist)}|{_normalize(title)}" if artist and title else ""
            if (key1 and key1 in existing) or (key2 and key2 in existing):
                continue
            reason = f"score={score.score}; reasons={','.join(score.reasons)}"
            writer.writerow([path_val, artist, title, score.decision, reason, ""])
            appended += 1
            if key1:
                existing.add(key1)
            if key2:
                existing.add(key2)
    return appended


def write_m3u(path: Path, items: Iterable[ClassifiedTrack]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        handle.write("#EXTM3U\n")
        for item in items:
            track = item.track
            score = item.score
            reasons = ",".join(score.reasons)
            handle.write(f"# score:{score.score} reasons:{reasons}\n")
            handle.write(f"{track.get('path', '')}\n")


def promote_safe_tracks(
    items: Iterable[ClassifiedTrack],
    output_root: Path,
    *,
    jobs: int = 4,
    overwrite: bool = False,
) -> tuple[int, int, int]:
    tracks: list[TrackRow] = []
    for idx, item in enumerate(items, start=1):
        track = item.track
        source_path = Path(str(track.get("path") or ""))
        if not source_path.exists():
            continue
        artist = str(track.get("artist") or "")
        title = str(track.get("title") or source_path.stem)
        tr = TrackRow(
            row_num=idx,
            album_artist=artist,
            album=str(track.get("album") or ""),
            track_number=None,
            title=title,
            track_artist=artist,
            external_id="",
            source="classify",
            source_path=source_path,
            dedupe_key=("",),
        )
        tr.dedupe_key = make_dedupe_key(tr)
        tracks.append(tr)

    if not tracks:
        return (0, 0, 0)

    assign_output_paths(tracks, output_root)
    ok = skipped = failed = 0

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        futures = [pool.submit(transcode_one, track, overwrite) for track in tracks]
        for future in as_completed(futures):
            status, _, _, _ = future.result()
            if status == "ok":
                ok += 1
            elif status == "skipped_existing":
                skipped += 1
            else:
                failed += 1

    return (ok, skipped, failed)
