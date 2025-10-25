#!/usr/bin/env bash
set -euo pipefail

QUAR="/Volumes/dotad/MUSIC/_quarantine_from_gemini"
ROOT="/Volumes/dotad/MUSIC"
OUT="quarantine_verification_report.csv"

echo "quarantine_path,original_path,status,quarantine_md5,original_md5" > "$OUT"

find "$QUAR" -type f -name "*.flac" | while IFS= read -r q; do
  rel="${q#$QUAR/}"
  orig="$ROOT/$rel"

  # Compute quarantine MD5
  q_md5=$(ffmpeg -v error -i "$q" -map 0:a -f md5 - 2>/dev/null | awk '{print $NF}' || true)

  if [[ -f "$orig" ]]; then
    o_md5=$(ffmpeg -v error -i "$orig" -map 0:a -f md5 - 2>/dev/null | awk '{print $NF}' || true)
    if [[ "$q_md5" == "$o_md5" ]]; then
      status="SAME"
    else
      status="MISMATCH"
    fi
  else
    o_md5=""
    status="MISSING"
  fi

  echo "\"$q\",\"$orig\",\"$status\",\"$q_md5\",\"$o_md5\"" >> "$OUT"
  echo "[ $status ] $rel"
done

echo "[✓] Report written to $OUT"
