#!/usr/bin/env bash
#
# safe_move_by_db_checksum.sh
#
# Safely MOVE FLAC files based on paths listed in a text file,
# validating each move against the main SQLite library DB.
#
# Usage:
#   bash safe_move_by_db_checksum.sh \
#       /path/to/library_final.db \
#       /path/to/list_of_source_paths.txt \
#       /source/root/prefix \
#       /destination/root/prefix
#
# Example:
#   bash safe_move_by_db_checksum.sh \
#       artifacts/db/library_final.db \
#       /Volumes/dotad/move_lists/to_move.txt \
#       /Volumes/dotad/MUSIC \
#       /Volumes/bad/MUSIC
#
# Assumptions:
#   - DB has table `library_files` with columns:
#       path (TEXT PRIMARY KEY),
#       size_bytes (INTEGER),
#       checksum (TEXT),
#       ... (other columns ignored here)
#   - Paths in the list file are absolute and match `library_files.path`.
#   - We only move files under SRC_ROOT into DEST_ROOT, preserving
#     the relative path.
#
# Safety guarantees:
#   - If file not found in DB: skip + log error.
#   - If size mismatch (disk vs DB): skip + log error.
#   - If checksum mismatch (disk vs DB): skip + log error.
#   - If destination exists with different checksum: skip + log error.
#   - If destination exists with same checksum: skip (already present) + log.
#   - Only when everything matches and destination is free, file is MOVED.
#   - After move, destination is re-verified (size + checksum) against DB.
#

set -euo pipefail

# ---------------- Configuration toggles ----------------

# If set to 1, do not actually move; just simulate and log.
DRY_RUN=0

# If set to 1, abort the entire run on the first critical error.
ABORT_ON_ERROR=0

# -------------------------------------------------------

