#!/usr/bin/env bash
set -euo pipefail

# backup_dbs.sh
# Copy DB files from the active backup location into a timestamped archive
# Usage: scripts/backup_dbs.sh [--src <src_dir>] [--dest <dest_dir>] [--keep N]

SRC_DEFAULT="$HOME/dedupe_repo_reclone_db_backup"
DEST_DEFAULT="$HOME/dedupe_db_backups"
KEEP_DEFAULT=7

SRC="$SRC_DEFAULT"
DEST="$DEST_DEFAULT"
KEEP="$KEEP_DEFAULT"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --src) SRC="$2"; shift 2;;
    --dest) DEST="$2"; shift 2;;
    --keep) KEEP="$2"; shift 2;;
    -h|--help) echo "Usage: $0 [--src <src_dir>] [--dest <dest_dir>] [--keep N]"; exit 0;;
    *) echo "Unknown arg: $1"; exit 1;;
  esac
done

if [[ ! -d "$SRC" ]]; then
  echo "Source directory does not exist: $SRC" >&2
  exit 1
fi

mkdir -p "$DEST"
TS=$(date +%Y%m%d_%H%M%S)
OUTDIR="$DEST/$TS"

echo "Creating backup: $OUTDIR"
cp -a "$SRC/" "$OUTDIR/"
chmod -R 700 "$OUTDIR"

echo "Backup created. Rotating older backups, keeping $KEEP entries."
# Remove old backups, keep $KEEP newest
cd "$DEST"
ls -1dt */ | sed -n "$((KEEP+1)),999p" | xargs -r rm -rf

echo "Done. Backups available at: $DEST"