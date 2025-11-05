#!/usr/bin/env python3
"""
file_operations.py - File operations manager

Consolidates filesystem utilities for FLAC deduplication:
- Archive root artifacts
- Move duplicates to trash
- Collect repair logs

Usage:
  python file_operations.py archive [--dest archive/] [--root .]
  python file_operations.py move-trash [--report /path/to/csv] [--dry-run]
  python file_operations.py collect-logs [--repaired-dir /path] [--out-file]
"""

import argparse
import glob
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Tuple


def cmd_archive(args):
    """Archive common top-level artifacts into an archive directory."""
    root_dir = Path(args.root or ".")
    archive_dest = Path(args.dest or "archive")
    
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest_path = archive_dest / f"root_archive_{ts}"
    dest_path.mkdir(parents=True, exist_ok=True)
    
    manifest_path = dest_path / "manifest.txt"
    
    print(f"🗂️  Archiving files to: {dest_path}")
    
    # Patterns to archive from repo root (maxdepth 1 only)
    file_patterns = [
        "consolidate_audio_artifacts.py",
        "consolidate_audio_artifacts.py.backup.*",
        "consolidate_audio_artifacts.py.bak",
        "consolidated.csv",
        "corrupt_now.csv",
        "corrupt.csv",
        "dd_missing_flac.txt",
        "dedupe_apply_*.csv",
        "dedupe_crossformat_*.csv",
        "dedupe_quarantine_*.csv",
        "dedupe_report_*.csv",
        "dedupe_swap*.py",
        "delude_dir.sh",
        "duplicates selected by gemini.txt",
        "health_scan.sh",
        "health_summary.md",
        "live_health.csv",
        "out.txt.txt",
        "preseed_flac_cache.py",
        "quarantine_*.sh",
        "quarantine_hash_verification.csv",
        "quarantine_verification_report.csv",
        "similar_candidates.csv",
        "SUMMARY.txt",
        "sync_*.sh",
        "temp_audio_dedupe*.py",
        "useful_scan.py",
        "verify_*.sh",
        "verify_near_dupes.py",
        "verify_quarantine.sh",
    ]
    
    manifest_entries = []
    
    # Archive files
    for pattern in file_patterns:
        for file_path in glob.glob(str(root_dir / pattern)):
            file_p = Path(file_path)
            if file_p.is_file():
                try:
                    shutil.move(str(file_p), str(dest_path / file_p.name))
                    print(f"✅ Moved: {file_p.name}")
                    manifest_entries.append(file_p.name)
                except Exception as e:
                    print(f"⚠️  Error moving {file_p.name}: {e}")
    
    # Archive directories
    dir_patterns = ["near_dupe_verify_out", "useful_scan_out_*"]
    for pattern in dir_patterns:
        for dir_path in glob.glob(str(root_dir / pattern)):
            dir_p = Path(dir_path)
            if dir_p.is_dir():
                try:
                    shutil.move(str(dir_p), str(dest_path / dir_p.name))
                    print(f"✅ Moved: {dir_p.name}/")
                    manifest_entries.append(f"{dir_p.name}/")
                except Exception as e:
                    print(f"⚠️  Error moving {dir_p.name}: {e}")
    
    # Write manifest
    with open(manifest_path, "w") as f:
        for entry in manifest_entries:
            f.write(f"{entry}\n")
    
    print(f"📋 Manifest written to: {manifest_path}")
    print(f"📊 Summary: {len(manifest_entries)} items archived")
    print(f"✅ Done. Review {manifest_path} to see what was moved.")
    
    return 0


