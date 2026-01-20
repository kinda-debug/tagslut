#!/usr/bin/env python3
"""
DupeGuru Duplicate Handler for FLAC Dedupe System
Safely quarantines duplicate files identified by dupeGuru
"""

import json
import shutil
import sqlite3
import hashlib
from pathlib import Path
from datetime import datetime
import sys

class DupeGuruHandler:
    def __init__(self, action_plan_path, db_path, quarantine_dir):
        self.action_plan_path = Path(action_plan_path)
        self.db_path = Path(db_path)
        self.quarantine_dir = Path(quarantine_dir)
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)

        # Load action plan
        with open(self.action_plan_path) as f:
            self.plan = json.load(f)

        # Connect to database
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()

        # Operation log
        self.operation_log = {
            "timestamp": datetime.now().isoformat(),
            "action_plan": str(self.action_plan_path),
            "quarantine_dir": str(self.quarantine_dir),
            "files_quarantined": 0,
            "space_freed_gb": 0,
            "errors": [],
            "quarantined_files": []
        }

    def verify_file_exists(self, path):
        """Check if file exists before processing"""
        return Path(path).exists()

    def quarantine_file(self, filepath, group_id):
        """Move file to quarantine with metadata preservation"""
        source = Path(filepath)

        if not source.exists():
            self.operation_log['errors'].append(f"File not found: {filepath}")
            return False

        # Create quarantine subdir by group
        group_dir = self.quarantine_dir / f"group_{group_id:04d}"
        group_dir.mkdir(parents=True, exist_ok=True)

        # Target path
        target = group_dir / source.name

        # Handle name collisions
        counter = 1
        while target.exists():
            target = group_dir / f"{source.stem}_{counter}{source.suffix}"
            counter += 1

        try:
            # Move file
            # PERFORM COPY ONLY
            # ABSOLUTELY NO DELETION ALLOWED.
            shutil.copy2(str(source), str(target))

            # Verify target exists and has matching size
            if not (target.exists() and target.stat().st_size == source.stat().st_size):
                raise IOError("Target file validation failed after copy")

            # log(f"[PROMOTED] (Source remains) {source} -> {target}")

            # Log
            size_mb = target.stat().st_size / 1024**2
            self.operation_log['files_quarantined'] += 1
            self.operation_log['space_freed_gb'] += size_mb / 1024
            self.operation_log['quarantined_files'].append({
                "original_path": str(source),
                "quarantine_path": str(target),
                "group_id": group_id,
                "size_mb": size_mb
            })

            return True

        except Exception as e:
            self.operation_log['errors'].append(f"Error moving {filepath}: {e}")
            return False

    def update_database(self, filepath, new_zone='quarantine'):
        """Update database zone for quarantined file"""
        try:
            self.cursor.execute("""
                UPDATE files
                SET zone = ?, updated_at = ?
                WHERE path = ?
            """, (new_zone, datetime.now().isoformat(), str(filepath)))
            self.conn.commit()
        except Exception as e:
            self.operation_log['errors'].append(f"DB update failed for {filepath}: {e}")

    def process_duplicates(self, dry_run=False):
        """Process all duplicate groups"""
        print("=" * 70)
        print("DUPEGURU DUPLICATE REMOVAL")
        print("=" * 70)
        print(f"\nMode: {'DRY RUN' if dry_run else 'LIVE'}")
        print(f"Quarantine: {self.quarantine_dir}")
        print(f"Database: {self.db_path}")
        print()

        total_groups = len(self.plan['duplicate_groups'])

        for i, group in enumerate(self.plan['duplicate_groups'], 1):
            group_id = group['group_id']
            keeper = group['keeper']['path']
            duplicates = group['duplicates']

            print(f"\r[{i}/{total_groups}] Processing group {group_id}...", end='', flush=True)

            # Verify keeper exists
            if not self.verify_file_exists(keeper):
                self.operation_log['errors'].append(f"Keeper missing: {keeper}")
                continue

            # Process duplicates
            for dup in duplicates:
                dup_path = dup['path']

                if dry_run:
                    # Just log what would happen
                    print(f"\n  [DRY RUN] Would quarantine: {Path(dup_path).name}")
                else:
                    # Actually quarantine
                    if self.quarantine_file(dup_path, group_id):
                        self.update_database(dup_path, 'quarantine')

        print("\n\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)
        print(f"Groups processed: {total_groups:,}")
        print(f"Files quarantined: {self.operation_log['files_quarantined']:,}")
        print(f"Space freed: {self.operation_log['space_freed_gb']:.2f} GB")
        print(f"Errors: {len(self.operation_log['errors'])}")

        if self.operation_log['errors']:
            print("\nErrors encountered:")
            for err in self.operation_log['errors'][:10]:
                print(f"  - {err}")
            if len(self.operation_log['errors']) > 10:
                print(f"  ... and {len(self.operation_log['errors']) - 10} more")

        # Save operation log
        log_path = self.quarantine_dir / 'operation_log.json'
        with open(log_path, 'w') as f:
            json.dump(self.operation_log, f, indent=2)

        print(f"\n✓ Operation log: {log_path}")
        print("=" * 70)

    def close(self):
        """Clean up database connection"""
        self.conn.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Handle dupeGuru duplicates')
    parser.add_argument('--plan', required=True, help='Path to dupeguru_action_plan.json')
    parser.add_argument('--db', required=True, help='Path to music.db')
    parser.add_argument('--quarantine', required=True, help='Quarantine directory')
    parser.add_argument('--dry-run', action='store_true', help='Preview actions without executing')

    args = parser.parse_args()

    handler = DupeGuruHandler(args.plan, args.db, args.quarantine)
    handler.process_duplicates(dry_run=args.dry_run)
    handler.close()
