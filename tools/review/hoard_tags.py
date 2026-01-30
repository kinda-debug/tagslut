#!/usr/bin/env python3
"""
hoard_tags.py
Inventory (hoard) ALL embedded tags from audio files under one or more roots.

Outputs (in --out dir):
- tags_summary.json  : per-tag counts + unique value counts
- tags_values.csv    : rows (tag, value, count) sorted by tag then count desc
- files_tags.jsonl   : optional per-file tag dump (JSON Lines), if --dump-files
- tags_keys.txt      : list of tag keys ordered by frequency
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import sqlite3
from datetime import datetime, timezone
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

try:
    import mutagen  # type: ignore
except Exception:
    print("ERROR: mutagen is required. Install with: pip install mutagen", file=sys.stderr)
    raise


DEFAULT_EXTS = {
    ".flac", ".mp3", ".m4a", ".mp4", ".aac",
    ".ogg", ".opus",
    ".wav", ".aif", ".aiff",
    ".wv", ".ape", ".asf",
}


SKIP_BASENAMES = {".DS_Store", "Thumbs.db"}
SKIP_PREFIXES = ("._",)


def _safe_str(x: Any, max_len: int) -> str:
    if x is None:
        return ""
    if hasattr(x, "text"):
        try:
            t = getattr(x, "text")
            if isinstance(t, (list, tuple)):
                s = " / ".join(str(v) for v in t)
            else:
                s = str(t)
            return s[:max_len]
        except Exception:
            pass
    if isinstance(x, (bytes, bytearray)):
        try:
            return x.decode("utf-8", "ignore")[:max_len]
        except Exception:
            return repr(x)[:max_len]
    if isinstance(x, (list, tuple)):
        parts = []
        for v in x:
            parts.append(_safe_str(v, max_len))
        s = " / ".join(p for p in parts if p != "")
        return s[:max_len]
    try:
        return str(x)[:max_len]
    except Exception:
        return repr(x)[:max_len]


def _normalize_key(k: Any) -> str:
    if k is None:
        return ""
    if isinstance(k, (bytes, bytearray)):
        try:
            return k.decode("utf-8", "ignore")
        except Exception:
            return repr(k)
    return str(k)


def iter_files(roots: List[Path], exts: set[str]) -> Iterable[Path]:
    for root in roots:
        root = root.expanduser().resolve()
        if not root.exists():
            continue
        for dirpath, _, filenames in os.walk(root):
            for name in filenames:
                if name in SKIP_BASENAMES or name.startswith(SKIP_PREFIXES):
                    continue
                p = Path(dirpath) / name
                if p.suffix.lower() in exts:
                    yield p


def extract_tags(path: Path, max_value_len: int) -> Tuple[Path, Dict[str, List[str]]]:
    audio = mutagen.File(str(path), easy=False)
    tags_map: Dict[str, List[str]] = {}

    if audio is None or getattr(audio, "tags", None) is None:
        return path, tags_map

    tags = audio.tags

    try:
        items = tags.items()  # type: ignore[attr-defined]
    except Exception:
        try:
            items = ((k, tags[k]) for k in tags.keys())  # type: ignore
        except Exception:
            return path, tags_map

    for k, v in items:
        key = _normalize_key(k).strip()
        if not key:
            continue

        vals: List[str] = []
        if isinstance(v, (list, tuple)):
            for one in v:
                s = _safe_str(one, max_value_len).strip()
                if s != "":
                    vals.append(s)
        else:
            s = _safe_str(v, max_value_len).strip()
            if s != "":
                vals.append(s)

        if not vals:
            continue

        seen = set()
        uniq_vals = []
        for s in vals:
            if s not in seen:
                uniq_vals.append(s)
                seen.add(s)

        tags_map[key] = uniq_vals

    return path, tags_map


@dataclass
class Aggregates:
    tag_files: Counter[str]
    tag_value_counts: Counter[Tuple[str, str]]
    tag_unique_values: Dict[str, set[str]]

    def __init__(self) -> None:
        self.tag_files = Counter()
        self.tag_value_counts = Counter()
        self.tag_unique_values = defaultdict(set)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Hoard ALL embedded tags from audio files and export counts."
    )
    ap.add_argument("roots", nargs="+", help="Root folder(s) to scan (one or more).")
    ap.add_argument("--out", default="tag_hoard_out", help="Output directory (default: tag_hoard_out).")
    ap.add_argument("--ext", action="append", default=None,
                    help="Add an extension to scan (repeatable). Example: --ext .flac --ext .mp3")
    ap.add_argument("--only-ext", action="store_true",
                    help="Scan ONLY extensions passed via --ext (otherwise defaults + extras).")
    ap.add_argument("--max-files", type=int, default=0,
                    help="Stop after N files (0 = no limit). Useful for testing.")
    ap.add_argument("--workers", type=int, default=min(32, (os.cpu_count() or 8) * 2),
                    help="Concurrent workers (default: ~2x CPU, capped at 32).")
    ap.add_argument("--max-value-len", type=int, default=300,
                    help="Truncate tag values to this length (default: 300).")
    ap.add_argument("--min-size", type=int, default=4096,
                    help="Skip files smaller than this byte size (default: 4096).")
    ap.add_argument("--dump-files", action="store_true",
                    help="Also write files_tags.jsonl containing per-file tag dumps (can be large).")
    ap.add_argument("--follow-symlinks", action="store_true",
                    help="Follow symlinked directories (off by default).")
    ap.add_argument("--db", type=Path,
                    help="Write aggregates to a SQLite DB (new DB by default).")
    ap.add_argument("--db-add", action="store_true",
                    help="Append results to an existing DB instead of creating a new one.")
    args = ap.parse_args()

    roots = [Path(r).expanduser() for r in args.roots]
    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.only_ext and not args.ext:
        print("ERROR: --only-ext requires at least one --ext", file=sys.stderr)
        return 2

    if args.only_ext:
        exts = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in args.ext or []}
    else:
        exts = set(DEFAULT_EXTS)
        if args.ext:
            exts |= {e.lower() if e.startswith(".") else f".{e.lower()}" for e in args.ext}

    files: List[Path] = []
    skipped: List[Tuple[str, str]] = []
    for p in iter_files(roots, exts):
        try:
            if args.min_size and p.stat().st_size < args.min_size:
                skipped.append((str(p), f"too_small<{args.min_size}"))
                continue
        except OSError as e:
            skipped.append((str(p), f"stat_error:{e}"))
            continue
        files.append(p)
        if args.max_files and len(files) >= args.max_files:
            break

    if not files:
        print("No audio files found for the given roots/extensions.", file=sys.stderr)
        return 1

    if args.follow_symlinks:
        print("NOTE: os.walk does not follow symlinks by default; pass real paths for symlinked trees.", file=sys.stderr)

    db_path = None
    if args.db:
        db_path = args.db.expanduser().resolve()
        if db_path.exists() and not args.db_add:
            print("ERROR: DB exists. Use --db-add to append.", file=sys.stderr)
            return 2
        db_path.parent.mkdir(parents=True, exist_ok=True)

    ag = Aggregates()

    jsonl_fp = None
    if args.dump_files:
        jsonl_fp = (out_dir / "files_tags.jsonl").open("w", encoding="utf-8")

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        futs = [ex.submit(extract_tags, p, args.max_value_len) for p in files]
        for fut in as_completed(futs):
            try:
                path, tags_map = fut.result()
            except Exception as e:
                print(f"ERROR reading tags: {e}", file=sys.stderr)
                continue

            if not tags_map:
                continue

            for k, vals in tags_map.items():
                ag.tag_files[k] += 1
                for v in vals:
                    ag.tag_value_counts[(k, v)] += 1
                    ag.tag_unique_values[k].add(v)

            if jsonl_fp:
                rec = {"path": str(path), "tags": tags_map}
                jsonl_fp.write(json.dumps(rec, ensure_ascii=False) + "\n")

    if jsonl_fp:
        jsonl_fp.close()

    if skipped:
        skipped_csv = out_dir / "tags_skipped.csv"
        with skipped_csv.open("w", newline="", encoding="utf-8") as fp:
            w = csv.writer(fp)
            w.writerow(["path", "reason"])
            w.writerows(skipped)

    summary = {
        "scanned_files": len(files),
        "roots": [str(r.expanduser().resolve()) for r in roots],
        "extensions": sorted(exts),
        "tags": {},
    }

    for tag, file_count in ag.tag_files.most_common():
        uniq_count = len(ag.tag_unique_values.get(tag, set()))
        summary["tags"][tag] = {
            "files_with_tag": file_count,
            "unique_values": uniq_count,
        }

    (out_dir / "tags_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    csv_path = out_dir / "tags_values.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fp:
        w = csv.writer(fp)
        w.writerow(["tag", "value", "count"])
        for (tag, value), cnt in sorted(
            ag.tag_value_counts.items(),
            key=lambda kv: (kv[0][0], -kv[1], kv[0][1]),
        ):
            w.writerow([tag, value, cnt])

    keys_txt = out_dir / "tags_keys.txt"
    keys_txt.write_text("\n".join([k for k, _ in ag.tag_files.most_common()]) + "\n", encoding="utf-8")

    if db_path:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tag_hoard_runs (
                    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT,
                    roots_json TEXT,
                    extensions_json TEXT,
                    scanned_files INTEGER,
                    max_files INTEGER,
                    workers INTEGER,
                    max_value_len INTEGER
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tag_hoard_keys (
                    run_id INTEGER,
                    tag TEXT,
                    files_with_tag INTEGER,
                    unique_values INTEGER,
                    PRIMARY KEY (run_id, tag)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tag_hoard_values (
                    run_id INTEGER,
                    tag TEXT,
                    value TEXT,
                    count INTEGER,
                    PRIMARY KEY (run_id, tag, value)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tag_hoard_files (
                    run_id INTEGER,
                    path TEXT,
                    tags_json TEXT
                )
            """)

            run_meta = (
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                json.dumps([str(r.expanduser().resolve()) for r in roots], ensure_ascii=False),
                json.dumps(sorted(exts), ensure_ascii=False),
                len(files),
                args.max_files,
                args.workers,
                args.max_value_len,
            )
            cur = conn.execute(
                "INSERT INTO tag_hoard_runs (created_at, roots_json, extensions_json, scanned_files, max_files, workers, max_value_len) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                run_meta,
            )
            run_id = cur.lastrowid

            key_rows = [
                (run_id, tag, file_count, len(ag.tag_unique_values.get(tag, set())))
                for tag, file_count in ag.tag_files.most_common()
            ]
            value_rows = [
                (run_id, tag, value, cnt)
                for (tag, value), cnt in ag.tag_value_counts.items()
            ]

            conn.executemany(
                "INSERT OR REPLACE INTO tag_hoard_keys (run_id, tag, files_with_tag, unique_values) VALUES (?, ?, ?, ?)",
                key_rows,
            )
            conn.executemany(
                "INSERT OR REPLACE INTO tag_hoard_values (run_id, tag, value, count) VALUES (?, ?, ?, ?)",
                value_rows,
            )

            if args.dump_files:
                file_rows = []
                jsonl_path = out_dir / "files_tags.jsonl"
                if jsonl_path.exists():
                    with jsonl_path.open("r", encoding="utf-8") as fp:
                        for line in fp:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                payload = json.loads(line)
                                file_rows.append((run_id, payload.get("path"), line))
                            except Exception:
                                file_rows.append((run_id, None, line))
                if file_rows:
                    conn.executemany(
                        "INSERT INTO tag_hoard_files (run_id, path, tags_json) VALUES (?, ?, ?)",
                        file_rows,
                    )

            conn.commit()
        finally:
            conn.close()

    print(f"OK: scanned_files={len(files)}")
    print(f"OK: wrote {out_dir / 'tags_summary.json'}")
    print(f"OK: wrote {out_dir / 'tags_values.csv'}")
    print(f"OK: wrote {out_dir / 'tags_keys.txt'}")
    if skipped:
        print(f"OK: wrote {out_dir / 'tags_skipped.csv'}")
    if args.dump_files:
        print(f"OK: wrote {out_dir / 'files_tags.jsonl'}")
    if db_path:
        print(f"OK: appended to DB {db_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
