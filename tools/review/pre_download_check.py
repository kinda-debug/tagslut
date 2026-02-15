#!/usr/bin/env python3
"""Pre-download DB check for Beatport/Tidal links.

Flow:
1) Extract tracklists from links (using scripts/extract_tracklists_from_links.py)
2) Match each track against DB (isrc -> beatport_id -> normalized tags)
3) Emit per-track decisions and keep-URL list for download tools

Match strategy (in priority order):
- ISRC match (confidence: high)
- Beatport track ID match (confidence: high, Beatport only)
- Normalized title + artist + album (confidence: medium)
- Normalized title + artist (confidence: low)

Usage:
    python tools/review/pre_download_check.py \\
        --input ~/links.txt \\
        --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db \\
        --out-dir output/precheck

Outputs:
- precheck_decisions_<ts>.csv: Per-track keep/skip with confidence
- precheck_summary_<ts>.csv: Per-link statistics
- precheck_keep_track_urls_<ts>.txt: URLs for downloader feed
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

# Confidence levels for match methods
CONFIDENCE_LEVELS = {
    "isrc": "high",
    "beatport_id": "high",
    "exact_title_artist_album": "medium",
    "exact_title_artist": "low",
}


@dataclass
class DbRow:
    path: str
    isrc: str
    beatport_id: str
    title: str
    artist: str
    album: str
    download_source: str


def norm_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(str(value).strip().lower().split())


def parse_json(s: str | None) -> dict[str, Any]:
    if not s:
        return {}
    try:
        return json.loads(s)
    except Exception:
        return {}


def first_meta(meta: dict[str, Any], keys: list[str]) -> str:
    for k in keys:
        v = meta.get(k)
        if isinstance(v, list) and v:
            val = str(v[0]).strip()
            if val:
                return val
        elif v is not None:
            val = str(v).strip()
            if val:
                return val
    return ""


def load_db_rows(db_path: Path) -> tuple[dict[str, list[DbRow]], dict[str, list[DbRow]], dict[str, list[DbRow]], dict[str, list[DbRow]]]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            path,
            canonical_isrc,
            beatport_id,
            canonical_title,
            canonical_artist,
            canonical_album,
            metadata_json,
            download_source
        FROM files
        """
    )

    by_isrc: dict[str, list[DbRow]] = defaultdict(list)
    by_beatport: dict[str, list[DbRow]] = defaultdict(list)
    by_exact3: dict[str, list[DbRow]] = defaultdict(list)
    by_exact2: dict[str, list[DbRow]] = defaultdict(list)

    for r in cur.fetchall():
        meta = parse_json(r["metadata_json"])

        isrc = (r["canonical_isrc"] or first_meta(meta, ["isrc", "ISRC", "TSRC"])).strip()
        beatport_id = (str(r["beatport_id"]) if r["beatport_id"] else first_meta(meta, ["beatport_id", "beatport_track_id", "BP_TRACK_ID"]))
        title = (r["canonical_title"] or first_meta(meta, ["title", "TITLE", "track_title", "name"])).strip()
        artist = (r["canonical_artist"] or first_meta(meta, ["artist", "ARTIST", "albumartist", "ALBUMARTIST"])).strip()
        album = (r["canonical_album"] or first_meta(meta, ["album", "ALBUM", "release"])).strip()

        row = DbRow(
            path=r["path"],
            isrc=isrc,
            beatport_id=str(beatport_id).strip(),
            title=title,
            artist=artist,
            album=album,
            download_source=(r["download_source"] or "").strip(),
        )

        if row.isrc:
            by_isrc[row.isrc].append(row)
        if row.beatport_id:
            by_beatport[row.beatport_id].append(row)

        k3 = "|".join([norm_text(row.title), norm_text(row.artist), norm_text(row.album)])
        if k3.strip("|"):
            by_exact3[k3].append(row)

        k2 = "|".join([norm_text(row.title), norm_text(row.artist)])
        if k2.strip("|"):
            by_exact2[k2].append(row)

    conn.close()
    return by_isrc, by_beatport, by_exact3, by_exact2


