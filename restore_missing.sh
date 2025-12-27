#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n'

# ----------------------------------------------------------------------
# RESTORE RECOVERED FLAC FILES TO ORIGINAL LIBRARY LOCATIONS
# ----------------------------------------------------------------------

MISSING_LISTS=(
    "missing_MUSIC_flac.txt"
    "missing_NEW_MUSIC_flac.txt"
    "missing_NEW_LIBRARY_flac.txt"
    "missing_QUARANTINE_AUTO_GLOBAL_flac.txt"
)

PREFIXES=(
    "/Volumes/dotad/MUSIC/"
    "/Volumes/dotad/NEW_MUSIC/"
    "/Volumes/dotad/NEW_LIBRARY/"
    "/Volumes/dotad/QUARANTINE_AUTO_GLOBAL/"
)

RECOVERED_BASE="/Volumes/dotad/RECOVERED_FROM_MISSING"
ERROR_LOG="restore_missing_errors.log"
> "$ERROR_LOG"

echo "------------------------------------------------------------"
echo "RESTORING MISSING FILES"
echo "Detailed errors: $ERROR_LOG"
echo "------------------------------------------------------------"

COPIED=0

process_list() {
    local list_file="$1"
    local prefix="$2"

    if [[ ! -f "$list_file" ]]; then
        echo "[SKIP] $list_file missing"
        return
    fi

    local subdir_name
    subdir_name=$(basename "$prefix")

    local src_base="$RECOVERED_BASE/$subdir_name"

    echo
    echo "Processing: $list_file"
    echo "Source base:      $src_base"
    echo "Destination base: $prefix"

    while IFS= read -r fullpath; do
        [[ -z "$fullpath" ]] && continue

        # Remove prefix to get relative path
        rel="${fullpath#"$prefix"}"

        src="$src_base/$rel"
        dst="$fullpath"

        mkdir -p "$(dirname "$dst")"

        if [[ -f "$src" ]]; then
            cp -v "$src" "$dst" || echo "COPY ERROR: $src" >> "$ERROR_LOG"
            COPIED=$((COPIED+1))
        else
            echo "RECOVERED FILE MISSING: $src" >> "$ERROR_LOG"
        fi

    done < "$list_file"
}

# Loop over all lists
for i in "${!MISSING_LISTS[@]}"; do
    process_list "${MISSING_LISTS[$i]}" "${PREFIXES[$i]}"
done

echo
echo "------------------------------------------------------------"
echo "RESTORE COMPLETE"
echo "Files copied: $COPIED"
echo "Errors logged in: $ERROR_LOG"
echo "------------------------------------------------------------"
