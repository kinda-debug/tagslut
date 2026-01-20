
import os
import shutil
import csv
import argparse
import hashlib
import sqlite3
import sys
from pathlib import Path

# Ensure we can import dedupe from root
sys.path.insert(0, str(Path(__file__).parent))
from dedupe.utils import env_paths

def get_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def get_db_info(conn, path):
    """Fetch SHA256 and integrity_state for a path from the database."""
    cursor = conn.execute(
        "SELECT sha256, integrity_state FROM files WHERE path = ?",
        (str(path),)
    )
    row = cursor.fetchone()
    if row:
        return {"sha256": row[0], "integrity_state": row[1]}
    return None

def main():
    parser = argparse.ArgumentParser(description="Restore missing library files from a source volume with DB verification.")
    parser.add_argument("--manifest", default="RECOVERY_MANIFEST.csv", help="Path to manifest file")
    parser.add_argument("--source-root", required=True, help="Root directory containing source files")
    parser.add_argument("--execute", action="store_true", help="Actually perform the copy")
    parser.add_argument("--verify", action="store_true", help="Verify SHA256 before copying (slow)")
    parser.add_argument("--db", help="Path to database (defaults to $DEDUPE_DB)")

    args = parser.parse_args()

    db_path = args.db or env_paths.get_db_path()
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)

    if not os.path.exists(args.manifest):
        print(f"Manifest not found: {args.manifest}")
        return

    print(f"Reading manifest {args.manifest}...")
    with open(args.manifest, "r") as f:
        reader = csv.DictReader(f)
        items = list(reader)

    print(f"Processing {len(items)} files...")

    success = 0
    missing_source = 0
    hash_mismatch = 0
    db_corrupt = 0
    errors = 0
    skipped_existing = 0

    for item in items:
        target = item['TARGET_PATH']
        sha_manifest = item['SHA256']
        rel_path = item['RELATIVE_SOURCE_PATH']

        # Check if target already exists
        if os.path.exists(target):
            skipped_existing += 1
            continue

        # DB CHECK: Ensure we aren't restoring something known to be corrupt
        db_info = get_db_info(conn, target)
        if db_info and db_info.get("integrity_state") == "corrupt":
            print(f"SKIPPING: {target} is marked CORRUPT in database.")
            db_corrupt += 1
            continue

        # Try to find source
        # 1. Exact relative path
        source_candidate = os.path.join(args.source_root, rel_path)

        # 2. If not found, try basename search in source-root (if it's a flattened folder)
        if not os.path.exists(source_candidate):
            basename = os.path.basename(target)
            source_candidate = os.path.join(args.source_root, basename)

        if not os.path.exists(source_candidate):
            missing_source += 1
            continue

        # Use DB hash if manifest is missing it or to be extra sure
        sha_to_verify = sha_manifest or (db_info.get("sha256") if db_info else None)

        if args.verify and sha_to_verify:
            print(f"Verifying hash for {source_candidate}...")
            actual_sha = get_sha256(source_candidate)
            if actual_sha != sha_to_verify:
                print(f"HASH MISMATCH for {source_candidate}")
                print(f"  Expected (DB/Manifest): {sha_to_verify}")
                print(f"  Actual (File):         {actual_sha}")
                hash_mismatch += 1
                continue

        if args.execute:
            try:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copy2(source_candidate, target)
                print(f"RESTORED: {target}")
                success += 1
            except Exception as e:
                print(f"ERROR copying {source_candidate} to {target}: {e}")
                errors += 1
        else:
            print(f"DRY-RUN: Would copy {source_candidate} to {target}")
            success += 1

    conn.close()

    print("\nSummary:")
    print(f"  Successfully processed: {success}")
    print(f"  Missing at source:      {missing_source}")
    print(f"  Skipped (DB Corrupt):   {db_corrupt}")
    print(f"  Hash mismatches:        {hash_mismatch}")
    print(f"  Skipped (Already exists): {skipped_existing}")
    print(f"  Errors:                 {errors}")

    if not args.execute:
        print("\n*** This was a DRY-RUN. Use --execute to perform the restoration. ***")

if __name__ == "__main__":
    main()
