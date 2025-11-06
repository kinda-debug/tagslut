#!/usr/bin/env python3
import os
import sys
import subprocess
import pandas as pd
import datetime

LOG_PATH = os.path.expanduser("~/audio_health_check_from_xlsx_log.txt")

SUPPORTED_EXTS = ('.flac', '.wav', '.aiff', '.aif', '.m4a')

def log(msg):
    print(msg)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

def check_flac(file_path):
    try:
        result = subprocess.run(["flac", "-t", file_path],
                                capture_output=True, text=True)
        if result.returncode == 0:
            return "OK"
        return result.stderr.strip() or "FLAC check failed"
    except FileNotFoundError:
        return "Missing flac binary"

def check_ffmpeg(file_path):
    try:
        result = subprocess.run(["ffmpeg", "-v", "error", "-i", file_path,
                                 "-f", "null", "-"], capture_output=True, text=True)
        if result.returncode == 0 and not result.stderr.strip():
            return "OK"
        return result.stderr.strip() or "FFmpeg decoding errors"
    except FileNotFoundError:
        return "Missing ffmpeg binary"

def check_file(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".flac":
        return check_flac(file_path)
    elif ext in (".wav", ".aiff", ".aif", ".m4a"):
        return check_ffmpeg(file_path)
    else:
        return "Unsupported format"

def main(xlsx_path):
    if not os.path.isfile(xlsx_path):
        print("Excel file not found.")
        sys.exit(1)

    df = pd.read_excel(xlsx_path, header=None)
    file_paths = df.iloc[:, 0].dropna().tolist()

    total = len(file_paths)
    log(f"\n--- Audio File Health Check from Excel ---")
    log(f"Loaded {total} paths from {xlsx_path}")
    log(f"Started: {datetime.datetime.now()}\n")

    errors = 0
    for idx, path in enumerate(file_paths, 1):
        path = str(path).strip()
        if not os.path.isfile(path):
            log(f"[MISSING] {path}")
            errors += 1
            continue

        result = check_file(path)
        if result == "OK":
            log(f"[OK] {path}")
        else:
            log(f"[ERROR] {path} -> {result}")
            errors += 1

    log(f"\nChecked {total} files, found {errors} issues.")
    log(f"Completed: {datetime.datetime.now()}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 audio_health_check_from_xlsx.py Corrupt.xlsx")
        sys.exit(1)
    if os.path.exists(LOG_PATH):
        os.remove(LOG_PATH)
    main(sys.argv[1])
