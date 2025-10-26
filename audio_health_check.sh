#!/bin/bash
# Automated FLAC/drive health check for troubleshooting batch failures

set -e

# Usage: ./audio_health_check.sh "/path/to/file.flac" /Volumes/dotad/MUSIC

AUDIO_FILE="$1"
MUSIC_DIR="$2"

if [ -z "$AUDIO_FILE" ] || [ -z "$MUSIC_DIR" ]; then
  echo "Usage: $0 /path/to/file.flac /Volumes/dotad/MUSIC"
  exit 1
fi

# 1. Direct spot check

echo "\n[1/4] Spot check with flac -t:"
if command -v flac >/dev/null 2>&1; then
  flac -t "$AUDIO_FILE" && echo "flac -t: OK" || echo "flac -t: FAIL"
else
  echo "flac not found"
fi

echo "\n[1/4] Spot check with ffmpeg:"
if command -v ffmpeg >/dev/null 2>&1; then
  ffmpeg -v error -i "$AUDIO_FILE" -f null - && echo "ffmpeg: OK" || echo "ffmpeg: FAIL"
else
  echo "ffmpeg not found"
fi

# 2. Drive health/mount check

echo "\n[2/4] diskutil verifyVolume:"
if command -v diskutil >/dev/null 2>&1; then
  diskutil verifyVolume "$(dirname "$MUSIC_DIR")"
else
  echo "diskutil not found (macOS only)"
fi

echo "\n[2/4] ls -l check:"
ls -l "$MUSIC_DIR" | head

# 3. Timeout/parallelism test (print recommended command)

echo "\n[3/4] To test with fewer workers and longer timeout, run:"
echo "python3 dd_flac_dedupe_db.py --root $MUSIC_DIR --workers 2 --skip-broken --dry-run --auto-quarantine --decode-timeout 600"

# 4. If all files fail, print diagnosis

echo "\n[4/4] If all files fail, check:"
echo "- Volume mount health"
echo "- Permissions for flac/ffmpeg"
echo "- Timeout settings"
echo "- System logs for I/O errors"
