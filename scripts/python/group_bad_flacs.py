#!/usr/bin/env python3
import csv
import json
from pathlib import Path

# ============================================================
# INPUT / OUTPUT PATHS
# ============================================================
BAD = Path("artifacts/reports/canonical_bad_flac_only.csv")
OUTDIR = Path("artifacts/reports/canonical_bad_flac_groups")
SUMMARY = OUTDIR / "summary.txt"

# ============================================================
# PREP OUTPUT
# ============================================================
OUTDIR.mkdir(parents=True, exist_ok=True)

if not BAD.exists():
    raise SystemExit(f"ERROR: missing input file: {BAD}")

# ============================================================
# LOAD BAD FLACS, SKIP HEADER ROW SAFELY
# ============================================================
rows = []
with BAD.open("r", encoding="utf8") as f:
    r = csv.reader(f)
    first = True
    for row in r:
        # Skip header if detected
        if first:
            first = False
            if "path" in row[0].lower() or "health" in row[1].lower():
                continue

        if len(row) < 3:
            continue

        path, score, info = row

        # Skip non-numeric score values
        try:
            score_f = float(score)
        except:
            continue

        # Parse info dict
        try:
            info_dict = json.loads(info.replace("'", '"'))
        except:
            info_dict = {"parse_error": info}

        rows.append((path, score_f, info_dict))

print(f"Loaded {len(rows)} problematic FLAC rows")

# ============================================================
# CATEGORY BUCKETS
# ============================================================
cats = {
    "not_flac": [],
    "unreadable": [],
    "ffprobe_error": [],
    "no_audio_params": [],
    "zero_size": [],
    "md5_fail": [],
    "tags_missing": [],
    "duration_zero": [],
    "samplerate_zero": [],
    "channels_zero": [],
    "bitdepth_zero": [],
    "unclassified": []
}

# ============================================================
# CLASSIFICATION LOGIC
# ============================================================
for path, score, info in rows:
    exists = info.get("exists")
    readable = info.get("readable")
    is_flac = info.get("is_flac")
    size = info.get("size")
    dur = info.get("duration")
    sr = info.get("sample_rate")
    ch = info.get("channels")
    bd = info.get("bit_depth")
    tags_ok = info.get("tags_ok")
    md5_ok = info.get("md5_ok")

    # ffprobe detection
    ff_err = "ffprobe" in json.dumps(info).lower()

    # Classification rules
    if exists and readable and not is_flac:
        cats["not_flac"].append(path)
        continue

    if not readable:
        cats["unreadable"].append(path)
        continue

    if ff_err:
        cats["ffprobe_error"].append(path)
        continue

    if size == 0:
        cats["zero_size"].append(path)
        continue

    if dur in (None, 0):
        cats["duration_zero"].append(path)
        continue

    if sr in (None, 0):
        cats["samplerate_zero"].append(path)
        continue

    if ch in (None, 0):
        cats["channels_zero"].append(path)
        continue

    if bd in (None, 0):
        cats["bitdepth_zero"].append(path)
        continue

    if md5_ok is False:
        cats["md5_fail"].append(path)
        continue

    if tags_ok is False:
        cats["tags_missing"].append(path)
        continue

    if any(x is None for x in (dur, sr, ch, bd)):
        cats["no_audio_params"].append(path)
        continue

    cats["unclassified"].append(path)

# ============================================================
# WRITE OUTPUT FILES
# ============================================================
for category, paths in cats.items():
    outfile = OUTDIR / f"{category}.txt"
    with outfile.open("w", encoding="utf8") as f:
        for p in paths:
            f.write(p + "\n")

# ============================================================
# SUMMARY
# ============================================================
with SUMMARY.open("w", encoding="utf8") as f:
    total = len(rows)
    f.write(f"Total problematic FLACs analyzed: {total}\n\n")
    for cat, paths in cats.items():
        f.write(f"{cat}: {len(paths)}\n")

print(f"Wrote grouped diagnostics to: {OUTDIR}")
print(f"Summary saved to: {SUMMARY}")
