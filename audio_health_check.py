#!/usr/bin/env python3
import os
import subprocess
import sys
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

# --- CONFIGURATION ---
SUPPORTED_EXTS = ('.flac', '.wav', '.aiff', '.aif', '.m4a')
LOG_PATH = os.path.expanduser("~/audio_health_check_log.txt")
MAX_WORKERS = os.cpu_count() or 4

# --- THREADING SETUP ---
lock = Lock()

def log(message):
    with lock:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(message + "\n")
        print(message)

# --- FILE CHECK FUNCTIONS ---
def check_flac(file_path):
    try:
        result = subprocess.run(
            ["flac", "-t", file_path],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            return "OK"
        else:
            return result.stderr.strip() or "FLAC check failed"
    except FileNotFoundError:
        return "flac binary not found (install via Homebrew: brew install flac)"

def check_ffmpeg(file_path):
    try:
        result = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", file_path, "-f", "null", "-"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0 and not result.stderr.strip():
            return "OK"
        else:
            return result.stderr.strip() or "FFmpeg decoding errors"
    except FileNotFoundError:
        return "ffmpeg binary not found (install via Homebrew: brew install ffmpeg)"

def check_file(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".flac":
        return check_flac(file_path)
    elif ext in (".wav", ".aiff", ".aif", ".m4a"):
        return check_ffmpeg(file_path)
    else:
        return "Unsupported format"

# --- MAIN WORKER FUNCTION ---
def process_file(file_path):
    result = check_file(file_path)
    if result == "OK":
        log(f"[OK] {file_path}")
        return False
    else:
        log(f"[ERROR] {file_path} -> {result}")
        return True

# --- MAIN ROUTINE ---
def main(root_dir):
    start_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log(f"\n--- Audio File Health Check started {start_time} ---")
    log(f"Root directory: {root_dir}")
    
    files_to_check = []
    for dirpath, _, filenames in os.walk(root_dir):
        for name in filenames:
            if name.lower().endswith(SUPPORTED_EXTS):
                files_to_check.append(os.path.join(dirpath, name))

    total = len(files_to_check)
    log(f"Found {total} supported audio files.\n")

    errors = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_file, f): f for f in files_to_check}
        for future in as_completed(futures):
            if future.result():
                errors += 1

    log(f"\nChecked {total} files, found {errors} issues.")
    end_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log(f"--- Completed {end_time} ---")

# --- ENTRY POINT ---
if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 audio_health_check_mt.py /path/to/music")
        sys.exit(1)
    target_dir = sys.argv[1]
    if not os.path.isdir(target_dir):
        print("Error: provided path is not a directory")
        sys.exit(1)
    if os.path.exists(LOG_PATH):
        os.remove(LOG_PATH)
    main(target_dir)