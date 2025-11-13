#!/usr/bin/env python3
"""
Fast file-MD5 deduplication scanner (file structure).

Much faster than audio-MD5 (1–2 sec/file vs 5–10 sec/file). Finds
byte-identical files, not audio-equivalent content.

With --audio-fingerprint flag, also computes audio fingerprints using
Chromaprint/fpcalc for audio-identical detection.
"""

import argparse
import csv
import hashlib
import signal
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Import audio fingerprinting from lib
try:
    from scripts.lib.common import compute_fingerprint
except ImportError:
    try:
        from lib.common import compute_fingerprint
    except ImportError:

        def compute_fingerprint(
            path: Path,
        ) -> Tuple[Optional[List[int]], Optional[str]]:
            """Fallback if lib not found."""
            return (None, None)


AUDIO_EXTS = {
    ".flac",
    ".mp3",
    ".m4a",
    ".aac",
    ".wav",
    ".aif",
    ".aiff",
    ".aifc",
    ".ogg",
    ".opus",
    ".wma",
    ".mka",
    ".mkv",
    ".alac",
}

DB_PATH = Path.home() / ".cache" / "file_dupes.db"

interrupted = False


def signal_handler(_signum: int, _frame: Any) -> None:
    """Handle Ctrl+C gracefully."""
    print("\n[INFO] Interrupt received. Saving progress...", file=sys.stderr)
    # Set module-level flag without 'global' statement
    globals()["interrupted"] = True


