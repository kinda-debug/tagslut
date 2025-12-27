#!/usr/bin/env python3
import sqlite3
import csv
import json
import argparse
import os


def export_manifest(db_path, out_path):
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found: {db_path}")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    query = """
        SELECT
            path,
            size_bytes,
            mtime,
            checksum,
            duration,
            sample_rate,
            bit_rate,
            channels,
            bit_depth,
            tags_json,
            fingerprint,
            fingerprint_duration
        FROM library_files
        ORDER BY path COLLATE NOCASE;
    """

    rows = cur.execute(query).fetchall()

    fieldnames = [
        "path",
        "size_bytes",
        "mtime",
        "checksum",
        "duration",
        "sample_rate",
        "bit_rate",
        "channels",
        "bit_depth",
        "tags",
        "fingerprint",
        "fingerprint_duration"
    ]

    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for (
            path,
            size_bytes,
            mtime,
            checksum,
            duration,
            sample_rate,
            bit_rate,
            channels,
            bit_depth,
            tags_json,
            fingerprint,
            fingerprint_duration
        ) in rows:

            # Parse JSON metadata if present
            try:
                tags = json.loads(tags_json) if tags_json else {}
            except Exception:
                tags = {}

            writer.writerow({
                "path": path,
                "size_bytes": size_bytes,
                "mtime": mtime,
                "checksum": checksum,
                "duration": duration,
                "sample_rate": sample_rate,
                "bit_rate": bit_rate,
                "channels": channels,
                "bit_depth": bit_depth,
                "tags": json.dumps(tags, ensure_ascii=False),
                "fingerprint": fingerprint,
                "fingerprint_duration": fingerprint_duration
            })

    conn.close()

    print(f"Manifest exported: {out_path}")
    print(f"Total rows: {len(rows)}")


def main():
    parser = argparse.ArgumentParser(description="Export library_files manifest to CSV")
    parser.add_argument("--db", required=True, help="Path to SQLite database")
    parser.add_argument("--out", required=True, help="Output CSV file")
    args = parser.parse_args()

    export_manifest(args.db, args.out)


if __name__ == "__main__":
    main()
