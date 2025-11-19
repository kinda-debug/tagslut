#!/usr/bin/env python3
"""
build_new_music_from_global_keeps.py

Build a canonical NEW_MUSIC library from global_keeps.csv.

- Input: artifacts/reports/global_keeps.csv
  - Expects at least a "path" column (absolute source path).
  - Extra columns are ignored.

- Output tree: dest_root (default: /Volumes/dotad/NEW_MUSIC)
  - For each source file path:
      /Volumes/<volume>/<...>  ->  dest_root/<... after volume name ...>

  Examples:
    /Volumes/dotad/NEW_LIBRARY/Garbage/D/... ->
        /Volumes/dotad/NEW_MUSIC/NEW_LIBRARY/Garbage/D/...

    /Volumes/sad/MUSIC/_repaired_flacs/... ->
        /Volumes/dotad/NEW_MUSIC/MUSIC/_repaired_flacs/...

    /Volumes/Vault/Vault/CORRUPTED_ORIGINALS/... ->
        /Volumes/dotad/NEW_MUSIC/Vault/CORRUPTED_ORIGINALS/...

- Resumable:
  - Uses a JSON state file (default: artifacts/state/build_new_music_state.json)
  - Tracks processed source paths.
  - Safe to interrupt and re-run.

- Disk-space aware:
  - Before each copy, checks free space on the destination filesystem.
  - If not enough space to copy the file (with a safety margin), prompts:
      - Enter a new destination root (will continue there), or
      - Press ENTER to abort gracefully (state preserved).
"""

import argparse
import csv
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, Set, Tuple

DEFAULT_CSV = "artifacts/reports/global_keeps.csv"
DEFAULT_DEST = "/Volumes/dotad/NEW_MUSIC"
DEFAULT_STATE = "artifacts/state/build_new_music_state.json"
DEFAULT_LOG = "artifacts/logs/build_new_music.log"

SAFETY_MARGIN_BYTES = 100 * 1024 * 1024  # 100 MB safety margin


def log(msg: str, log_path: Path) -> None:
    text = msg.rstrip()
    print(text)
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(text + "\n")
    except Exception:
        # Do not crash on logging failure.
        pass


def load_state(state_path: Path) -> Dict:
    if not state_path.exists():
        return {
            "csv_path": None,
            "dest_root": None,
            "processed_paths": [],
        }
    with state_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state_path: Path, state: Dict) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = state_path.with_suffix(state_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)
    tmp_path.replace(state_path)


def normalize_source_path(raw: str) -> str:
    """
    Clean up the path string from CSV:
    - strip whitespace
    - strip surrounding quotes
    """
    if raw is None:
        return ""
    s = raw.strip()
    if s.startswith('"') and s.endswith('"') and len(s) >= 2:
        s = s[1:-1]
    if s.startswith("'") and s.endswith("'") and len(s) >= 2:
        s = s[1:-1]
    return s


def compute_relative_path(src: str) -> Path:
    """
    Compute the path inside NEW_MUSIC based on the source.

    Strategy:
      - For /Volumes/<volume>/<rest...>
        -> <rest...> (drop /Volumes/<volume>)
      - If the pattern does not match, fall back to dropping leading '/'
    """
    p = Path(src)
    parts = p.parts  # tuple

    # Expect something like ('/', 'Volumes', 'sad', 'MUSIC', '_repaired_flacs', ...)
    try:
        idx_volumes = parts.index("Volumes")
    except ValueError:
        # No "Volumes" component; just drop leading slash.
        if parts and parts[0] == os.sep:
            return Path(*parts[1:])
        return p

    # After 'Volumes', the next part should be the volume name; we skip both.
    # Example: /Volumes/sad/MUSIC/... -> rel = MUSIC/...
    if len(parts) > idx_volumes + 2:
        rel_parts = parts[idx_volumes + 2 :]
        return Path(*rel_parts)

    # If there is nothing beyond the volume name, just return the last part.
    if len(parts) > 0:
        return Path(parts[-1])

    return Path("UNKNOWN_PATH")


