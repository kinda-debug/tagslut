#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
import termios
import tty
import io
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any, Iterable

TRACK_OVERRIDES_PATH = Path("config/dj/track_overrides.csv")
BLOCKLIST_PATH = Path("config/blocklists/non_dj_artists.txt")

SAFE_OVERRIDES = {
    "pantha du prince",
    "kollektiv turmstrasse",
    "soulwax",
    "bicep",
    "kerri chandler",
    "dj t.",
    "crazy p",
}

REMIX_KEYWORDS = [
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
]

CLASSICAL_KEYWORDS = {
    "symphony",
    "concerto",
    "sonata",
    "quartet",
    "opus",
    "suite",
    "nocturne",
    "prelude",
    "fugue",
    "étude",
    "etude",
    "requiem",
    "oratorio",
    "cantata",
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "n/a"
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins}:{secs:02d}"


def _latest_by_timestamp(pattern: str) -> Path | None:
    files = list(Path().glob(pattern))
    if not files:
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

    return sorted(files, key=key)[-1]


def _load_csv(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({k.strip(): v for k, v in row.items()})
    return rows


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _detect_columns(rows: list[dict[str, Any]]) -> dict[str, str | None]:
    if not rows:
        return {
            "artist": None,
            "title": None,
            "genre": None,
            "bpm": None,
            "duration": None,
            "path": None,
        }
    keys = [k for k in rows[0].keys()]
    norm_map = {k: _normalize(k) for k in keys}

    def find_key(candidates: list[str]) -> str | None:
        for key, norm in norm_map.items():
            for cand in candidates:
                if cand in norm:
                    return key
        return None

    return {
        "artist": find_key(["artist", "track_artist", "trackartist", "performer"]),
        "title": find_key(["title", "track", "name"]),
        "genre": find_key(["genre", "track_genre", "canonical_genre"]),
        "bpm": find_key(["bpm", "canonical_bpm", "tempo"]),
        "duration": find_key(["duration", "duration_sec", "duration_seconds", "length"]),
        "path": find_key(["path", "source_path", "file_path"]),
    }


def _validate_columns(path: Path, rows: list[dict[str, Any]]) -> dict[str, str | None]:
    cols = _detect_columns(rows)
    if not cols["artist"] or not cols["title"]:
        found = ", ".join(rows[0].keys()) if rows else "<none>"
        print(
            "ERROR: Input file has no usable columns for track classification.\n"
            f"File: {path}\n"
            f"Found columns: {found}\n"
            "Expected at least: artist + title"
        )
        raise SystemExit(2)
    return cols


def _parse_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def _parse_duration_seconds(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if re.match(r"^\d+:\d+$", text):
        mins, secs = text.split(":", 1)
        return float(mins) * 60 + float(secs)
    try:
        return float(text)
    except ValueError:
        return None


def _normalize_path(path_str: str) -> str:
    text = path_str.strip()
    if not text:
        return ""
    p = Path(text)
    suffix = p.suffix.lower()
    stem = p.stem
    if suffix == ".flac" and stem.lower().endswith(".flac"):
        p = p.with_name(stem[:-5] + ".flac")
    return str(p)


def _iter_tracks_from_rows(rows: list[dict[str, Any]], *, path: Path) -> list[dict[str, Any]]:
    cols = _validate_columns(path, rows)
    tracks = []
    for row in rows:
        artist = row.get(cols["artist"], "") if cols["artist"] else ""
        title = row.get(cols["title"], "") if cols["title"] else ""
        genre = row.get(cols["genre"], "") if cols["genre"] else ""
        bpm = _parse_float(row.get(cols["bpm"], "")) if cols["bpm"] else None
        duration = _parse_duration_seconds(row.get(cols["duration"], "")) if cols["duration"] else None
        source_path = row.get(cols["path"], "") if cols["path"] else ""
        normalized_path = _normalize_path(str(source_path)) if source_path else ""
        tracks.append(
            {
                "artist": str(artist).strip(),
                "title": str(title).strip(),
                "genre": str(genre).strip(),
                "bpm": bpm,
                "duration": duration,
                "path": normalized_path,
            }
        )
    return tracks


def _load_existing_overrides(path: Path) -> tuple[set[str], set[str]]:
    if not path.exists():
        return set(), set()
    by_path: set[str] = set()
    by_artist_title: set[str] = set()
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.reader(handle)
        for row in reader:
            if not row:
                continue
            if row[0].strip().startswith("#"):
                continue
            while len(row) < 3:
                row.append("")
            p, artist, title = [cell.strip() for cell in row[:3]]
            if p:
                normalized = _normalize_path(p)
                if normalized:
                    by_path.add(normalized.lower())
            if artist and title:
                by_artist_title.add(f"{_normalize(artist)}|{_normalize(title)}")
    return by_path, by_artist_title


def _prompt_choice() -> str:
    try:
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        return ch.upper()
    except Exception:
        return input().strip().upper()[:1]


def _extract_remixer(title: str) -> str | None:
    # Look for last parenthetical/bracketed segment with remix keyword
    segments = re.findall(r"[\(\[]([^\)\]]+)[\)\]]", title)
    for seg in reversed(segments):
        seg_lower = seg.lower()
        if any(k in seg_lower for k in REMIX_KEYWORDS):
            cleaned = _clean_remixer(seg)
            return cleaned

    # Look for hyphen pattern: " - Name Remix"
    m = re.search(r"-\s*([^\-]+?)\s*(remix|edit|rework|re-edit|refix|dub|mix|version|vip)$", title, re.I)
    if m:
        cleaned = _clean_remixer(m.group(1))
        return cleaned

    return None


def _clean_remixer(text: str) -> str | None:
    cleaned = text
    cleaned = re.sub(
        r"\b(remix|edit|rework|re-edit|refix|dub|mix|version|vip|club|extended|instrumental)\b",
        "",
        cleaned,
        flags=re.I,
    )
    cleaned = cleaned.strip(" -[]()\t ")
    if not cleaned:
        return None
    # Remove generic labels
    generic = {"radio", "club", "extended", "instrumental", "version", "dub"}
    if _normalize(cleaned) in generic:
        return None
    return cleaned


def _detect_remix_tier(title: str, primary_artists: set[str]) -> tuple[str | None, str | None]:
    title_lower = title.lower()
    if not any(k in title_lower for k in REMIX_KEYWORDS):
        return None, None
    remixer = _extract_remixer(title)
    if remixer:
        if _normalize(remixer) in primary_artists:
            return "tier1", remixer
        return "tier2", remixer
    return "tier3", None


def _select_latest_input() -> Path | None:
    report = _latest_by_timestamp("output/spreadsheet/dj*scan_report*.csv")
    if report and report.exists():
        return report
    integrity = _latest_by_timestamp("artifacts/integrity_*.jsonl")
    if integrity and integrity.exists():
        return integrity
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed DJ track overrides from library metadata")
    parser.add_argument("--dry-run", action="store_true", help="Run classification but do not write")
    parser.add_argument("--auto-only", action="store_true", help="Skip interactive prompts")
    parser.add_argument("--limit", type=int, default=30, help="Cap interactive prompts")
    args = parser.parse_args()

    input_path = _select_latest_input()
    if input_path is None:
        print("No input data found. Expected one of:")
        print("- output/spreadsheet/dj*scan_report*.csv")
        print("- artifacts/integrity_*.jsonl")
        return 2

    if input_path.suffix.lower() == ".jsonl":
        rows = _load_jsonl(input_path)
    else:
        rows = _load_csv(input_path)

    columns = ", ".join(rows[0].keys()) if rows else "<none>"
    print(f"Using: {input_path} ({len(rows)} rows, columns: {columns})")

    tracks = _iter_tracks_from_rows(rows, path=input_path)
    if not tracks:
        print("No track rows found in input files. Check file formats.")
        return 2

    existing_paths, existing_artist_titles = _load_existing_overrides(TRACK_OVERRIDES_PATH)

    primary_artists = set()
    for t in tracks:
        artist_field = str(t.get("artist") or "").strip()
        if not artist_field:
            continue
        for part in artist_field.split(","):
            name = part.strip()
            if name:
                primary_artists.add(_normalize(name))

    # build artist stats
    artist_stats: dict[str, dict[str, Any]] = {}
    for t in tracks:
        artist = str(t.get("artist") or "").strip()
        if not artist:
            continue
        key = _normalize(artist)
        stats = artist_stats.setdefault(
            key,
            {
                "artist": artist,
                "track_count": 0,
                "bpms": [],
                "durations": [],
                "tracks": [],
            },
        )
        stats["track_count"] += 1
        if t.get("bpm") is not None:
            stats["bpms"].append(float(t["bpm"]))
        if t.get("duration") is not None:
            stats["durations"].append(float(t["duration"]))
        stats["tracks"].append(t)

    def artist_median_bpm(artist_key: str) -> float | None:
        bpms = artist_stats[artist_key]["bpms"]
        return median(bpms) if bpms else None

    def artist_median_duration(artist_key: str) -> float | None:
        durations = artist_stats[artist_key]["durations"]
        return median(durations) if durations else None

    # classification
    auto_safe_t1 = []
    auto_safe_t2 = []
    auto_blocked = []
    manual_kept = []
    manual_blocked = []
    manual_review = []
    skipped = []
    assigned_crates = 0

    session_safe_overrides = set(SAFE_OVERRIDES)

    # build interactive queue
    queue = []
    for t in tracks:
        artist = t.get("artist") or ""
        title = t.get("title") or ""
        if not artist or not title:
            continue
        key = _normalize(artist)
        track_key = f"{_normalize(artist)}|{_normalize(title)}"
        path_value = str(t.get("path") or "").strip().lower()
        if path_value and path_value in existing_paths:
            continue
        if track_key in existing_artist_titles:
            continue

        tier, remixer = _detect_remix_tier(title, primary_artists)
        if tier == "tier1":
            auto_safe_t1.append((t, f"remix_tier1:{remixer}"))
            continue
        if tier == "tier2":
            auto_safe_t2.append((t, f"remix_tier2:{remixer}"))
            continue
        if tier == "tier3":
            queue.append((t, "remix_tier3"))
            continue

        if _normalize(artist) in session_safe_overrides:
            skipped.append(t)
            continue

        title_lower = title.lower()
        has_classical = any(k in title_lower for k in CLASSICAL_KEYWORDS)
        med_bpm = artist_median_bpm(key)
        med_dur = artist_median_duration(key)
        bpm_condition = (med_bpm is None or med_bpm < 60)
        dur_condition = (med_dur is not None and med_dur < 300)
        if has_classical and bpm_condition and dur_condition:
            auto_blocked.append((t, "classical_low_bpm_short_duration"))
            continue

        queue.append((t, "manual"))

    # interactive session
    if not args.auto_only:
        queue_sorted = sorted(
            queue,
            key=lambda item: (-artist_stats[_normalize(item[0]["artist"])]["track_count"], item[0]["artist"], item[0]["title"]),
        )
        processed = 0
        for track, reason in queue_sorted:
            if processed >= args.limit:
                skipped.append(track)
                continue
            artist = track.get("artist") or ""
            title = track.get("title") or ""
            key = _normalize(artist)
            stats = artist_stats[key]
            bpm = track.get("bpm")
            duration = track.get("duration")
            genre = track.get("genre") or ""

            tier_label = ""
            if reason == "remix_tier3":
                tier_label = " [TIER 3 — remix keyword only]"

            print("\n" + "─" * 48)
            print(f"ARTIST: {artist}")
            print(f"TITLE:  \"{title}\"{tier_label}")
            bpm_display = f"{bpm:.0f}" if isinstance(bpm, (int, float)) else "n/a"
            dur_display = _format_duration(duration)
            print(f"BPM: {bpm_display}  |  Duration: {dur_display}  |  Genre: {genre or 'n/a'}")

            # top 3 longest tracks by artist
            durations = [t for t in stats["tracks"] if t.get("duration")]
            durations.sort(key=lambda x: x.get("duration"), reverse=True)
            print("Top 3 longest tracks by this artist:")
            for t in durations[:3]:
                print(f"  - \"{t.get('title') or ''}\" {_format_duration(t.get('duration'))}")

            print("[K] Keep  [B] Block  [R] Review  [A] Always-safe  [S] Skip")
            choice = _prompt_choice()
            if choice == "A":
                session_safe_overrides.add(_normalize(artist))
                manual_kept.append((track, "always_safe"))
            elif choice == "K":
                manual_kept.append((track, "manual_keep"))
            elif choice == "B":
                manual_blocked.append((track, "manual_block"))
            elif choice == "R":
                manual_review.append((track, "manual_review"))
            else:
                skipped.append(track)
                processed += 1
                continue

            crate = ""
            if choice in {"K", "R"}:
                existing_crates = sorted({c for _, _, _, _, _, c in _load_existing_rows(TRACK_OVERRIDES_PATH) if c})
                if existing_crates:
                    print(f"Existing crates: {', '.join(existing_crates)}")
                crate = input("Assign crate (Enter to skip, Tab for existing crates): ").strip()
            if crate:
                assigned_crates += 1
                track["crate"] = crate

            processed += 1

    else:
        skipped.extend([t for t, _ in queue])

    # Build output rows
    to_write = []
    for track, reason in auto_safe_t1 + auto_safe_t2:
        to_write.append(_row(track, "safe", reason))
    for track, reason in auto_blocked:
        to_write.append(_row(track, "block", reason))
    for track, reason in manual_kept:
        to_write.append(_row(track, "safe", reason))
    for track, reason in manual_blocked:
        to_write.append(_row(track, "block", reason))
    for track, reason in manual_review:
        to_write.append(_row(track, "review", reason))

    # Summary
    print("\nSummary:")
    print(f"- {len(auto_safe_t1)} tracks auto-safe TIER 1 (remixer in library)")
    print(f"- {len(auto_safe_t2)} tracks auto-safe TIER 2 (remixer unknown but remix detected)")
    print(f"- {len(auto_blocked)} tracks auto-blocked (classical + BPM + duration)")
    print(f"- {len(manual_kept)} tracks manually kept")
    print(f"- {len(manual_blocked)} tracks manually blocked")
    print(f"- {len(manual_review)} tracks added to review list")
    print(f"- {assigned_crates} tracks assigned to crates")
    print(f"- {len(skipped)} tracks skipped")

    if not args.auto_only:
        confirm = input("Proceed? [y/n] ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            return 1

    if args.dry_run:
        print("\n[DRY RUN] Would append to track_overrides.csv:")
        print(f"# Seeded {dt.datetime.now().strftime('%Y-%m-%d')} via seed_dj_blocklists.py")
        for row in to_write[:20]:
            output = io.StringIO()
            writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
            writer.writerow(row)
            print(output.getvalue().strip())
        return 0

    if not to_write:
        print("No new classifications to write.")
        return 0

    TRACK_OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TRACK_OVERRIDES_PATH.open("a", encoding="utf-8", newline="") as handle:
        handle.write(f"# Seeded {dt.datetime.now().strftime('%Y-%m-%d')} via seed_dj_blocklists.py\n")
        writer = csv.writer(handle, quoting=csv.QUOTE_MINIMAL)
        for row in to_write:
            writer.writerow(row)
    return 0


def _row(track: dict[str, Any], verdict: str, reason: str) -> list[str]:
    path = str(track.get("path") or "").strip()
    artist = str(track.get("artist") or "").strip()
    title = str(track.get("title") or "").strip()
    crate = str(track.get("crate") or "").strip()
    return [path, artist, title, verdict, reason, crate]


def _load_existing_rows(path: Path):
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.reader(handle)
        for row in reader:
            if not row:
                continue
            if row[0].strip().startswith("#"):
                continue
            while len(row) < 6:
                row.append("")
            rows.append(row[:6])
    return rows


if __name__ == "__main__":
    raise SystemExit(main())
