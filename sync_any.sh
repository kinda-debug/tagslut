#!/bin/bash
# sync_any.sh
# Sync ANY two directories with rsync on macOS, with:
# - FS detection per path (APFS/HFS get rich metadata; exFAT/NTFS skip it)
# - Resumable large files (--partial + --append-verify)
# - Mirror mode by default (--delete), can dry-run (-n) or verify-only (--verify)
# - Clean console: one bold green static overall progress line; action logs above it
# - Logs saved under ~/.sync_logs (raw + summary)
#
# Usage:
#   ./sync_any.sh [options] <SRC> <DST>
#
# Examples:
#   ./sync_any.sh -y "/Volumes/sad/MUSIC" "/Volumes/rad/MUSIC"
#   ./sync_any.sh --verify "/Users/me/Pictures" "/Volumes/Backup/Pictures"
#
# Options:
#   -y, --yes         run without confirmation
#   -n                dry-run (no changes; shows what would happen)
#   --no-delete       do NOT delete extras on destination (not a mirror)
#   --verify          checksum-verify only (no copying/deleting)
#   --no-excludes     don’t exclude .DS_Store and AppleDouble (._*) files
#   --quiet           minimize on-screen action lines (still logs)
#
# Notes:
# - Works across exFAT ↔ APFS (incl. case-sensitive / encrypted APFS).
# - Case-insensitive destinations (exFAT/APFS default) can’t represent two
#   distinct names that differ only by case. Script warns; rsync will pick one.

set -euo pipefail

# ---------- CLI parsing ----------
YES=0
DRYRUN=0
VERIFY_ONLY=0
DELETE=1
EXCLUDES=1
QUIET=0

ARGS=()
while (( $# )); do
  case "$1" in
    -y|--yes) YES=1;;
    -n) DRYRUN=1;;
    --verify) VERIFY_ONLY=1;;
    --no-delete) DELETE=0;;
    --no-excludes) EXCLUDES=0;;
    --quiet) QUIET=1;;
    -h|--help)
      sed -n '1,60p' "$0"; exit 0;;
    --) shift; break;;
    -*)
      echo "Unknown option: $1" >&2; exit 2;;
    *) ARGS+=("$1");;
  esac
  shift
done
# Remaining args if any
if (( ${#ARGS[@]} < 2 )); then
  echo "Usage: $0 [options] <SRC> <DST>" >&2
  exit 2
fi

# Normalize paths; accept dir paths with/without trailing slash
SRC="${ARGS[0]}"
DST="${ARGS[1]}"
# Ensure they refer to directories
[[ -d "$SRC" ]] || { echo "✖ Source not found or not a directory: $SRC" >&2; exit 1; }
[[ -d "$DST" ]] || { echo "✖ Destination not found or not a directory: $DST" >&2; exit 1; }

# Trailing slashes: rsync semantics copy contents of SRC when SRC ends with /
case "$SRC" in */) :;; *) SRC="${SRC}/";; esac
case "$DST" in */) :;; *) DST="${DST}/";; esac

# ---------- Logging ----------
STAMP="$(date +"%Y%m%d-%H%M%S")"
LOG_DIR="${HOME}/.sync_logs"
LOG_RAW="${LOG_DIR}/rsync-${STAMP}.log"
LOG_SUM="${LOG_DIR}/summary-${STAMP}.log"
mkdir -p "$LOG_DIR"

# ---------- UI helpers ----------
log(){ printf "▶ %s\n" "$*"; }
die(){ echo "✖ $*" >&2; exit 1; }

if [[ -t 1 ]]; then
  BOLD=$(tput bold || true); RESET=$(tput sgr0 || true)
  GREEN=$(tput setaf 2 || true); BLUE=$(tput setaf 4 || true)
  YELLOW=$(tput setaf 3 || true); RED=$(tput setaf 1 || true)
  CLEAR=$(tput el 2>/dev/null || printf '\033[K')
else
  BOLD=""; RESET=""; GREEN=""; BLUE=""; YELLOW=""; RED=""; CLEAR=""
fi

