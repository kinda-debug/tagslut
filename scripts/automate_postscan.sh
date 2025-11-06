#!/usr/bin/env bash
# Safe, interactive automation for the post-scan pipeline.
# Usage: ./scripts/automate_postscan.sh /path/to/music

set -euo pipefail

ROOT="${1:-}"
if [[ -z "$ROOT" ]]; then
  echo "Usage: $0 /path/to/music"
  exit 2
fi

export PYTHONPATH="$(pwd)"

# Default staging: sibling dir to the music root (keeps staging OUTSIDE the music tree
# so `flac_scan.py` won't re-process repaired outputs while scanning the library).
REPAIRED="$(dirname "$ROOT")/REPAIRED_STAGING_$(date +%s)"

echo "Repository root: $(pwd)"
echo "Library root: $ROOT"
echo "Repaired staging: $REPAIRED"

confirm() {
  read -r -p "$1 [y/N]: " resp
  case "$resp" in
    [yY][eE][sS]|[yY]) return 0 ;;
    *) return 1 ;;
  esac
}

echo
echo "1) Running scan on $ROOT (this may take some time)"
if confirm "Run scan now?"; then
  python scripts/flac_scan.py --root "$ROOT" --workers 4 --verbose --broken-playlist "$ROOT/broken_files_unrepaired.m3u"
else
  echo "Skipping scan.";
fi

echo
echo "2) Building broken-files playlist from DB"
sqlite3 -batch "$ROOT/_DEDUP_INDEX.db" "SELECT path FROM files WHERE healthy=0;" > broken_files_unrepaired.m3u
echo "Broken playlist written: broken_files_unrepaired.m3u ($(wc -l < broken_files_unrepaired.m3u) entries)"

echo
echo "3) Repairing listed files into staging ($REPAIRED)"
if confirm "Run repairs now? (recommended: yes)"; then
  python scripts/flac_repair.py --playlist broken_files_unrepaired.m3u --output "$REPAIRED" --capture-stderr --ffmpeg-timeout 30
  echo "Repairs complete. Inspect $REPAIRED and $REPAIRED/logs before reintegration."
else
  echo "Skipping repairs.";
fi

echo
echo "4) Preview rsync dry-run from REPAIRED -> ROOT"
echo "Dry-run output (first 50 lines):"
rsync -avhn --progress "$REPAIRED"/ "$ROOT"/ | head -n 50 || true

if confirm "Perform rsync to copy repaired files into $ROOT?"; then
  rsync -avh --progress "$REPAIRED"/ "$ROOT"/
  echo "Files copied."
else
  echo "Skipped copying repaired files."
fi

echo
echo "5) Re-scan library to refresh DB"
if confirm "Re-run scan on $ROOT now?"; then
  python scripts/flac_scan.py --root "$ROOT" --workers 4 --recompute --verbose
else
  echo "Skipping rescan.";
fi

echo
echo "6) Run dedupe dry-run"
python scripts/flac_dedupe.py --root "$ROOT" --dry-run --verbose --trash-dir "$ROOT/_TRASH_DUPES_preview"
REPORT=$(ls -1 "$ROOT"/_DEDUP_REPORT_*.csv | tail -n1 || true)
if [[ -n "$REPORT" ]]; then
  echo "Dedupe report: $REPORT"
else
  echo "No report found."
fi

if confirm "Commit dedupe moves (move losers to $ROOT/_TRASH_DUPES)?"; then
  python scripts/flac_dedupe.py --root "$ROOT" --commit --trash-dir "$ROOT/_TRASH_DUPES" --verbose
  echo "Dedupe commit complete. Check $ROOT/_TRASH_DUPES and dedupe CSV for details."
else
  echo "Dedupe commit skipped."
fi

echo
echo "Automated pipeline finished. Review logs and reports before removing backups or trash."
