#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv, os, subprocess, sys, hashlib
from pathlib import Path
from collections import defaultdict

SIMILAR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("./similar_candidates.csv")
ROOT    = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/Volumes/dotad/MUSIC")
OUTDIR  = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("./near_dupe_verify_out")
OUTDIR.mkdir(parents=True, exist_ok=True)

paths = []
if not SIMILAR.exists():
    print(f"ERROR: similar_candidates.csv not found at {SIMILAR}", file=sys.stderr); sys.exit(2)

# Load candidate paths (robust CSV parsing)
with SIMILAR.open(newline='', encoding='utf-8', errors='replace') as f:
    rd = csv.DictReader(f)
    if "path" not in rd.fieldnames:
        print("ERROR: CSV missing 'path' column.", file=sys.stderr); sys.exit(3)
    for row in rd:
        p = row.get("path", "").strip()
        if p: paths.append(p)

# Unique, existing only
uniq = []
seen = set()
for p in paths:
    if p in seen: continue
    seen.add(p)
    if Path(p).exists():
        uniq.append(p)

print(f"[i] Near-dupe rows: {len(paths)}; unique existing paths: {len(uniq)}")

# Compute content MD5 by decoding to PCM (codec/container agnostic)
def content_md5(path: str) -> str:
    # ffmpeg prints "MD5=xxxxxxxx..." to stdout when using -f md5 -
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-i", path, "-map", "a", "-f", "md5", "-"]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        line = out.decode("utf-8", "replace").strip()
        if line.startswith("MD5="): return line.split("=",1)[1].strip()
    except subprocess.CalledProcessError as e:
        # if decoding fails, mark as BAD:<sha1(file)> to isolate later
        try:
            h = hashlib.sha1(Path(path).read_bytes()).hexdigest()
            return f"BAD:{h}"
        except Exception:
            return "BAD:IO"
    return ""

rows = []
for i, p in enumerate(uniq, 1):
    try:
        st = os.stat(p)
        size = st.st_size
    except FileNotFoundError:
        size = ""
    print(f"[i] ({i}/{len(uniq)}) hashing audio content: {p}", flush=True)
    md5 = content_md5(p)
    rows.append({"path": p, "stream_md5": md5, "size_bytes": size})

# Write raw fingerprints
fp_csv = OUTDIR / "stream_md5.csv"
with fp_csv.open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["path","stream_md5","size_bytes"])
    w.writeheader()
    for r in rows: w.writerow(r)
print(f"[+] Wrote {fp_csv}")

# Group and pick keepers
by = defaultdict(list)
for r in rows:
    by[r["stream_md5"]].append(r)

dupes = []
move_plan = []
group_id = 0
for md5, recs in by.items():
    if not md5 or md5.startswith("BAD:"):  # undecodable or empty hash
        continue
    if len(recs) < 2:
        continue
    group_id += 1
    # Keeper policy: prefer shortest path (adjust if you have a canonical subtree)
    recs_sorted = sorted(recs, key=lambda x: (len(x["path"]), x["path"]))
    keep = recs_sorted[0]["path"]
    for i, r in enumerate(recs_sorted):
        dupes.append({
            "group_id": group_id,
            "stream_md5": md5,
            "keep": 1 if r["path"] == keep else 0,
            "path": r["path"],
            "size_bytes": r["size_bytes"],
        })
        if r["path"] != keep:
            rel = os.path.relpath(r["path"], start=str(ROOT)) if str(r["path"]).startswith(str(ROOT)) else os.path.basename(r["path"])
            dest = OUTDIR / "_quarantine_streammd5" / rel
            move_plan.append((r["path"], str(dest)))

dupes_csv = OUTDIR / "dupes_streammd5.csv"
with dupes_csv.open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["group_id","stream_md5","keep","path","size_bytes"])
    w.writeheader()
    for d in dupes: w.writerow(d)
print(f"[+] Wrote {dupes_csv}")

# Quarantine script
sh = OUTDIR / "dedupe_quarantine_streammd5.sh"
with sh.open("w", encoding="utf-8") as f:
    f.write("#!/usr/bin/env bash\nset -euo pipefail\n")
    f.write(f'QUAR="{(OUTDIR / "_quarantine_streammd5")}"\nmkdir -p "$QUAR"\n\n')
    for src, dest in move_plan:
        dd = os.path.dirname(dest)
        f.write(f'mkdir -p {dd!r}\n')
        f.write(f'[[ -e {dest!r} ]] || mv -v {src!r} {dest!r} || true\n')
print(f"[+] Wrote {sh}")
os.chmod(sh, 0o755)
