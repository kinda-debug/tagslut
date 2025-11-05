#!/usr/bin/env python3
"""
FLAC Deduplication CLI - A unified command-line interface for
FLAC deduplication tools.

Usage:
    python dedupe_cli.py <command> [options]

Commands:
    scan        Scan FLAC library and build database index
    repair      Repair broken/corrupt FLAC files
    dedupe      Find and remove duplicate FLAC files
    workflow    Run the complete scan->repair->dedupe workflow
    status      Show current deduplication status
    clean       Clean up temporary files and cache

Examples:
    python dedupe_cli.py scan --verbose
    python dedupe_cli.py workflow --commit
    python dedupe_cli.py status
"""

import argparse
import subprocess
import sys
from pathlib import Path


def run_command(cmd, description):
    """Run a command and return the result."""
    print(f"🔄 {description}...")
    try:
        result = subprocess.run(cmd, check=True,
                               capture_output=True, text=True)
        print(f"✅ {description} completed successfully")
        return result
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed: {e}")
        print(f"Error output: {e.stderr}")
        return None


def cmd_scan(args):
    """Run the scan command."""
    cmd = [sys.executable, "flac_scan.py"]

    if args.verbose:
        cmd.append("--verbose")
    if args.recompute:
        cmd.append("--recompute")
    if args.workers:
        cmd.extend(["--workers", str(args.workers)])
    if args.root:
        cmd.extend(["--root", args.root])

    return run_command(cmd, "Scanning FLAC library")


def cmd_repair(args):
    """Run the repair command."""
    cmd = [sys.executable, "flac_repair.py"]

    if args.file:
        cmd.extend(["--file", args.file])
    if args.output_dir:
        cmd.extend(["--output", args.output_dir])
    if args.verbose:
        cmd.append("--verbose")

    return run_command(cmd, "Repairing broken files")


def cmd_dedupe(args):
    """Run the deduplication command."""
    cmd = [sys.executable, "flac_dedupe.py"]

    if args.commit:
        cmd.append("--commit")
    if not args.verbose:
        cmd.append("--verbose")  # dedupe defaults to verbose=True, so we need to explicitly disable
    if args.dry_run:
        cmd.append("--dry-run")
    if args.trash_dir:
        cmd.extend(["--trash-dir", args.trash_dir])
    if args.root:
        cmd.extend(["--root", args.root])

    action = "Moving duplicates to trash" if args.commit else "Analyzing duplicates (dry run)"
    return run_command(cmd, action)


def cmd_workflow(args):
    """Run the complete workflow."""
    print("🚀 Starting complete FLAC deduplication workflow...")

    # Step 1: Scan
    if not cmd_scan(args):
        return False

    # Step 2: Check for broken files and repair if needed
    root = Path(args.root or "/Volumes/dotad/MUSIC")
    broken_playlist = root / "broken_files_unrepaired.m3u"
    if broken_playlist.exists() and broken_playlist.read_text().strip():
        print("📋 Found broken files, repairing...")
        if not cmd_repair(args):
            return False
    else:
        print("✅ No broken files found, skipping repair")

    # Step 3: Dedupe
    if not cmd_dedupe(args):
        return False

    print("🎉 Workflow completed successfully!")
    return True


def cmd_status(args):
    """Show current status."""
    root = Path(args.root or "/Volumes/dotad/MUSIC")
    db_path = root / "_DEDUP_INDEX.db"

    print(f"📊 Deduplication Status for: {root}")
    print("=" * 50)

    if db_path.exists():
        print(f"✅ Database exists: {db_path}")

        # Get some basic stats from the database
        try:
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            # Count total files
            cursor.execute("SELECT COUNT(*) FROM files")
            total_files = cursor.fetchone()[0]
            print(f"📁 Total files indexed: {total_files:,}")

            # Count duplicates found
            cursor.execute("""
                SELECT COUNT(*) FROM (
                    SELECT file_path FROM duplicates
                    GROUP BY group_id HAVING COUNT(*) > 1
                )
            """)
            duplicate_groups = cursor.fetchone()[0]
            print(f"🔍 Duplicate groups found: {duplicate_groups:,}")

            conn.close()
        except Exception as e:
            print(f"⚠️  Could not read database: {e}")
    else:
        print(f"❌ Database not found: {db_path}")
        print("   Run 'scan' command first")

    # Check for broken files playlist
    broken_playlist = root / "broken_files_unrepaired.m3u"
    if broken_playlist.exists():
        content = broken_playlist.read_text()
        if content.strip():
            broken_count = len([line for line in content.split('\n') if line.strip()])
            print(f"🔧 Broken files to repair: {broken_count}")
        else:
            print("✅ No broken files detected")
    else:
        print("✅ No broken files playlist found")

    print("=" * 50)


