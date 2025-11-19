#!/usr/bin/env bash
set -euo pipefail

echo "=== DATABASE HEALTH CHECK ==="

DB_DIR="artifacts/db"
DBS=(library.db recovered.db secondary_candidates.db recovered_sample.db)

for db in "${DBS[@]}"; do
    path="$DB_DIR/$db"
    if [[ -f "$path" ]]; then
        echo "-- $db FOUND at $path"
        echo "   Size: $(du -h "$path" | cut -f1)"
        echo "   Tables:"
        sqlite3 "$path" "SELECT name FROM sqlite_master WHERE type='table';" || true
        echo "   Row counts:"
        tables=$(sqlite3 "$path" "SELECT name FROM sqlite_master WHERE type='table';")
        for t in $tables; do
            cnt=$(sqlite3 "$path" "SELECT COUNT(*) FROM $t;")
            echo "     $t: $cnt"
        done
        echo
    else
        echo "-- $db MISSING"
    fi
done

echo "=== HEALTH CHECK COMPLETE ==="
