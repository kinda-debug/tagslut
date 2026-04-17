#!/usr/bin/env bash
# resolve_lossless_winner.sh
#
# Per-stem lossless winner selection for SpotiFLACnext staging directories.
#
# Rules (in priority order):
#   1. Losslessness is codec-based, not container-based.
#      ALAC/FLAC m4a are canonical; AAC m4a is provisional/lossy.
#   2. eac3 codec → not lossless regardless of container; flag as NO_LOSSLESS.
#   3. ALAC m4a only → transcode to FLAC in-place, delete m4a.
#   4. FLAC only → keep.
#   5. Both FLAC and ALAC m4a → LARGER file is the better source.
#      - ALAC larger: transcode ALAC → FLAC, delete original FLAC and m4a.
#      - FLAC larger: keep FLAC, delete m4a.
#   6. MP3s are never deleted by this script; they stay provisional until a lossless source returns.
#
# Output (stdout): TSV  ACTION<tab>PATH
#   Actions: KEEP_FLAC  TRANSCODE_ALAC  WIN_ALAC_LARGER  WIN_FLAC_LARGER
#            NO_LOSSLESS  NO_LOSSLESS_KEEP_MP3  DELETE_LOSSY_M4A
#            DELETE_INFERIOR_ALAC  SKIP_EXISTS  ERROR
#
# Usage:
#   resolve_lossless_winner.sh --scan-path DIR [--dry-run] [--overwrite]
#   resolve_lossless_winner.sh [--dry-run] [--overwrite] FILE [FILE ...]

set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  resolve_lossless_winner.sh --scan-path DIR [--dry-run] [--overwrite]
  resolve_lossless_winner.sh [--dry-run] [--overwrite] FILE [FILE ...]

Options:
  --scan-path DIR   Recursively scan DIR for .flac / .m4a / .mp3 files.
  --dry-run         Print actions, make no changes.
  --overwrite       Re-transcode even if output FLAC already exists.
EOF
}

need_bin() {
  command -v "$1" >/dev/null 2>&1 || { echo "missing dependency: $1" >&2; exit 1; }
}
need_bin ffmpeg
need_bin ffprobe

dry_run=0
overwrite=0
scan_path=""
inputs=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --scan-path)
      [[ $# -ge 2 ]] || { echo "--scan-path requires a value" >&2; exit 1; }
      scan_path="$2"; shift 2 ;;
    --dry-run)   dry_run=1;   shift ;;
    --overwrite) overwrite=1; shift ;;
    --) shift; break ;;
    -*) echo "unknown option: $1" >&2; usage >&2; exit 1 ;;
    *) inputs+=("$1"); shift ;;
  esac
done

if [[ -n "$scan_path" ]]; then
  [[ -d "$scan_path" ]] || { echo "scan-path is not a directory: $scan_path" >&2; exit 1; }
  scan_path="$(cd "$scan_path" && pwd)"
  while IFS= read -r -d '' f; do
    inputs+=("$f")
  done < <(find "$scan_path" -type f \
    \( -iname '*.flac' -o -iname '*.m4a' -o -iname '*.mp3' \) \
    ! -name '._*' -print0 | sort -z)
fi