def cmd_clean(args):
    """Clean up temporary files and cache."""
    root = Path(args.root or "/Volumes/dotad/MUSIC")

    print("🧹 Cleaning up temporary files...")

    # Remove broken files playlist if empty
    broken_playlist = root / "broken_files_unrepaired.m3u"
    if broken_playlist.exists():
        content = broken_playlist.read_text()
        if not content.strip():
            broken_playlist.unlink()
            print("✅ Removed empty broken files playlist")

    # Clean up any __pycache__ directories
    pycache_dirs = list(root.rglob("__pycache__"))
    for pycache_dir in pycache_dirs:
        import shutil
        shutil.rmtree(pycache_dir)
        print(f"✅ Removed cache: {pycache_dir}")

    print("🧹 Cleanup completed!")


def main():
    parser = argparse.ArgumentParser(
        description="FLAC Deduplication CLI - Unified interface for FLAC deduplication tools",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        "--root",
        default="/Volumes/dotad/MUSIC",
        help="Root directory for FLAC library (default: /Volumes/dotad/MUSIC)"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Scan command
    scan_parser = subparsers.add_parser("scan", help="Scan FLAC library and build database")
    scan_parser.add_argument("--verbose", action="store_true", help="Show detailed progress")
    scan_parser.add_argument("--recompute", action="store_true", help="Force recomputation of fingerprints")
    scan_parser.add_argument("--workers", type=int, default=8, help="Number of worker threads")

    # Repair command
    repair_parser = subparsers.add_parser("repair", help="Repair broken/corrupt FLAC files")
    repair_parser.add_argument("--file", help="Repair a single file instead of playlist")
    repair_parser.add_argument("--output-dir", "-o", help="Output directory for repaired files")
    repair_parser.add_argument("--verbose", action="store_true", help="Show detailed progress")

    # Dedupe command
    dedupe_parser = subparsers.add_parser("dedupe", help="Find and remove duplicate files")
    dedupe_parser.add_argument("--commit", action="store_true", help="Actually move duplicates to trash")
    dedupe_parser.add_argument("--verbose", action="store_true", help="Show detailed progress")
    dedupe_parser.add_argument("--dry-run", action="store_true", help="Force dry-run mode")
    dedupe_parser.add_argument("--trash-dir", help="Custom directory for duplicate files")

    # Workflow command
    workflow_parser = subparsers.add_parser("workflow", help="Run complete scan->repair->dedupe workflow")
    workflow_parser.add_argument("--commit", action="store_true", help="Actually move duplicates in final step")
    workflow_parser.add_argument("--verbose", action="store_true", help="Show detailed progress")

    # Status command
    status_parser = subparsers.add_parser("status", help="Show current deduplication status")

    # Clean command
    clean_parser = subparsers.add_parser("clean", help="Clean up temporary files and cache")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Execute the appropriate command
    commands = {
        "scan": cmd_scan,
        "repair": cmd_repair,
        "dedupe": cmd_dedupe,
        "workflow": cmd_workflow,
        "status": cmd_status,
        "clean": cmd_clean,
    }

    if args.command in commands:
        success = commands[args.command](args)
        sys.exit(0 if success else 1)
    else:
        print(f"Unknown command: {args.command}")
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()