def init_db(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Initialize database and schema."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA synchronous=NORMAL")
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS file_hashes (
            file_path TEXT PRIMARY KEY,
            file_md5 TEXT NOT NULL,
            file_size INTEGER,
            scan_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            audio_fingerprint TEXT,
            audio_fingerprint_hash TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_file_md5
        ON file_hashes(file_md5)
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_audio_fingerprint_hash
        ON file_hashes(audio_fingerprint_hash)
        """
    )
    conn.commit()
    return conn


def file_md5(path: Path) -> Optional[str]:
    """Return MD5 of file bytes, or None on error."""
    try:
        md5_hash = hashlib.md5()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                md5_hash.update(chunk)
        return md5_hash.hexdigest()
    except OSError as e:
        print(f"  Error hashing {path.name}: {e}", file=sys.stderr)
        return None


def scan_directory(
    root: Path,
    conn: sqlite3.Connection,
    verbose: bool = True,
    output_csv: Optional[Path] = None,
    checkpoint: int = 200,
    heartbeat_path: Optional[Path] = None,
    audio_fingerprint: bool = False,
) -> Dict[str, List[Path]]:
    """Scan directory and hash files.

    Verbose by default. Writes a heartbeat file every ~30s with counters so
    external monitors can detect stalls.

    If audio_fingerprint=True, also computes audio fingerprints using
    Chromaprint. This is much slower (~5-10 sec/file vs 1-2 sec/file).
    """

    cur = conn.cursor()
    # Preload existing hashes (resume without rehashing)
    existing: Dict[str, str] = {}
    existing_audio: Dict[str, str] = {}
    try:
        cur.execute("SELECT file_path, file_md5 FROM file_hashes")
        for fp, md5 in cur.fetchall():
            existing[fp] = md5
        if audio_fingerprint:
            cur.execute(
                "SELECT file_path, audio_fingerprint_hash FROM file_hashes "
                "WHERE audio_fingerprint_hash IS NOT NULL"
            )
            for fp, afp_hash in cur.fetchall():
                existing_audio[fp] = afp_hash
    except sqlite3.OperationalError:
        existing = {}
        existing_audio = {}

    hash_map: Dict[str, List[Path]] = defaultdict(list)
    audio_files: List[Path] = []
    for ext in AUDIO_EXTS:
        audio_files.extend(root.rglob(f"*{ext}"))

    total_files = len(audio_files)
    print(f"[INFO] Found {total_files} audio files", file=sys.stderr)
    start_time = time.time()
    last_heartbeat = 0.0

    for i, file_path in enumerate(audio_files, 1):
        if interrupted:
            print("[INFO] Scan interrupted", file=sys.stderr)
            break

        file_str = str(file_path)
        if verbose:
            print(f"[{i}/{total_files}] {file_path.name}...", file=sys.stderr)
        else:
            print(f"[{i}/{total_files}]", end="\r", file=sys.stderr)

        # Resume from DB when possible
        file_hash: Optional[str]
        if file_str in existing:
            file_hash = existing[file_str]
        else:
            file_hash = file_md5(file_path)

        # Compute audio fingerprint if requested
        audio_fp_hash: Optional[str] = None
        if audio_fingerprint:
            if file_str in existing_audio:
                audio_fp_hash = existing_audio[file_str]
                if verbose:
                    print(
                        "  [Using cached audio fingerprint]",
                        file=sys.stderr,
                    )
            else:
                if verbose:
                    print(
                        "  [Computing audio fingerprint...]",
                        file=sys.stderr,
                    )
                _, audio_fp_hash = compute_fingerprint(file_path)
                if audio_fp_hash and verbose:
                    fp_short = audio_fp_hash[:16]
                    print(
                        f"  [Audio fingerprint: {fp_short}...]",
                        file=sys.stderr,
                    )

        if file_hash:
            hash_map[file_hash].append(file_path)
            try:
                file_size = file_path.stat().st_size
                retries = 3
                while retries > 0:
                    try:
                        if audio_fingerprint and audio_fp_hash:
                            cur.execute(
                                """
                                INSERT OR REPLACE INTO file_hashes
                                (file_path, file_md5, file_size,
                                 audio_fingerprint_hash)
                                VALUES (?, ?, ?, ?)
                                """,
                                (
                                    file_str,
                                    file_hash,
                                    file_size,
                                    audio_fp_hash,
                                ),
                            )
                        else:
                            cur.execute(
                                """
                                INSERT OR REPLACE INTO file_hashes
                                (file_path, file_md5, file_size)
                                VALUES (?, ?, ?)
                                """,
                                (file_str, file_hash, file_size),
                            )
                        break
                    except sqlite3.OperationalError as e:
                        if "database is locked" in str(e) and retries > 1:
                            retries -= 1
                            time.sleep(0.5)
                        else:
                            raise
            except (OSError, sqlite3.OperationalError):
                pass

        if i % 100 == 0:
            conn.commit()

        if output_csv and checkpoint > 0 and i % checkpoint == 0:
            try:
                _write_csv_snapshot(hash_map, output_csv)
                print(
                    f" [CSV updated at {i}/{total_files}]",
                    file=sys.stderr,
                )
            except OSError:
                pass

        now = time.time()
        if heartbeat_path and (now - last_heartbeat) >= 30:
            last_heartbeat = now
            try:
                rate = i / (now - start_time) if now > start_time else 0.0
                with heartbeat_path.open("w", encoding="utf-8") as hb:
                    hb.write(
                        f"files_scanned={i}\n"
                        f"total_files={total_files}\n"
                        f"elapsed_sec={int(now - start_time)}\n"
                        f"rate_per_sec={rate:.2f}\n"
                        f"timestamp={int(now)}\n"
                    )
            except OSError:
                pass

    conn.commit()
    print("", file=sys.stderr)
    return hash_map


def _write_csv_snapshot(
    hash_map: Dict[str, List[Path]],
    output_csv: Path,
) -> None:
    """Write current duplicate groups to CSV (overwrites)."""
    duplicates = {h: p for h, p in hash_map.items() if len(p) > 1}
    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "md5_hash", "count", "keeper_path", "duplicate_paths"
        ])
        for md5_hex, paths in sorted(
            duplicates.items(), key=lambda x: len(x[1]), reverse=True
        ):
            keeper = paths[0]
            dupes = paths[1:]
            dup_paths = " | ".join(str(p) for p in dupes)
            writer.writerow([md5_hex, len(paths), keeper, dup_paths])


def report_cross_dupes(conn: sqlite3.Connection, output_path: Path) -> None:
    """Generate deduplication report from DB."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT file_md5, COUNT(*) as count
        FROM file_hashes
        GROUP BY file_md5
        HAVING count > 1
        ORDER BY count DESC
        """
    )
    duplicates: Dict[str, List[Path]] = {}
    for md5_hex, _ in cur.fetchall():
        cur.execute(
            "SELECT file_path FROM file_hashes WHERE file_md5 = ?",
            (md5_hex,),
        )
        paths = [Path(row[0]) for row in cur.fetchall()]
        duplicates[md5_hex] = paths

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "md5_hash", "count", "keeper_path", "duplicate_paths"
        ])
        for md5_hex, paths in sorted(duplicates.items()):
            keeper = paths[0]
            dupes = paths[1:]
            dup_paths = " | ".join(str(p) for p in dupes)
            writer.writerow([md5_hex, len(paths), keeper, dup_paths])

    print(f"[INFO] Report written to {output_path}", file=sys.stderr)
    total_dupes = sum(len(p) - 1 for p in duplicates.values())
    print("\n=== SCAN SUMMARY ===", file=sys.stderr)
    print(f"Duplicate groups: {len(duplicates)}", file=sys.stderr)
    print(f"Files to delete: {total_dupes}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fast file-MD5 deduplication (byte-identical files)"
    )
    parser.add_argument(
        "directory", type=Path, nargs="?", help="Directory to scan"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/tmp/file_dupes.csv"),
        help="Output CSV file",
    )
    parser.add_argument(
        "--db", type=Path, default=DB_PATH, help="SQLite DB path"
    )
    parser.add_argument(
        "--report", action="store_true", help="Report from DB only"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Disable verbose per-file output (verbose is default)",
    )
    parser.add_argument(
        "--heartbeat",
        type=Path,
        default=Path("/tmp/find_dupes_fast.heartbeat"),
        help="Heartbeat file path",
    )
    parser.add_argument(
        "--watchdog", action="store_true", help="Auto relaunch loop"
    )
    parser.add_argument(
        "--watchdog-timeout",
        type=int,
        default=120,
        help="Seconds of no heartbeat before relaunch",
    )
    parser.add_argument(
        "--audio-fingerprint",
        action="store_true",
        help="Compute audio fingerprints (slower, ~5-10 sec/file)",
    )

    args = parser.parse_args()

    # Avoid SIGPIPE killing the process when output is piped to a closed reader
    try:
        signal.signal(signal.SIGPIPE, signal.SIG_IGN)
    except (ValueError, AttributeError):
        pass

    conn = init_db(args.db)

    if args.report:
        report_cross_dupes(conn, args.output)
        conn.close()
        return 0

    if not args.directory:
        parser.error("directory required unless --report is specified")

    if not args.directory.is_dir():
        print(f"❌ Directory not found: {args.directory}", file=sys.stderr)
        conn.close()
        return 1

    signal.signal(signal.SIGINT, signal_handler)

    def _run_once() -> int:
        if args.audio_fingerprint:
            print(
                "[INFO] Scan with audio fingerprinting (SLOW)",
                file=sys.stderr,
            )
        else:
            print(
                "[INFO] Fast scan (file MD5, not audio decode)",
                file=sys.stderr,
            )
        print(f"[INFO] Scanning {args.directory}...", file=sys.stderr)
        hash_map = scan_directory(
            args.directory,
            conn,
            verbose=not args.quiet,
            output_csv=args.output,
            checkpoint=200,
            heartbeat_path=args.heartbeat,
            audio_fingerprint=args.audio_fingerprint,
        )
        duplicates = {h: p for h, p in hash_map.items() if len(p) > 1}
        print(
            f"[INFO] Found {len(duplicates)} duplicate groups",
            file=sys.stderr,
        )
        with args.output.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "md5_hash", "count", "keeper_path", "duplicate_paths"
            ])
            for md5_hex, paths in sorted(
                duplicates.items(), key=lambda x: len(x[1]), reverse=True
            ):
                keeper = paths[0]
                dupes = paths[1:]
                dup_paths = " | ".join(str(p) for p in dupes)
                writer.writerow([md5_hex, len(paths), keeper, dup_paths])
        print(f"[INFO] Report written to {args.output}", file=sys.stderr)
        total_dupes = sum(len(p) - 1 for p in duplicates.values())
        print("\n=== SCAN SUMMARY ===", file=sys.stderr)
        print(f"Total files scanned: {len(hash_map)}", file=sys.stderr)
        print(f"Duplicate groups: {len(duplicates)}", file=sys.stderr)
        print(f"Files to delete: {total_dupes}", file=sys.stderr)
        print("Estimated space savings: ", end="", file=sys.stderr)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT SUM(file_size)
            FROM (
                SELECT file_size, row_number()
                    OVER (PARTITION BY file_md5 ORDER BY file_path)
                    as rn
                FROM file_hashes
            )
            WHERE rn > 1
            """
        )
        res = cur.fetchone()
        if res and res[0]:
            size_gb = res[0] / (1024 ** 3)
            print(f"{size_gb:.2f} GB", file=sys.stderr)
        else:
            print("0 GB", file=sys.stderr)
        return 0

    if args.watchdog:
        print("[INFO] Watchdog enabled", file=sys.stderr)
        while True:
            exit_code = _run_once()
            if interrupted:
                print("[INFO] Exiting after user interrupt", file=sys.stderr)
                break
            try:
                if args.heartbeat.exists():
                    age = time.time() - args.heartbeat.stat().st_mtime
                    if age > args.watchdog_timeout:
                        msg = (
                            f"[WATCHDOG] Heartbeat stale {int(age)}s; "
                            "relaunching"
                        )
                        print(msg, file=sys.stderr)
                        continue
                else:
                    print("[WATCHDOG] Heartbeat missing; relaunching",
                          file=sys.stderr)
                    continue
            except OSError:
                print("[WATCHDOG] Error reading heartbeat; relaunching",
                      file=sys.stderr)
                continue
            break
        ret = exit_code
    else:
        ret = _run_once()

    conn.close()
    return ret


if __name__ == "__main__":
    sys.exit(main())
