#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
consolidate_audio_artifacts.py
Consolidate existing audio dedupe/corruption artifacts into one actionable report.

What it ingests (recursively from --artifacts-root):
  - audio_dedupe_*/index.tsv, report.csv, report.txt
  - *dupes*_groups.tsv, music_dupes_groups.tsv, dupes_only.txt, dupes.json, music_dupes.json
  - rad_all_dupes*.tsv
  - flac_hashes.tsv, flaccindex_paths*.csv
  - corrupt_*.csv, corrupt_*.txt, flac_native_failures*.txt, flac_permanent_failures*.txt
  - quarantine_health_*.csv, quarantine_verify_*.tsv

Tolerates varied headers: path/file/rel_path, size/bytes, content_hash/sha1/sha256,
duration/duration_seconds/length, codec/codec_name, corrupt/bad/error.

Outputs (./artifact_consolidation_out_<timestamp>):
  - consolidated.csv        : one row per referenced file (current existence/size included)
  - duplicates.csv          : exact dups by reported hash with keep/candidate flags
  - similar_candidates.csv  : near-dupes (same ext & size & ~duration with differing/missing hashes)
  - corrupt.csv             : files flagged corrupt with reasons (merged)
  - SUMMARY.txt             : totals and next steps
  - dedupe_quarantine.sh    : reviewable mv plan to _quarantine/ (only with --write-plan)