def build_keep_track_url(domain: str, track_id: str) -> str:
    tid = (track_id or "").strip()
    if not tid:
        return ""
    if domain == "beatport":
        return f"https://www.beatport.com/track/-/{tid}"
    if domain == "tidal":
        return f"https://tidal.com/browse/track/{tid}"
    return ""


def get_repo_root() -> Path:
    """Get repository root by finding the directory containing pyproject.toml."""
    current = Path(__file__).resolve().parent
    for _ in range(10):  # Max 10 levels up
        if (current / "pyproject.toml").exists():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    # Fallback to environment variable if set
    env_root = os.environ.get("TAGSLUT_ROOT")
    if env_root:
        return Path(env_root).resolve()
    raise SystemExit("Could not find repository root (pyproject.toml)")


def main() -> int:
    repo_root = get_repo_root()
    default_extract_script = repo_root / "scripts" / "extract_tracklists_from_links.py"
    default_db = os.environ.get("TAGSLUT_DB", "")

    ap = argparse.ArgumentParser(
        description="Check Beatport/Tidal links against DB before download",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tools/review/pre_download_check.py --input ~/links.txt --db ~/db/music.db
  python tools/review/pre_download_check.py --input ~/links.txt --db ~/db/music.db --out-dir output/precheck

Match Methods (in priority order):
  1. ISRC match (confidence: high)
  2. Beatport track ID match (confidence: high, Beatport links only)
  3. Title + Artist + Album exact match (confidence: medium)
  4. Title + Artist exact match (confidence: low)
""",
    )
    ap.add_argument("--input", required=True, help="Text file with links (one URL per line)")
    ap.add_argument(
        "--db",
        default=default_db,
        required=not default_db,
        help="Path to music.db (or set TAGSLUT_DB env var)",
    )
    ap.add_argument("--out-dir", default="output/precheck", help="Output directory (default: output/precheck)")
    ap.add_argument(
        "--extract-script",
        default=str(default_extract_script),
        help="Path to extract_tracklists_from_links.py (auto-detected from repo root)",
    )
    args = ap.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    db_path = Path(args.db).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    extract_script = Path(args.extract_script).expanduser().resolve()

    if not input_path.exists():
        raise SystemExit(f"Input not found: {input_path}")
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")
    if not extract_script.exists():
        raise SystemExit(f"Extract script not found: {extract_script}\n(Tip: Run from repository root or set --extract-script)")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)

    tracks_csv = out_dir / f"precheck_tracks_extracted_{ts}.csv"
    summary_csv = out_dir / f"precheck_links_extracted_{ts}.csv"
    report_md = out_dir / f"precheck_extracted_report_{ts}.md"

    cmd = [
        "python3",
        str(extract_script),
        "--input",
        str(input_path),
        "--tracks-csv",
        str(tracks_csv),
        "--summary-csv",
        str(summary_csv),
        "--report-md",
        str(report_md),
    ]
    subprocess.run(cmd, check=True)

    by_isrc, by_beatport, by_exact3, by_exact2 = load_db_rows(db_path)

    decision_csv = out_dir / f"precheck_decisions_{ts}.csv"
    decision_summary_csv = out_dir / f"precheck_summary_{ts}.csv"
    keep_urls_txt = out_dir / f"precheck_keep_track_urls_{ts}.txt"

    link_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"keep": 0, "skip": 0})
    keep_urls: list[str] = []

    with tracks_csv.open("r", encoding="utf-8", newline="") as fin, decision_csv.open("w", encoding="utf-8", newline="") as fout:
        reader = csv.DictReader(fin)
        fields = list(reader.fieldnames or []) + [
            "decision",
            "confidence",
            "match_method",
            "db_path",
            "db_download_source",
        ]
        writer = csv.DictWriter(fout, fieldnames=fields)
        writer.writeheader()

        for row in reader:
            domain = (row.get("domain") or "").strip()
            source_link = (row.get("source_link") or "").strip()
            isrc = (row.get("isrc") or "").strip()
            track_id = (row.get("track_id") or "").strip()
            title = (row.get("title") or "").strip()
            artist = (row.get("artist") or "").strip()
            album = (row.get("album") or "").strip()

            matched: DbRow | None = None
            method = ""

            # Match hierarchy: ISRC (high) > Beatport ID (high) > title+artist+album (medium) > title+artist (low)
            if isrc and isrc in by_isrc:
                matched = by_isrc[isrc][0]
                method = "isrc"
            elif domain == "beatport" and track_id and track_id in by_beatport:
                matched = by_beatport[track_id][0]
                method = "beatport_id"
            else:
                k3 = "|".join([norm_text(title), norm_text(artist), norm_text(album)])
                if k3 in by_exact3:
                    matched = by_exact3[k3][0]
                    method = "exact_title_artist_album"
                else:
                    k2 = "|".join([norm_text(title), norm_text(artist)])
                    if k2 in by_exact2:
                        matched = by_exact2[k2][0]
                        method = "exact_title_artist"

            if matched:
                decision = "skip"
                confidence = CONFIDENCE_LEVELS.get(method, "unknown")
                db_path_val = matched.path
                db_source = matched.download_source
            else:
                decision = "keep"
                confidence = ""
                db_path_val = ""
                db_source = ""
                keep_url = build_keep_track_url(domain, track_id)
                if keep_url:
                    keep_urls.append(keep_url)

            row.update(
                {
                    "decision": decision,
                    "confidence": confidence,
                    "match_method": method,
                    "db_path": db_path_val,
                    "db_download_source": db_source,
                }
            )
            writer.writerow(row)
            link_stats[source_link][decision] += 1

    with decision_summary_csv.open("w", encoding="utf-8", newline="") as fsum:
        writer = csv.DictWriter(fsum, fieldnames=["source_link", "keep", "skip"])
        writer.writeheader()
        for source_link, stats in sorted(link_stats.items()):
            writer.writerow({"source_link": source_link, "keep": stats["keep"], "skip": stats["skip"]})

    keep_urls_unique = list(dict.fromkeys(u for u in keep_urls if u))
    keep_urls_txt.write_text("\n".join(keep_urls_unique) + ("\n" if keep_urls_unique else ""), encoding="utf-8")

    total_keep = sum(s["keep"] for s in link_stats.values())
    total_skip = sum(s["skip"] for s in link_stats.values())

    # Generate summary report
    report_txt = out_dir / f"precheck_report_{ts}.md"
    with report_txt.open("w", encoding="utf-8") as f:
        f.write("# Pre-Download Check Report\n\n")
        f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**Input:** `{input_path}`\n")
        f.write(f"**Database:** `{db_path}`\n\n")
        f.write("## Summary\n\n")
        f.write(f"| Metric | Count |\n")
        f.write(f"|--------|-------|\n")
        f.write(f"| Tracks to download (keep) | {total_keep} |\n")
        f.write(f"| Tracks already in library (skip) | {total_skip} |\n")
        f.write(f"| Total tracks checked | {total_keep + total_skip} |\n")
        f.write(f"| Links processed | {len(link_stats)} |\n\n")
        f.write("## Outputs\n\n")
        f.write(f"- **Decisions CSV:** `{decision_csv}`\n")
        f.write(f"- **Summary CSV:** `{decision_summary_csv}`\n")
        f.write(f"- **Keep URLs (for downloader):** `{keep_urls_txt}`\n\n")
        f.write("## Match Methods\n\n")
        f.write("| Method | Confidence | Description |\n")
        f.write("|--------|------------|-------------|\n")
        f.write("| isrc | high | Exact ISRC match |\n")
        f.write("| beatport_id | high | Exact Beatport track ID match |\n")
        f.write("| exact_title_artist_album | medium | Normalized title+artist+album match |\n")
        f.write("| exact_title_artist | low | Normalized title+artist match (no album) |\n")

    print("Pre-download check complete")
    print(f"  decisions_csv: {decision_csv}")
    print(f"  summary_csv:   {decision_summary_csv}")
    print(f"  keep_urls:     {keep_urls_txt}")
    print(f"  report:        {report_txt}")
    print(f"  keep={total_keep} skip={total_skip}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
