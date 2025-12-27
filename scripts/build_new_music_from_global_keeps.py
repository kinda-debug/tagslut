#!/usr/bin/env python3
"""
build_new_music_from_global_keeps.py

Create /Volumes/.../NEW_MUSIC from global_keeps.csv (resumable, disk-space-aware).

Inputs:
  - artifacts/reports/global_keeps.csv (must contain a 'path' column)

Outputs:
  - dest_root (default: /Volumes/dotad/NEW_MUSIC)
  - Places each file using the path after /Volumes/<volume>/
  - Fully resumable using JSON state file
  - Asks for new destination if disk becomes full
"""

import argparse
import csv
import json
import os
import shutil
from pathlib import Path

# Defaults
DEFAULT_CSV = "artifacts/reports/global_keeps.csv"
DEFAULT_DEST = "/Volumes/dotad/NEW_MUSIC"
DEFAULT_STATE = "artifacts/state/build_new_music_state.json"
DEFAULT_LOG = "artifacts/logs/build_new_music.log"

SAFETY_MARGIN_BYTES = 100 * 1024 * 1024  # 100 MB


# ------------------------------------------------------------
# Utility functions
# ------------------------------------------------------------

def log(msg: str, log_path: Path):
    msg = msg.rstrip()
    print(msg)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")


def load_state(state_path: Path):
    if not state_path.exists():
        return {"processed": []}
    with state_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state_path: Path, state):
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)
    tmp.replace(state_path)


def normalize_path(p: str) -> str:
    p = p.strip()
    if p.startswith('"') and p.endswith('"') and len(p) >= 2:
        p = p[1:-1]
    if p.startswith("'") and p.endswith("'") and len(p) >= 2:
        p = p[1:-1]
    return p


def compute_relative(src: str) -> Path:
    parts = Path(src).parts
    try:
        i = parts.index("Volumes")
        # drop /Volumes/<volume>/
        return Path(*parts[i + 2 :])
    except ValueError:
        # fallback: drop leading slash
        if parts and parts[0] == "/":
            return Path(*parts[1:])
        return Path(src)


def ensure_dest(dest_root: Path, log_path: Path):
    if not dest_root.exists():
        log(f"Creating destination root: {dest_root}", log_path)
        dest_root.mkdir(parents=True, exist_ok=True)


def freespace(path: Path) -> int:
    probe = path if path.exists() else path.parent
    return shutil.disk_usage(str(probe)).free


def copy_file(src: Path, dst: Path, log_path: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(src), str(dst))
    log(f"Copied: {src} -> {dst}", log_path)


def prompt_new_dest(old_dest: Path, src: Path, required: int, log_path: Path):
    MB = required / (1024 * 1024)
    log(f"Not enough space in {old_dest} to copy {src} (needs ~{MB:.1f} MB).", log_path)
    ans = input("Enter NEW destination root or press ENTER to abort: ").strip()
    if not ans:
        return old_dest, True
    new = Path(ans).expanduser()
    log(f"Switched to new destination root: {new}", log_path)
    return new, False


# ------------------------------------------------------------
# Main build function
# ------------------------------------------------------------

def build(csv_path: Path, dest_root: Path, state_path: Path, log_path: Path):
    log("=== Starting NEW_MUSIC build ===", log_path)
    log(f"CSV: {csv_path}", log_path)
    log(f"DEST: {dest_root}", log_path)
    log(f"STATE: {state_path}", log_path)

    ensure_dest(dest_root, log_path)

    state = load_state(state_path)
    processed = set(state.get("processed", []))

    total = 0
    copied = 0
    skipped_exists = 0
    skipped_missing = 0
    resumed = 0

    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)

        try:
            path_idx = [i for i, h in enumerate(header) if h.strip().lower() == "path"][0]
        except IndexError:
            path_idx = 0

        for row in reader:
            total += 1
            raw = normalize_path(row[path_idx])
            if not raw:
                continue

            if raw in processed:
                resumed += 1
                continue

            src = Path(raw)
            if not src.is_file():
                log(f"Missing, skipping: {src}", log_path)
                processed.add(raw)
                skipped_missing += 1
                state["processed"] = sorted(processed)
                save_state(state_path, state)
                continue

            rel = compute_relative(raw)
            dst = dest_root / rel

            if dst.exists():
                skipped_exists += 1
                processed.add(raw)
                state["processed"] = sorted(processed)
                save_state(state_path, state)
                continue

            size = src.stat().st_size
            need = size + SAFETY_MARGIN_BYTES

            while True:
                free = freespace(dest_root)
                if free >= need:
                    copy_file(src, dst, log_path)
                    copied += 1
                    processed.add(raw)
                    state["processed"] = sorted(processed)
                    state["dest_root"] = str(dest_root)
                    save_state(state_path, state)
                    break
                else:
                    new_dest, abort = prompt_new_dest(dest_root, src, need, log_path)
                    if abort:
                        log("Aborted by user due to insufficient space.", log_path)
                        return
                    dest_root = new_dest
                    ensure_dest(dest_root, log_path)
                    state["dest_root"] = str(dest_root)
                    save_state(state_path, state)

    log("=== Finished NEW_MUSIC build ===", log_path)
    log(f"Total rows: {total}", log_path)
    log(f"Copied: {copied}", log_path)
    log(f"Already existed: {skipped_exists}", log_path)
    log(f"Missing: {skipped_missing}", log_path)
    log(f"Resumed: {resumed}", log_path)


# ------------------------------------------------------------
# CLI
# ------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description="Build NEW_MUSIC from global_keeps.csv")
    p.add_argument("--csv", default=DEFAULT_CSV)
    p.add_argument("--dest-root", default=DEFAULT_DEST)
    p.add_argument("--state", default=DEFAULT_STATE)
    p.add_argument("--log", default=DEFAULT_LOG)
    args = p.parse_args()

    build(Path(args.csv), Path(args.dest_root), Path(args.state), Path(args.log))


if __name__ == "__main__":
    main()