This script DOES NOT re-hash or re-probe media; it consolidates prior results.
"""

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Set

# -------------------- Config & helpers

AUDIO_EXTS: Set[str] = {
    ".flac",".mp3",".m4a",".aac",".wav",".aiff",".aif",".ogg",".opus",".wma",".alac",
    ".wv",".ape",".dsf",".dff",".mka"
}

# canonical header synonyms
SYN: Dict[str, Set[str]] = {
    "path": {"path","file","filepath","file_path","fullpath","full_path","abs_path"},
    "rel_path": {"rel_path","relative_path","relpath"},
    "size_bytes": {"size_bytes","bytes","size","filesize"},
    "content_hash": {"content_hash","sha1","sha256","blake3","hash"},
    "duration_seconds": {"duration_seconds","duration","length","secs","seconds"},
    "codec_name": {"codec_name","codec","format"},
    "corrupt": {"corrupt","bad","is_corrupt","broken","undecodable","failed"},
    "corrupt_reason": {"corrupt_reason","error","reason","note","message","why"},
}

# fast-prune directories that explode traversal time
PRUNE_DIR_BASENAMES = {
    ".git",".Trash",".Trashes",".Spotlight-V100",".fseventsd","__MACOSX",
    "node_modules","Cache","Caches","tmp","temp",".venv","venv","venvs",
    "Photos Library.photoslibrary","iPhoto Library.photolibrary"
}
PRUNE_DIR_CONTAINS = (
    "/Library/CloudStorage/",
    "/Library/Mobile Documents/",
    "/Library/Application Support/FileProvider/",
)

# filename/path patterns we actually care about (based on your tree)
ARTIFACT_FILE_PATTERNS: List[re.Pattern] = [
    re.compile(r".*/audio_dedupe_[^/]+/(index\.tsv|report\.(csv|txt))$", re.I),
    re.compile(r".*/(music_)?dupes?_groups\.tsv$", re.I),
    re.compile(r".*/rad_all_dupes.*\.tsv$", re.I),
    re.compile(r".*/flac_hashes\.tsv$", re.I),
    re.compile(r".*/flaccindex_paths.*\.csv$", re.I),
    re.compile(r".*/corrupt_.*\.(csv|txt)$", re.I),
    re.compile(r".*/flac_(native_)?failures.*\.txt$", re.I),
    re.compile(r".*/flac_permanent_failures.*\.txt$", re.I),
    re.compile(r".*/quarantine_health_.*\.csv$", re.I),
    re.compile(r".*/quarantine_verify_.*\.tsv$", re.I),
    re.compile(r".*/dupes_only\.txt$", re.I),
    re.compile(r".*/(dupes|music_dupes)\.json$", re.I),
]

def human_bytes(n: int) -> str:
    if n is None:
        return ""
    units = ["B","KB","MB","GB","TB","PB"]
    i = 0
    x = float(n)
    while i < len(units)-1 and x >= 1024:
        x /= 1024.0
        i += 1
    return f"{x:.2f} {units[i]}"

def shell_quote(path: str) -> str:
    return "'" + path.replace("'", "'\"'\"'") + "'"

def sniff_delimiter(sample: str) -> str:
    if "\t" in sample:
        return "\t"
    for d in [",",";","|"]:
        if d in sample:
            return d
    return ","

def canon_map(header: List[str]) -> Dict[str, Optional[str]]:
    canon = {k: None for k in SYN}
    lower = [h.strip().lower() for h in header]
    for i, h in enumerate(lower):
        for key, alts in SYN.items():
            if h in alts and canon[key] is None:
                canon[key] = header[i]  # keep original case
    return canon

def load_table(path: Path) -> List[Dict[str, str]]:
    text = path.read_text(errors="replace")
    # JSON
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(text)
            rows: List[Dict[str, str]] = []
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        rows.append({k: str(v) for k, v in item.items()})
            elif isinstance(data, dict):
                # common nested forms
                for key in ("rows","data","items"):
                    if key in data and isinstance(data[key], list):
                        for item in data[key]:
                            if isinstance(item, dict):
                                rows.append({k: str(v) for k, v in item.items()})
                        break
            return rows
        except Exception:
            return []
    # Plain text vs delimited
    if path.suffix.lower() == ".txt":
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            return []
        # If first lines look delimited (header etc.), fall through to CSV/TSV
        head = "\n".join(lines[:3]).lower()
        if ("\t" in head) or ("," in head) or ("path" in head and ":" in head):
            pass
        else:
            return [{"path": ln} for ln in lines]

    # CSV/TSV
    sample = "\n".join(text.splitlines()[:5])
    delim = sniff_delimiter(sample)
    try:
        rd = csv.DictReader(text.splitlines(), delimiter=delim)
        return [{(k.strip() if k else ""): (v if v is not None else "") for k, v in row.items()} for row in rd]
    except Exception:
        return []

def to_int(x) -> Optional[int]:
    try:
        if x in ("","N/A",None):
            return None
        return int(float(str(x).strip()))
    except Exception:
        return None

def to_float(x) -> Optional[float]:
    try:
        if x in ("","N/A",None):
            return None
        return float(str(x).strip())
    except Exception:
        return None

def ext_of(path: str) -> str:
    return Path(path).suffix.lower()

# -------------------- Artifact discovery (fast, pruned, chatty)

def find_artifact_files(root: Path, verbose: bool = True) -> List[Path]:
    root = root.expanduser()
    if not root.exists():
        return []
    found: List[Path] = []
    scanned_dirs = 0

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        scanned_dirs += 1
        # prune by basename
        for d in list(dirnames):
            if d in PRUNE_DIR_BASENAMES:
                dirnames.remove(d)
        # prune by substring
        pruned = []
        for d in list(dirnames):
            full = os.path.join(dirpath, d)
            for frag in PRUNE_DIR_CONTAINS:
                if frag in full:
                    pruned.append(d)
                    break
        for d in pruned:
            if d in dirnames:
                dirnames.remove(d)

        # progress every 250 dirs
        if verbose and (scanned_dirs % 250 == 0):
            print(f"[i] Scanned {scanned_dirs} dirs… found {len(found)} artifacts so far", flush=True)

        # match files
        for fn in filenames:
            if fn.startswith("._"):
                continue
            p = Path(dirpath) / fn
            s = str(p)
            for pat in ARTIFACT_FILE_PATTERNS:
                if pat.match(s):
                    found.append(p)
                    break

    # de-dup while preserving order
    out: List[Path] = []
    seen: Set[Path] = set()
    for p in found:
        rp = p.resolve()
        if rp not in seen and rp.is_file():
            seen.add(rp)
            out.append(rp)
    return out

# -------------------- Main consolidation

def main():
    ap = argparse.ArgumentParser(description="Consolidate previous audio dedupe/corruption artifacts.")
    ap.add_argument("--artifacts-root", default=str(Path.home()),
                    help="Where to search (default: ~). Use a tighter dir for speed (e.g., $HOME/dev).")
    ap.add_argument("--focus-root", default="",
                    help="Optional path prefix to filter rows (e.g., /Volumes/dotad/MUSIC).")
    ap.add_argument("--similar-tolerance-sec", type=float, default=0.5,
                    help="Duration bucket for near-dupe grouping (default 0.5s).")
    ap.add_argument("--write-plan", action="store_true",
                    help="Write dedupe_quarantine.sh to move dupes to _quarantine/ (no deletes).")
    ap.add_argument("--save-dir", default="",
                    help="Output dir (default: ./artifact_consolidation_out_<timestamp>)")
    ap.add_argument("--quiet-find", action="store_true", help="Suppress directory-scan progress logs.")
    args = ap.parse_args()

    arte_root = Path(args.artifacts_root).expanduser()
    focus_root = Path(args.focus_root).resolve() if args.focus_root else None

    if not arte_root.exists():
        print(f"ERROR: artifacts root not found: {arte_root}", file=sys.stderr)
        sys.exit(2)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir = Path(args.save_dir) if args.save_dir else Path(f"./artifact_consolidation_out_{ts}")
    outdir.mkdir(parents=True, exist_ok=True)

    # Discover artifacts
    print(f"[i] Searching under: {arte_root}")
    files = find_artifact_files(arte_root, verbose=not args.quiet_find)
    if not files:
        print("No artifact files found. Tighten/adjust --artifacts-root or patterns.", file=sys.stderr)
        sys.exit(3)

    print(f"[i] Found {len(files)} artifact files to ingest.")
    for i, f in enumerate(files, 1):
        print(f"  - [{i}/{len(files)}] {f}", flush=True)

    # Consolidate by absolute path
    records: Dict[str, Dict[str, object]] = {}   # key = path string

    def get_rec(path_str: str) -> Optional[Dict[str, object]]:
        if not path_str:
            return None
        p = Path(path_str).expanduser()
        s = str(p) if p.is_absolute() else str(p)
        rec = records.get(s)
        if rec is None:
            rec = {
                "path": s,
                "ext": ext_of(s),
                "reported_size": None,
                "reported_hash": None,
                "reported_duration": None,
                "reported_codec": None,
                "corrupt": 0,
                "corrupt_reason": "",
                "sources": set(),
            }
            records[s] = rec
        return rec

    # Ingest each artifact
    for idx, f in enumerate(files, 1):
        print(f"[i] Ingesting {idx}/{len(files)}: {f}", flush=True)
        try:
            rows = load_table(f)
            print(f"    -> rows: {len(rows)}", flush=True)
            if not rows:
                continue
            header = list(rows[0].keys())
            keymap = canon_map(header)
            file_hint_corrupt = bool(re.search(r"(corrupt|failure|errors?)", f.name, re.I))

            for row in rows:
                # path
                p = None
                if keymap["path"]:
                    p = row.get(keymap["path"])
                elif "path" in row:
                    p = row["path"]
                elif "file" in row:
                    p = row["file"]
                if not p or str(p).strip() == "":
                    continue

                rec = get_rec(p)
                if rec is None:
                    continue

                rec["sources"].add(str(f))

                # size/hash/duration/codec
                if keymap["size_bytes"]:
                    sz = to_int(row.get(keymap["size_bytes"]))
                    if sz and not rec["reported_size"]:
                        rec["reported_size"] = sz
                if keymap["content_hash"]:
                    h = row.get(keymap["content_hash"])
                    if h and not rec["reported_hash"]:
                        rec["reported_hash"] = str(h).strip()
                if keymap["duration_seconds"]:
                    d = to_float(row.get(keymap["duration_seconds"]))
                    if d is not None and rec["reported_duration"] is None:
                        rec["reported_duration"] = d
                if keymap["codec_name"]:
                    c = row.get(keymap["codec_name"])
                    if c and not rec["reported_codec"]:
                        rec["reported_codec"] = str(c)

                # corruption flags
                flagged = False
                if keymap["corrupt"]:
                    v = row.get(keymap["corrupt"])
                    if str(v).strip().lower() in {"1","true","yes","y"}:
                        flagged = True
                if file_hint_corrupt:
                    flagged = True
                if flagged:
                    rec["corrupt"] = 1
                    reason = ""
                    if keymap["corrupt_reason"]:
                        reason = str(row.get(keymap["corrupt_reason"]) or "").strip()
                    if not reason:
                        for k in ("error","reason","message","note","why"):
                            if k in row and row[k]:
                                reason = str(row[k])
                                break
                    if rec["corrupt_reason"]:
                        if reason and reason not in rec["corrupt_reason"]:
                            rec["corrupt_reason"] += f" | {reason}"
                    else:
                        rec["corrupt_reason"] = reason

        except Exception as e:
            print(f"[w] Failed to parse {f}: {e}", file=sys.stderr)

    # materialize
    all_rows = list(records.values())

    # existence & current size
    for r in all_rows:
        p = Path(r["path"]).expanduser()
        if p.exists():
            r["exists_now"] = 1
            try:
                r["current_size"] = p.stat().st_size
            except Exception:
                r["current_size"] = None
        else:
            r["exists_now"] = 0
            r["current_size"] = None

    # optional filter to focus-root
    if focus_root:
        prefix = str(focus_root)
        all_rows = [r for r in all_rows if str(r["path"]).startswith(prefix)]

    if not all_rows:
        print("No rows after filtering. Check --focus-root or artifacts.", file=sys.stderr)
        sys.exit(4)

    # write consolidated.csv
    consolidated = sorted(all_rows, key=lambda r: (-(r["exists_now"]), r["path"]))
    cons_csv = outdir / "consolidated.csv"
    with cons_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "path","ext","exists_now","current_size","reported_size","reported_hash",
            "reported_duration","reported_codec","corrupt","corrupt_reason","sources"
        ])
        w.writeheader()
        for r in consolidated:
            w.writerow({
                "path": r["path"],
                "ext": r["ext"],
                "exists_now": r["exists_now"],
                "current_size": r.get("current_size") or "",
                "reported_size": r.get("reported_size") or "",
                "reported_hash": r.get("reported_hash") or "",
                "reported_duration": r.get("reported_duration") if r.get("reported_duration") is not None else "",
                "reported_codec": r.get("reported_codec") or "",
                "corrupt": r.get("corrupt") or 0,
                "corrupt_reason": r.get("corrupt_reason") or "",
                "sources": ";".join(sorted(r["sources"]))[:1000],
            })
    print(f"[+] Wrote {cons_csv}")

    # exact duplicates by hash
    by_hash: Dict[str, List[Dict[str, object]]] = {}
    for r in consolidated:
        h = r.get("reported_hash")
        if h:
            by_hash.setdefault(h, []).append(r)

    dup_groups: List[Dict[str, object]] = []
    group_id = 0
    reclaimable = 0
    quarantine_moves: List[Tuple[str, str]] = []

    def dur_val(rec) -> float:
        try:
            return float(rec.get("reported_duration") or 0.0)
        except Exception:
            return 0.0

    for h, recs in by_hash.items():
        if len(recs) < 2:
            continue
        group_id += 1
        # keep policy: prefer non-corrupt, then longer duration, then shorter path
        recs_sorted = sorted(recs, key=lambda r: (r.get("corrupt") or 0, -dur_val(r), len(r["path"])))
        keep = recs_sorted[0]
        size_for_reclaim = keep.get("current_size") or keep.get("reported_size") or 0

        for i, rec in enumerate(recs_sorted):
            dup_groups.append({
                "group_id": group_id,
                "content_hash": h,
                "keep": 1 if i == 0 else 0,
                "path": rec["path"],
                "size_bytes": rec.get("current_size") or rec.get("reported_size") or "",
                "duration_seconds": rec.get("reported_duration") or "",
                "codec_name": rec.get("reported_codec") or "",
                "corrupt": rec.get("corrupt") or 0,
            })
            if i != 0 and size_for_reclaim:
                reclaimable += int(size_for_reclaim)
                rel = os.path.relpath(rec["path"], start=str(focus_root)) if focus_root else os.path.basename(rec["path"])
                dest = outdir / "_quarantine" / rel
                quarantine_moves.append((rec["path"], str(dest)))

    dups_csv = outdir / "duplicates.csv"
    if dup_groups:
        with dups_csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=[
                "group_id","content_hash","keep","path","size_bytes","duration_seconds","codec_name","corrupt"
            ])
            w.writeheader()
            for row in dup_groups:
                w.writerow(row)
        print(f"[+] Wrote {dups_csv}")
    else:
        print("[i] No exact duplicates by hash found in artifacts (or no hashes present).")

    # near-duplicates: same ext & size & duration bucket, with different/missing hashes
    def bucket(d: Optional[float], tol: float) -> Optional[int]:
        if d is None or d == "":
            return None
        try:
            return int(round(float(d)/tol))
        except Exception:
            return None

    index_sim: Dict[Tuple[str, int, Optional[int]], List[Dict[str, object]]] = {}
    for r in consolidated:
        size = r.get("current_size") or r.get("reported_size")
        if not size:
            continue
        b = bucket(r.get("reported_duration"), args.similar_tolerance_sec)
        key = (r["ext"], int(size), b)
        index_sim.setdefault(key, []).append(r)

    fuzzy_rows: List[Dict[str, object]] = []
    for key, recs in index_sim.items():
        if len(recs) < 2:
            continue
        hashes = {rec.get("reported_hash") for rec in recs}
        if len(hashes) == 1 and None not in hashes and "" not in hashes:
            continue
        for rec in sorted(recs, key=lambda x: x["path"]):
            fuzzy_rows.append({
                "ext": key[0],
                "size_bytes": key[1],
                "duration_bucket": key[2],
                "duration_seconds": rec.get("reported_duration") or "",
                "path": rec["path"],
                "reported_hash": rec.get("reported_hash") or "",
            })

    sim_csv = outdir / "similar_candidates.csv"
    if fuzzy_rows:
        with sim_csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=[
                "ext","size_bytes","duration_bucket","duration_seconds","path","reported_hash"
            ])
            w.writeheader()
            for row in fuzzy_rows:
                w.writerow(row)
        print(f"[+] Wrote {sim_csv}")
    else:
        print("[i] No near-duplicate candidates by size+~duration found (in artifacts).")

    # corruption list
    corrupt_rows = [r for r in consolidated if (r.get("corrupt") or 0) == 1]
    corrupt_csv = outdir / "corrupt.csv"
    if corrupt_rows:
        with corrupt_csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=[
                "path","exists_now","current_size","reported_size",
                "reported_hash","reported_duration","reported_codec","corrupt_reason"
            ])
            w.writeheader()
            for r in corrupt_rows:
                w.writerow({
                    "path": r["path"],
                    "exists_now": r["exists_now"],
                    "current_size": r.get("current_size") or "",
                    "reported_size": r.get("reported_size") or "",
                    "reported_hash": r.get("reported_hash") or "",
                    "reported_duration": r.get("reported_duration") or "",
                    "reported_codec": r.get("reported_codec") or "",
                    "corrupt_reason": r.get("corrupt_reason") or "",
                })
        print(f"[+] Wrote {corrupt_csv}")
    else:
        print("[i] No corrupt rows flagged in artifacts.")

    # SUMMARY
    total_rows = len(consolidated)
    total_bytes = sum(int(r.get("current_size") or r.get("reported_size") or 0) for r in consolidated)
    num_dupe_files = sum(1 for g in dup_groups if g["keep"] == 0)

    summary_lines: List[str] = []
    summary_lines.append(f"Artifacts root: {arte_root}")
    summary_lines.append(f"Focus root    : {focus_root if focus_root else '(none)'}")
    summary_lines.append(f"Rows consolidated: {total_rows}")
    summary_lines.append(f"Total size (current/reported): {human_bytes(total_bytes)}")
    summary_lines.append(f"Exact duplicates by hash: {num_dupe_files} files across {len(set(g['group_id'] for g in dup_groups)) if dup_groups else 0} groups")
    summary_lines.append(f"Reclaimable if quarantining dup candidates: {human_bytes(reclaimable)}")
    summary_lines.append(f"Near-duplicate candidate rows: {len(fuzzy_rows)}")
    summary_lines.append(f"Corrupt flagged: {len(corrupt_rows)}")
    summary_lines.append("")
    summary_lines.append("Next steps:")
    if dup_groups:
        summary_lines.append("  1) Review duplicates.csv; confirm the keep=1 choice per group.")
        if args.write_plan:
            summary_lines.append("  2) Inspect dedupe_quarantine.sh; it only moves to _quarantine/ for review.")
            summary_lines.append("  3) After verification, remove quarantined dupes once satisfied.")
        else:
            summary_lines.append("  2) Re-run with --write-plan to generate a reviewable quarantine script.")
    else:
        summary_lines.append("  1) If no exact dupes, review similar_candidates.csv for size≈duration matches.")
    (outdir / "SUMMARY.txt").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
    print(f"[+] Wrote {outdir/'SUMMARY.txt'}")

    # Quarantine move plan
    if args.write_plan and dup_groups:
        sh = outdir / "dedupe_quarantine.sh"
        lines = []
        lines.append("#!/usr/bin/env bash")
        lines.append("set -euo pipefail")
        lines.append(f'QUAR={shell_quote(str(outdir / "_quarantine"))}')
        lines.append('mkdir -p "$QUAR"')
        lines.append("")
        for src, dest in quarantine_moves:
            dest_dir = os.path.dirname(dest)
            lines.append(f"mkdir -p {shell_quote(dest_dir)}")
            lines.append(f"if [ -e {shell_quote(dest)} ]; then")
            lines.append(f"  echo 'SKIP (already exists): {shell_quote(dest)}'")
            lines.append("else")
            lines.append(f"  mv -v {shell_quote(src)} {shell_quote(dest)} || true")
            lines.append("fi")
        sh.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.chmod(sh, 0o755)
        print(f"[+] Wrote {sh}")

if __name__ == "__main__":
    # Ensure unbuffered prints if user forgot PYTHONUNBUFFERED=1
    try:
        main()
    except KeyboardInterrupt:
        print("\n[!] Interrupted by user.", file=sys.stderr)
        sys.exit(130)