def ensure_dest_root_exists(dest_root: Path, log_path: Path) -> None:
    if not dest_root.exists():
        log(f"Destination root does not exist, creating: {dest_root}", log_path)
        dest_root.mkdir(parents=True, exist_ok=True)


def get_free_space_bytes(dest_root: Path) -> int:
    """
    Return free bytes on filesystem containing dest_root.
    If dest_root doesn't exist yet, check its parent.
    """
    probe = dest_root
    if not probe.exists():
        probe = dest_root.parent
        if not probe.exists():
            probe = Path("/")  # fallback
    usage = shutil.disk_usage(str(probe))
    return usage.free


def safe_copy(src: Path, dst: Path, log_path: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(src), str(dst))
    log(f"Copied: {src} -> {dst}", log_path)


def prompt_new_destination(current_dest: Path, src: Path, required_bytes: int, log_path: Path) -> Tuple[Path, bool]:
    """
    Ask user for a new destination root when space is insufficient.

    Returns (new_dest_root, should_abort).
    """
    size_mb = required_bytes / (1024 * 1024)
    log(
        f"Insufficient space in {current_dest} to copy {src} "
        f"(needs ~{size_mb:.1f} MB including safety margin).",
        log_path,
    )
    print()
    print("Destination appears full or nearly full.")
    new_root_str = input(
        "Enter NEW destination root path to continue, or press ENTER to abort: "
    ).strip()

    if not new_root_str:
        log("User chose to abort due to insufficient space.", log_path)
        return current_dest, True

    new_dest_root = Path(new_root_str).expanduser()
    log(f"Switching destination root to: {new_dest_root}", log_path)
    return new_dest_root, False


