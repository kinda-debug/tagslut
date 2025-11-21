#!/usr/bin/env python3
import os
import subprocess
import csv
import sys

ROOT = "/Volumes/dotad/NEW_LIBRARY"
LOG_FILE = "deleted_bad_flacs.csv"

def is_flac(path):
    return path.lower().endswith(".flac")

def file_size(path):
    try:
        return os.path.getsize(path)
    except:
        return 0

def ffprobe_available():
    try:
        subprocess.run(
            ["ffprobe", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return True
    except FileNotFoundError:
        return False

USE_FFPROBE = ffprobe_available()

def flac_is_valid_ffprobe(path):
    """
    Use ffprobe to check if FLAC metadata + first frame is readable.
    """
    try:
        p = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-select_streams", "a:0",
                "-show_entries", "stream=codec_name",
                "-of", "default=nw=1:nk=1",
                path
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        out = p.stdout.strip().lower()
        return ("flac" in out)
    except Exception:
        return False

def flac_is_valid_header_only(path):
    """
    Minimal fallback: check if the file starts with the standard FLAC signature.
    """
    try:
        with open(path, "rb") as f:
            sig = f.read(4)
        return sig == b"fLaC"
    except:
        return False

def is_valid_flac(path):
    """
    Composite validity check:
    - Reject zero-byte files
    - Prefer ffprobe
    - Fallback to header check
    """
    if file_size(path) < 16:
        return False

    if USE_FFPROBE:
        return flac_is_valid_ffprobe(path)

    return flac_is_valid_header_only(path)


def main():
    flac_count = 0
    deleted_count = 0
    valid_count = 0
    error_count = 0

    records = []

    print("=== CLEAN NEW_LIBRARY ===")
    print(f"Scanning: {ROOT}")
    print(f"ffprobe available: {USE_FFPROBE}")
    print("")

    for root, dirs, files in os.walk(ROOT):
        for f in files:
            if not is_flac(f):
                continue

            full = os.path.join(root, f)
            flac_count += 1

            valid = is_valid_flac(full)

            if not valid:
                # bad file → delete
                try:
                    os.remove(full)
                    deleted_count += 1
                    records.append([full, "DELETED"])
                    print(f"[DELETE] {full}")
                except Exception as e:
                    error_count += 1
                    records.append([full, f"ERROR: {e}"])
                    print(f"[ERROR] could not delete {full}: {e}")
            else:
                valid_count += 1
                records.append([full, "OK"])

    # Write CSV
    with open(LOG_FILE, "w", newline="", encoding="utf-8") as out:
        writer = csv.writer(out)
        writer.writerow(["file", "action"])
        writer.writerows(records)

    print("")
    print("=== SUMMARY ===")
    print(f"Total FLAC files checked: {flac_count}")
    print(f"Valid FLAC files:        {valid_count}")
    print(f"Deleted bad files:       {deleted_count}")
    print(f"Errors:                  {error_count}")
    print(f"Log written to:          {LOG_FILE}")
    print("=========================")

if __name__ == "__main__":
    main()
