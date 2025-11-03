#!/usr/bin/env bash
#
# move_dupes_to_trash.sh
# Moves duplicate audio files marked "plan" in the dedup report
# to the structured trash directory under _TRASH_DUPES_20251028_014226.
# Safe, resumable, and fully logged.

set -euo pipefail
IFS=$'\n\t'

REPORT_PATH="/Volumes/dotad/MUSIC/_DEDUP_REPORT_20251028_014226.csv"
LOG_PATH="./move_dupes_$(date +%Y%m%d_%H%M%S).log"
TRASH_ROOT="/Volumes/dotad/MUSIC/_TRASH_DUPES_20251028_014226"

# Dry run flag: set to true to only print commands
DRY_RUN=false

if [[ ! -f "$REPORT_PATH" ]]; then
    echo "❌ Dedup report not found: $REPORT_PATH"
    exit 1
fi

echo "🚀 Starting duplicate move process..."
echo "📝 Log: $LOG_PATH"
echo "🗑️  Trash root: $TRASH_ROOT"
if $DRY_RUN; then echo "🔍 DRY RUN MODE"; fi
echo

# Skip header line, iterate over planned entries
tail -n +2 "$REPORT_PATH" | \
awk -F',' 'BEGIN {OFS=","} {if ($16=="plan") print $4,$17}' | \
while IFS=, read -r src dest; do
    # Clean paths from potential quotes
    src="${src%\"}"; src="${src#\"}"
    dest="${dest%\"}"; dest="${dest#\"}"

    # Skip if source doesn't exist
    if [[ ! -f "$src" ]]; then
        echo "⚠️  Skipping missing: $src" | tee -a "$LOG_PATH"
        continue
    fi

    # Ensure destination directory exists
    dest_dir=$(dirname "$dest")
    if $DRY_RUN; then
        echo "mkdir -p '$dest_dir'" | tee -a "$LOG_PATH"
    else
        mkdir -p "$dest_dir"
    fi

    # Move file using rsync (safe & resumable)
    if $DRY_RUN; then
        echo "rsync -av --remove-source-files '$src' '$dest_dir/'" | tee -a "$LOG_PATH"
    else
        rsync -av --remove-source-files --progress "$src" "$dest_dir/" >> "$LOG_PATH" 2>&1
    fi

    # Double-check and log
    if [[ -f "$dest" ]]; then
        echo "✅ Moved: $src → $dest" | tee -a "$LOG_PATH"
    else
        echo "❌ Failed: $src" | tee -a "$LOG_PATH"
    fi
done

# Clean up empty directories after move (only if not dry run)
if ! $DRY_RUN; then
    echo
    echo "🧹 Cleaning empty directories..."
    find "/Volumes/dotad/MUSIC" -type d -empty -delete 2>/dev/null || true
fi

echo
echo "✅ Done. Log saved at: $LOG_PATH"

# --- Post-move verification (TODO #6) ---
echo
echo "🔍 Starting post-move verification..."
echo "🔍 Starting post-move verification..." >> "$LOG_PATH"

if $DRY_RUN; then
    echo "⚠️ DRY RUN mode: skipping post-move verification checks." | tee -a "$LOG_PATH"
else
    # Count files remaining in MUSIC (excluding trash)
    music_count=$(find "/Volumes/dotad/MUSIC" -type f ! -path "$TRASH_ROOT/*" 2>/dev/null | wc -l)
    echo "📂 Files remaining in MUSIC (excluding trash): $music_count" | tee -a "$LOG_PATH"

    # Count files in trash directory
    trash_count=$(find "$TRASH_ROOT" -type f 2>/dev/null | wc -l)
    echo "🗑️ Files currently in trash directory: $trash_count" | tee -a "$LOG_PATH"

    # Verify all "keep" files still exist
    missing_keep=0
    echo "🔎 Verifying 'keep' files existence..." | tee -a "$LOG_PATH"
    tail -n +2 "$REPORT_PATH" | \
    awk -F',' 'BEGIN {OFS=","} {if ($16=="keep") print $4}' | \
    while IFS= read -r keep_file; do
        keep_file="${keep_file%\"}"; keep_file="${keep_file#\"}"
        if [[ ! -f "$keep_file" ]]; then
            echo "❌ Missing 'keep' file: $keep_file" | tee -a "$LOG_PATH"
            missing_keep=$((missing_keep+1))
        fi
    done
    echo "✅ 'Keep' files missing count: $missing_keep" | tee -a "$LOG_PATH"

    # Count how many planned files actually landed in trash
    planned_total=0
    planned_found=0
    missing_moves=()
    tail -n +2 "$REPORT_PATH" | \
    awk -F',' 'BEGIN {OFS=","} {if ($16=="plan") print $4,$17}' | \
    while IFS=, read -r src dest; do
        src="${src%\"}"; src="${src#\"}"
        dest="${dest%\"}"; dest="${dest#\"}"
        planned_total=$((planned_total+1))
        if [[ -f "$dest" ]]; then
            planned_found=$((planned_found+1))
        else
            missing_moves+=("$src")
        fi
    done

    echo "📊 Planned files total: $planned_total" | tee -a "$LOG_PATH"
    echo "📊 Planned files found in trash: $planned_found" | tee -a "$LOG_PATH"

    if (( planned_found < planned_total )); then
        echo "⚠️ Missing or failed moves:" | tee -a "$LOG_PATH"
        for f in "${missing_moves[@]}"; do
            echo " - $f" | tee -a "$LOG_PATH"
        done
    else
        echo "✅ All planned files found in trash." | tee -a "$LOG_PATH"
    fi
fi

echo
echo "🔍 Post-move verification complete." | tee -a "$LOG_PATH"