def build_new_music(
    csv_path: Path,
    dest_root: Path,
    state_path: Path,
    log_path: Path,
) -> None:
    log(f"Starting build_new_music_from_global_keeps", log_path)
    log(f"  CSV:  {csv_path}", log_path)
    log(f"  Dest: {dest_root}", log_path)
    log(f"  State:{state_path}", log_path)

    ensure_dest_root_exists(dest_root, log_path)

    state = load_state(state_path)
    processed_paths: Set[str] = set(state.get("processed_paths", []))

    # If CSV changed, update reference (but keep processed paths by string).
    if state.get("csv_path") != str(csv_path):
        log(
            f"State CSV ({state.get('csv_path')}) != current CSV ({csv_path}), "
            f"continuing but updating state.",
            log_path,
        )
        state["csv_path"] = str(csv_path)

    # Always record the latest dest_root in state.
    state["dest_root"] = str(dest_root)
    save_state(state_path, state)

    total_rows = 0
    skipped_existing = 0
    skipped_missing = 0
    copied = 0
    already_processed = 0

    if not csv_path.exists():
        log(f"ERROR: CSV not found: {csv_path}", log_path)
        sys.exit(1)

    with csv_path.open("r", newline="", encoding="utf-8") as f_in:
        reader = csv.reader(f_in)
        try:
            header = next(reader)
        except StopIteration:
            log("CSV is empty.", log_path)
            return

        # Try to locate "path" column
        path_idx = None
        for i, col in enumerate(header):
            if col.strip().lower() == "path":
                path_idx = i
                break

        if path_idx is None:
            # Assume first column is path
            log(
                "No 'path' column found in header; using first column as path.",
                log_path,
            )
            path_idx = 0

        for row in reader:
            total_rows += 1
            if path_idx >= len(row):
                log(f"Skipping row with no path column: {row}", log_path)
                continue

            raw_path = row[path_idx]
            src_str = normalize_source_path(raw_path)

            if not src_str:
                log(f"Skipping row with empty path: {row}", log_path)
                continue

            if src_str in processed_paths:
                already_processed += 1
                continue

            src = Path(src_str)

            if not src.is_file():
                log(f"Source missing, skipping: {src}", log_path)
                processed_paths.add(src_str)
                skipped_missing += 1
                state["processed_paths"] = sorted(processed_paths)
                save_state(state_path, state)
                continue

            # Compute destination path
            rel = compute_relative_path(src_str)
            dst = dest_root / rel

            if dst.is_file():
                # File already exists at destination; treat as done.
                log(f"Destination exists, skipping copy: {dst}", log_path)
                processed_paths.add(src_str)
                skipped_existing += 1
                state["processed_paths"] = sorted(processed_paths)
                save_state(state_path, state)
                continue

            # Check free space
            try:
                src_size = src.stat().st_size
            except OSError as e:
                log(f"ERROR: Cannot stat source {src}: {e}", log_path)
                processed_paths.add(src_str)
                skipped_missing += 1
                state["processed_paths"] = sorted(processed_paths)
                save_state(state_path, state)
                continue

            required_bytes = src_size + SAFETY_MARGIN_BYTES

            while True:
                free_bytes = get_free_space_bytes(dest_root)
                if free_bytes >= required_bytes:
                    # Enough space, perform copy
                    try:
                        safe_copy(src, dst, log_path)
                        copied += 1
                    except Exception as e:
                        log(f"ERROR during copy {src} -> {dst}: {e}", log_path)
                        # Mark as processed to avoid infinite loop on repeated failures
                    processed_paths.add(src_str)
                    state["processed_paths"] = sorted(processed_paths)
                    state["dest_root"] = str(dest_root)
                    save_state(state_path, state)
                    break
                else:
                    # Not enough space; prompt for new destination
                    new_dest, abort = prompt_new_destination(
                        dest_root, src, required_bytes, log_path
                    )
                    if abort:
                        # Persist current state and exit
                        state["processed_paths"] = sorted(processed_paths)
                        state["dest_root"] = str(dest_root)
                        save_state(state_path, state)
                        log("Aborting due to insufficient space.", log_path)
                        log(
                            f"Progress: total_rows={total_rows}, "
                            f"copied={copied}, "
                            f"skipped_existing={skipped_existing}, "
                            f"skipped_missing={skipped_missing}, "
                            f"already_processed={already_processed}",
                            log_path,
                        )
                        return
                    else:
                        dest_root = new_dest
                        ensure_dest_root_exists(dest_root, log_path)
                        state["dest_root"] = str(dest_root)
                        save_state(state_path, state)
                        # Loop continues, will re-check free space on new dest_root

    log("Done building NEW_MUSIC.", log_path)
    log(
        f"Summary: total_rows={total_rows}, "
        f"copied={copied}, "
        f"skipped_existing={skipped_existing}, "
        f"skipped_missing={skipped_missing}, "
        f"already_processed={already_processed}",
        log_path,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build NEW_MUSIC from global_keeps.csv (resumable, space-aware)."
    )
    parser.add_argument(
        "--csv",
        type=str,
        default=DEFAULT_CSV,
        help=f"Path to global_keeps.csv (default: {DEFAULT_CSV})",
    )
    parser.add_argument(
        "--dest-root",
        type=str,
        default=DEFAULT_DEST,
        help=f"Destination root for NEW_MUSIC (default: {DEFAULT_DEST})",
    )
    parser.add_argument(
        "--state",
        type=str,
        default=DEFAULT_STATE,
        help=f"State file for resumable progress (default: {DEFAULT_STATE})",
    )
    parser.add_argument(
        "--log",
        type=str,
        default=DEFAULT_LOG,
        help=f"Log file path (default: {DEFAULT_LOG})",
    )

    args = parser.parse_args()

    csv_path = Path(args.csv).expanduser()
    dest_root = Path(args.dest_root).expanduser()
    state_path = Path(args.state).expanduser()
    log_path = Path(args.log).expanduser()

    build_new_music(csv_path, dest_root, state_path, log_path)


if __name__ == "__main__":
    main()
