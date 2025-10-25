#!/usr/bin/env bash
# delude_dir.sh
# Safe deletion / quarantine helper for a directory.
# Author: generated for Georges (complete script, not fragments)
# Usage:
#   ./delude_dir.sh --path "/Volumes/dotad/MUSIC/tres"            # dry-run (safe)
#   ./delude_dir.sh --path "/Volumes/dotad/MUSIC/tres" --quarantine
#   ./delude_dir.sh --path "/Volumes/dotad/MUSIC/tres" --backup
#   ./delude_dir.sh --path "/Volumes/dotad/MUSIC/tres" --confirm-delete --backup
#
# Behavior:
#   - If no destructive flag given, the script performs a dry-run and prints counts/sizes.
#   - --quarantine moves contents into a timestamped folder on the same volume.
#   - --backup creates a tar.gz archive before destructive action.
#   - --confirm-delete is required to perform permanent deletion (rm -rf).
#   - Always logs operations to ./delude_dir.log

set -euo pipefail

# -------- Configurable defaults --------
TARGET=""
QUIARANTINE_BASE=""
DO_QUARANTINE=false
DO_BACKUP=false
DO_DELETE=false
DRY_RUN=true
LOGFILE="./delude_dir.log"
# ---------------------------------------

function usage() {
  cat <<EOF
delude_dir.sh - safe deletion/quarantine tool

Options:
  --path PATH              Path to the target directory (required).
  --quarantine             Move contents to a timestamped quarantine dir on same volume.
  --backup                 Create a tar.gz backup of the directory before destructive actions.
  --confirm-delete         Actually delete files (permanent). Must be supplied to run rm -rf.
  --log FILE               Write operation log to FILE (default: ./delude_dir.log).
  --help                   Show this help and exit.

By default the script does a dry-run (reports counts and sizes). Use --confirm-delete
and optionally --quarantine or --backup to actually take action.
EOF
  exit 1
}

# -------- parse args --------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --path) TARGET="$2"; shift 2;;
    --quarantine) DO_QUARANTINE=true; DRY_RUN=false; shift;;
    --backup) DO_BACKUP=true; DRY_RUN=false; shift;;
    --confirm-delete) DO_DELETE=true; DRY_RUN=false; shift;;
    --log) LOGFILE="$2"; shift 2;;
    --help) usage ;;
    *) echo "Unknown arg: $1"; usage ;;
  esac
done

if [[ -z "$TARGET" ]]; then
  echo "Error: --path is required." >&2
  usage
fi

# Normalize path
TARGET="$(cd "$(dirname "$TARGET")" 2>/dev/null && pwd)/$(basename "$TARGET")" || TARGET="$TARGET"

timestamp() { date +"%Y%m%d-%H%M%S"; }

echo "=== delude_dir.sh started at $(date) ===" | tee -a "$LOGFILE"
echo "Target: $TARGET" | tee -a "$LOGFILE"
echo "Dry-run mode: $DRY_RUN" | tee -a "$LOGFILE"

# Check existence and mount
if [[ ! -e "$TARGET" ]]; then
  echo "ERROR: Target does not exist: $TARGET" | tee -a "$LOGFILE"
  exit 2
fi

# Ensure it's a directory
if [[ ! -d "$TARGET" ]]; then
  echo "ERROR: Target is not a directory: $TARGET" | tee -a "$LOGFILE"
  exit 3
fi

# Ensure the volume is mounted (macOS/Linux portable check)
vol_dev="$(df -P "$TARGET" | awk 'NR==2{print $1, $6}')"
if [[ -z "$vol_dev" ]]; then
  echo "WARNING: Could not determine mount for $TARGET" | tee -a "$LOGFILE"
else
  echo "Mount info: $vol_dev" | tee -a "$LOGFILE"
fi

# Summarize contents (dry-run)
echo "--- Summary (will run even in destructive mode before changes) ---" | tee -a "$LOGFILE"
total_files=$(find "$TARGET" -mindepth 1 -type f 2>/dev/null | wc -l || echo 0)
total_dirs=$(find "$TARGET" -mindepth 1 -type d 2>/dev/null | wc -l || echo 0)
total_size_bytes=$(du -sb "$TARGET" 2>/dev/null | awk '{print $1}' || echo 0)
human_size=$(numfmt --to=iec --format="%.1f" "$total_size_bytes" 2>/dev/null || printf "%.1f" "$(echo "$total_size_bytes/1" | bc -l)")

echo "Files:  $total_files" | tee -a "$LOGFILE"
echo "Folders: $total_dirs" | tee -a "$LOGFILE"
echo "Size: $human_size bytes ($total_size_bytes bytes)" | tee -a "$LOGFILE"

# Show top 10 largest items under TARGET
echo "" | tee -a "$LOGFILE"
echo "Top 15 largest items under $TARGET:" | tee -a "$LOGFILE"
( find "$TARGET" -mindepth 1 -maxdepth 3 -exec du -sh {} + 2>/dev/null || true ) \
  | sort -hr | head -n 15 | tee -a "$LOGFILE"

echo "" | tee -a "$LOGFILE"

