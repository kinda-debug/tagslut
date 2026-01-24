#!/usr/bin/env bash
set -euo pipefail

########################################
# USER CONFIGURATION
########################################

# Path to your FLAC source library
FLAC_SOURCE="$HOME/Music/FLAC"

# Mount point name you want for the SD card
SD_NAME="AUDI_SD"

# MP3 quality (LAME V0 = recommended)
MP3_QUALITY="0"

########################################
# SAFETY CHECKS
########################################

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg not found. Install with: brew install ffmpeg"
  exit 1
fi

if [ ! -d "$FLAC_SOURCE" ]; then
  echo "FLAC source directory not found: $FLAC_SOURCE"
  exit 1
fi

echo
echo "⚠️  ALL DATA ON THE SD CARD WILL BE ERASED."
echo "Target volume name will be: $SD_NAME"
echo
read -rp "Type YES to continue: " CONFIRM
if [ "$CONFIRM" != "YES" ]; then
  echo "Aborted."
  exit 1
fi

########################################
# DETECT SD CARD
########################################

echo
echo "Available disks:"
diskutil list
echo
read -rp "Enter the disk identifier for the SD card (e.g. disk2): " DISK_ID

if ! diskutil info "/dev/$DISK_ID" >/dev/null 2>&1; then
  echo "Invalid disk identifier."
  exit 1
fi

########################################
# FORMAT SD CARD (FAT32)
########################################

echo
echo "Formatting /dev/$DISK_ID as FAT32..."
diskutil eraseDisk MS-DOS "$SD_NAME" MBRFormat "/dev/$DISK_ID"

SD_MOUNT="/Volumes/$SD_NAME"

if [ ! -d "$SD_MOUNT" ]; then
  echo "SD card not mounted correctly."
  exit 1
fi

########################################
# CONVERT & COPY
########################################

echo
echo "Converting FLAC → MP3 and copying to SD card..."
echo

find "$FLAC_SOURCE" -type f -iname "*.flac" | while read -r FLAC_FILE; do
  REL_PATH="${FLAC_FILE#$FLAC_SOURCE/}"
  MP3_PATH="${REL_PATH%.flac}.mp3"
  DEST="$SD_MOUNT/$MP3_PATH"

  mkdir -p "$(dirname "$DEST")"

  ffmpeg -loglevel error -y \
    -i "$FLAC_FILE" \
    -map_metadata 0 \
    -vn \
    -c:a libmp3lame \
    -q:a "$MP3_QUALITY" \
    "$DEST"

  echo "✔ $(basename "$DEST")"
done

########################################
# FINAL SYNC
########################################

sync
echo
echo "Done."
echo "SD card '$SD_NAME' is ready for Audi A1."

