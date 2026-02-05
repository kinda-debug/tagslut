#!/usr/bin/env python3
"""
Normalize genre/style for a path and backfill DB canonical_genre/canonical_sub_genre.
Also emit a report of original tags, dropped tags, and final normalized values.
"""
from __future__ import annotations

import argparse
import csv
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


def choose_normalized(tags: Dict[str, Any], rules: Dict[str, Dict[str, str]]) -> Tuple[str | None, str | None, List[str]]:
    """Return (genre, style, dropped_tags)."""
    genre_candidates = (
        get_tag(tags, "GENRE_PREFERRED")
        or get_tag(tags, "SUBGENRE")
        or get_tag(tags, "GENRE")
        or get_tag(tags, "GENRE_FULL")
    )
    style_candidates = get_tag(tags, "STYLE")

    dropped = []
    # Any present tag that doesn't participate in the chosen output is "dropped" for reporting
    all_tag_keys = ["GENRE_PREFERRED", "SUBGENRE", "GENRE", "GENRE_FULL", "STYLE"]
    for k in all_tag_keys:
        if get_tag(tags, k) and k not in ("STYLE",) and k not in ("GENRE_PREFERRED", "SUBGENRE", "GENRE", "GENRE_FULL"):
            dropped.append(k)

    genre = None
    if genre_candidates:
        genre = normalize_value(genre_candidates[0], rules["genre_map"])

    style = None
    if style_candidates:
        style = normalize_value(style_candidates[0], rules["style_map"])

    return genre, style, dropped


def iter_flac_paths(root: Path) -> List[Path]:
    if root.is_file():
        return [root]
    return list(root.rglob("*.flac"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Normalize genre/style and backfill DB")
    ap.add_argument("path", type=Path, help="Root path to scan (FLAC) or a single file")
    ap.add_argument("--db", type=Path, required=True, help="SQLite DB path")
    ap.add_argument("--rules", type=Path, default=Path("tools/rules/genre_normalization.json"))
    ap.add_argument("--output", type=Path, default=Path("artifacts/genre_normalization_report.md"))
    ap.add_argument("--csv", type=Path, default=Path("artifacts/genre_normalization_rows.csv"))
    ap.add_argument("--execute", action="store_true", help="Write updates to DB")
    args = ap.parse_args()

    rules = load_rules(args.rules)
    root = args.path.expanduser().resolve()
    db_path = args.db.expanduser().resolve()

    flacs = iter_flac_paths(root)
    if not flacs:
        print("No FLAC files found.")
        return 1

    import sqlite3
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    rows = []
    updated = 0
    for p in flacs:
        try:
            audio = mutagen.File(str(p), easy=False)
            tags = audio.tags or {} if audio else {}
            genre_raw = get_tag(tags, "GENRE")
            subgenre_raw = get_tag(tags, "SUBGENRE")
            genre_pref = get_tag(tags, "GENRE_PREFERRED")
            genre_full = get_tag(tags, "GENRE_FULL")
            style_raw = get_tag(tags, "STYLE")

            norm_genre, norm_style, dropped = choose_normalized(tags, rules)

            rows.append({
                "path": str(p),
                "genre_raw": " | ".join(genre_raw),
                "subgenre_raw": " | ".join(subgenre_raw),
                "genre_preferred": " | ".join(genre_pref),
                "genre_full": " | ".join(genre_full),
                "style_raw": " | ".join(style_raw),
                "dropped_tags": ",".join(dropped),
                "normalized_genre": norm_genre or "",
                "normalized_style": norm_style or "",
            })

            if args.execute:
                cur.execute(
                    """
                    UPDATE files SET canonical_genre = ?, canonical_sub_genre = ?
                    WHERE path = ?
                    """,
                    (norm_genre, norm_style, str(p)),
                )
                updated += cur.rowcount
        except Exception:
            continue

    if args.execute:
        conn.commit()
    conn.close()

    args.csv.parent.mkdir(parents=True, exist_ok=True)
    with args.csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "path",
                "genre_raw",
                "subgenre_raw",
                "genre_preferred",
                "genre_full",
                "style_raw",
                "dropped_tags",
                "normalized_genre",
                "normalized_style",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "\n".join(
            [
                "# Genre/Style Normalization Report",
                f"- Files scanned: {len(flacs)}",
                f"- DB updated: {updated if args.execute else 0}",
                f"- Rules: {args.rules}",
                f"- CSV: {args.csv}",
            ]
        ),
        encoding="utf-8",
    )

    print(f"Scanned: {len(flacs)}")
    print(f"Updated DB rows: {updated if args.execute else 0}")
    print(f"Report: {args.output}")
    print(f"CSV: {args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
