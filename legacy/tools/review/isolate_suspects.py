from __future__ import annotations
import sqlite3
import shutil
import os
import argparse
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Isolate corrupt or suspect files based on scan results.")
    parser.add_argument("--db", required=True, help="Path to the SQLite database")
    parser.add_argument("--dest", required=True, help="Destination directory for suspect files")
    parser.add_argument("--execute", action="store_true", help="Actually perform the file operation")
    parser.add_argument("--move", action="store_true", help="Move files instead of copying")
    args = parser.parse_args()

    db_path = Path(args.db)
    dest_root = Path(args.dest)
    operation = "move" if args.move else "copy"
    operation_past = "moved" if args.move else "copied"

    if not db_path.exists():
        print(f"Error: Database {db_path} not found.")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Find files marked as corrupt (flac_ok = 0)
    cursor.execute("SELECT path FROM files WHERE flac_ok = 0")
    rows = cursor.fetchall()

    if not rows:
        print("No corrupt files found in database.")
        return

    print(f"Found {len(rows)} corrupt/suspect files.")

    if not args.execute:
        print("\n*** DRY RUN MODE ***")
        for row in rows[:10]:
            print(f"Would {operation}: {row['path']}")
        if len(rows) > 10:
            print(f"... and {len(rows) - 10} more.")
        print(f"\nRun with --execute to {operation} files.")
        return

    dest_root.mkdir(parents=True, exist_ok=True)

    success = 0
    fail = 0
    for row in rows:
        src = Path(row['path'])
        if not src.exists():
            print(f"Warning: File not found on disk: {src}")
            fail += 1
            continue

        # Reconstruct path under dest_root
        # Use volume name or relative path
        if src.parts[1] == 'Volumes':
            rel_path = Path(*src.parts[2:])
        else:
            rel_path = src.relative_to('/')

        dest = dest_root / rel_path

        try:
            dest.parent.mkdir(parents=True, exist_ok=True)

            if args.move:
                shutil.move(str(src), str(dest))
                # Verify target exists and source is gone
                if not dest.exists() or src.exists():
                    raise IOError("Target file validation failed after move")
            else:
                shutil.copy2(str(src), str(dest))
                # Verify target exists and has matching size
                if not (dest.exists() and dest.stat().st_size == src.stat().st_size):
                    raise IOError("Target file validation failed after copy")

            success += 1
            if success % 100 == 0:
                print(f"{operation_past.capitalize()} {success} files...")
        except Exception as e:
            print(f"Error {operation}ing {src}: {e}")
            fail += 1

    print(f"\nFinished: {success} {operation_past}, {fail} failed/skipped.")

if __name__ == "__main__":
    main()