[[ ${#inputs[@]} -gt 0 ]] || { echo "no input files" >&2; usage >&2; exit 1; }

# ---------------------------------------------------------------------------
# Phase 1: probe all files, group by directory+stem
# ---------------------------------------------------------------------------

declare -A file_codec   # path -> codec string
declare -A file_size    # path -> bytes
declare -A stem_files   # "dir|stem" -> newline-separated list of paths

for f in "${inputs[@]}"; do
  [[ -f "$f" ]] || continue
  codec="$(ffprobe -v error -select_streams a:0 \
    -show_entries stream=codec_name -of default=nk=1:nw=1 "$f" 2>/dev/null \
    | head -1 || true)"
  size="$(stat -f '%z' "$f" 2>/dev/null || stat -c '%s' "$f" 2>/dev/null || echo 0)"
  file_codec["$f"]="${codec:-unknown}"
  file_size["$f"]="$size"

  d="$(dirname "$f")"
  base="$(basename "$f")"
  stem="${base%.*}"
  key="${d}|${stem}"
  stem_files["$key"]="${stem_files[$key]:-}${f}"$'\n'
done

# ---------------------------------------------------------------------------
# Phase 2: per-stem decision
# ---------------------------------------------------------------------------

transcode_alac_to_flac() {
  local src="$1" dest="$2"
  local tmp
  tmp="$(dirname "$dest")/.tmp.$$.$(basename "$dest")"
  rm -f "$tmp" 2>/dev/null || true
  if ffmpeg -hide_banner -loglevel error -nostdin -y \
      -i "$src" -map_metadata 0 -map 0:a:0 -map 0:v? \
      -c:a flac -compression_level 12 -c:v copy \
      "$tmp" 2>/dev/null; then
    :
  else
    ffmpeg -hide_banner -loglevel error -nostdin -y \
      -i "$src" -map_metadata 0 -map 0:a:0 \
      -c:a flac -compression_level 12 "$tmp"
  fi
  mv -f "$tmp" "$dest"
}

maybe_rm() {
  local f="$1"
  echo -e "DELETE\t$f"
  [[ "$dry_run" -eq 1 ]] || rm -f "$f"
}

transcoded=0; kept=0; flagged=0; errors=0

for key in "${!stem_files[@]}"; do
  flac_files=(); alac_files=(); eac3_files=(); aac_files=(); mp3_files=()

  while IFS= read -r f; do
    [[ -n "$f" ]] || continue
    ext="${f##*.}"; ext="${ext,,}"
    codec="${file_codec[$f]}"
    case "$ext" in
      flac) flac_files+=("$f") ;;
      mp3)  mp3_files+=("$f") ;;
      m4a)
        case "$codec" in
          alac|flac) alac_files+=("$f") ;;
          eac3)      eac3_files+=("$f") ;;
          *)         aac_files+=("$f") ;;
        esac ;;
    esac
  done <<< "${stem_files[$key]}"

  has_flac=${#flac_files[@]}; has_alac=${#alac_files[@]}

  # No lossless at all
  if [[ $has_flac -eq 0 && $has_alac -eq 0 ]]; then
    for f in "${eac3_files[@]:-}" "${aac_files[@]:-}"; do
      [[ -n "$f" ]] && echo -e "NO_LOSSLESS\t$f"
    done
    for f in "${mp3_files[@]:-}"; do
      [[ -n "$f" ]] && echo -e "NO_LOSSLESS_KEEP_MP3\t$f"
    done
    (( flagged++ )) || true
    continue
  fi

  # Find largest ALAC and largest FLAC
  best_alac=""; best_alac_size=0
  for f in "${alac_files[@]:-}"; do
    [[ -n "$f" ]] || continue
    sz="${file_size[$f]}"
    (( sz > best_alac_size )) && { best_alac_size=$sz; best_alac="$f"; }
  done

  best_flac=""; best_flac_size=0
  for f in "${flac_files[@]:-}"; do
    [[ -n "$f" ]] || continue
    sz="${file_size[$f]}"
    (( sz > best_flac_size )) && { best_flac_size=$sz; best_flac="$f"; }
  done

  # Only FLAC, no ALAC
  if [[ $has_alac -eq 0 ]]; then
    echo -e "KEEP_FLAC\t$best_flac"
    (( kept++ )) || true
    for f in "${eac3_files[@]:-}" "${aac_files[@]:-}"; do
      [[ -n "$f" ]] && maybe_rm "$f"
    done
    continue
  fi

  # Only ALAC, no FLAC
  if [[ $has_flac -eq 0 ]]; then
    stem="${best_alac%.*}"; dest="${stem}.flac"
    if [[ -f "$dest" && "$overwrite" -eq 0 ]]; then
      echo -e "SKIP_EXISTS\t$dest"; (( kept++ )) || true
    else
      echo -e "TRANSCODE_ALAC\t$best_alac -> $dest"
      if [[ "$dry_run" -eq 0 ]]; then
        if transcode_alac_to_flac "$best_alac" "$dest"; then
          rm -f "$best_alac"; (( transcoded++ )) || true
        else
          echo -e "ERROR\t$best_alac" >&2; (( errors++ )) || true
        fi
      fi
    fi
    for f in "${alac_files[@]:-}"; do
      [[ -n "$f" && "$f" != "$best_alac" ]] && maybe_rm "$f"
    done
    for f in "${eac3_files[@]:-}" "${aac_files[@]:-}"; do
      [[ -n "$f" ]] && maybe_rm "$f"
    done
    continue
  fi

  # Both FLAC and ALAC present — larger wins
  if (( best_alac_size >= best_flac_size )); then
    stem="${best_alac%.*}"; dest="${stem}.flac"
    tmp_dest="${stem}.__winner__.flac"
    echo -e "WIN_ALAC_LARGER\t$best_alac -> $dest  (ALAC ${best_alac_size}B > FLAC ${best_flac_size}B)"
    if [[ "$dry_run" -eq 0 ]]; then
      if transcode_alac_to_flac "$best_alac" "$tmp_dest"; then
        for f in "${flac_files[@]:-}"; do [[ -n "$f" ]] && rm -f "$f"; done
        mv -f "$tmp_dest" "$dest"
        rm -f "$best_alac"
        for f in "${alac_files[@]:-}"; do [[ -n "$f" && "$f" != "$best_alac" ]] && rm -f "$f"; done
        (( transcoded++ )) || true
      else
        rm -f "$tmp_dest" 2>/dev/null || true
        echo -e "ERROR\t$best_alac" >&2; (( errors++ )) || true
      fi
    fi
  else
    echo -e "WIN_FLAC_LARGER\t$best_flac  (FLAC ${best_flac_size}B > ALAC ${best_alac_size}B)"
    (( kept++ )) || true
    for f in "${alac_files[@]:-}"; do [[ -n "$f" ]] && maybe_rm "$f"; done
    for f in "${flac_files[@]:-}"; do [[ -n "$f" && "$f" != "$best_flac" ]] && maybe_rm "$f"; done
    for f in "${eac3_files[@]:-}" "${aac_files[@]:-}"; do [[ -n "$f" ]] && maybe_rm "$f"; done
  fi

done

echo "---" >&2
echo "transcoded: $transcoded  kept: $kept  flagged_no_lossless: $flagged  errors: $errors" >&2
[[ $errors -eq 0 ]]
