#!/usr/bin/env python3
"""Minimal recovery workflow: parse R-Studio Recognized export and match
against an existing library DB to produce a recovery CSV.

Usage examples:
  # parse recognized list into a candidates DB
  ./scripts/recover_workflow.py parse-recognized "Recognized5_5 SanDisk Extreme 55AE 3008.txt" \
      --out artifacts/db/recovered_candidates.db

  # match candidates against existing library DB (artifacts/db/library.db)
  ./scripts/recover_workflow.py match --library artifacts/db/library.db \
      --candidates artifacts/db/recovered_candidates.db \
      --out artifacts/reports/recovery_list.csv

This is intentionally conservative: it will not rescan your whole library.
The `scan` step can be added later if you want me to run a full library scan.
"""
from __future__ import annotations

import argparse
import csv
import re
import sqlite3
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from dedupe import scanner as dedupe_scanner


@dataclass
class Candidate:
    source_path: str
    filename: str
    ext: str
    size: Optional[int] = None
    duration: Optional[float] = None


def parse_recognized(path: Path) -> Iterable[Candidate]:
    """Parse an R-Studio Recognized plain-text export.

    Heuristic parser: extracts tokens that look like file paths / filenames
    with audio extensions. Sizes/duration are not present in the export so
    these fields are left empty where unavailable.
    """
    audio_exts = {".flac", ".wav", ".mp3", ".m4a", ".aac", ".ogg", ".aif", ".aiff"}
    path_like_re = re.compile(r"(/[^\s]+\.(?:flac|wav|mp3|m4a|aac|ogg|aif|aiff))", re.I)
    basename_re = re.compile(r"([^/\\]+\.(?:flac|wav|mp3|m4a|aac|ogg|aif|aiff))$", re.I)

    with path.open("r", encoding="utf8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            # find full path-like tokens first
            for m in path_like_re.finditer(line):
                p = m.group(1)
                fname = Path(p).name
                ext = Path(p).suffix.lower()
                yield Candidate(source_path=p, filename=fname, ext=ext)
                # continue scanning line for more tokens
            # otherwise look for bare filenames
            m2 = basename_re.search(line)
            if m2:
                fname = m2.group(1)
                yield Candidate(source_path=fname, filename=fname, ext=Path(fname).suffix.lower())


def write_candidates_db(candidates: Iterable[Candidate], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(out)
    with db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS candidates (
                id INTEGER PRIMARY KEY,
                source_path TEXT,
                filename TEXT,
                ext TEXT,
                size INTEGER,
                duration REAL
            )
            """
        )
        insert = "INSERT INTO candidates (source_path, filename, ext, size, duration) VALUES (?, ?, ?, ?, ?)"
        for c in candidates:
            db.execute(insert, (c.source_path, c.filename, c.ext, c.size, c.duration))


def read_library_db(path: Path) -> List[Dict]:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    with conn:
        cur = conn.execute("SELECT path, size_bytes, duration, sample_rate, bit_rate, checksum FROM library_files")
        return [dict(row) for row in cur.fetchall()]


def normalise_name(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


def score_match(lib: Dict, cand: Candidate) -> Tuple[float, List[str]]:
    notes: List[str] = []
    lib_fname = Path(lib["path"]).name
    nlib = normalise_name(lib_fname)
    ncand = normalise_name(cand.filename)

    # filename similarity
    if lib_fname == cand.filename:
        fname_score = 1.0
        notes.append("exact_name")
    elif nlib == ncand:
        fname_score = 0.95
        notes.append("norm_name")
    else:
        fname_score = SequenceMatcher(None, nlib, ncand).ratio()

    # size comparison (if candidate size known)
    size_score = 0.0
    if cand.size and lib.get("size_bytes"):
        l = lib["size_bytes"]
        c = cand.size
        if c > l:
            notes.append("candidate_larger")
            size_score = min(1.0, (c - l) / max(1, l))
        else:
            # similar sizes
            rel = abs(c - l) / max(1, l)
            if rel < 0.01:
                notes.append("size_similar")
                size_score = 0.5

    # duration comparison
    dur_score = 0.0
    if cand.duration and lib.get("duration"):
        ld = lib.get("duration")
        cd = cand.duration
        if cd and ld and cd > ld + 1.0:
            notes.append("candidate_longer")
            dur_score = min(1.0, (cd - ld) / max(1.0, ld))

    # quality signal
    q_score = 0.0
    if lib.get("bit_rate") and lib.get("bit_rate") and cand.ext == Path(lib["path"]).suffix.lower():
        lb = lib.get("bit_rate") or 0
        # no candidate bitrate; skip

    # final weighted score
    score = 0.6 * fname_score + 0.25 * size_score + 0.15 * dur_score
    return score, notes


def match_candidates(library_db: Path, candidates_db: Path, out_csv: Path, threshold: float = 0.6) -> None:
    libs = read_library_db(library_db)
    conn = sqlite3.connect(candidates_db)
    conn.row_factory = sqlite3.Row
    with conn:
        rows = conn.execute("SELECT id, source_path, filename, ext, size, duration FROM candidates").fetchall()

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf8") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "source_fragment_path",
            "expected_final_filename",
            "reason",
            "score",
            "library_path",
            "library_size",
            "library_duration",
        ])

        for r in rows:
            cand = Candidate(source_path=r["source_path"], filename=r["filename"], ext=r["ext"], size=r["size"], duration=r["duration"])
            # naive linear scan over libs
            best_score = 0.0
            best_lib = None
            best_notes: List[str] = []
            for lib in libs:
                score, notes = score_match(lib, cand)
                if score > best_score:
                    best_score = score
                    best_lib = lib
                    best_notes = notes

            if best_score >= threshold:
                reason = ";".join(best_notes) or "name_similarity"
                writer.writerow([
                    cand.source_path,
                    best_lib["path"].split("/")[-1],
                    reason,
                    f"{best_score:.3f}",
                    best_lib["path"],
                    best_lib.get("size_bytes"),
                    best_lib.get("duration"),
                ])


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd")

    p_parse = sub.add_parser("parse-recognized")
    p_parse.add_argument("path", help="Recognized file path")
    p_parse.add_argument("--out", default="artifacts/db/recovered_candidates.db")

    p_match = sub.add_parser("match")
    p_match.add_argument("--library", default="artifacts/db/library.db")
    p_match.add_argument("--candidates", default="artifacts/db/recovered_candidates.db")
    p_match.add_argument("--out", default="artifacts/reports/recovery_list.csv")
    p_match.add_argument("--threshold", type=float, default=0.6)

    p_scan = sub.add_parser("scan")
    p_scan.add_argument("--root", default="/Volumes/dotad/NEW_LIBRARY")
    p_scan.add_argument("--db", dest="database", default="artifacts/db/library.db")
    p_scan.add_argument("--include-fp", action="store_true", help="Include fingerprints (slow)")
    p_scan.add_argument("--batch-size", type=int, default=100)
    p_scan.add_argument("--resume", action="store_true", help="Resume existing DB and skip unchanged files")
    p_scan.add_argument("--progress", action="store_true", help="Show progress bar if tqdm available")

    args = p.parse_args()
    if args.cmd == "parse-recognized":
        path = Path(args.path)
        out = Path(args.out)
        cands = list(parse_recognized(path))
        write_candidates_db(cands, out)
        print(f"Wrote {len(cands)} candidates to {out}")
        return 0

    if args.cmd == "match":
        lib = Path(args.library)
        cdb = Path(args.candidates)
        out = Path(args.out)
        if not lib.exists():
            print(f"Library DB not found: {lib}")
            return 2
        if not cdb.exists():
            print(f"Candidates DB not found: {cdb}")
            return 3
        match_candidates(lib, cdb, out, threshold=args.threshold)
        print(f"Wrote recovery CSV to {out}")
        return 0

    if args.cmd == "scan":
        root = Path(args.root)
        db_path = Path(args.database)
        cfg = dedupe_scanner.ScanConfig(
            root=root,
            database=db_path,
            include_fingerprints=bool(args.include_fp),
            batch_size=int(args.batch_size),
            resume=bool(args.resume),
            show_progress=bool(args.progress),
        )
        print(f"Starting scan of {cfg.root} -> {cfg.database} (resume={cfg.resume})")
        total = dedupe_scanner.scan_library(cfg)
        print(f"Completed scan: {total} files processed")
        return 0

    p.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
