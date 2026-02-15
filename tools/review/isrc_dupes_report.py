#!/usr/bin/env python3
"""
isrc_dupes_report.py

Report duplicate groups by ISRC from the tagslut DB (metadata_json), with an
optional Chromaprint fingerprint join.

Why ISRC:
- Beatport can assign different Beatport track IDs to the same ISRC across releases.
- ISRC is a better "track identity" anchor for cross-release duplicates.

Outputs:
- Markdown report of groups and per-file details
- CSV plan with actions: KEEP | MOVE | REVIEW

Notes:
- This does not move anything. Use tools/review/quarantine_from_plan.py to execute MOVE actions.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_SPECIAL_COMPILATION_KEYWORDS = [
    "dj-kicks",
    "global underground",
    "permanent vacation",
    "fabric",
    "renaissance",
    "balance",
]


def _norm(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        v = v[0] if v else ""
    return str(v).strip()


def _is_compilation_path(p: str) -> bool:
    return "[Compilation]" in p


def _is_special_compilation(p: str, keywords: List[str]) -> bool:
    if not _is_compilation_path(p):
        return False
    pl = p.lower()
    return any(k in pl for k in keywords)


def _audio_identical(fingerprints: List[Optional[str]]) -> bool:
    if not fingerprints:
        return False
    if any(fp is None or fp == "" for fp in fingerprints):
        return False
    return len(set(fingerprints)) == 1


def _load_fingerprints(fp_report_csv: Optional[Path]) -> Dict[str, str]:
    if not fp_report_csv:
        return {}
    fp_report_csv = fp_report_csv.expanduser().resolve()
    if not fp_report_csv.exists():
        return {}
    out: Dict[str, str] = {}
    with fp_report_csv.open(newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            p = (row.get("path") or "").strip()
            fp = (row.get("fingerprint") or "").strip()
            if p and fp:
                out[p] = fp
    return out


@dataclass
class FileRow:
    path: str
    meta: Dict[str, Any]
    duration_s: Optional[float]
    streaminfo_md5: Optional[str]
    fingerprint: Optional[str]


def _where_paths(prefixes: List[str]) -> Tuple[str, List[str]]:
    if not prefixes:
        return "1=1", []
    parts: List[str] = []
    params: List[str] = []
    for p in prefixes:
        parts.append("path LIKE ?")
        params.append(p.rstrip("/") + "/%")
    return "(" + " OR ".join(parts) + ")", params


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Report ISRC duplicate groups from the tagslut DB")
    ap.add_argument("--db", required=True, type=Path, help="SQLite DB path")
    ap.add_argument("--root", action="append", default=[], help="Path prefix filter (repeatable)")
    ap.add_argument("--fingerprints", type=Path, help="Optional fingerprint_report CSV to join")
    ap.add_argument("--out-report", type=Path, default=None, help="Markdown report output path")
    ap.add_argument("--out-plan", type=Path, default=None, help="CSV plan output path")
    ap.add_argument(
        "--special-compilation-keyword",
        action="append",
        default=[],
        help="Keyword (repeatable) to prefer keeping compilation copies (default set applies if none given)",
    )
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    today = date.today().isoformat()

    db_path = args.db.expanduser().resolve()
    fp_by_path = _load_fingerprints(args.fingerprints)
    keywords = args.special_compilation_keyword or DEFAULT_SPECIAL_COMPILATION_KEYWORDS

    out_report = (args.out_report or Path(f"artifacts/isrc_dupe_report_{today}.md")).expanduser().resolve()
    out_plan = (args.out_plan or Path(f"artifacts/isrc_dupe_plan_{today}.csv")).expanduser().resolve()
    out_report.parent.mkdir(parents=True, exist_ok=True)
    out_plan.parent.mkdir(parents=True, exist_ok=True)

    where_paths, params = _where_paths(args.root)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        f"""
        SELECT path, metadata_json, duration, streaminfo_md5
        FROM files
        WHERE {where_paths}
        """,
        params,
    ).fetchall()
    conn.close()

    by_isrc: Dict[str, List[FileRow]] = defaultdict(list)
    for r in rows:
        path = r["path"]
        mj = r["metadata_json"]
        if not mj:
            continue
        try:
            meta = json.loads(mj)
        except Exception:
            continue
        isrc = _norm(meta.get("isrc"))
        if not isrc:
            continue
        by_isrc[isrc].append(
            FileRow(
                path=path,
                meta=meta,
                duration_s=r["duration"],
                streaminfo_md5=r["streaminfo_md5"],
                fingerprint=fp_by_path.get(path),
            )
        )

    groups = [(isrc, files) for isrc, files in by_isrc.items() if len(files) > 1]
    groups.sort(key=lambda t: (-len(t[1]), t[0]))

    md: List[str] = []
    md.append(f"# ISRC Duplicate Groups (generated {today})")
    if args.root:
        md.append("")
        md.append("Roots:")
        for p in args.root:
            md.append(f"- `{p}`")
    md.append("")
    md.append(f"- groups: {len(groups)}")
    md.append("")

    plan_rows: List[Dict[str, str]] = []

    for idx, (isrc, files) in enumerate(groups, start=1):
        files_sorted = sorted(files, key=lambda fr: fr.path)
        audio_ok = _audio_identical([fr.fingerprint for fr in files_sorted])

        comps = [fr for fr in files_sorted if _is_compilation_path(fr.path)]
        noncomps = [fr for fr in files_sorted if not _is_compilation_path(fr.path)]

        keeper = files_sorted[0]
        keep_reason = "keep_first_sorted"
        if comps and noncomps:
            special_comps = [fr for fr in comps if _is_special_compilation(fr.path, keywords)]
            if special_comps:
                keeper = sorted(special_comps, key=lambda fr: fr.path)[0]
                keep_reason = "keep_special_compilation"
            else:
                keeper = noncomps[0]
                keep_reason = "keep_non_compilation"

        md.append(
            f"## Group {idx} (isrc={isrc}, count={len(files_sorted)}, audio_identical={str(audio_ok).lower()})"
        )
        md.append("")

        for fr in files_sorted:
            meta = fr.meta
            artist = _norm(meta.get("artist")) or _norm(meta.get("albumartist"))
            title = _norm(meta.get("title"))
            album = _norm(meta.get("album"))
            label = _norm(meta.get("label"))
            date_ = _norm(meta.get("date"))
            bpid = _norm(meta.get("beatport_track_id"))
            dur = "" if fr.duration_s is None else f"{fr.duration_s:.3f}"
            fp_yes = "yes" if fr.fingerprint else "no"

            md.append(f"- `{fr.path}`")
            md.append(f"  - {artist} - {title}")
            md.append(f"  - album={album} | label={label} | date={date_} | beatport_track_id={bpid}")
            md.append(f"  - duration_s={dur} | streaminfo_md5={fr.streaminfo_md5 or ''} | fp={fp_yes}")

            if fr.path == keeper.path:
                action = "KEEP"
                reason = keep_reason
            else:
                action = "MOVE" if audio_ok else "REVIEW"
                reason = "dupe_audio_identical" if audio_ok else "dupe_isrc_audio_diff"

            plan_rows.append(
                {
                    "group": str(idx),
                    "match": "isrc",
                    "isrc": isrc,
                    "audio_identical": "1" if audio_ok else "0",
                    "action": action,
                    "reason": reason,
                    "path": fr.path,
                }
            )

        md.append("")

    out_report.write_text("\n".join(md) + "\n", encoding="utf-8")
    with out_plan.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["group", "match", "isrc", "audio_identical", "action", "reason", "path"],
        )
        w.writeheader()
        w.writerows(plan_rows)

    print(f"Wrote: {out_report}")
    print(f"Wrote: {out_plan}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
