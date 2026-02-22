#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import sys
import termios
import tty
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any, Iterable

BLOCKLIST_PATH = Path("config/blocklists/non_dj_artists.txt")
REVIEWLIST_PATH = Path("config/blocklists/borderline_artists.txt")

SAFE_GENRES = {
    "techno",
    "house",
    "tech house",
    "deep house",
    "melodic house & techno",
    "minimal/deep tech",
    "trance",
    "progressive house",
    "big room",
    "bass/club",
    "breaks/breakbeat/uk bass",
    "drum & bass",
    "dubstep",
    "hard techno",
    "afro house",
    "nu disco/disco",
    "funky/groove/jackin' house",
    "indie dance",
    "uk garage/bassline",
    "trap/wave",
}

BLOCK_GENRES = {
    "classical",
    "jazz",
    "ambient",
    "spoken word",
    "soundtrack",
    "children's",
    "folk",
    "country",
    "gospel",
    "opera",
    "acoustic",
    "singer-songwriter",
    "world",
    "reggae/dancehall/dub",
    "organic house/downtempo",
    "electronica",
    "dj tools",
}

AMBIGUOUS_GENRES = {
    "electronic",
    "pop",
    "r&b",
    "hip-hop",
    "soul",
    "disco",
    "dance",
    "alternative",
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _split_genres(raw: str) -> list[str]:
    if not raw:
        return []
    # split by common separators
    parts = re.split(r"[\|,/;]+", raw)
    return [p.strip() for p in parts if p.strip()]


def _match_bucket(genres: Iterable[str], bucket: set[str]) -> bool:
    for g in genres:
        g_norm = _normalize(g)
        for b in bucket:
            if _normalize(b) in g_norm:
                return True
    return False


def _all_in_bucket(genres: Iterable[str], bucket: set[str]) -> bool:
    normalized = [_normalize(g) for g in genres if g.strip()]
    if not normalized:
        return False
    for g in normalized:
        if not any(_normalize(b) in g for b in bucket):
            return False
    return True


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
    # support mm:ss
    if re.match(r"^\d+:\d+$", text):
        mins, secs = text.split(":", 1)
        return float(mins) * 60 + float(secs)
    try:
        return float(text)
    except ValueError:
        return None


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

    # sort by detected timestamp, fallback to mtime
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
        return {"artist": None, "genre": None, "bpm": None, "duration": None, "title": None}
    keys = [k for k in rows[0].keys()]
    norm_map = {k: _normalize(k) for k in keys}

    def find_key(candidates: list[str]) -> str | None:
        for key, norm in norm_map.items():
            for cand in candidates:
                if cand in norm:
                    return key
        return None

    return {
        "artist": find_key(["artist", "album artist", "track artist", "artist name"]),
        "genre": find_key(["genre", "style", "subgenre"]),
        "bpm": find_key(["bpm", "tempo"]),
        "duration": find_key(["duration", "length", "seconds", "duration_s"]),
        "title": find_key(["title", "track", "name"]),
    }


def _iter_tracks_from_rows(rows: list[dict[str, Any]]) -> Iterable[dict[str, Any]]:
    cols = _detect_columns(rows)
    for row in rows:
        artist = row.get(cols["artist"] or "", "") if cols["artist"] else ""
        genre = row.get(cols["genre"] or "", "") if cols["genre"] else ""
        bpm = _parse_float(row.get(cols["bpm"] or "", "")) if cols["bpm"] else None
        duration = _parse_duration_seconds(row.get(cols["duration"] or "", "")) if cols["duration"] else None
        title = row.get(cols["title"] or "", "") if cols["title"] else ""
        yield {
            "artist": artist,
            "genre": genre,
            "bpm": bpm,
            "duration": duration,
            "title": title,
        }


def _read_existing(path: Path) -> set[str]:
    if not path.exists():
        return set()
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    items = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        items.append(_normalize(line))
    return set(items)


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


def _select_latest_inputs() -> dict[str, Path | None]:
    return {
        "dj_draft": _latest_by_timestamp("output/spreadsheet/dj_draft_scan_report_*.csv"),
        "genre_summary": _latest_by_timestamp("output/spreadsheet/genre_summary_*.csv"),
        "integrity": _latest_by_timestamp("artifacts/integrity_*.jsonl"),
    }


def build_artist_profiles(tracks: Iterable[dict[str, Any]]):
    profiles: dict[str, dict[str, Any]] = {}
    for t in tracks:
        artist_raw = str(t.get("artist") or "").strip()
        if not artist_raw:
            continue
        artist_key = _normalize(artist_raw)
        profile = profiles.setdefault(
            artist_key,
            {
                "artist": artist_raw,
                "genres": defaultdict(int),
                "bpms": [],
                "durations": [],
                "titles": [],
                "track_count": 0,
                "missing_genre": 0,
            },
        )
        genres = _split_genres(str(t.get("genre") or ""))
        if not genres:
            profile["missing_genre"] += 1
        for g in genres:
            profile["genres"][g] += 1
        if t.get("bpm") is not None:
            profile["bpms"].append(float(t["bpm"]))
        if t.get("duration") is not None:
            profile["durations"].append(float(t["duration"]))
        title = str(t.get("title") or "").strip()
        if title:
            profile["titles"].append(title)
        profile["track_count"] += 1
    return profiles


def classify_artists(profiles: dict[str, dict[str, Any]], auto_only: bool):
    auto_blocked = []
    auto_safe = []
    manual_blocked = []
    manual_review = []
    manual_skipped = []

    for key, p in sorted(profiles.items(), key=lambda kv: kv[0]):
        genres = list(p["genres"].keys())
        bpm_list = p["bpms"]
        duration_list = p["durations"]
        track_count = p["track_count"]
        missing_genre_ratio = (p["missing_genre"] / track_count) if track_count else 1

        median_bpm = median(bpm_list) if bpm_list else None
        all_under_90 = all(d < 90 for d in duration_list) if duration_list else False
        bpm_outside = (median_bpm is not None and (median_bpm < 80 or median_bpm > 210))

        genres_exclusive_block = _all_in_bucket(genres, BLOCK_GENRES)
        has_safe_genre = _match_bucket(genres, SAFE_GENRES)
        has_block_genre = _match_bucket(genres, BLOCK_GENRES)
        has_ambiguous = _match_bucket(genres, AMBIGUOUS_GENRES)

        # Auto BLOCK
        if genres_exclusive_block or bpm_outside or all_under_90:
            auto_blocked.append(p)
            continue

        # Auto SAFE
        if has_safe_genre and median_bpm is not None and 100 <= median_bpm <= 175:
            auto_safe.append(p)
            continue

        # Uncertain
        uncertain = False
        if has_safe_genre and has_block_genre:
            uncertain = True
        if missing_genre_ratio > 0.5:
            uncertain = True
        if has_ambiguous:
            uncertain = True

        if uncertain:
            if auto_only:
                manual_skipped.append(p)
            else:
                print("\n" + "─" * 38)
                bpm_range = (
                    f"{min(bpm_list):.0f}–{max(bpm_list):.0f}" if bpm_list else "n/a"
                )
                dur_avg = (
                    f"{(sum(duration_list)/len(duration_list))/60:.1f}"
                    if duration_list
                    else "n/a"
                )
                genre_counts = ", ".join(
                    f"{g} ({c})" for g, c in sorted(p["genres"].items(), key=lambda kv: -kv[1])
                )
                titles = ", ".join(p["titles"][:3])
                print(f"ARTIST: {p['artist']}")
                print(f"Tracks: {track_count}  |  BPM range: {bpm_range}  |  Duration avg: {dur_avg} min")
                print(f"Genres: {genre_counts or 'n/a'}")
                if titles:
                    print(f"Sample titles: {titles}")
                print("[K] Keep (DJ-safe)  [B] Block  [R] Review list  [S] Skip for now")
                choice = _prompt_choice()
                if choice == 'B':
                    manual_blocked.append(p)
                elif choice == 'R':
                    manual_review.append(p)
                elif choice == 'K':
                    auto_safe.append(p)
                else:
                    manual_skipped.append(p)
        else:
            manual_skipped.append(p)

    return {
        "auto_blocked": auto_blocked,
        "auto_safe": auto_safe,
        "manual_blocked": manual_blocked,
        "manual_review": manual_review,
        "manual_skipped": manual_skipped,
    }


def append_blocklists(
    blocked: list[dict[str, Any]],
    review: list[dict[str, Any]],
    *,
    dry_run: bool,
):
    today = dt.datetime.now().strftime("%Y-%m-%d")
    blocked_names = [p["artist"] for p in blocked]
    review_names = [p["artist"] for p in review]

    existing_block = _read_existing(BLOCKLIST_PATH)
    existing_review = _read_existing(REVIEWLIST_PATH)

    blocked_new = []
    for name in blocked_names:
        if _normalize(name) not in existing_block:
            blocked_new.append(name)

    review_new = []
    for name in review_names:
        if _normalize(name) not in existing_review:
            review_new.append(name)

    header = f"# Seeded {today} via seed_dj_blocklists.py — {len(blocked_new)} auto-blocked, {len(review_new)} manual\n"

    if dry_run:
        print("\n[DRY RUN] Would append to non_dj_artists.txt:")
        print(header.rstrip())
        for name in blocked_new:
            print(name)
        print("\n[DRY RUN] Would append to borderline_artists.txt:")
        print(header.rstrip())
        for name in review_new:
            print(name)
        return

    for path, names in [(BLOCKLIST_PATH, blocked_new), (REVIEWLIST_PATH, review_new)]:
        if not names:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write("\n" + header)
            for name in names:
                f.write(name + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed DJ artist blocklists from library metadata")
    parser.add_argument("--dry-run", action="store_true", help="Run classification but do not write")
    parser.add_argument("--auto-only", action="store_true", help="Skip interactive prompts")
    args = parser.parse_args()

    inputs = _select_latest_inputs()
    if not any(inputs.values()):
        print("No input data found. Expected one of:")
        print("- output/spreadsheet/dj_draft_scan_report_*.csv")
        print("- output/spreadsheet/genre_summary_*.csv")
        print("- artifacts/integrity_*.jsonl")
        return 2

    tracks = []
    used = []
    if inputs["dj_draft"] and inputs["dj_draft"].exists():
        rows = _load_csv(inputs["dj_draft"])
        tracks.extend(_iter_tracks_from_rows(rows))
        used.append(inputs["dj_draft"])
    elif inputs["genre_summary"] and inputs["genre_summary"].exists():
        rows = _load_csv(inputs["genre_summary"])
        tracks.extend(_iter_tracks_from_rows(rows))
        used.append(inputs["genre_summary"])
    elif inputs["integrity"] and inputs["integrity"].exists():
        rows = _load_jsonl(inputs["integrity"])
        tracks.extend(_iter_tracks_from_rows(rows))
        used.append(inputs["integrity"])

    if not tracks:
        print("No track rows found in input files. Check file formats.")
        return 2

    print("Using input files:")
    for p in used:
        print(f"- {p}")

    profiles = build_artist_profiles(tracks)
    classified = classify_artists(profiles, auto_only=args.auto_only)

    auto_blocked = classified["auto_blocked"]
    auto_safe = classified["auto_safe"]
    manual_blocked = classified["manual_blocked"]
    manual_review = classified["manual_review"]
    manual_skipped = classified["manual_skipped"]

    print("\nSummary:")
    print(f"- {len(auto_blocked)} artists auto-blocked")
    print(f"- {len(auto_safe)} artists auto-safe (skipped)")
    print(f"- {len(manual_blocked)} manually blocked")
    print(f"- {len(manual_review)} added to review list")
    print(f"- {len(manual_skipped)} skipped (undecided)")

    if not args.auto_only:
        confirm = input("Proceed? [y/n] ").strip().lower()
        if confirm != 'y':
            print("Aborted.")
            return 1

    append_blocklists(auto_blocked + manual_blocked, manual_review, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
