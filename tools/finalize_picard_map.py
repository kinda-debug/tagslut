#!/usr/bin/env python3
"""
Read source FLAC paths on stdin and print CSV lines:
src,dest

Dest is built by importing `dedupe.picard_path.build_picard_path` and prefixing
with provided DEST_ROOT.

Usage:
    cat canonical_paths.txt | tools/finalize_picard_map.py --dest-root /Volumes/COMMUNE/20_ACCEPTED

If metadata extraction fails, falls back to mirroring the /Volumes/COMMUNE/ relative path.
"""
import argparse
import shlex
import subprocess
import sys
import os
from typing import Dict, List

# Ensure repository root is on sys.path so `dedupe` package can be imported
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

try:
    from dedupe.picard_path import build_picard_path
except Exception:
    # attempt to import from top-level picard_path for backwards compatibility
    try:
        from picard_path import build_picard_path
    except Exception as e:
        print(f"FATAL: Could not import picard path builder: {e}", file=sys.stderr)
        sys.exit(2)


METACLAC_TAGS = [
    'ALBUMARTIST', 'ARTIST', 'ALBUM', 'DATE', 'ORIGINALYEAR', 'ORIGINALDATE',
    'TRACKNUMBER', 'TITLE', 'DISCNUMBER', 'TOTALDISCS'
]


def extract_tags(path: str) -> Dict[str, object]:
    tags = {}
    try:
        args = ['metaflac'] + [f'--show-tag={t}' for t in METACLAC_TAGS] + [path]
        out = subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL)
        for line in out.splitlines():
            if '=' not in line:
                continue
            k, v = line.split('=', 1)
            k = k.lower()
            # accumulate multi-valued tags into lists
            if k in tags:
                if isinstance(tags[k], list):
                    tags[k].append(v)
                else:
                    tags[k] = [tags[k], v]
            else:
                tags[k] = v
    except FileNotFoundError:
        # metaflac not installed; return empty to trigger fallback
        return {}
    except subprocess.CalledProcessError:
        # Could not read tags; return empty
        return {}
    return tags


def fallback_relpath(src: str) -> str:
    # If src is under /Volumes/COMMUNE/, mirror relative path; otherwise use basename
    base_root = '/Volumes/COMMUNE/'
    if src.startswith(base_root):
        return src[len(base_root) :]
    return os.path.basename(src)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--dest-root', required=True, help='Destination root (e.g., /Volumes/COMMUNE/20_ACCEPTED)')
    p.add_argument('--dry-run', action='store_true', help='Only print planned mappings')
    args = p.parse_args()

    dest_root = args.dest_root.rstrip('/')

    for line in sys.stdin:
        src = line.strip()
        if not src:
            continue
        tags = extract_tags(src)
        if tags:
            try:
                rel = build_picard_path(tags)
                # build_picard_path returns a relative path, ensure no leading slash
                rel = rel.lstrip(os.sep)
            except Exception:
                rel = fallback_relpath(src)
        else:
            rel = fallback_relpath(src)

        dest = os.path.join(dest_root, rel)
        # escape any commas in paths for CSV safety
        src_esc = src.replace(',', '_')
        dest_esc = dest.replace(',', '_')
        print(f"{src_esc},{dest_esc}")


if __name__ == '__main__':
    main()
