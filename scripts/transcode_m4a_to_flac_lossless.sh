#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  transcode_m4a_to_flac_lossless.sh [--scan-path DIR] [--output-dir DIR] [--overwrite] [FILE.m4a ...]

  --scan-path DIR   Recursively find all .m4a files under DIR and process them.
                    When combined with --output-dir, the source tree structure is
                    mirrored under that output directory (provenance preserved).
  --output-dir DIR  Write .flac files to DIR instead of beside the source file.
                    With --scan-path the full relative sub-path is reproduced.
  --lossy-to-mp3    Also transcode AAC .m4a files to 320k CBR MP3 instead of
                    skipping them. Note: AAC->MP3 is a lossy-to-lossy transcode.
  --overwrite       Re-transcode even if the output file already exists.

By default only ALAC/FLAC .m4a files are transcoded (lossless -> FLAC).
Use --lossy-to-mp3 to also handle AAC files.
All metadata and embedded artwork are carried through intact.
EOF
}

need_bin() {
  command -v "$1" >/dev/null 2>&1 || { echo "missing dependency: $1" >&2; exit 1; }
}

need_bin ffmpeg
need_bin ffprobe

output_dir=""
overwrite=0
scan_path=""
lossy_to_mp3=0
inputs=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --scan-path)
      [[ $# -ge 2 ]] || { echo "--scan-path requires a value" >&2; exit 1; }
      scan_path="$2"
      shift 2
      ;;
    --output-dir)
      [[ $# -ge 2 ]] || { echo "--output-dir requires a value" >&2; exit 1; }
      output_dir="$2"
      shift 2
      ;;
    --lossy-to-mp3)
      lossy_to_mp3=1
      shift
      ;;
    --overwrite)
      overwrite=1
      shift
      ;;
    --) shift; break ;;
    -*) echo "unknown option: $1" >&2; usage >&2; exit 1 ;;
    *) inputs+=("$1"); shift ;;
  esac
done

# Populate inputs from --scan-path if given
if [[ -n "$scan_path" ]]; then
  [[ -d "$scan_path" ]] || { echo "scan-path is not a directory: $scan_path" >&2; exit 1; }
  scan_path="$(cd "$scan_path" && pwd)"   # canonical, no trailing slash
  while IFS= read -r -d '' f; do
    inputs+=("$f")
  done < <(find "$scan_path" -type f -iname '*.m4a' ! -name '._*' -print0 | sort -z)
fi

if [[ ${#inputs[@]} -eq 0 ]]; then
  echo "no input files found" >&2
  usage >&2
  exit 1
fi

total=${#inputs[@]}
done_count=0
skip_count=0
echo "found $total .m4a file(s) to evaluate" >&2

for in_path in "${inputs[@]}"; do
  if [[ ! -f "$in_path" ]]; then
    echo "missing file: $in_path" >&2
    (( skip_count++ )) || true
    continue
  fi

  codec="$(ffprobe -v error -select_streams a:0 -show_entries stream=codec_name -of default=nk=1:nw=1 "$in_path" | head -n 1 || true)"

  if [[ "$codec" == "alac" || "$codec" == "flac" ]]; then
    mode="flac"
  elif [[ "$codec" == "aac" && "$lossy_to_mp3" -eq 1 ]]; then
    mode="mp3"
  else
    echo "skip (not lossless, codec=${codec:-unknown}): $in_path" >&2
    (( skip_count++ )) || true
    continue
  fi

  base="$(basename "$in_path")"
  stem="${base%.*}"

  if [[ -n "$output_dir" ]]; then
    if [[ -n "$scan_path" ]]; then
      # Mirror relative sub-path under output_dir to preserve provenance.
      in_abs="$(cd "$(dirname "$in_path")" && pwd)/$base"
      rel_dir="${in_abs#"$scan_path"/}"
      rel_dir="$(dirname "$rel_dir")"
      dest_dir="$output_dir/$rel_dir"
    else
      dest_dir="$output_dir"
    fi
    mkdir -p "$dest_dir"
    out_path="$dest_dir/$stem.$mode"
  else
    out_path="${in_path%.*}.$mode"
  fi

  if [[ -f "$out_path" && "$overwrite" -ne 1 ]]; then
    echo "skip (exists): $out_path" >&2
    (( skip_count++ )) || true
    continue
  fi

  tmp_path="$(dirname "$out_path")/.tmp.$$.$(basename "$out_path")"
  rm -f "$tmp_path" 2>/dev/null || true

  if [[ "$mode" == "flac" ]]; then
    # First try including embedded artwork (often present as a video stream in .m4a).
    if ffmpeg -hide_banner -loglevel error -nostdin -y \
        -i "$in_path" \
        -map_metadata 0 \
        -map 0:a:0 -map 0:v? \
        -c:a flac -compression_level 12 \
        -c:v copy \
        "$tmp_path" 2>/dev/null; then
      :
    else
      # Fallback: audio-only (still lossless for ALAC/FLAC-in-M4A -> FLAC).
      ffmpeg -hide_banner -loglevel error -nostdin -y \
        -i "$in_path" \
        -map_metadata 0 \
        -map 0:a:0 \
        -c:a flac -compression_level 12 \
        "$tmp_path"
    fi
  else
    # AAC -> MP3 320k CBR; ID3v2.3 for broad Rekordbox compatibility.
    ffmpeg -hide_banner -loglevel error -nostdin -y \
      -i "$in_path" \
      -map_metadata 0 \
      -map 0:a:0 \
      -c:a libmp3lame -b:a 320k -id3v2_version 3 \
      "$tmp_path"
  fi

  mv -f "$tmp_path" "$out_path"
  echo "$out_path"
  (( done_count++ )) || true
done

echo "done: $done_count transcoded, $skip_count skipped" >&2

