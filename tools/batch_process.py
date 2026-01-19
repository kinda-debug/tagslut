#!/usr/bin/env python3
"""
Batch processor for FLAC deduplication workflow.

Usage:
    python tools/batch_process.py /path/to/new/files [options]

This script automates the complete workflow:
1. SCAN - Index files with integrity verification
2. PLAN - Generate removal plan for duplicates
3. REPORT - Show unique files and duplicates
4. PROMOTE - Copy unique files to canonical library (optional)
5. APPLY - Execute removal plan (delete duplicates) (optional)
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path
from datetime import datetime

# Project root
PROJECT_ROOT = Path(__file__).parents[1]
VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"

# Defaults
DEFAULT_DB_ROOT = Path.home() / "Projects" / "dedupe_db"
DEFAULT_CANONICAL = Path("/Volumes/COMMUNE/M/Library_CANONICAL")
DEFAULT_QUARANTINE = Path("/Volumes/COMMUNE/M/_quarantine")


def run_cmd(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a command and return result."""
    print(f"\n>>> {' '.join(str(c) for c in cmd)}\n")
    return subprocess.run(cmd, check=check)


def main():
    parser = argparse.ArgumentParser(
        description="Process a directory through the deduplication workflow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Dry run (scan + plan + report only)
    python tools/batch_process.py /Volumes/new_music

    # Full execution (scan + plan + promote unique + quarantine dupes)
    python tools/batch_process.py /Volumes/new_music --execute

    # Use existing database epoch
    python tools/batch_process.py /Volumes/new_music --db-epoch 2026-01-19

    # Custom canonical library location
    python tools/batch_process.py /Volumes/new_music --canonical /path/to/library
        """
    )

    parser.add_argument("source", type=Path, help="Directory to process")
    parser.add_argument("--zone", default="suspect",
                        choices=["suspect", "staging"],
                        help="Zone to assign to source files (default: suspect)")
    parser.add_argument("--db-epoch", type=str, default=None,
                        help="Use existing epoch (YYYY-MM-DD), or create new if omitted")
    parser.add_argument("--db-root", type=Path, default=DEFAULT_DB_ROOT,
                        help=f"Database root directory (default: {DEFAULT_DB_ROOT})")
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL,
                        help=f"Canonical library path (default: {DEFAULT_CANONICAL})")
    parser.add_argument("--quarantine-root", type=Path, default=DEFAULT_QUARANTINE,
                        help=f"Quarantine directory (default: {DEFAULT_QUARANTINE})")
    parser.add_argument("--execute", action="store_true",
                        help="Actually execute promotion and quarantine (default: dry run)")
    parser.add_argument("--skip-scan", action="store_true",
                        help="Skip scanning (use existing database)")
    parser.add_argument("--skip-canonical-scan", action="store_true",
                        help="Skip scanning canonical library (already in database)")
    parser.add_argument("--promote-only", action="store_true",
                        help="Only promote unique files, skip quarantine")
    parser.add_argument("--quarantine-only", action="store_true",
                        help="Only quarantine duplicates, skip promotion")

    args = parser.parse_args()

    # Validate source
    if not args.source.exists():
        print(f"ERROR: Source directory does not exist: {args.source}")
        sys.exit(1)

    # Determine epoch and database path
    if args.db_epoch:
        epoch = args.db_epoch
    else:
        epoch = datetime.now().strftime("%Y-%m-%d")

    epoch_dir = args.db_root / f"EPOCH_{epoch}"
    epoch_dir.mkdir(parents=True, exist_ok=True)
    db_path = epoch_dir / "music.db"

    print("=" * 70)
    print("BATCH PROCESSING WORKFLOW")
    print("=" * 70)
    print(f"Source:      {args.source}")
    print(f"Zone:        {args.zone}")
    print(f"Database:    {db_path}")
    print(f"Canonical:   {args.canonical}")
    print(f"Quarantine:  {args.quarantine_root}")
    print(f"Mode:        {'EXECUTE' if args.execute else 'DRY RUN'}")
    print("=" * 70)

    # Working directory
    work_dir = epoch_dir / "batch_work"
    work_dir.mkdir(exist_ok=True)

    removal_plan = work_dir / "removal_plan.json"
    unique_files = work_dir / "unique_files.txt"
    promote_log = work_dir / "promote.log"

    # =========================================================================
    # STAGE 1: SCAN
    # =========================================================================
    if not args.skip_scan:
        print("\n" + "=" * 70)
        print("STAGE 1: SCAN")
        print("=" * 70)

        # Scan canonical library first (if not skipped and exists)
        if not args.skip_canonical_scan and args.canonical.exists():
            print(f"\nScanning canonical library: {args.canonical}")
            run_cmd([
                str(VENV_PYTHON), str(PROJECT_ROOT / "tools" / "integrity" / "scan.py"),
                str(args.canonical),
                "--db", str(db_path),
                "--zone", "accepted",
                "--check-integrity",
                "--check-hash",
                "--create-db",
                "--progress"
            ])

        # Scan source directory
        print(f"\nScanning source: {args.source}")
        run_cmd([
            str(VENV_PYTHON), str(PROJECT_ROOT / "tools" / "integrity" / "scan.py"),
            str(args.source),
            "--db", str(db_path),
            "--zone", args.zone,
            "--check-integrity",
            "--check-hash",
            "--create-db" if not (args.canonical.exists() and not args.skip_canonical_scan) else "",
            "--progress"
        ])

    # =========================================================================
    # STAGE 2: DATABASE STATE
    # =========================================================================
    print("\n" + "=" * 70)
    print("DATABASE STATE")
    print("=" * 70)

    import sqlite3
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT zone,
               COUNT(*) as files,
               SUM(CASE WHEN integrity_state='valid' THEN 1 ELSE 0 END) as valid,
               SUM(CASE WHEN integrity_state='corrupt' THEN 1 ELSE 0 END) as corrupt,
               ROUND(SUM(size)/1024.0/1024.0/1024.0, 2) as size_gb
        FROM files
        GROUP BY zone
        ORDER BY CASE zone
            WHEN 'accepted' THEN 1
            WHEN 'staging' THEN 2
            WHEN 'suspect' THEN 3
            WHEN 'quarantine' THEN 4
        END
    """)

    print(f"\n{'Zone':<12} {'Files':>8} {'Valid':>8} {'Corrupt':>8} {'Size GB':>10}")
    print("-" * 50)
    for row in cursor.fetchall():
        print(f"{row[0]:<12} {row[1]:>8} {row[2]:>8} {row[3]:>8} {row[4]:>10}")

    # =========================================================================
    # STAGE 3: PLAN
    # =========================================================================
    print("\n" + "=" * 70)
    print("STAGE 3: GENERATE REMOVAL PLAN")
    print("=" * 70)

    run_cmd([
        str(VENV_PYTHON), str(PROJECT_ROOT / "tools" / "decide" / "recommend.py"),
        "--db", str(db_path),
        "--output", str(removal_plan),
        "--priority", "accepted",
        "--priority", "staging",
        "--priority", "suspect",
        "--priority", "quarantine"
    ])

    # =========================================================================
    # STAGE 4: FIND UNIQUE FILES
    # =========================================================================
    print("\n" + "=" * 70)
    print("STAGE 4: FIND UNIQUE FILES")
    print("=" * 70)

    cursor.execute(f"""
        SELECT path FROM files
        WHERE zone = ?
          AND sha256 IS NOT NULL
          AND integrity_state = 'valid'
          AND sha256 NOT IN (
              SELECT sha256 FROM files
              WHERE zone = 'accepted' AND sha256 IS NOT NULL
          )
        ORDER BY path
    """, (args.zone,))

    unique_paths = [row[0] for row in cursor.fetchall()]

    with open(unique_files, 'w') as f:
        for path in unique_paths:
            f.write(path + '\n')

    print(f"\nUnique files (not in canonical library): {len(unique_paths)}")
    print(f"Saved to: {unique_files}")

    # Count duplicates
    cursor.execute(f"""
        SELECT COUNT(*) FROM files
        WHERE zone = ?
          AND sha256 IS NOT NULL
          AND sha256 IN (
              SELECT sha256 FROM files
              WHERE zone = 'accepted' AND sha256 IS NOT NULL
          )
    """, (args.zone,))
    dupe_count = cursor.fetchone()[0]
    print(f"Duplicates (already in canonical library): {dupe_count}")

    conn.close()

    # =========================================================================
    # STAGE 5: PROMOTE UNIQUE FILES
    # =========================================================================
    if not args.quarantine_only and len(unique_paths) > 0:
        print("\n" + "=" * 70)
        print(f"STAGE 5: PROMOTE UNIQUE FILES ({'EXECUTE' if args.execute else 'DRY RUN'})")
        print("=" * 70)

        promote_cmd = [
            str(VENV_PYTHON), str(PROJECT_ROOT / "tools" / "review" / "promote_by_tags.py"),
            "--paths-from-file", str(unique_files),
            "--dest-root", str(args.canonical),
            "--mode", "copy",
            "--no-resume",
            "--progress-every-seconds", "5"
        ]

        if args.execute:
            promote_cmd.extend(["--execute", "--log-file", str(promote_log)])

        run_cmd(promote_cmd, check=False)

        if args.execute:
            print(f"\nPromotion log: {promote_log}")

    # =========================================================================
    # STAGE 6: QUARANTINE DUPLICATES
    # =========================================================================
    if not args.promote_only and removal_plan.exists():
        print("\n" + "=" * 70)
        print(f"STAGE 6: APPLY REMOVAL PLAN ({'EXECUTE' if args.execute else 'DRY RUN'})")
        print("=" * 70)

        apply_cmd = [
            str(VENV_PYTHON), str(PROJECT_ROOT / "tools" / "decide" / "apply.py"),
            "--input", str(removal_plan)
        ]

        if args.execute:
            apply_cmd.append("--confirm")

        run_cmd(apply_cmd, check=False)

    # =========================================================================
    # SUMMARY
    # =========================================================================
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Database:        {db_path}")
    print(f"Removal plan:    {removal_plan}")
    print(f"Unique files:    {unique_files} ({len(unique_paths)} files)")
    print(f"Mode:            {'EXECUTED' if args.execute else 'DRY RUN - use --execute to apply'}")
    print("=" * 70)


if __name__ == "__main__":
    main()
