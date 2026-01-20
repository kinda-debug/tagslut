
import os
import shutil
import csv
import argparse
import hashlib
from pathlib import Path

def get_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def main():
    parser = argparse.ArgumentParser(description="Restore missing library files using the readiness report.")
    parser.add_argument("--report", default="restoration_readiness_report.csv", help="Path to readiness report")
    parser.add_argument("--execute", action="store_true", help="Actually perform the copy")
    parser.add_argument("--verify", action="store_true", help="Verify SHA256 before copying (slow)")

    args = parser.parse_args()

    if not os.path.exists(args.report):
        print(f"Report not found: {args.report}")
        return

    print(f"Reading report {args.report}...")
    with open(args.report, "r") as f:
        reader = csv.DictReader(f)
        items = [row for row in reader if row['STATUS'] == "FOUND"]

    print(f"Ready to restore {len(items)} files...")

    success = 0
    missing_source = 0
    hash_mismatch = 0
    errors = 0
    skipped_existing = 0

    for item in items:
        target = item['TARGET_PATH']
        sha = item['SHA256']
        source = item['CURRENT_LOCATION']

        # Check if target already exists
        if os.path.exists(target):
            skipped_existing += 1
            continue

        if not os.path.exists(source):
            print(f"SOURCE GONE: {source}")
            missing_source += 1
            continue

        if args.verify:
            print(f"Verifying {source}...")
            actual_sha = get_sha256(source)
            if actual_sha != sha:
                print(f"HASH MISMATCH for {source}")
                hash_mismatch += 1
                continue

        if args.execute:
            try:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copy2(source, target)
                # print(f"RESTORED: {target}")
                success += 1
                if success % 500 == 0:
                    print(f"Restored {success} files...")
            except Exception as e:
                print(f"ERROR copying {source} to {target}: {e}")
                errors += 1
        else:
            # print(f"DRY-RUN: Would copy {source} to {target}")
            success += 1

    print("\nSummary:")
    print(f"  Successfully processed: {success}")
    print(f"  Missing at source:      {missing_source}")
    print(f"  Hash mismatches:        {hash_mismatch}")
    print(f"  Skipped (already exists): {skipped_existing}")
    print(f"  Errors:                 {errors}")

    if not args.execute:
        print("\n*** This was a DRY-RUN. Use --execute to perform the restoration. ***")

if __name__ == "__main__":
    main()