# If dry-run and no destructive flags, stop here.
if $DRY_RUN && ! $DO_QUARANTINE && ! $DO_BACKUP && ! $DO_DELETE; then
  echo "Dry-run only. No changes made. To act, pass --quarantine, --backup, or --confirm-delete." | tee -a "$LOGFILE"
  exit 0
fi

# Prepare quarantine path (same volume as target)
if $DO_QUARANTINE; then
  # Find root mountpoint of TARGET (POSIX-ish)
  MOUNT_POINT="$(df -P "$TARGET" | awk 'NR==2{print $6}')"
  if [[ -z "$MOUNT_POINT" ]]; then
    echo "ERROR: Could not determine mount point for quarantine location." | tee -a "$LOGFILE"
    exit 4
  fi
  QUIARANTINE_BASE="$MOUNT_POINT/_quarantine_delude"
  QUAR_DIR="$QUIARANTINE_BASE/$(basename "$TARGET")-$(timestamp)"
  echo "Quarantine base: $QUIARANTINE_BASE" | tee -a "$LOGFILE"
  echo "Will move contents to: $QUAR_DIR" | tee -a "$LOGFILE"
fi

# Create backup if requested
if $DO_BACKUP; then
  BACKUP_DIR="./delude_backups"
  mkdir -p "$BACKUP_DIR"
  BACKUP_FILE="$BACKUP_DIR/$(basename "$TARGET")-backup-$(timestamp).tar.gz"
  echo "Creating backup archive (this may take a while): $BACKUP_FILE" | tee -a "$LOGFILE"
  # Use tar with --warning=no-file-changed to be a bit calmer
  tar -C "$(dirname "$TARGET")" -czf "$BACKUP_FILE" "$(basename "$TARGET")" \
    2>&1 | tee -a "$LOGFILE"
  echo "Backup complete: $BACKUP_FILE" | tee -a "$LOGFILE"
fi

# If quarantine requested: move contents (not the directory itself) into quarantine
if $DO_QUARANTINE; then
  echo "Preparing quarantine directories..." | tee -a "$LOGFILE"
  mkdir -p "$QUAR_DIR"
  # Move content safely: use rsync --remove-source-files might be slower; mv is atomic on same FS
  echo "Moving contents of $TARGET -> $QUAR_DIR" | tee -a "$LOGFILE"
  # double-check same filesystem: compare df device fields
  dev_target=$(df -P "$TARGET" | awk 'NR==2{print $1}')
  dev_quar=$(df -P "$QUAR_DIR" | awk 'NR==2{print $1}' 2>/dev/null || echo "$dev_target")
  if [[ "$dev_target" != "$dev_quar" ]]; then
    echo "WARNING: quarantine and target are on different devices; moving will copy then delete. Proceeding anyway." | tee -a "$LOGFILE"
  fi

  # Move (preserve attributes)
  # We intentionally move *contents* not the folder itself
  shopt -s dotglob
  mv_cmd=(mv -v -- "$TARGET"/* "$QUAR_DIR"/)
  echo "Running: ${mv_cmd[*]}" | tee -a "$LOGFILE"
  if $DRY_RUN; then
    echo "DRY RUN: would run mv to quarantine. Re-run without dry-run to actually move." | tee -a "$LOGFILE"
  else
    "${mv_cmd[@]}" 2>&1 | tee -a "$LOGFILE" || {
      echo "mv returned non-zero. Trying rsync fallback..." | tee -a "$LOGFILE"
      rsync -a --remove-source-files --info=progress2 "$TARGET"/ "$QUAR_DIR"/ 2>&1 | tee -a "$LOGFILE"
      # cleanup empty dirs under TARGET
      find "$TARGET" -type d -empty -delete 2>/dev/null || true
    }
    echo "Move complete. Quarantine location: $QUAR_DIR" | tee -a "$LOGFILE"
  fi
  shopt -u dotglob
fi

# If permanent delete requested
if $DO_DELETE; then
  if $DRY_RUN; then
    echo "DRY RUN: would permanently delete contents under $TARGET (rm -rf) -- no action taken." | tee -a "$LOGFILE"
  else
    echo "!!! PERMANENT DELETION ENABLED !!!" | tee -a "$LOGFILE"
    # Double-safety: require specific env var or confirm prompt if running interactively
    if [[ -t 0 ]]; then
      read -p "Type EXACTLY the word DELETE to permanently remove all contents under $TARGET: " CONF
      if [[ "$CONF" != "DELETE" ]]; then
        echo "Confirmation failed. Aborting deletion." | tee -a "$LOGFILE"
        exit 5
      fi
    else
      # non-interactive: check env var MUST_CONFIRM_DELETE=1
      if [[ "${MUST_CONFIRM_DELETE:-0}" != "1" ]]; then
        echo "Non-interactive removal requires environment variable MUST_CONFIRM_DELETE=1. Aborting." | tee -a "$LOGFILE"
        exit 6
      fi
    fi

    echo "Running permanent removal: rm -rf -- \"$TARGET\"/*" | tee -a "$LOGFILE"
    # perform deletion
    rm -rf -- "$TARGET"/* 2>&1 | tee -a "$LOGFILE" || true
    find "$TARGET" -type d -empty -delete 2>/dev/null || true
    echo "Deletion complete." | tee -a "$LOGFILE"
  fi
fi

echo "=== Completed at $(date) ===" | tee -a "$LOGFILE"
exit 0