if [[ $# -ne 4 ]]; then
    echo "Usage: $0 <db_path> <list_file> <src_root> <dest_root>" >&2
    exit 1
fi

DB_PATH=$1
LIST_FILE=$2
SRC_ROOT=$3
DEST_ROOT=$4

# Normalise roots: strip trailing slashes
SRC_ROOT=${SRC_ROOT%/}
DEST_ROOT=${DEST_ROOT%/}

# ---------- Sanity checks ----------

if [[ ! -f "$DB_PATH" ]]; then
    echo "ERROR: DB not found: $DB_PATH" >&2
    exit 1
fi

if [[ ! -f "$LIST_FILE" ]]; then
    echo "ERROR: List file not found: $LIST_FILE" >&2
    exit 1
fi

if [[ ! -d "$SRC_ROOT" ]]; then
    echo "ERROR: Source root directory not found: $SRC_ROOT" >&2
    exit 1
fi

if [[ ! -d "$DEST_ROOT" ]]; then
    echo "ERROR: Destination root directory not found: $DEST_ROOT" >&2
    exit 1
fi

if ! command -v sqlite3 >/dev/null 2>&1; then
    echo "ERROR: sqlite3 is required but not found in PATH." >&2
    exit 1
fi

# Detect an MD5 command (macOS: md5, Linux: md5sum)
detect_md5_cmd() {
    if command -v md5 >/dev/null 2>&1; then
        echo "md5"
    elif command -v md5sum >/dev/null 2>&1; then
        echo "md5sum"
    else
        echo ""
    fi
}

MD5_CMD=$(detect_md5_cmd)
if [[ -z "$MD5_CMD" ]]; then
    echo "ERROR: Neither 'md5' nor 'md5sum' was found. Cannot compute checksums." >&2
    exit 1
fi

# Compute size in bytes, portable between macOS and Linux
filesize() {
    local f=$1
    if stat -f%z "$f" >/dev/null 2>&1; then
        stat -f%z "$f"
    else
        stat -c%s "$f"
    fi
}

# Compute MD5 hex digest only (no filename)
file_md5() {
    local f=$1
    if [[ "$MD5_CMD" == "md5" ]]; then
        md5 -q "$f"
    else
        md5sum "$f" | awk '{print $1}'
    fi
}

# ---------- Logging setup ----------

RUN_ID=$(date +"%Y%m%d_%H%M%S")
LOG_DIR="artifacts/move_logs/safe_move_${RUN_ID}"
mkdir -p "$LOG_DIR"

MOVED_LOG="${LOG_DIR}/moved.log"
SKIPPED_LOG="${LOG_DIR}/skipped.log"
ERROR_LOG="${LOG_DIR}/errors.log"
SUMMARY_LOG="${LOG_DIR}/summary.log"

echo "------------------------------------------------------------"
echo "SAFE MOVE BY DB CHECKSUM"
echo "DB:          $DB_PATH"
echo "List file:   $LIST_FILE"
echo "Source root: $SRC_ROOT"
echo "Dest root:   $DEST_ROOT"
echo "Log dir:     $LOG_DIR"
echo "Dry-run:     $DRY_RUN"
echo "Abort on error: $ABORT_ON_ERROR"
echo "------------------------------------------------------------"

echo "# Moved files" > "$MOVED_LOG"
echo "# Skipped files" > "$SKIPPED_LOG"
echo "# Errors" > "$ERROR_LOG"

TOTAL=0
MOVED=0
SKIPPED=0
ERRORS=0

log_moved() {
    local src=$1 dest=$2 checksum=$3
    ((MOVED++))
    printf "%s\tMOVED\t%s\t%s\t%s\n" "$(date -Iseconds)" "$checksum" "$src" "$dest" >> "$MOVED_LOG"
}

log_skipped() {
    local reason=$1 src=$2 dest=${3:-""}
    ((SKIPPED++))
    printf "%s\tSKIPPED\t%s\t%s\t%s\n" "$(date -Iseconds)" "$reason" "$src" "$dest" >> "$SKIPPED_LOG"
}

log_error() {
    local reason=$1 src=$2 dest=${3:-""}
    ((ERRORS++))
    printf "%s\tERROR\t%s\t%s\t%s\n" "$(date -Iseconds)" "$reason" "$src" "$dest" >> "$ERROR_LOG"
    if [[ "$ABORT_ON_ERROR" -eq 1 ]]; then
        echo "ABORT_ON_ERROR=1: aborting due to error: $reason" >&2
        exit 1
    fi
}

# ---------- Main loop ----------

while IFS= read -r SRC_PATH; do
    # Skip empty or comment lines
    [[ -z "$SRC_PATH" ]] && continue
    [[ "$SRC_PATH" =~ ^# ]] && continue

    ((TOTAL++))

    # Ensure source path is under the SRC_ROOT
    if [[ "$SRC_PATH" != "$SRC_ROOT"* ]]; then
        log_error "SRC_NOT_UNDER_ROOT" "$SRC_PATH"
        continue
    fi

    # Check file exists on disk
    if [[ ! -f "$SRC_PATH" ]]; then
        log_error "SRC_NOT_FOUND_ON_DISK" "$SRC_PATH"
        continue
    fi

    # Lookup in DB
    # Escape single quotes for SQL
    SQL_PATH=${SRC_PATH//\'/\'\'}
    DB_ROW=$(sqlite3 "$DB_PATH" "SELECT checksum,size_bytes FROM library_files WHERE path='$SQL_PATH';" || true)

    if [[ -z "$DB_ROW" ]]; then
        log_error "NOT_FOUND_IN_DB" "$SRC_PATH"
        continue
    fi

    DB_CHECKSUM=${DB_ROW%%|*}
    DB_SIZE=${DB_ROW##*|}

    if [[ -z "$DB_CHECKSUM" || -z "$DB_SIZE" ]]; then
        log_error "DB_ROW_INCOMPLETE" "$SRC_PATH"
        continue
    fi

    # Verify size against DB
    DISK_SIZE=$(filesize "$SRC_PATH")
    if [[ "$DISK_SIZE" != "$DB_SIZE" ]]; then
        log_error "SIZE_MISMATCH_DB_VS_DISK (db=$DB_SIZE,disk=$DISK_SIZE)" "$SRC_PATH"
        continue
    fi

    # Verify checksum against DB
    DISK_MD5=$(file_md5 "$SRC_PATH")
    if [[ "$DISK_MD5" != "$DB_CHECKSUM" ]]; then
        log_error "CHECKSUM_MISMATCH_DB_VS_DISK (db=$DB_CHECKSUM,disk=$DISK_MD5)" "$SRC_PATH"
        continue
    fi

    # Compute destination path by substituting SRC_ROOT -> DEST_ROOT
    REL_PATH=${SRC_PATH#"$SRC_ROOT"}
    DEST_PATH="${DEST_ROOT}${REL_PATH}"

    DEST_DIR=$(dirname "$DEST_PATH")
    mkdir -p "$DEST_DIR"

    # If destination exists, check content
    if [[ -f "$DEST_PATH" ]]; then
        DEST_SIZE=$(filesize "$DEST_PATH")
        DEST_MD5=$(file_md5 "$DEST_PATH")

        if [[ "$DEST_MD5" == "$DB_CHECKSUM" && "$DEST_SIZE" == "$DB_SIZE" ]]; then
            # Already present with same content: safe but no need to move
            log_skipped "DEST_ALREADY_HAS_SAME_CONTENT" "$SRC_PATH" "$DEST_PATH"
            continue
        else
            # Different content at destination: do not overwrite
            log_error "DEST_CONFLICT_DIFFERENT_CONTENT (dest_md5=$DEST_MD5, db=$DB_CHECKSUM)" "$SRC_PATH" "$DEST_PATH"
            continue
        fi
    fi

    # At this point: source is verified, destination is free.
    if [[ "$DRY_RUN" -eq 1 ]]; then
        log_skipped "DRY_RUN_NO_MOVE" "$SRC_PATH" "$DEST_PATH"
        continue
    fi

    # Perform the move
    if mv -- "$SRC_PATH" "$DEST_PATH"; then
        :
    else
        log_error "MOVE_FAILED" "$SRC_PATH" "$DEST_PATH"
        continue
    fi

    # Re-verify at destination
    if [[ ! -f "$DEST_PATH" ]]; then
        log_error "DEST_MISSING_AFTER_MOVE" "$SRC_PATH" "$DEST_PATH"
        continue
    fi

    DEST_SIZE_AFTER=$(filesize "$DEST_PATH")
    DEST_MD5_AFTER=$(file_md5 "$DEST_PATH")

    if [[ "$DEST_SIZE_AFTER" != "$DB_SIZE" ]]; then
        log_error "DEST_SIZE_MISMATCH_AFTER_MOVE (db=$DB_SIZE,dest=$DEST_SIZE_AFTER)" "$SRC_PATH" "$DEST_PATH"
        continue
    fi

    if [[ "$DEST_MD5_AFTER" != "$DB_CHECKSUM" ]]; then
        log_error "DEST_CHECKSUM_MISMATCH_AFTER_MOVE (db=$DB_CHECKSUM,dest=$DEST_MD5_AFTER)" "$SRC_PATH" "$DEST_PATH"
        continue
    fi

    log_moved "$SRC_PATH" "$DEST_PATH" "$DB_CHECKSUM"

done < "$LIST_FILE"

# ---------- Summary ----------

{
    echo "SAFE MOVE SUMMARY"
    echo "-----------------"
    echo "DB:            $DB_PATH"
    echo "List file:     $LIST_FILE"
    echo "Source root:   $SRC_ROOT"
    echo "Dest root:     $DEST_ROOT"
    echo "Dry-run:       $DRY_RUN"
    echo "Abort on error:$ABORT_ON_ERROR"
    echo
    echo "Total paths processed: $TOTAL"
    echo "Moved:                 $MOVED"
    echo "Skipped:               $SKIPPED"
    echo "Errors:                $ERRORS"
    echo
    echo "Logs:"
    echo "  Moved:   $MOVED_LOG"
    echo "  Skipped: $SKIPPED_LOG"
    echo "  Errors:  $ERROR_LOG"
} | tee "$SUMMARY_LOG"

echo "------------------------------------------------------------"
echo "Done. Summary written to: $SUMMARY_LOG"
echo "------------------------------------------------------------"
