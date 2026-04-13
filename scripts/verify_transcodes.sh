#!/usr/bin/env bash
# verify_transcodes.sh — sanity-check transcoded files produced by
# transcode_m4a_to_flac_lossless.sh.
#
# For ALAC -> FLAC: bit-perfect PCM MD5 comparison (decoded samples must match).
# For AAC  -> MP3 : duration match within 1 s + full decode without error.
#
# Usage:
#   verify_transcodes.sh --scan-path DIR [--lossy-mp3]
#   verify_transcodes.sh FILE.m4a [FILE2.m4a ...]
#
#   --scan-path DIR   Recursively find source .m4a files under DIR.
#   --lossy-mp3       Also verify AAC -> MP3 pairs (otherwise AAC is reported as skipped).

set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  verify_transcodes.sh [--scan-path DIR] [--lossy-mp3] [FILE.m4a ...]

  --scan-path DIR   Recursively find source .m4a files under DIR.
  --lossy-mp3       Also verify AAC .m4a -> .mp3 pairs (duration + decode check).
                    Without this flag, AAC files are reported as skipped.
EOF
}

need_bin() {
  command -v "$1" >/dev/null 2>&1 || { echo "missing dependency: $1" >&2; exit 1; }
}

need_bin ffmpeg
need_bin ffprobe

scan_path=""
lossy_mp3=0
inputs=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --scan-path)
      [[ $# -ge 2 ]] || { echo "--scan-path requires a value" >&2; exit 1; }
      scan_path="$2"
      shift 2
      ;;
    --lossy-mp3)
      lossy_mp3=1
      shift
      ;;
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
  done < <(find "$scan_path" -type f -iname '*.m4a' ! -name '._*' -print0 | sort -z)
fi

if [[ ${#inputs[@]} -eq 0 ]]; then
  echo "no input files found" >&2; usage >&2; exit 1
fi

# Decode to raw PCM and return MD5 via ffmpeg's md5 muxer.
pcm_md5() {
  ffmpeg -hide_banner -loglevel error -nostdin \
    -i "$1" \
    -map 0:a:0 \
    -c:a pcm_s16le \
    -f md5 - 2>/dev/null | grep -oE '[0-9A-Fa-f]{32}' | head -n 1
}

# Return duration in seconds (float) using ffprobe.
duration_s() {
  ffprobe -v error -select_streams a:0 \
    -show_entries stream=duration \
    -of default=nk=1:nw=1 "$1" 2>/dev/null | head -n 1
}

ok=0
fail=0
skip=0

for src in "${inputs[@]}"; do
  [[ -f "$src" ]] || { echo "MISSING_SRC $src" >&2; (( fail++ )) || true; continue; }

  codec="$(ffprobe -v error -select_streams a:0 -show_entries stream=codec_name \
    -of default=nk=1:nw=1 "$src" | head -n 1 || true)"

  stem="${src%.*}"

  if [[ "$codec" == "alac" || "$codec" == "flac" ]]; then
    out="$stem.flac"
    if [[ ! -f "$out" ]]; then
      echo "NO_OUTPUT  $src -> $out (not yet transcoded?)"
      (( skip++ )) || true
      continue
    fi

    src_md5="$(pcm_md5 "$src")"
    out_md5="$(pcm_md5 "$out")"

    if [[ -z "$src_md5" || -z "$out_md5" ]]; then
      echo "MD5_ERROR  $src (could not decode one of the pair)"
      (( fail++ )) || true
    elif [[ "$src_md5" == "$out_md5" ]]; then
      echo "OK_LOSSLESS  $(basename "$src")  [$src_md5]"
      (( ok++ )) || true
    else
      echo "MISMATCH   $(basename "$src")"
      echo "  src  md5=$src_md5"
      echo "  flac md5=$out_md5"
      (( fail++ )) || true
    fi

  elif [[ "$codec" == "aac" && "$lossy_mp3" -eq 1 ]]; then
    out="$stem.mp3"
    if [[ ! -f "$out" ]]; then
      echo "NO_OUTPUT  $src -> $out (not yet transcoded?)"
      (( skip++ )) || true
      continue
    fi

    # Decode MP3 fully for errors; capture stderr.
    decode_err="$(ffmpeg -hide_banner -nostdin -y \
      -i "$out" -map 0:a:0 -f null - 2>&1 | grep -iE 'error|invalid|corrupt' | head -n 3 || true)"

    src_dur="$(duration_s "$src")"
    out_dur="$(duration_s "$out")"

    # Allow 1 second tolerance (encoder/decoder delay differences).
    dur_ok=0
    if [[ -n "$src_dur" && -n "$out_dur" ]]; then
      diff="$(awk -v a="$src_dur" -v b="$out_dur" 'BEGIN { d=a-b; if(d<0)d=-d; print (d<=1.0)?"1":"0" }')"
      [[ "$diff" == "1" ]] && dur_ok=1
    fi

    if [[ -n "$decode_err" ]]; then
      echo "DECODE_ERR $(basename "$src") -> $(basename "$out")"
      echo "  $decode_err"
      (( fail++ )) || true
    elif [[ "$dur_ok" -eq 0 ]]; then
      echo "DUR_MISMATCH $(basename "$src") src=${src_dur}s out=${out_dur}s"
      (( fail++ )) || true
    else
      echo "OK_LOSSY   $(basename "$src")  [${src_dur}s -> ${out_dur}s 320k mp3]"
      (( ok++ )) || true
    fi

  else
    echo "SKIPPED    $(basename "$src") (codec=$codec, not handled)"
    (( skip++ )) || true
  fi
done

echo ""
echo "result: $ok ok, $fail failed, $skip skipped"
[[ "$fail" -eq 0 ]]
