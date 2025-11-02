#!/usr/bin/env python3
"""
Combine and clean `found_candidates_*` outputs produced under a directory (e.g. /tmp/found_candidates_dir).

Features:
- Reads all files matching `found_candidates_*.txt` in an input dir.
- Tries multiple heuristics to extract full-path candidates from each line:
  * If the line contains a tab, take the last tab-separated field.
  * Split on runs of 2+ spaces and take tokens that start with '/'.
  * Fallback to last whitespace-separated token.
- Optionally filters by existence and by file extensions (audio).
- Deduplicates preserving order and writes an output file.
- Optionally maps basenames from a `--basenames` file and writes matches to another file.

Usage examples:

# produce a combined, deduped list of existing FLAC/M4A/MP3 files
python3 scripts/combine_found_candidates.py \
  --indir /tmp/found_candidates_dir \
  --out /tmp/found_candidates.txt \
  --require-exists --ext flac,m4a,mp3

# map basenames to found full paths and write only matches
python3 scripts/combine_found_candidates.py \
  --indir /tmp/found_candidates_dir \
  --basenames /tmp/unhealthy_not_found_basenames.txt \
  --out-matches /tmp/to_repair_candidates.txt \
  --require-exists --ext flac

"""

import argparse
import os
import re
from pathlib import Path
from collections import OrderedDict


def extract_paths_from_line(line: str):
    line = line.rstrip("\n")
    if not line:
        return []

    # 1) If tab separated, take last column
    if "\t" in line:
        parts = line.split("\t")
        last = parts[-1].strip()
        if last:
            return [last]

    # 2) split on runs of 2+ spaces (common when printing pretty columns)
    tokens = re.split(r"\s{2,}", line.strip())
    results = []
    for tok in tokens:
        tok = tok.strip()
        if not tok:
            continue
        if tok.startswith("/"):
            results.append(tok)
            continue
        # if token contains an absolute path somewhere, extract from first '/'
        idx = tok.find("/")
        if idx != -1:
            results.append(tok[idx:].strip())

    if results:
        return results

    # 3) fallback: last whitespace-separated token
    ws = line.strip().split()
    if ws:
        last = ws[-1].strip()
        return [last]

    return []


def canonicalize(path: str) -> str:
    # Expand tilde and normalize; do not resolve symlinks to avoid surprises
    return os.path.normpath(os.path.expanduser(path))


def read_all_candidates(indir: Path):
    out = []
    for p in sorted(indir.glob("found_candidates_*.txt")):
        try:
            with p.open("r", errors="replace") as fh:
                for line in fh:
                    for candidate in extract_paths_from_line(line):
                        if candidate:
                            out.append(candidate)
        except Exception as e:
            print(f"warning: failed reading {p}: {e}")
    return out


def filter_and_dedupe(candidates, require_exists=False, exts=None):
    seen = OrderedDict()
    for c in candidates:
        c2 = canonicalize(c)
        # If path contains concatenated duplicates (e.g. multiple paths jammed together) keep it — user review will catch
        if exts:
            if not any(c2.lower().endswith('.' + x.lower()) for x in exts):
                continue
        if require_exists and not os.path.exists(c2):
            continue
        if c2 not in seen:
            seen[c2] = True
    return list(seen.keys())


def map_basenames(basenames_path: Path, candidates_list):
    # basenames file: one basename per line (e.g. "Artist - Title.flac")
    # returns mapping: basename -> [paths...]
    basename_to_paths = {}
    # build quick index by basename
    idx = {}
    for p in candidates_list:
        b = os.path.basename(p)
        idx.setdefault(b, []).append(p)
    with basenames_path.open('r', errors='replace') as fh:
        for line in fh:
            b = line.strip()
            if not b:
                continue
            # exact basename match first
            matches = idx.get(b)
            if matches:
                basename_to_paths[b] = matches
                continue
            # fallback: substring match anywhere in candidate basename
            lower = b.lower()
            matches = [p for name, paths in idx.items() for p in paths if lower in name.lower()]
            if matches:
                basename_to_paths[b] = matches
            else:
                basename_to_paths[b] = []
    return basename_to_paths


def write_lines(path: Path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w') as fh:
        for l in lines:
            fh.write(l + '\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--indir', required=True, help='Directory containing found_candidates_*.txt')
    ap.add_argument('--out', help='Write combined candidate paths (one per line)')
    ap.add_argument('--out-matches', help='Write matched candidate paths when --basenames is provided (one per line)')
    ap.add_argument('--basenames', help='File with basenames (one per line) to map to candidate paths')
    ap.add_argument('--require-exists', action='store_true', help='Keep only paths that exist on disk')
    ap.add_argument('--ext', help='Comma-separated list of extensions to keep (e.g. flac,m4a,mp3)')
    args = ap.parse_args()

    indir = Path(args.indir)
    if not indir.is_dir():
        print(f"error: indir {indir} is not a directory")
        raise SystemExit(2)

    ext_list = None
    if args.ext:
        ext_list = [x.strip().lstrip('.') for x in args.ext.split(',') if x.strip()]

    raw = read_all_candidates(indir)
    print(f"read {len(raw)} raw tokens from {indir}")

    combined = filter_and_dedupe(raw, require_exists=args.require_exists, exts=ext_list)
    print(f"kept {len(combined)} candidate paths after filter+dedupe (require_exists={args.require_exists}, ext={ext_list})")

    if args.out:
        write_lines(Path(args.out), combined)
        print(f"wrote combined candidate list to {args.out}")

    if args.basenames:
        bm = map_basenames(Path(args.basenames), combined)
        total_matches = sum(len(v) for v in bm.values())
        print(f"mapped {len(bm)} basenames -> {total_matches} matched paths")
        if args.out_matches:
            # Write one matching path per line; keep order from `combined` for determinism
            ordered = []
            # Create mapping basename -> set for quick check
            for b, paths in bm.items():
                for p in paths:
                    ordered.append(p)
            # dedupe while preserving order
            deduped = []
            seen = set()
            for p in ordered:
                if p not in seen:
                    deduped.append(p)
                    seen.add(p)
            write_lines(Path(args.out_matches), deduped)
            print(f"wrote {len(deduped)} matched candidate paths to {args.out_matches}")
        else:
            # Print summary to stdout
            for b, paths in bm.items():
                print(f"{b}: {len(paths)} matches")


if __name__ == '__main__':
    main()
