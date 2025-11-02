#!/usr/bin/env python3
"""
scripts/find_missing_candidates.py

Run several passes to locate missing candidate files referenced by basename.

Outputs (all in /tmp):
- found_candidates_mdfind.txt       (exact Spotlight matches)
- found_candidates_find_all.txt    (find across /Volumes)
- found_candidates_token.txt       (partial-token Spotlight matches)

Usage:
  python3 scripts/find_missing_candidates.py --basenames /tmp/missing_basenames_parsed.txt

This script is conservative and will not modify any repo files.
"""
import argparse
import subprocess
import sys
from pathlib import Path


def run_mdfind_exact(name):
    # case-insensitive exact name match in Spotlight
    q = f"kMDItemFSName == '{name}'c"
    try:
        out = subprocess.check_output(["mdfind", q], stderr=subprocess.DEVNULL)
        return [p.decode("utf-8").rstrip("\n") for p in out.splitlines()]
    except subprocess.CalledProcessError:
        return []


def run_find_volumes(name):
    # search all mounts under /Volumes for a case-insensitive filename match
    try:
        proc = subprocess.run(
            [
                "find",
                "/Volumes",
                "-type",
                "f",
                "-iname",
                name,
                "-print",
                "-quit",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        out = proc.stdout.decode("utf-8").strip()
        return [out] if out else []
    except Exception:
        return []


def run_mdfind_token(token):
    q = f"kMDItemFSName == '*{token}*'c"
    try:
        out = subprocess.check_output(["mdfind", q], stderr=subprocess.DEVNULL)
        return [p.decode("utf-8").rstrip("\n") for p in out.splitlines()]
    except subprocess.CalledProcessError:
        return []


def tokens_from_name(name, min_len=3):
    import re
    parts = re.split(r"[^A-Za-z0-9]+", name)
    toks = [p for p in parts if len(p) >= min_len]
    return list(dict.fromkeys(toks))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--basenames", default="/tmp/missing_basenames_parsed.txt")
    p.add_argument("--outdir", default="/tmp")
    args = p.parse_args()

    basenames_path = Path(args.basenames)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    mdfind_out = outdir / "found_candidates_mdfind.txt"
    find_out = outdir / "found_candidates_find_all.txt"
    token_out = outdir / "found_candidates_token.txt"

    # clear previous outputs
    for f in (mdfind_out, find_out, token_out):
        try:
            f.unlink()
        except FileNotFoundError:
            pass

    if not basenames_path.exists():
        print(f"Basename file not found: {basenames_path}")
        sys.exit(2)

    basenames = [
        line.strip()
        for line in basenames_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    print(f"Searching {len(basenames)} basenames")

    # exact Spotlight pass
    for name in basenames:
        found = run_mdfind_exact(name)
        if found:
            with mdfind_out.open("a", encoding="utf-8") as fh:
                for pth in found:
                    fh.write(f"{name}\t{pth}\n")

    # find across /Volumes
    for name in basenames:
        found = run_find_volumes(name)
        if found:
            with find_out.open("a", encoding="utf-8") as fh:
                for pth in found:
                    fh.write(f"{name}\t{pth}\n")

    # tokenized Spotlight pass
    seen_tokens = set()
    for name in basenames:
        toks = tokens_from_name(name)
        for t in toks:
            if t in seen_tokens:
                continue
            seen_tokens.add(t)
            found = run_mdfind_token(t)
            if found:
                with token_out.open("a", encoding="utf-8") as fh:
                    for pth in found:
                        fh.write(f"{t}\t{pth}\n")

    # summaries
    def lines(pth):
        try:
            return len(pth.read_text(encoding="utf-8").splitlines())
        except FileNotFoundError:
            return 0

    print("found (mdfind):", lines(mdfind_out))
    print("found (find /Volumes):", lines(find_out))
    print("found (token mdfind):", lines(token_out))

    for out in (mdfind_out, find_out, token_out):
        if out.exists():
            print(f"--- sample from {out} ---")
            with out.open("r", encoding="utf-8") as fh:
                for i, line in enumerate(fh):
                    if i >= 20:
                        break
                    print(line.rstrip("\n"))


if __name__ == "__main__":
    main()
