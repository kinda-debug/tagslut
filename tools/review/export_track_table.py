#!/usr/bin/env python3
"""
export_track_table.py
Read files_tags.jsonl produced by hoard_tags.py and export a per-track CSV
with core tags, identifiers, and duration comparison (tag vs actual audio).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

try:
    import mutagen  # type: ignore
except Exception:
    print("ERROR: mutagen is required. Install with: pip install mutagen", file=sys.stderr)
    raise


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Export a per-track CSV from files_tags.jsonl with durations and identifiers."
    )
    ap.add_argument(
        "jsonl_path",
        type=Path,
        help="Path to files_tags.jsonl produced by hoard_tags.py (--dump-files).",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=Path("library_export.csv"),
        help="Output CSV path (default: library_export.csv in current directory).",
    )
    ap.add_argument(
        "--duration-threshold-ms",
        type=int,
        default=2000,
        help="Threshold in ms to flag duration mismatches (default: 2000 ms).",
    )
    return ap.parse_args()


def normalize_tag_value(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        parts = []
        for x in v:
            s = normalize_tag_value(x)
            if s:
                parts.append(s)
        return " / ".join(parts)
    if isinstance(v, (bytes, bytearray)):
        try:
            return v.decode("utf-8", "ignore")
        except Exception:
            return repr(v)
    try:
        return str(v)
    except Exception:
        return repr(v)


def _get_raw_tag(tags: Dict[str, Any], *keys: str) -> Any:
    for k in keys:
        if k in tags:
            return tags[k]
    return None


def get_first(tags: Dict[str, Any], *keys: str) -> Optional[str]:
    raw = _get_raw_tag(tags, *keys)
    if raw is None:
        return None
    s = normalize_tag_value(raw).strip()
    return s or None


def get_first_int(tags: Dict[str, Any], *keys: str) -> Optional[int]:
    raw_str = get_first(tags, *keys)
    if raw_str is None:
        return None
    try:
        return int(raw_str)
    except ValueError:
        for sep in ("/", ";", ","):
            if sep in raw_str:
                try:
                    return int(raw_str.split(sep, 1)[0].strip())
                except Exception:
                    break
    except Exception:
        return None
    return None


def get_first_float(tags: Dict[str, Any], *keys: str) -> Optional[float]:
    raw_str = get_first(tags, *keys)
    if raw_str is None:
        return None
    raw_str = raw_str.replace(",", ".")
    try:
        return float(raw_str)
    except Exception:
        return None


def parse_duration_from_tags(tags: Dict[str, Any]) -> Optional[int]:
    mb_len = get_first_int(tags, "MUSICBRAINZ_TRACK_LENGTH")
    if mb_len is not None:
        return mb_len
    tlen = get_first_int(tags, "TLEN")
    if tlen is not None:
        if tlen < 3600:
            return tlen * 1000
        return tlen
    return None


def open_audio_info(path: Path) -> Tuple[Optional[int], Optional[int], Optional[int], Optional[int]]:
    try:
        audio = mutagen.File(str(path), easy=False)
    except Exception as e:
        print(f"WARNING: mutagen could not open file: {path} ({e})", file=sys.stderr)
        return None, None, None, None
    if audio is None or not hasattr(audio, "info") or audio.info is None:
        return None, None, None, None
    info = audio.info
    duration_ms: Optional[int] = None
    try:
        if hasattr(info, "length") and info.length is not None:
            duration_ms = int(float(info.length) * 1000)
    except Exception:
        duration_ms = None
    bitrate_kbps: Optional[int] = None
    try:
        if hasattr(info, "bitrate") and info.bitrate:
            bitrate_kbps = int(round(info.bitrate / 1000))
    except Exception:
        bitrate_kbps = None
    sample_rate_hz: Optional[int] = None
    try:
        if hasattr(info, "sample_rate") and info.sample_rate:
            sample_rate_hz = int(info.sample_rate)
    except Exception:
        sample_rate_hz = None
    channels: Optional[int] = None
    try:
        if hasattr(info, "channels") and info.channels:
            channels = int(info.channels)
    except Exception:
        channels = None
    return duration_ms, bitrate_kbps, sample_rate_hz, channels


def iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as fp:
        for idx, line in enumerate(fp, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception as e:
                print(f"WARNING: JSON parse error at line {idx}: {e}", file=sys.stderr)
                continue
            if not isinstance(obj, dict):
                print(f"WARNING: Line {idx} is not an object; skipping.", file=sys.stderr)
                continue
            yield obj


def main() -> int:
    args = parse_args()
    jsonl_path = args.jsonl_path.expanduser().resolve()
    out_path = args.out.expanduser().resolve()
    duration_threshold_ms = args.duration_threshold_ms

    if not jsonl_path.exists():
        print(f"ERROR: JSONL path not found: {jsonl_path}", file=sys.stderr)
        return 1

    out_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "file_path",
        "file_name",
        "artist",
        "title",
        "album",
        "album_artist",
        "track_number",
        "disc_number",
        "year",
        "label",
        "genre",
        "bpm",
        "key",
        "isrc",
        "mb_track_id",
        "mb_recording_id",
        "mb_release_id",
        "beatport_id",
        "itunes_id",
        "duration_tag_ms",
        "duration_actual_ms",
        "duration_external_ms",
        "duration_tag_vs_actual_diff_ms",
        "duration_mismatch_flag",
        "audio_format",
        "bitrate_kbps",
        "sample_rate_hz",
        "channels",
        "file_size_bytes",
    ]

    total_records = 0
    written_rows = 0
    duration_mismatches = 0

    with out_path.open("w", newline="", encoding="utf-8") as csv_fp:
        writer = csv.DictWriter(csv_fp, fieldnames=fieldnames)
        writer.writeheader()

        for rec in iter_jsonl(jsonl_path):
            total_records += 1
            file_path_str = rec.get("path")
            if not file_path_str:
                print("WARNING: Record missing 'path' field; skipping.", file=sys.stderr)
                continue
            file_path = Path(file_path_str)
            tags = rec.get("tags", {})
            if not isinstance(tags, dict):
                print(f"WARNING: 'tags' is not a dict for {file_path_str}; skipping.", file=sys.stderr)
                continue

            file_name = os.path.basename(file_path_str)
            audio_format = file_path.suffix.lower().lstrip(".") if file_path.suffix else ""

            file_size_bytes: Optional[int] = None
            try:
                file_size_bytes = file_path.stat().st_size
            except OSError as e:
                print(f"WARNING: Cannot stat file {file_path_str}: {e}", file=sys.stderr)

            duration_actual_ms, bitrate_kbps, sample_rate_hz, channels = open_audio_info(file_path)
            duration_tag_ms = parse_duration_from_tags(tags)
            duration_external_ms: Optional[int] = None

            duration_tag_vs_actual_diff_ms: Optional[int] = None
            duration_mismatch_flag: Optional[bool] = None
            if duration_actual_ms is not None and duration_tag_ms is not None:
                duration_tag_vs_actual_diff_ms = duration_actual_ms - duration_tag_ms
                duration_mismatch_flag = abs(duration_tag_vs_actual_diff_ms) > duration_threshold_ms
                if duration_mismatch_flag:
                    duration_mismatches += 1

            isrc = get_first(tags, "ISRC", "TSRC")
            mb_track_id = get_first(tags, "MUSICBRAINZ_TRACKID")
            mb_recording_id = get_first(tags, "MUSICBRAINZ_RELEASETRACKID")
            mb_release_id = get_first(tags, "MUSICBRAINZ_ALBUMID")
            beatport_id = get_first(
                tags,
                "BEATPORT_TRACK_ID",
                "BP_TRACK_ID",
                "beatport_track_id",
                "BeatportTrackId",
            )
            itunes_id = get_first(tags, "ITUNES_ID", "iTunes_ID", "ITUNNORM", "ITUNES_ALBUMID")

            artist = get_first(tags, "ARTIST", "artist", "TPE1")
            title = get_first(tags, "TITLE", "title", "TIT2")
            album = get_first(tags, "ALBUM", "album", "TALB")
            album_artist = get_first(tags, "ALBUMARTIST", "albumartist", "TPE2")
            track_number = get_first_int(tags, "TRACKNUMBER", "tracknumber", "TRCK")
            disc_number = get_first_int(tags, "DISCNUMBER", "discnumber", "TPOS")
            year = get_first_int(tags, "DATE", "date", "YEAR", "TDRC")
            label = get_first(tags, "LABEL", "TXXX:LABEL")
            genre = get_first(tags, "GENRE", "genre", "TCON")
            bpm = get_first_float(tags, "BPM", "bpm", "TBPM")
            musical_key = get_first(tags, "INITIALKEY", "initialkey", "TKEY")

            row = {
                "file_path": file_path_str,
                "file_name": file_name,
                "artist": artist or "",
                "title": title or "",
                "album": album or "",
                "album_artist": album_artist or "",
                "track_number": track_number if track_number is not None else "",
                "disc_number": disc_number if disc_number is not None else "",
                "year": year if year is not None else "",
                "label": label or "",
                "genre": genre or "",
                "bpm": bpm if bpm is not None else "",
                "key": musical_key or "",
                "isrc": isrc or "",
                "mb_track_id": mb_track_id or "",
                "mb_recording_id": mb_recording_id or "",
                "mb_release_id": mb_release_id or "",
                "beatport_id": beatport_id or "",
                "itunes_id": itunes_id or "",
                "duration_tag_ms": duration_tag_ms if duration_tag_ms is not None else "",
                "duration_actual_ms": duration_actual_ms if duration_actual_ms is not None else "",
                "duration_external_ms": duration_external_ms if duration_external_ms is not None else "",
                "duration_tag_vs_actual_diff_ms": (
                    duration_tag_vs_actual_diff_ms
                    if duration_tag_vs_actual_diff_ms is not None
                    else ""
                ),
                "duration_mismatch_flag": (
                    1 if duration_mismatch_flag else (0 if duration_mismatch_flag is False else "")
                ),
                "audio_format": audio_format,
                "bitrate_kbps": bitrate_kbps if bitrate_kbps is not None else "",
                "sample_rate_hz": sample_rate_hz if sample_rate_hz is not None else "",
                "channels": channels if channels is not None else "",
                "file_size_bytes": file_size_bytes if file_size_bytes is not None else "",
            }
            writer.writerow(row)
            written_rows += 1

    print(f"Processed JSONL records: {total_records}")
    print(f"Wrote CSV rows: {written_rows}")
    print(f"Duration mismatches (>|{duration_threshold_ms}| ms): {duration_mismatches}")
    print(f"Output written to: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
