#!/usr/bin/env bash
set -euo pipefail

echo "=== DB INTEGRITY AUDIT ==="

DB_DIR="artifacts/db"
DBS=(library.db recovered.db secondary_candidates.db recovered_sample.db)

for db in "${DBS[@]}"; do
    path="$DB_DIR/$db"
    if [[ ! -f "$path" ]]; then
        echo "-- $db MISSING"
        continue
    fi

    echo "-- Checking $db"

    echo "   PRAGMA integrity_check:"
    sqlite3 "$path" "PRAGMA integrity_check;" | sed 's/^/      /'

    echo "   PRAGMA quick_check:"
    sqlite3 "$path" "PRAGMA quick_check;" | sed 's/^/      /'

    echo "   Checking page size and freelist consistency:"
    sqlite3 "$path" "PRAGMA page_size;" | sed 's/^/      Page size: /'
    sqlite3 "$path" "PRAGMA freelist_count;" | sed 's/^/      Freelist pages: /'

    echo
done

echo "=== INTEGRITY AUDIT COMPLETE ==="
