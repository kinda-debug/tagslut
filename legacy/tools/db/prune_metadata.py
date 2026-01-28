import sqlite3
import argparse
from pathlib import Path

def prune_metadata(db_path, auto_confirm=False):
    path = Path(db_path)
    if not path.exists():
        print(f"❌ Database not found: {path}")
        return

    print(f"🧹 Inspecting for metadata artifacts: {path}")
    uri = f"file:{path.as_posix()}"
    
    try:
        with sqlite3.connect(uri, uri=True) as conn:
            # 1. Detect Table
            try:
                conn.execute("SELECT 1 FROM files LIMIT 1")
                table = "files"
            except sqlite3.OperationalError:
                table = "library_files"
            
            # 2. Count metadata files (._*)
            # We look for paths ending in /._* or just starting with ._
            query = f"SELECT COUNT(*) FROM {table} WHERE path LIKE '%/._%' OR path LIKE '._%'"
            count = conn.execute(query).fetchone()[0]
            
            if count == 0:
                print("✅ No metadata files found. Database is clean.")
            else:
                print(f"⚠️  Found {count} macOS metadata files (AppleDouble '._' files).")
                print("   These cause false positives in duplicate detection.")
                
                if auto_confirm:
                    confirm = 'y'
                else:
                    confirm = input(f"   Delete {count} rows from table '{table}'? [y/N] ").strip().lower()
                
                if confirm == 'y':
                    conn.execute(f"DELETE FROM {table} WHERE path LIKE '%/._%' OR path LIKE '._%'")
                    conn.commit()
                    print(f"🗑  Deleted {count} rows.")
                else:
                    print("   Aborted.")

            # 3. Report remaining valid files
            total = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"📊 Total remaining files in DB: {total}")
            
    except sqlite3.Error as e:
        print(f"❌ Database Error: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--confirm", action="store_true", help="Automatically confirm deletion")
    args = parser.parse_args()
    prune_metadata(args.db, args.confirm)