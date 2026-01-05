#!/usr/bin/env python3
"""Minimal recovery workflow: parse R-Studio Recognized export and match
against an existing library DB to produce a recovery CSV.

Usage examples:
  # parse recognized list into a candidates DB
  ./scripts/recover_workflow.py parse-recognized "Recognized5_5 SanDisk Extreme 55AE 3008.txt" \
      --out artifacts/db/recovered_candidates.db

  # scan a secondary salvage root into a secondary candidates DB
  ./scripts/recover_workflow.py scan-secondary --root "/Volumes/COMMUNE/10_STAGING" \
      --out artifacts/db/secondary_candidates.db

  # match candidates against existing library DB with three-tier logic
  ./scripts/recover_workflow.py match --library artifacts/db/library.db \
      --secondary artifacts/db/secondary_candidates.db \
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


def write_secondary_db_from_scan(root: Path, out: Path, include_fingerprints: bool = False, batch_size: int = 100) -> int:
    """Scan `root` and write a `secondary_candidates` table into `out` DB.

    The table schema mirrors the simple candidates table but includes a few
    extra metadata columns captured from :mod:`dedupe.scanner` records.
    This function intentionally does not alter `artifacts/db/library.db`.
    Returns number of rows written.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(out)
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS secondary_candidates (
                id INTEGER PRIMARY KEY,
                source_path TEXT,
                filename TEXT,
                ext TEXT,
                size INTEGER,
                duration REAL,
                sample_rate INTEGER,
                bit_rate INTEGER,
                checksum TEXT
            )
            """
        )
        insert_sql = (
            "INSERT INTO secondary_candidates (source_path, filename, ext, size, duration, sample_rate, bit_rate, checksum) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        )

        count = 0
        from dedupe import scanner as dedupe_scanner_local  # local import
        from dedupe import utils as dedupe_utils

        for path in dedupe_utils.iter_audio_files(root):
            try:
                record = dedupe_scanner_local._prepare_record(path, include_fingerprints)
            except Exception:
                continue
            conn.execute(
                insert_sql,
                (
                    record.path,
                    Path(record.path).name,
                    Path(record.path).suffix.lower(),
                    record.size_bytes,
                    record.duration,
                    record.sample_rate,
                    record.bit_rate,
                    record.checksum,
                ),
            )
            count += 1
            if count % batch_size == 0:
                conn.commit()
        conn.commit()
    return count


def read_library_db(path: Path) -> List[Dict]:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    with conn:
        cur = conn.execute("SELECT path, size_bytes, duration, sample_rate, bit_rate, checksum FROM library_files")
        return [dict(row) for row in cur.fetchall()]


def read_secondary_candidates(path: Path) -> List[Dict]:
    """Read rows from a secondary_candidates table into a list of dicts.

    This mirrors the simple candidates table but includes extra metadata
    collected during a salvage-area scan.
    """
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    with conn:
        cur = conn.execute(
            "SELECT id, source_path, filename, ext, size, duration, sample_rate, bit_rate, checksum FROM secondary_candidates"
        )
        return [dict(row) for row in cur.fetchall()]


def normalise_name(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


def score_match(
    lib: Dict,
    cand: Candidate,
    min_name_similarity: float,
    size_tolerance: float,
    duration_tolerance: float,
    w_name: float,
    w_size: float,
    w_duration: float,
) -> Tuple[float, List[str]]:
    """Score a candidate against a library row and apply validation checks.

    The function returns (score, notes). If a validation fails (filename
    similarity below `min_name_similarity`, or size/duration checks fail when
    the corresponding metrics are available), the function returns (0.0, notes)
    and the caller should treat the candidate as skipped.
    """
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

    # enforce minimum name similarity
    if fname_score < float(min_name_similarity):
        notes.append("name_below_min")
        return 0.0, notes

    # size comparison (if both sizes are available)
    size_score = 0.0
    lib_size = lib.get("size_bytes")
    if cand.size is not None and lib_size:
        c = cand.size
        l = lib_size
        diff = abs(c - l)
        if diff > size_tolerance * l:
            notes.append("size_out_of_tolerance")
            return 0.0, notes
        # produce a normalized relative size score (smaller diff -> higher)
        rel = 1.0 - (diff / max(1, l))
        size_score = max(0.0, min(1.0, rel))

    # duration comparison (if both durations are available)
    dur_score = 0.0
    lib_dur = lib.get("duration")
    if cand.duration is not None and lib_dur:
        cd = cand.duration
        ld = lib_dur
        diff = abs(cd - ld)
        if diff > duration_tolerance:
            notes.append("duration_out_of_tolerance")
            return 0.0, notes
        # normalized duration score: closer durations -> higher score
        dur_score = max(0.0, min(1.0, 1.0 - (diff / max(1.0, ld))))

    # normalize weights so they sum to 1.0 (avoids needing caller to normalize)
    total_w = float(w_name + w_size + w_duration) or 1.0
    nw = float(w_name) / total_w
    sw = float(w_size) / total_w
    dw = float(w_duration) / total_w

    score = nw * fname_score + sw * size_score + dw * dur_score
    return score, notes


def match_candidates_wrapper(
    library_db: Path,
    candidates_db: Path,
    out_csv: Path,
    *,
    secondary_db: Optional[Path] = None,
    min_name_similarity: float = 0.65,
    size_tolerance: float = 0.02,
    duration_tolerance: float = 1.0,
    weight_name: float = 0.6,
    weight_size: float = 0.25,
    weight_duration: float = 0.15,
    threshold: float = 0.55,
) -> None:
    libs = read_library_db(library_db)

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
            "source_type",
        ])

        # Helper: evaluate whether candidate is strictly "better" than lib.
        def candidate_is_better(lib_row: Dict, cand_row: Dict) -> Tuple[bool, List[str]]:
            notes: List[str] = []
            # size larger
            if cand_row.get("size") and lib_row.get("size_bytes"):
                if cand_row["size"] > lib_row["size_bytes"]:
                    notes.append("size_larger")
            # duration longer
            if cand_row.get("duration") and lib_row.get("duration"):
                if cand_row["duration"] > lib_row["duration"]:
                    notes.append("duration_longer")
            # metadata quality: prefer higher bit_rate or sample_rate
            if cand_row.get("bit_rate") and lib_row.get("bit_rate"):
                if cand_row["bit_rate"] > (lib_row.get("bit_rate") or 0):
                    notes.append("bitrate_better")
            if cand_row.get("sample_rate") and lib_row.get("sample_rate"):
                if cand_row["sample_rate"] > (lib_row.get("sample_rate") or 0):
                    notes.append("samplerate_better")
            return (len(notes) > 0), notes

        matched_library_paths = set()

        # Phase 1: secondary candidates (preferred salvage pool)
        secondary_rows = []
        if secondary_db and Path(secondary_db).exists():
            secondary_rows = read_secondary_candidates(Path(secondary_db))

        for r in secondary_rows:
            cand = Candidate(
                source_path=r.get("source_path"),
                filename=r.get("filename"),
                ext=r.get("ext"),
                size=r.get("size"),
                duration=r.get("duration"),
            )
            best_score = 0.0
            best_lib = None
            best_notes: List[str] = []
            for lib in libs:
                score, notes = score_match(
                    lib,
                    cand,
                    min_name_similarity=min_name_similarity,
                    size_tolerance=size_tolerance,
                    duration_tolerance=duration_tolerance,
                    w_name=weight_name,
                    w_size=weight_size,
                    w_duration=weight_duration,
                )
                if score > best_score:
                    best_score = score
                    best_lib = lib
                    best_notes = notes

            if best_lib is None:
                continue
            if best_lib["path"] in matched_library_paths:
                continue
            if best_score >= float(threshold):
                better, reason_notes = candidate_is_better(best_lib, r)
                if better:
                    reason = ";".join(reason_notes or best_notes) or "better_candidate"
                    writer.writerow([
                        r.get("source_path"),
                        best_lib["path"].split("/")[-1],
                        reason,
                        f"{best_score:.3f}",
                        best_lib["path"],
                        best_lib.get("size_bytes"),
                        best_lib.get("duration"),
                        "secondary",
                    ])
                    matched_library_paths.add(best_lib["path"])

        # Phase 2: R-Studio recognized candidates
        conn = sqlite3.connect(candidates_db)
        conn.row_factory = sqlite3.Row
        with conn:
            rrows = conn.execute("SELECT id, source_path, filename, ext, size, duration FROM candidates").fetchall()

        for r in rrows:
            cand = Candidate(source_path=r["source_path"], filename=r["filename"], ext=r["ext"], size=r["size"], duration=r["duration"])
            best_score = 0.0
            best_lib = None
            best_notes: List[str] = []
            for lib in libs:
                if lib["path"] in matched_library_paths:
                    continue
                score, notes = score_match(
                    lib,
                    cand,
                    min_name_similarity=min_name_similarity,
                    size_tolerance=size_tolerance,
                    duration_tolerance=duration_tolerance,
                    w_name=weight_name,
                    w_size=weight_size,
                    w_duration=weight_duration,
                )
                if score > best_score:
                    best_score = score
                    best_lib = lib
                    best_notes = notes

            if best_lib is None:
                continue
            if best_score >= float(threshold):
                rdict = {"size": r["size"], "duration": r["duration"], "bit_rate": None, "sample_rate": None}
                better, reason_notes = candidate_is_better(best_lib, rdict)
                if better:
                    reason = ";".join(reason_notes or best_notes) or "better_candidate"
                    writer.writerow([
                        r["source_path"],
                        best_lib["path"].split("/")[-1],
                        reason,
                        f"{best_score:.3f}",
                        best_lib["path"],
                        best_lib.get("size_bytes"),
                        best_lib.get("duration"),
                        "rstudio",
                    ])
                    matched_library_paths.add(best_lib["path"])


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd")

    p_parse = sub.add_parser("parse-recognized")
    p_parse.add_argument("path", help="Recognized file path")
    p_parse.add_argument("--out", default="artifacts/db/recovered_candidates.db")

    p_match = sub.add_parser("match")
    p_match.add_argument("--library", default="artifacts/db/library.db")
    p_match.add_argument("--secondary", default="artifacts/db/secondary_candidates.db",
                         help="Optional DB with a secondary_candidates table (rejected copy)")
    p_match.add_argument("--candidates", default="artifacts/db/recovered_candidates.db")
    p_match.add_argument("--out", default="artifacts/reports/recovery_list.csv")
    p_match.add_argument("--min-name-similarity", type=float, default=0.65,
                         help="Minimum filename similarity to consider a candidate")
    p_match.add_argument("--size-tolerance", type=float, default=0.02,
                         help="Allowed relative size difference (fraction of library file size)")
    p_match.add_argument("--duration-tolerance", type=float, default=1.0,
                         help="Allowed absolute duration difference in seconds")
    p_match.add_argument("--weight-name", type=float, default=0.6, help="Weight for name similarity")
    p_match.add_argument("--weight-size", type=float, default=0.25, help="Weight for size similarity")
    p_match.add_argument("--weight-duration", type=float, default=0.15, help="Weight for duration similarity")
    p_match.add_argument("--threshold", type=float, default=0.55,
                         help="Minimum final score to write candidate to CSV")

    p_scan = sub.add_parser("scan")
    p_scan.add_argument("--root", default="/Volumes/COMMUNE/20_ACCEPTED")
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
        # call the centralized wrapper implementation (keeps CLI simple)
        match_candidates_wrapper(
            lib,
            cdb,
            out,
            secondary_db=Path(args.secondary) if args.secondary else None,
            min_name_similarity=args.min_name_similarity,
            size_tolerance=args.size_tolerance,
            duration_tolerance=args.duration_tolerance,
            weight_name=args.weight_name,
            weight_size=args.weight_size,
            weight_duration=args.weight_duration,
            threshold=args.threshold,
        )
        print(f"Wrote recovery CSV to {out}")
        return 0

    if args.cmd == "scan":
        root = Path(args.root)
        db_path = Path(args.database)
        # Construct ScanConfig positionally and set attributes to be robust
        # against possible signature differences in installed modules.
        cfg = dedupe_scanner.ScanConfig(root, db_path)
        if hasattr(cfg, "include_fingerprints"):
            cfg.include_fingerprints = bool(args.include_fp)
        if hasattr(cfg, "batch_size"):
            cfg.batch_size = int(args.batch_size)
        if hasattr(cfg, "resume"):
            cfg.resume = bool(args.resume)
        if hasattr(cfg, "show_progress"):
            cfg.show_progress = bool(args.progress)
        resume_flag = getattr(cfg, "resume", False)
        print(f"Starting scan of {cfg.root} -> {cfg.database} (resume={resume_flag})")
        total = dedupe_scanner.scan_library(cfg)
        print(f"Completed scan: {total} files processed")
        return 0

    p.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
