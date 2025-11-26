set -euo pipefail
mkdir -p artifacts/reports
DB=artifacts/db/dotad_final_scan.sqlite
OLD=artifacts/db/dotad_scan.sqlite
OUT=artifacts/reports/dotad_canonical_list.txt
SUMMARY=artifacts/reports/dotad_scan_summary.txt

if [ ! -f "$DB" ]; then
  echo "Final DB missing: $DB"
  exit 1
fi

# Export using library_files (confirmed schema)
sqlite3 "$DB" "SELECT path FROM library_files ORDER BY path;" > "$OUT"
CNT=$(wc -l < "$OUT" || echo 0)

{
  echo "Indexed files: $CNT"
  echo "Generated: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
} > "$SUMMARY"

if [ -f "$OLD" ]; then
  OLDTABLE=$(sqlite3 "$OLD" "SELECT name FROM sqlite_master WHERE type='table' AND (name='files' OR name='library_files') LIMIT 1;" || true)
  if [ -n "$OLDTABLE" ]; then
    OLDLIST=$(mktemp)
    if [ "$OLDTABLE" = "files" ]; then
      sqlite3 "$OLD" "SELECT path FROM files ORDER BY path;" > "$OLDLIST"
    else
      sqlite3 "$OLD" "SELECT path FROM library_files ORDER BY path;" > "$OLDLIST"
    fi
    LC_ALL=C comm -23 "$OUT" "$OLDLIST" > artifacts/reports/dotad_scan_added.txt || true
    LC_ALL=C comm -13 "$OUT" "$OLDLIST" > artifacts/reports/dotad_scan_removed.txt || true
    echo "Added count: $(wc -l < artifacts/reports/dotad_scan_added.txt || echo 0)" >> "$SUMMARY"
    echo "Removed count: $(wc -l < artifacts/reports/dotad_scan_removed.txt || echo 0)" >> "$SUMMARY"
    rm -f "$OLDLIST"
  else
    echo "Previous DB $OLD has no recognized files table; skipping diffs." >> "$SUMMARY"
  fi
else
  echo "Previous DB not found: $OLD" >> "$SUMMARY"
fi

wc -l "$OUT" || true
ls -lh "$DB" || true
echo
echo "Summary:"
cat "$SUMMARY"