# ---------- Filesystem detection ----------
# Given an absolute path, find its mountpoint and filesystem type
mountpoint_for() {
  # df -P prints last column as mountpoint
  df -P "$1" 2>/dev/null | tail -1 | awk '{print $NF}'
}
fs_type_from_mount() {
  local mp="$1" line fs
  line="$(mount | grep -F " on $mp " || true)"
  if [[ -n "$line" ]]; then
    fs="$(printf '%s\n' "$line" | sed -n 's/.*(//; s/,.*//p')"
    [[ -n "$fs" ]] && { echo "$fs"; return; }
  fi
  # Fallback
  fs="$(stat -f %T "$mp" 2>/dev/null || true)"
  [[ -n "$fs" ]] && echo "$fs" || echo "unknown"
}
supports_meta(){ case "$1" in apfs|hfs) return 0;; *) return 1;; esac; }
is_case_insensitive(){
  # Quick heuristic: APFS default is case-insensitive unless explicitly CS; exfat is case-insensitive
  case "$1" in
    apfs)
      # Try “ls” trick: create a tmp dir with weird case, check if it collides (best effort, no write on src)
      # We can’t write on arbitrary mounts safely; assume APFS may be CI unless volume says "Case-sensitive".
      # We’ll detect from diskutil if available.
      diskutil info "$(mountpoint_for "$2")" 2>/dev/null | grep -qi "Case-sensitive: Yes" && return 1 || return 0
      ;;
    exfat|msdos|ntfs|fusefs) return 0;;
    *) return 0;; # conservative: assume CI
  esac
}

SRC_MP="$(mountpoint_for "$SRC")"
DST_MP="$(mountpoint_for "$DST")"
[[ -n "$SRC_MP" ]] || die "Could not determine source mountpoint for $SRC"
[[ -n "$DST_MP" ]] || die "Could not determine destination mountpoint for $DST"

SRC_FS="$(fs_type_from_mount "$SRC_MP")"
DST_FS="$(fs_type_from_mount "$DST_MP")"
[[ -n "$SRC_FS" ]] || SRC_FS="unknown"
[[ -n "$DST_FS" ]] || DST_FS="unknown"

# Warn on case-insensitive destination when source may have case-colliding names
DEST_CI=0
if is_case_insensitive "$DST_FS" "$DST_MP"; then DEST_CI=1; fi

# ---------- Build rsync flags ----------
RSYNC_FLAGS=(
  -a -h
  -i                                   # itemize changes (for parsing decisions)
  --info=flist2,progress2,stats
  --partial --append-verify
  --fsync
  --no-inc-recursive
  --inplace
  --protect-args
  --prune-empty-dirs
  --out-format="RSYNCX|%i|%n|%l|%b"
)

if (( EXCLUDES )); then
  RSYNC_FLAGS+=( --exclude=".DS_Store" --exclude="._*" )
fi

if (( DELETE )); then
  RSYNC_FLAGS+=( --delete --delete-delay )
fi

META_NOTE="skipping macOS metadata (one side lacks support)"
if supports_meta "$SRC_FS" && supports_meta "$DST_FS"; then
  RSYNC_FLAGS+=( --xattrs --acls --fileflags --crtimes )
  META_NOTE="preserving xattrs, ACLs, fileflags, creation times"
fi

if (( DRYRUN )); then
  RSYNC_FLAGS+=( -n )
fi

# VERIFY mode: checksum both sides, make NO changes (ignore all transfer/deletes)
if (( VERIFY_ONLY )); then
  RSYNC_FLAGS=( -a -h -n --checksum --info=stats )
  (( EXCLUDES )) && RSYNC_FLAGS+=( --exclude=".DS_Store" --exclude="._*" )
fi

# ---------- Preflight ----------
log "Source:      $SRC   (fs: $SRC_FS; mp: $SRC_MP)"
log "Destination: $DST   (fs: $DST_FS; mp: $DST_MP)"
if (( VERIFY_ONLY )); then
  log "Mode:        VERIFY (checksum-only; no changes)"
else
  if (( DELETE )); then
    log "Mode:        MIRROR (extra files on destination will be removed)"
  else
    log "Mode:        COPY-UPDATE (no deletes; extras on destination kept)"
  fi
  log "Resume:      --partial + --append-verify"
  log "Metadata:    $META_NOTE"
fi
(( EXCLUDES )) && log "Excludes:    .DS_Store, ._*"
log "Log files:   $LOG_RAW (raw), $LOG_SUM (summary)"
log "rsync args:  ${RSYNC_FLAGS[*]}"

if (( DEST_CI )); then
  log "Note:        Destination appears CASE-INSENSITIVE. If source contains two names differing only by case,"
  log "             they will COLLIDE on destination. rsync will copy one; the other will be overwritten/merged."
