#!/usr/bin/env bash
# Archive common top-level artefacts into an archive directory.
# Review and run from the repository root.

set -euo pipefail

TS=$(date +%Y%m%d_%H%M%S)
DEST="archive/root_archive_${TS}"
mkdir -p "$DEST"
MANIFEST="$DEST/manifest.txt"

echo "Archiving matched files to: $DEST"

# Patterns to consider moving from repo root (maxdepth 1 only)
FILES=(
  consolidate_audio_artifacts.py
  consolidate_audio_artifacts.py.backup.*
  consolidate_audio_artifacts.py.bak
  consolidated.csv
  corrupt_now.csv
  corrupt.csv
  dd_missing_flac.txt
  dedupe_apply_*.csv
  dedupe_crossformat_*.csv
  dedupe_quarantine_*.csv
  dedupe_report_*.csv
  dedupe_swap*.py
  delude_dir.sh
  "duplicates selected by gemini.txt"
  health_scan.sh
  health_summary.md
  live_health.csv
  out.txt.txt
  preseed_flac_cache.py
  quarantine_*.sh
  quarantine_hash_verification.csv
  quarantine_verification_report.csv
  similar_candidates.csv
  SUMMARY.txt
  sync_*.sh
  temp_audio_dedupe*.py
  useful_scan.py
  verify_*.sh
  verify_near_dupes.py
  verify_quarantine.sh
)

shopt -s nullglob
for pat in "${FILES[@]}"; do
  for f in $pat; do
    if [ -e "$f" ]; then
      mv -v -- "$f" "$DEST/"
      echo "$f" >> "$MANIFEST"
    fi
  done
done
shopt -u nullglob

# Move directories matching patterns
for d in near_dupe_verify_out useful_scan_out_*; do
  if [ -d "$d" ]; then
    mv -v -- "$d" "$DEST/"
    echo "$d/" >> "$MANIFEST"
  fi
done

echo "Archive manifest written to: $MANIFEST"
echo "Summary:"
wc -l "$MANIFEST" || true

echo "Done. Review $DEST/manifest.txt to see what was moved."
