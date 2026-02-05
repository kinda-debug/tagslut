#!/usr/bin/env python3
"""Normalize Beatport-style genre tags in-place for FLAC files."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Any, List, Tuple

try:
    import mutagen
except Exception as e:
    raise SystemExit("mutagen is required (pip install mutagen)") from e


def load_rules(path: Path) -> Dict[str, Dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "genre_map": data.get("genre_map", {}),
        "style_map": data.get("style_map", {}),
    }


def get_tag(tags: Dict[str, Any], key: str) -> List[str]:
    if key in tags:
        val = tags[key]
        if isinstance(val, (list, tuple)):
            return [str(v).strip() for v in val if str(v).strip()]
        return [str(val).strip()] if str(val).strip() else []
    return []


def normalize_value(value: str, mapping: Dict[str, str]) -> str:
    return mapping.get(value, value)


def choose_normalized(tags: Dict[str, Any], rules: Dict[str, Dict[str, str]]) -> Tuple[str | None, str | None]:
    genre_candidates = (
        get_tag(tags, "GENRE_PREFERRED")
        or get_tag(tags, "SUBGENRE")
        or get_tag(tags, "GENRE")
        or get_tag(tags, "GENRE_FULL")
    )
    style_candidates = get_tag(tags, "SUBGENRE") or get_tag(tags, "STYLE")

    genre = None
    if genre_candidates:
        genre = normalize_value(genre_candidates[0], rules["genre_map"])

    style = None
    if style_candidates:
        style = normalize_value(style_candidates[0], rules["style_map"])

    return genre, style


def iter_flac_paths(root: Path) -> List[Path]:
    if root.is_file():
        return [root]
    return [p for p in root.rglob("*.flac") if not p.name.startswith("._")]


def main() -> int:
    ap = argparse.ArgumentParser(description="Normalize Beatport-style genre tags (GENRE/SUBGENRE/GENRE_PREFERRED/GENRE_FULL)")
    ap.add_argument("path", type=Path, help="Root path to scan (FLAC) or a single file")
    ap.add_argument("--rules", type=Path, default=Path("tools/rules/genre_normalization.json"))
    ap.add_argument("--execute", action="store_true", help="Write tags in-place")
    ap.add_argument("--limit", type=int, help="Limit number of files")
    args = ap.parse_args()

    rules = load_rules(args.rules)
    root = args.path.expanduser().resolve()
    flacs = iter_flac_paths(root)
    if args.limit:
        flacs = flacs[: args.limit]

    if not flacs:
        print("No FLAC files found.")
        return 1

    changed = 0
    for idx, p in enumerate(flacs, start=1):
        try:
            audio = mutagen.File(str(p), easy=False)
        except Exception:
            continue
        if audio is None or audio.tags is None:
            continue
        tags = audio.tags

        norm_genre, norm_style = choose_normalized(tags, rules)
        if not norm_genre:
            continue

        # Beatport approach: GENRE + SUBGENRE + GENRE_PREFERRED + GENRE_FULL
        new_genre = norm_genre
        new_subgenre = norm_style or ""
        new_preferred = norm_style or norm_genre
        new_full = f"{norm_genre} | {norm_style}" if norm_style else norm_genre

        if args.execute:
            tags["GENRE"] = new_genre
            if new_subgenre:
                tags["SUBGENRE"] = new_subgenre
            else:
                if "SUBGENRE" in tags:
                    del tags["SUBGENRE"]
            tags["GENRE_PREFERRED"] = new_preferred
            tags["GENRE_FULL"] = new_full
            audio.save()
            changed += 1

        if idx % 50 == 0 or idx == len(flacs):
            print(f"[{idx}/{len(flacs)}] {p.name}")

    print(f"Scanned: {len(flacs)}")
    print(f"Tagged:  {changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