fi

# Writable test only when not verify-only
if (( ! VERIFY_ONLY )); then
  TEST="$DST/.rsync_write_test_$$"
  : > "$TEST" 2>/dev/null || die "Cannot write to destination: $DST"
  rm -f "$TEST"
fi

if (( ! YES )); then
  read -r -p "Proceed? [y/N] " ans
  [[ "$ans" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }
fi

# ---------- Counters & progress ----------
copied=0
resumed=0
skipped=0
deleted=0
last_progress=""

paint_progress() {
  [[ -n "$last_progress" ]] || return 0
  printf "\r${BOLD}${GREEN}%s${RESET}%s" "$last_progress" "$CLEAR"
}

START=$(date +%s)

# VERIFY mode is simple: run and print the rsync stats; no parsing of progress/action lines.
if (( VERIFY_ONLY )); then
  rsync "${RSYNC_FLAGS[@]}" "$SRC" "$DST" | tee -a "$LOG_RAW"
  printf "\n"
  ELAPSED=$(( $(date +%s) - START ))
  HUMAN_TIME=$(date -u -r "$ELAPSED" +%H:%M:%S 2>/dev/null || printf "%ss" "$ELAPSED")
  echo "${BOLD}${BLUE}▶ Verify finished in ${HUMAN_TIME}${RESET}"
  echo "Raw log: $LOG_RAW"
  exit 0
fi

# ---------- Run rsync; parse; keep console clean ----------
while IFS= read -r line; do
  printf "%s\n" "$line" >> "$LOG_RAW"

  # Overall progress (from --progress2), we repaint a single line
  if [[ "$line" =~ ^[[:space:]]+[0-9] ]]; then
    last_progress="$line"
    paint_progress
    continue
  fi

  # Deletions
  if [[ "$line" == deleting\ * ]]; then
    ((deleted++))
    name="${line#deleting }"
    (( QUIET )) || { printf "\n${RED}deleted:${RESET} %s\n" "$name"; }
    printf " | deleted | %s\n" "$name" >> "$LOG_SUM"
    paint_progress
    continue
  fi

  # Structured action line
  if [[ "$line" == RSYNCX\|* ]]; then
    IFS='|' read -r _ item name len bytes <<< "$line"
    if [[ "$item" == \>* ]]; then
      # Data written to destination
      if [[ "$bytes" =~ ^[0-9]+$ && "$len" =~ ^[0-9]+$ && "$bytes" -lt "$len" ]]; then
        ((resumed++))
        (( QUIET )) || { printf "\n${YELLOW}resumed:${RESET} %s\n" "$name"; }
        printf " | resumed | %s | bytes=%s of %s\n" "$name" "$bytes" "$len" >> "$LOG_SUM"
      else
        ((copied++))
        (( QUIET )) || { printf "\n${BLUE}copied :${RESET} %s\n" "$name"; }
        printf " | copied  | %s | bytes=%s of %s\n" "$name" "$bytes" "$len" >> "$LOG_SUM"
      fi
    elif [[ "$item" == .* ]]; then
      ((skipped++))
      printf " | skipped | %s\n" "$name" >> "$LOG_SUM"
    else
      # metadata/dir changes
      printf " | other   | %s | item=%s\n" "$name" "$item" >> "$LOG_SUM"
    fi
    paint_progress
    continue
  fi

  # Other rsync chatter (headings, stats)
  if [[ -n "$line" ]]; then
    (( QUIET )) || { printf "\n%s\n" "$line"; }
    paint_progress
  fi
done < <( rsync "${RSYNC_FLAGS[@]}" "$SRC" "$DST" 2>&1 | tr '\r' '\n' )

printf "\n"
ELAPSED=$(( $(date +%s) - START ))
HUMAN_TIME=$(date -u -r "$ELAPSED" +%H:%M:%S 2>/dev/null || printf "%ss" "$ELAPSED")

echo "${BOLD}${BLUE}▶ Sync finished in ${HUMAN_TIME}${RESET}"
{
  printf "%s\n" "---- SUMMARY ${STAMP} ----"
  printf "copied : %d\n"  "$copied"
  printf "resumed: %d\n"  "$resumed"
  printf "skipped: %d\n"  "$skipped"
  printf "deleted: %d\n"  "$deleted"
  echo "Raw log: $LOG_RAW"
  echo "Summary: $LOG_SUM"
} | tee -a "$LOG_SUM"