def cmd_move_trash(args):
    """Move duplicate audio files marked 'plan' in dedup report to trash."""
    report_path = Path(args.report or "/Volumes/dotad/MUSIC/_DEDUP_REPORT_20251028_014226.csv")
    
    if not report_path.exists():
        print(f"❌ Dedup report not found: {report_path}")
        return 1
    
    trash_root = Path("/Volumes/dotad/MUSIC/_TRASH_DUPES_20251028_014226")
    log_path = Path(f"move_dupes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    dry_run = args.dry_run
    
    print("🚀 Starting duplicate move process...")
    print(f"📝 Log: {log_path}")
    print(f"🗑️  Trash root: {trash_root}")
    if dry_run:
        print("🔍 DRY RUN MODE")
    print()
    
    try:
        import csv
        
        moved_count = 0
        failed_count = 0
        skipped_count = 0
        
        with open(report_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                # Parse CSV (assuming columns like source, dest, status)
                try:
                    # Adjust field names based on actual CSV structure
                    status = row.get("status") or row.get("Status", "")
                    if status != "plan":
                        continue
                    
                    src = row.get("source") or row.get("Source", "")
                    dest = row.get("dest") or row.get("Dest", "")
                    
                    if not src or not dest:
                        continue
                    
                    src_path = Path(src.strip('"'))
                    dest_path = Path(dest.strip('"'))
                    
                    # Skip if source doesn't exist
                    if not src_path.exists():
                        msg = f"⚠️  Skipping missing: {src_path}"
                        print(msg)
                        with open(log_path, "a") as log:
                            log.write(msg + "\n")
                        skipped_count += 1
                        continue
                    
                    # Ensure destination directory exists
                    dest_dir = dest_path.parent
                    
                    if dry_run:
                        msg = f"mkdir -p '{dest_dir}'"
                        print(msg)
                        with open(log_path, "a") as log:
                            log.write(msg + "\n")
                    else:
                        dest_dir.mkdir(parents=True, exist_ok=True)
                    
                    # Move file using rsync for safety and resumability
                    if dry_run:
                        msg = f"rsync -av --remove-source-files '{src_path}' '{dest_dir}/'"
                        print(msg)
                        with open(log_path, "a") as log:
                            log.write(msg + "\n")
                    else:
                        try:
                            subprocess.run(
                                ["rsync", "-av", "--remove-source-files", 
                                 "--progress", str(src_path), f"{dest_dir}/"],
                                check=True,
                                stdout=open(log_path, "a"),
                                stderr=subprocess.STDOUT
                            )
                            
                            # Verify move
                            if dest_path.exists():
                                msg = f"✅ Moved: {src_path} → {dest_path}"
                                print(msg)
                                with open(log_path, "a") as log:
                                    log.write(msg + "\n")
                                moved_count += 1
                            else:
                                msg = f"❌ Failed: {src_path}"
                                print(msg)
                                with open(log_path, "a") as log:
                                    log.write(msg + "\n")
                                failed_count += 1
                        except subprocess.CalledProcessError as e:
                            msg = f"❌ Rsync error for {src_path}: {e}"
                            print(msg)
                            with open(log_path, "a") as log:
                                log.write(msg + "\n")
                            failed_count += 1
                
                except Exception as e:
                    print(f"⚠️  Error processing row: {e}")
                    with open(log_path, "a") as log:
                        log.write(f"Error: {e}\n")
        
        # Clean up empty directories after move
        if not dry_run:
            print("\n🧹 Cleaning empty directories...")
            try:
                # This is a simplification; in bash we use: find ... -type d -empty -delete
                # For Python we need to be more careful
                music_root = Path("/Volumes/dotad/MUSIC")
                if music_root.exists():
                    for dirpath in sorted(music_root.rglob("*"), reverse=True):
                        if dirpath.is_dir():
                            try:
                                if not any(dirpath.iterdir()):  # Check if empty
                                    dirpath.rmdir()
                            except OSError:
                                pass
            except Exception as e:
                print(f"⚠️  Error cleaning directories: {e}")
        
        print(f"\n✅ Done. Log saved at: {log_path}")
        print(f"📊 Summary: {moved_count} moved, {failed_count} failed, {skipped_count} skipped")
        
        return 0 if failed_count == 0 else 1
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


def cmd_collect_logs(args):
    """Collect non-empty ffmpeg stderr logs from REPAIRED tree into tarball."""
    repaired_dir = Path(args.repaired_dir or "/Volumes/dotad/MUSIC/REPAIRED")
    out_file = Path(args.out_file or f"repair_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.tar.gz")
    
    if not repaired_dir.exists():
        print(f"❌ Repaired directory not found: {repaired_dir}")
        return 1
    
    # Find non-empty .stderr.log files
    log_files = []
    for log_file in repaired_dir.rglob("*.stderr.log"):
        if log_file.stat().st_size > 0:
            log_files.append(log_file)
    
    if not log_files:
        print(f"❌ No non-empty stderr logs found under {repaired_dir}")
        return 1
    
    # Create tarball
    try:
        with tarfile.open(out_file, "w:gz") as tar:
            for log_file in log_files:
                # Add with relative path for cleaner structure
                arcname = log_file.relative_to(repaired_dir.parent)
                tar.add(log_file, arcname=arcname)
        
        print(f"✅ Wrote {out_file} (contains {len(log_files)} log files)")
        return 0
        
    except Exception as e:
        print(f"❌ Error creating tarball: {e}")
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="File operations manager for FLAC deduplication",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    subparsers = parser.add_subparsers(dest="command", required=True, help="Available commands")
    
    # Archive command
    archive_parser = subparsers.add_parser("archive", help="Archive root artifacts")
    archive_parser.add_argument("--dest", default="archive/", help="Archive destination directory")
    archive_parser.add_argument("--root", default=".", help="Root directory to scan")
    archive_parser.set_defaults(func=cmd_archive)
    
    # Move trash command
    move_parser = subparsers.add_parser("move-trash", help="Move duplicates to trash")
    move_parser.add_argument("--report", default="/Volumes/dotad/MUSIC/_DEDUP_REPORT_20251028_014226.csv",
                            help="Path to dedupe report CSV")
    move_parser.add_argument("--dry-run", action="store_true", help="Dry run mode (no actual moves)")
    move_parser.set_defaults(func=cmd_move_trash)
    
    # Collect logs command
    logs_parser = subparsers.add_parser("collect-logs", help="Collect repair stderr logs")
    logs_parser.add_argument("--repaired-dir", default="/Volumes/dotad/MUSIC/REPAIRED",
                            help="Directory containing repaired files")
    logs_parser.add_argument("--out-file", help="Output tarball path")
    logs_parser.set_defaults(func=cmd_collect_logs)
    
    args = parser.parse_args()
    
    if hasattr(args, "func"):
        return args.func(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
