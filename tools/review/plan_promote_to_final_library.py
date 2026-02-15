#!/usr/bin/env python3
"""
plan_promote_to_final_library.py

Plan (dry-run) a MOVE-only promotion into a strict canonical FINAL_LIBRARY layout.

This script does NOT move files. It generates a plan CSV with explicit dest_path
for each file that can be deterministically named from tags.

Convention (library-only):
  {albumartist}/({year}) {album}/{artist_or_albumartist} – ({year}) {album} – {disc}{track} {title}.flac

Notes:
- Uses albumartist for folder + filename, except "Various Artists" albums where
  filename uses track artist.
- Applies canon rules (tools/rules/library_canon.json) by default.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

sys.path.insert(0, str(Path(__file__).parents[2]))

from mutagen.flac import FLAC
from mutagen import MutagenError

from tagslut.metadata.canon import apply_canon, load_canon_rules
from tagslut.utils.final_library_layout import FinalLibraryLayoutError, build_final_library_destination
from tagslut.utils.paths import list_files


@dataclass(frozen=True)
class PlanRow:
    action: str
    path: str
    dest_path: str
    reason: str


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _default_canon_rules_path() -> Path:
    return Path(__file__).parents[2] / "tools" / "rules" / "library_canon.json"


def _iter_flacs(sources: Iterable[Path]) -> Iterable[Path]:
    for src in sources:
        if src.is_dir():
            yield from list_files(src, {".flac"})
        elif src.is_file() and src.suffix.lower() == ".flac":
            yield src


def _load_db_tags(conn: sqlite3.Connection, roots: list[Path]) -> dict[str, dict[str, Any]]:
    """
    Prefetch metadata_json for all DB rows under any root.
    Returns: {path_str: tags_dict}
    """
    out: dict[str, dict[str, Any]] = {}
    for root in roots:
        root_s = str(root.expanduser().resolve())
        if not root_s.endswith("/"):
            root_s += "/"
        like = root_s + "%"
        for path, meta_json in conn.execute(
            "SELECT path, metadata_json FROM files WHERE path LIKE ? AND metadata_json IS NOT NULL",
            (like,),
        ):
            if not meta_json:
                continue
            try:
                meta = json.loads(meta_json)
            except Exception:
                continue
            if isinstance(meta, dict):
                out[str(path)] = meta
    return out


def _read_tags_from_file(path: Path) -> Mapping[str, Any]:
    audio = FLAC(path)
    # mutagen tags are already mapping-like
    return {k: list(v) if isinstance(v, (list, tuple)) else v for k, v in (audio.tags or {}).items()}


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Plan promotion into FINAL_LIBRARY layout (no moves)")
    ap.add_argument("sources", nargs="+", type=Path, help="Source file(s) or directory(ies) to plan")
    ap.add_argument(
        "--dest-root",
        required=True,
        type=Path,
        help="FINAL_LIBRARY root (destination), e.g. /Volumes/SAD/_work/MUSIC/FINAL_LIBRARY",
    )
    ap.add_argument("--db", type=Path, help="Optional tagslut SQLite DB (for fast tag reads via metadata_json)")
    ap.add_argument("--no-db", action="store_true", help="Ignore DB even if provided")
    ap.add_argument("--canon/--no-canon", dest="canon", default=True, help="Apply canonical tag rules (default: on)")
    ap.add_argument("--canon-rules", type=Path, help="Path to canon rules JSON")
    ap.add_argument(
        "--strip-brackets/--keep-brackets",
        dest="strip_brackets",
        default=True,
        help="Remove []{} bracket characters from path components (default: strip)",
    )
    ap.add_argument("--out-dir", type=Path, default=Path("artifacts/compare"), help="Output directory for plan+summary")
    ap.add_argument("--stamp", default=None, help="Optional timestamp stamp override (default: now UTC)")
    ap.add_argument("--limit", type=int, help="Only process first N files (debug)")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    sources = [p.expanduser().resolve() for p in args.sources]
    dest_root = args.dest_root.expanduser().resolve()
    out_dir = args.out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = args.stamp or _now_stamp()

    plan_csv = out_dir / f"plan_promote_final_library_{stamp}.csv"
    summary_json = out_dir / f"plan_promote_final_library_summary_{stamp}.json"

    canon_rules = None
    if args.canon:
        rules_path = args.canon_rules.expanduser().resolve() if args.canon_rules else _default_canon_rules_path()
        canon_rules = load_canon_rules(rules_path)

    db_tags: dict[str, dict[str, Any]] = {}
    if args.db and not args.no_db:
        db_path = args.db.expanduser().resolve()
        if db_path.exists() and db_path.is_file():
            conn = sqlite3.connect(str(db_path))
            try:
                db_tags = _load_db_tags(conn, [p for p in sources if p.is_dir()])
            finally:
                conn.close()

    rows: list[PlanRow] = []
    dest_to_sources: dict[str, list[str]] = defaultdict(list)
    reason_counts: Counter[str] = Counter()
    total = 0

    for idx, flac_path in enumerate(_iter_flacs(sources), start=1):
        if args.limit and idx > int(args.limit):
            break
        total += 1
        src = flac_path.expanduser().resolve()
        src_s = str(src)

        raw_tags: Mapping[str, Any] | None = None
        if db_tags:
            raw_tags = db_tags.get(src_s)
        if raw_tags is None:
            try:
                raw_tags = _read_tags_from_file(src)
            except (MutagenError, ValueError) as e:
                reason = f"tag_read_error:{type(e).__name__}"
                rows.append(PlanRow(action="SKIP", path=src_s, dest_path="", reason=reason))
                reason_counts[reason] += 1
                continue
            except Exception as e:
                reason = f"tag_read_error:{type(e).__name__}"
                rows.append(PlanRow(action="SKIP", path=src_s, dest_path="", reason=reason))
                reason_counts[reason] += 1
                continue

        tags_for_layout: Mapping[str, Any]
        if canon_rules:
            try:
                tags_for_layout = apply_canon(dict(raw_tags), canon_rules)
            except Exception as e:
                reason = f"canon_error:{type(e).__name__}"
                rows.append(PlanRow(action="SKIP", path=src_s, dest_path="", reason=reason))
                reason_counts[reason] += 1
                continue
        else:
            tags_for_layout = raw_tags

        try:
            layout = build_final_library_destination(
                tags_for_layout,
                dest_root,
                strip_brackets=bool(args.strip_brackets),
            )
        except FinalLibraryLayoutError as e:
            msg = str(e)
            if msg.startswith("missing") or "missing required tag" in msg:
                reason = f"missing_tags:{msg}"
                reason_counts["missing_tags"] += 1
            elif msg.startswith("path component too long"):
                reason = f"path_too_long:{msg}"
                reason_counts["path_too_long"] += 1
            else:
                reason = f"layout_rejected:{msg}"
                reason_counts["layout_rejected"] += 1
            rows.append(PlanRow(action="SKIP", path=src_s, dest_path="", reason=reason))
            continue
        except Exception as e:
            reason = f"layout_error:{type(e).__name__}"
            rows.append(PlanRow(action="SKIP", path=src_s, dest_path="", reason=reason))
            reason_counts[reason] += 1
            continue

        dest = layout.dest_path
        dest_s = str(dest)
        try:
            if dest.exists():
                rows.append(PlanRow(action="SKIP", path=src_s, dest_path=dest_s, reason="dest_exists"))
                reason_counts["dest_exists"] += 1
                continue
        except OSError as e:
            rows.append(PlanRow(action="SKIP", path=src_s, dest_path=dest_s, reason=f"path_error:{e.errno}"))
            reason_counts["path_error"] += 1
            continue

        rows.append(PlanRow(action="MOVE", path=src_s, dest_path=dest_s, reason="final_library"))
        dest_to_sources[dest_s].append(src_s)

    # Deconflict: if multiple sources map to the same destination, mark them all SKIP.
    conflict_dests = {d for d, srcs in dest_to_sources.items() if len(srcs) > 1}
    if conflict_dests:
        updated: list[PlanRow] = []
        for r in rows:
            if r.action == "MOVE" and r.dest_path in conflict_dests:
                updated.append(PlanRow(action="SKIP", path=r.path, dest_path=r.dest_path, reason="conflict_same_dest"))
            else:
                updated.append(r)
        rows = updated
        reason_counts["conflict_same_dest"] += sum(len(dest_to_sources[d]) for d in conflict_dests)

    # Write plan CSV
    with plan_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["action", "path", "dest_path", "reason"])
        w.writeheader()
        for r in rows:
            w.writerow({"action": r.action, "path": r.path, "dest_path": r.dest_path, "reason": r.reason})

    move_count = sum(1 for r in rows if r.action == "MOVE")
    skip_count = sum(1 for r in rows if r.action != "MOVE")

    summary = {
        "stamp": stamp,
        "sources": [str(p) for p in sources],
        "dest_root": str(dest_root),
        "total_flac": total,
        "move_count": move_count,
        "skip_count": skip_count,
        "reason_counts": dict(reason_counts),
        "conflict_dest_count": len(conflict_dests),
        "plan_csv": str(plan_csv),
    }
    summary_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Planned MOVE rows: {move_count}")
    print(f"Planned SKIP rows: {skip_count}")
    if conflict_dests:
        print(f"Conflicts (same dest): {len(conflict_dests)} destinations")
    if reason_counts:
        top = sorted(reason_counts.items(), key=lambda kv: kv[1], reverse=True)[:8]
        print("Top reasons:")
        for k, v in top:
            print(f"  {k}: {v}")
    print(f"Wrote: {plan_csv}")
    print(f"Wrote: {summary_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
