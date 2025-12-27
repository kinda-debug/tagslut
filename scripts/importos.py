import os
import sqlite3
import shutil

DB_PATH = "artifacts/db/library.db"
DEST_ROOT = "/Volumes/dotad/NEW_MUSIC"

def main():
    os.makedirs(DEST_ROOT, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Optional: if you have a global_moves.csv listing paths to DROP,
    # load it into a set here. For now, we keep everything present on disk.
    drop_paths = set()

    cur.execute("SELECT path FROM library_files")
    rows = cur.fetchall()
    conn.close()

    total = len(rows)
    print(f"Total DB rows: {total}")

    copied = 0
    skipped_missing = 0
    skipped_exists = 0

    for (p,) in rows:
        if p in drop_paths:
            continue

        if not os.path.isfile(p):
            skipped_missing += 1
            continue

        # Strip /Volumes/<volume>/ and preserve rest as relative path
        parts = p.split("/")
        if len(parts) > 3 and parts[0] == "" and parts[1] == "Volumes":
            rel = "/".join(parts[3:])
        else:
            rel = p.lstrip("/")

        dst = os.path.join(DEST_ROOT, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)

        if os.path.isfile(dst):
            skipped_exists += 1
            continue

        shutil.copy2(p, dst)
        copied += 1
        if copied % 100 == 0:
            print(f"Copied {copied} files...")

    print("Done.")
    print(f"Copied: {copied}")
    print(f"Skipped missing: {skipped_missing}")
    print(f"Skipped already in NEW_MUSIC: {skipped_exists}")

if __name__ == "__main__":
    main()
