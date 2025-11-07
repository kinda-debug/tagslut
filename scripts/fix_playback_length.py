#!/usr/bin/env python3
"""Repair helpers: remux or re-encode FLAC files to correct STREAMINFO / length.

This script writes fixed files as <name>.fixed.flac next to original. It
preserves metadata if metaflac is installed, and keeps the original as
<name>.bak until you confirm.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def which(cmd: str):
    from shutil import which as _which

    return _which(cmd)


def export_tags(src: str, tagfile: str):
    if which("metaflac"):
        subprocess.run(["metaflac", "--export-tags-to=%s" % tagfile, src],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def import_tags(dst: str, tagfile: str):
    if which("metaflac") and os.path.exists(tagfile):
        subprocess.run(["metaflac", "--import-tags-from=%s" % tagfile, dst],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def remux_or_reencode(src: str, dst: str) -> bool:
    # try remux (fast)
    ffmpeg = which("ffmpeg")
    if not ffmpeg:
        return False
    # attempt stream copy remux
    rc = subprocess.run([ffmpeg, "-y", "-v", "error", "-i", src,
                         "-c", "copy", dst]).returncode
    if rc == 0 and os.path.exists(dst):
        return True
    # fallback: decode and re-encode
    rc = subprocess.run([ffmpeg, "-y", "-v", "error", "-i", src,
                         "-c:a", "flac", dst]).returncode
    return rc == 0 and os.path.exists(dst)


def process_one(path: str, keep_backup: bool = True):
    p = Path(path)
    if not p.exists():
        return False, "missing"
    out = p.with_suffix(p.suffix + ".fixed")
    tagfile = str(p) + ".tags"
    export_tags(str(p), tagfile)
    ok = remux_or_reencode(str(p), str(out))
    if not ok:
        try:
            if os.path.exists(tagfile):
                os.remove(tagfile)
        except Exception:
            pass
        return False, "repair-failed"
    import_tags(str(out), tagfile)
    # swap with backup
    bak = str(p) + ".bak"
    try:
        if keep_backup:
            shutil.move(str(p), bak)
        else:
            os.remove(str(p))
        shutil.move(str(out), str(p))
    except Exception as e:
        return False, str(e)
    try:
        if os.path.exists(tagfile):
            os.remove(tagfile)
    except Exception:
        pass
    return True, "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+", help="Files to fix")
    ap.add_argument("--no-backup", dest="backup", action="store_false",
                    help="Do not keep .bak backup; overwrite")
    args = ap.parse_args()
    for p in args.paths:
        ok, msg = process_one(p, keep_backup=args.backup)
        print(p, ok, msg)


if __name__ == "__main__":
    main()
