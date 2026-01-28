import sqlite3
import argparse
import json
from pathlib import Path

def inspect_db(db_path, output_path=None):
    path = Path(db_path)
    if not path.exists():
        print(f"❌ Error: Database not found at {path}")
        return

    print(f"🔍 Inspecting: {path}")
    
    # Connect in read-only mode to prevent locking
    uri = f"file:{path.as_posix()}?mode=ro"
    
    try:
        with sqlite3.connect(uri, uri=True) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            
            report = {
                "database": str(path),
                "table": None,
                "checksum_column": None,
                "duplicate_groups": [],
                "analysis": {}
            }

            # 1. Detect Table Name (Schema Ambiguity Fix)
            target_table = None
            for candidate in ["files", "library_files"]:
                try:
                    cur.execute(f"SELECT COUNT(*) FROM {candidate}")
                    count = cur.fetchone()[0]
                    print(f"📊 Found table '{candidate}' with {count} rows.")
                    target_table = candidate
                    report["table"] = candidate
                    break
                except sqlite3.OperationalError:
                    continue
            
            if not target_table:
                print("❌ Error: Database has no 'files' or 'library_files' table.")
                return

            # 2. Detect Hash Columns
            col_query = f"PRAGMA table_info({target_table})"
            all_columns = [row['name'] for row in cur.execute(col_query).fetchall()]
            
            # We want to check these specific columns if they exist
            hash_cols = [c for c in ["checksum", "sha256", "streaminfo_md5"] if c in all_columns]
            
            if not hash_cols:
                 print(f"❌ Error: No hash columns (checksum, sha256, streaminfo_md5) found in {target_table}")
                 return

            # 3. Analyze Each Column
            cur.execute(f"SELECT COUNT(*) FROM {target_table}")
            total_files = cur.fetchone()[0]
            print(f"📊 Total Files: {total_files}")
            
            for col in hash_cols:
                print(f"\n🔎 Analyzing column: '{col}'")
                
                # Count valid
                cur.execute(f"SELECT COUNT(*) FROM {target_table} WHERE {col} IS NOT NULL AND {col} != 'NOT_SCANNED' AND {col} != ''")
                scanned_files = cur.fetchone()[0]
                coverage = (scanned_files/total_files*100) if total_files else 0
                print(f"   - Coverage: {scanned_files} ({coverage:.1f}%)")
                
                # Find Duplicates
                query = f"""
                    SELECT {col} as hash, COUNT(*) as count, GROUP_CONCAT(path, ' | ') as paths
                    FROM {target_table}
                    WHERE {col} IS NOT NULL AND {col} != 'NOT_SCANNED' AND {col} != ''
                    GROUP BY {col}
                    HAVING count > 1
                    ORDER BY count DESC
                """
                cur.execute(query)
                results = cur.fetchall()
                
                report["analysis"][col] = {
                    "coverage": scanned_files,
                    "duplicate_groups": len(results)
                }

                if not results:
                    print(f"   - ✅ No duplicates found.")
                else:
                    print(f"   - ⚠️  Found {len(results)} duplicate groups.")
                    # Show top 3 groups
                    for i, row in enumerate(results[:3], 1):
                        print(f"     Group {i}: {row['hash']} (Count: {row['count']})")
                        paths = row['paths'].split(' | ')
                        for p in paths[:3]:
                            print(f"       - {p}")
                        if len(paths) > 3:
                            print(f"       - ... ({len(paths)-3} more)")
            
            if output_path:
                with open(output_path, "w") as f:
                    json.dump(report, f, indent=2)
                print(f"\n📄 Report saved to: {output_path}")
                    
    except sqlite3.Error as e:
        print(f"❌ Database Error: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True, help="Path to SQLite DB")
    parser.add_argument("--output", help="Path to save JSON report artifact")
    args = parser.parse_args()
    inspect_db(args.db, args.output)