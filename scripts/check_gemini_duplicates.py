#!/usr/bin/env python3
import argparse
import csv
import os
import sqlite3
import hashlib
from dataclasses import dataclass
from typing import Dict, List, Tuple

DB_DEFAULT = "artifacts/db/library_final.db"


@dataclass
class FileRow:
    path: str
    checksum: str
    duration: float


def compute_checksum(path: str, blocksize: int = 65536) -> str:
    """
    Compute SHA1 checksum for a file on disk.
    Adjust blocksize if you want, but 64KB is reasonable.
    """
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(blocksize), b""):
            h.update(chunk)
    return h.hexdigest()


def load_library_rows(db_path: str) -> Tuple[Dict[str, FileRow], Dict[str, List[FileRow]]]:
    """Load all rows from library_files into:
      - path_index: path -> FileRow
      - checksum_index: checksum -> [FileRow,...]
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='library_files';"
    )
    if cur.fetchone() is None:
        raise SystemExit("ERROR: table 'library_files' not found in DB.")

    query = """
        SELECT path, checksum,
               COALESCE(duration, 0.0)
        FROM library_files
        WHERE checksum IS NOT NULL
    """

    rows = cur.execute(query).fetchall()
    conn.close()

    path_index: Dict[str, FileRow] = {}
    checksum_index: Dict[str, List[FileRow]] = {}

    for path, checksum, dur in rows:
        fr = FileRow(path=path, checksum=checksum, duration=float(dur or 0.0))
        path_index[path] = fr
        checksum_index.setdefault(checksum, []).append(fr)

    print(f"Loaded {len(rows)} rows from library_files (all roots)")
    print(f"Unique checksums in DB: {len(checksum_index)}")
    return path_index, checksum_index


def is_in_music_root(path: str) -> bool:
    """Return True if path is under the canonical MUSIC root."""
    return path.startswith("/Volumes/dotad/MUSIC/")


def classify_entry(
    gemini_path: str,
    analysis_row: Dict[str, str],
    path_index: Dict[str, FileRow],
    checksum_index: Dict[str, List[FileRow]],
    duration_tolerance: float,
    verbose: bool,
) -> Dict[str, str]:
    """Classify a single Gemini entry using DB-level reconciliation.

    Returns a dict for CSV output with keys:
      gemini_path, exists_on_disk, in_db, checksum, n_db_copies, n_other_copies,
      n_music_copies, best_music_path, decision, reason, delete_path
    """
    exists = os.path.isfile(gemini_path)
    exists_on_disk = "1" if exists else "0"

    # Base output structure
    out: Dict[str, str] = {
        "gemini_path": gemini_path,
        "exists_on_disk": exists_on_disk,
        "in_db": "0",
        "checksum": "",
        "n_db_copies": "0",
        "n_other_copies": "0",
        "n_music_copies": "0",
        "best_music_path": "",
        "decision": "",
        "reason": "",
        "delete_path": "",
    }

    if not exists:
        out["decision"] = "MISSING_ON_DISK"
        out["reason"] = "Gemini path does not exist on disk"
        if verbose:
            print(f"[MISSING] {gemini_path}")
        return out

    # DB row for this exact path
    fr = path_index.get(gemini_path)
    if fr is None:
        # Try checksum from analysis CSV
        checksum = (analysis_row.get("checksum") or "").strip()

        # If analysis has no checksum, compute it from disk now
        if not checksum:
            try:
                checksum = compute_checksum(gemini_path)
                if verbose:
                    print(f"[CHECKSUM] computed for {gemini_path}: {checksum}")
            except Exception as e:
                out["decision"] = "KEEP_NO_DB_ROW"
                out["reason"] = f"File exists but checksum computation failed: {e}"
                if verbose:
                    print(f"[KEEP] {gemini_path} : checksum computation failed: {e}")
                return out

        out["checksum"] = checksum

        matches = checksum_index.get(checksum, [])
        out["n_db_copies"] = str(len(matches))
        if not matches:
            out["decision"] = "KEEP_NO_DB_ROW"
            out["reason"] = "Checksum has no matches in DB"
            if verbose:
                print(f"[KEEP] {gemini_path} : checksum {checksum} not found in DB")
            return out

        music_copies = [m for m in matches if is_in_music_root(m.path)]
        out["n_music_copies"] = str(len(music_copies))

        if music_copies:
            best_music = music_copies[0]
            out["best_music_path"] = best_music.path
            out["decision"] = "SAFE_TO_DELETE"
            out["reason"] = (
                "Gemini file not in DB, checksum matches at least one file in MUSIC; "
                "MUSIC copy treated as canonical"
            )
            out["delete_path"] = gemini_path
            if verbose:
                print(
                    f"[SAFE] {gemini_path}\n"
                    f"       -> canonical in MUSIC: {best_music.path}"
                )
            return out

        # No MUSIC copies, but there are copies elsewhere in DB
        out["decision"] = "KEEP_DUPES_NO_MUSIC"
        out["reason"] = "Checksum matches only outside MUSIC; canonical not clear"
        if verbose:
            print(
                f"[KEEP] {gemini_path} : checksum matches {len(matches)} DB rows, "
                "none in MUSIC"
            )
        return out

    # We have a DB row for the Gemini path
    out["in_db"] = "1"
    out["checksum"] = fr.checksum

    matches = checksum_index.get(fr.checksum, [])
    out["n_db_copies"] = str(len(matches))

    # Exclude itself
    others = [m for m in matches if m.path != fr.path]
    out["n_other_copies"] = str(len(others))

    music_copies = [m for m in others if is_in_music_root(m.path)]
    out["n_music_copies"] = str(len(music_copies))
    if music_copies:
        best_music = music_copies[0]
        out["best_music_path"] = best_music.path

    # No other copies anywhere
    if not others:
        out["decision"] = "KEEP_UNIQUE"
        out["reason"] = "No other DB rows share this checksum"
        if verbose:
            print(f"[KEEP] {gemini_path} : unique checksum in DB")
        return out

    # Other copies exist. Now branch on where Gemini lives.
    if is_in_music_root(fr.path):
        # Gemini file is itself under MUSIC
        if music_copies:
            out["decision"] = "KEEP_DUPES_IN_MUSIC"
            out["reason"] = (
                "Gemini file is in MUSIC and other MUSIC copies share the checksum; "
                "manual review recommended"
            )
        else:
            out["decision"] = "KEEP_IN_MUSIC"
            out["reason"] = (
                "Gemini file is in MUSIC and duplicates exist only outside MUSIC; "
                "treat MUSIC copy as canonical"
            )
        if verbose:
            print(
                f"[KEEP] {gemini_path} : in MUSIC with {len(others)} other DB copies, "
                f"{len(music_copies)} also in MUSIC"
            )
        return out

    # Gemini file is NOT in MUSIC
    if music_copies:
        # Safe: at least one MUSIC copy exists
        best_music = music_copies[0]
        out["best_music_path"] = best_music.path
        out["decision"] = "SAFE_TO_DELETE"
        out["reason"] = (
            "Gemini file is outside MUSIC, checksum matches at least one file in MUSIC; "
            "MUSIC copy treated as canonical"
        )
        out["delete_path"] = gemini_path
        if verbose:
            print(
                f"[SAFE] {gemini_path}\n"
                f"       -> canonical in MUSIC: {best_music.path}"
            )
        return out

    # Duplicates exist, but none in MUSIC
    out["decision"] = "KEEP_DUPES_NO_MUSIC"
    out["reason"] = "Duplicates exist only outside MUSIC; canonical not clear"
    if verbose:
        print(
            f"[KEEP] {gemini_path} : {len(others)} other DB copies, none in MUSIC"
        )
    return out


def reconcile(
    db_path: str,
    analysis_csv: str,
    out_csv: str,
    duration_tolerance: float,
    verbose: bool,
) -> None:
    print("=== RECONCILING GEMINI LIST AGAINST DB (GLOBAL) ===")
    path_index, checksum_index = load_library_rows(db_path)

    os.makedirs(os.path.dirname(out_csv), exist_ok=True)

    with open(analysis_csv, "r", encoding="utf-8") as f_in, open(
        out_csv, "w", newline="", encoding="utf-8"
    ) as f_out:
        reader = csv.DictReader(f_in)
        fieldnames = [
            "gemini_path",
            "exists_on_disk",
            "in_db",
            "checksum",
            "n_db_copies",
            "n_other_copies",
            "n_music_copies",
            "best_music_path",
            "decision",
            "reason",
            "delete_path",
        ]
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()

        total = 0
        n_missing = 0
        n_no_checksum = 0
        n_safe = 0
        n_in_music_root = 0
        n_keep_unique = 0
        n_keep_dupes_no_music = 0
        n_keep_dupes_in_music = 0
        n_keep_no_db_row = 0

        for row in reader:
            total += 1
            gemini_path = row.get("gemini_path") or row.get("path") or ""
            gemini_path = gemini_path.strip()
            if not gemini_path:
                continue

            result = classify_entry(
                gemini_path,
                row,
                path_index,
                checksum_index,
                duration_tolerance=duration_tolerance,
                verbose=verbose,
            )
            writer.writerow(result)

            decision = result["decision"]
            if decision == "MISSING_ON_DISK":
                n_missing += 1
            elif decision == "SAFE_TO_DELETE":
                n_safe += 1
            elif decision == "KEEP_UNIQUE":
                n_keep_unique += 1
            elif decision == "KEEP_DUPES_NO_MUSIC":
                n_keep_dupes_no_music += 1
            elif decision == "KEEP_DUPES_IN_MUSIC":
                n_keep_dupes_in_music += 1
            elif decision in ("KEEP_IN_MUSIC", "KEEP_NO_DB_ROW"):
                if decision == "KEEP_NO_DB_ROW":
                    n_keep_no_db_row += 1
                else:
                    n_in_music_root += 1

            if not result["checksum"]:
                n_no_checksum += 1

    print("=== RECONCILIATION COMPLETE ===")
    print(f"Output CSV:               {out_csv}")
    print(f"Total Gemini entries:     {total}")
    print(f"  Missing on disk:        {n_missing}")
    print(f"  No checksum:            {n_no_checksum}")
    print(f"  SAFE_TO_DELETE:         {n_safe}")
    print(f"  IN_MUSIC_ROOT:          {n_in_music_root}")
    print(f"  KEEP_UNIQUE:            {n_keep_unique}")
    print(f"  KEEP_DUPES_NO_MUSIC:    {n_keep_dupes_no_music}")
    print(f"  KEEP_DUPES_IN_MUSIC:    {n_keep_dupes_in_music}")
    print(f"  KEEP_NO_DB_ROW:         {n_keep_no_db_row}")
    print()
    print("Rows with decision = SAFE_TO_DELETE have delete_path populated.")
    print("You can feed this CSV to your delete_gemini_dupes.py script if it")
    print("expects a delete_path column.")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Reconcile Gemini duplicate selections against library_final.db "
            "using DB-level checksum matches."
        )
    )
    p.add_argument("--db", default=DB_DEFAULT, help="Path to SQLite DB (library_final.db)")
    p.add_argument(
        "--analysis-csv",
        required=True,
        help="Gemini analysis CSV (e.g. gemini_dupe_analysis.csv)",
    )
    p.add_argument(
        "--out",
        required=True,
        help="Output CSV with reconciliation + delete_path decisions",
    )
    p.add_argument(
        "--duration-tolerance",
        type=float,
        default=2.0,
        help="Duration tolerance in seconds (reserved for future use)",
    )
    p.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose per-entry logging",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    reconcile(
        db_path=args.db,
        analysis_csv=args.analysis_csv,
        out_csv=args.out,
        duration_tolerance=args.duration_tolerance,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()