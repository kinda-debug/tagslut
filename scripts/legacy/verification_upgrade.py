#!/usr/bin/env python3
import csv
import subprocess
import os
from pathlib import Path

INPUT_CSV = "artifacts/reports/matches_upgrade_candidates.csv"
OUTPUT_CSV = "artifacts/reports/upgrade_verified.csv"
LOG_CSV = "artifacts/reports/upgrade_verification_log.csv"

def get_duration(path: str):
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "a:0",
                "-show_entries", "stream=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                path
            ],
            capture_output=True,
            text=True,
        )
        out = result.stdout.strip()
        return float(out) if out else None
    except Exception:
        return None

def get_flac_stream_md5(path: str):
    if not path.lower().endswith(".flac"):
        return ""
    try:
        result = subprocess.run(
            ["metaflac", "--show-md5sum", path],
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except Exception:
        return ""

def classify(lib_path, rec_path, similarity):
    entry = {
        "library_path": lib_path,
        "recovered_path": rec_path,
        "similarity": similarity,
        "lib_duration": "",
        "rec_duration": "",
        "duration_delta": "",
        "lib_md5": "",
        "rec_md5": "",
        "status": "",
    }

    if not os.path.exists(rec_path):
        entry["status"] = "RECOVERED_NOT_FOUND"
        return entry

    if not os.path.exists(lib_path):
        entry["status"] = "LIBRARY_NOT_FOUND"
        return entry

    lib_dur = get_duration(lib_path)
    rec_dur = get_duration(rec_path)
    entry["lib_duration"] = lib_dur
    entry["rec_duration"] = rec_dur

    if lib_dur is None or rec_dur is None:
        entry["status"] = "CANNOT_READ_DURATION"
        return entry

    entry["duration_delta"] = rec_dur - lib_dur

    if abs(rec_dur - lib_dur) > 3.0:
        entry["status"] = "DURATION_MISMATCH"
        return entry

    lib_md5 = get_flac_stream_md5(lib_path)
    rec_md5 = get_flac_stream_md5(rec_path)
    entry["lib_md5"] = lib_md5
    entry["rec_md5"] = rec_md5

    if lib_md5 and rec_md5:
        entry["status"] = (
            "OK_IDENTICAL_AUDIO" if lib_md5 == rec_md5 else "OK_DIFFERENT_AUDIO"
        )
        return entry

    entry["status"] = "OK_NO_MD5_AVAILABLE"
    return entry

def main():
    Path("artifacts/reports").mkdir(parents=True, exist_ok=True)
    with open(INPUT_CSV, "r", encoding="utf8") as f:
        rows = list(csv.DictReader(f))

    verified = []
    log_rows = []

    for r in rows:
        out = classify(r["library_path"], r["recovered_path"], float(r["similarity"]))
        log_rows.append(out)
        if out["status"].startswith("OK"):
            verified.append(out)

    with open(OUTPUT_CSV, "w", encoding="utf8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=log_rows[0].keys())
        w.writeheader()
        for x in verified:
            w.writerow(x)

    with open(LOG_CSV, "w", encoding="utf8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=log_rows[0].keys())
        w.writeheader()
        for x in log_rows:
            w.writerow(x)

    print("Verified upgrades written:", OUTPUT_CSV)
    print("Full log written:", LOG_CSV)
    print("Verified count:", len(verified))
    print("Total processed:", len(rows))

if __name__ == "__main__":
    main()
