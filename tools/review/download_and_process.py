#!/usr/bin/env python3
"""Download from Tidal or Beatport, then run the processing pipeline.

Usage examples:
  python3 tools/review/download_and_process.py --source tidal --url https://tidal.com/album/123
  python3 tools/review/download_and_process.py --source beatport --url https://www.beatport.com/track/xyz
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

# Ensure repo root is on sys.path when run as a script
_repo_root = Path(__file__).resolve().parents[2]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from tagslut.utils.env_paths import get_library_volume
from tagslut.utils.db import DbResolutionError, resolve_cli_env_db_path


def _infer_source(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "tidal.com" in host:
        return "tidal"
    if "beatport.com" in host:
        return "beatport"
    return ""


def run(cmd: list[str]) -> None:
    print("\n$ " + " ".join(cmd))
    subprocess.check_call(cmd)


def main() -> None:
    ap = argparse.ArgumentParser(description="Download and process a URL")
    ap.add_argument("url_arg", nargs="?", help="Track/album/playlist URL (positional)")
    ap.add_argument("--source", choices=["tidal", "beatport"], help="Download source (optional)")
    ap.add_argument("--url", help="Track/album/playlist URL (overrides positional)")
    ap.add_argument("--urls-file", help="File with one URL per line")
    ap.add_argument("--db", help="DB path (default from TAGSLUT_DB)")
    ap.add_argument("--library", help="Library destination (default from VOLUME_LIBRARY)")
    ap.add_argument("--root", help="Download staging root (default by source)")
    ap.add_argument("--providers", default="beatport,deezer,apple_music,itunes")
    ap.add_argument("--force", action="store_true", help="Force re-enrichment")
    ap.add_argument("--no-art", action="store_true", help="Skip cover art embedding")
    ap.add_argument("--art-force", action="store_true", help="Force replace embedded art")
    ap.add_argument("--allow-duplicate-hash", action="store_true", default=True, help="Allow duplicate hash on promote (default: true)")
    ap.add_argument("--no-allow-duplicate-hash", action="store_true", help="Disallow duplicate hash on promote")
    ap.add_argument("--tiddl-bin", default="tools/tiddl", help="Path to tiddl wrapper")
    ap.add_argument("--beatport-bin", default="/Users/georgeskhawam/Projects/beatportdl/beatportdl-darwin-arm64", help="Path to beatport downloader")
    ap.add_argument("--bpdl-timeout", type=int, default=180, help="Seconds to wait before killing beatportdl after download")
    args = ap.parse_args()

    if args.urls_file:
        url = Path(args.urls_file).expanduser().read_text(encoding="utf-8", errors="replace")
    else:
        url = args.url or args.url_arg or ""
        if url and Path(url).expanduser().exists() and not url.startswith("http"):
            url = Path(url).expanduser().read_text(encoding="utf-8", errors="replace")
    if not url:
        raise SystemExit("url is required (pass --url, a positional URL, or --urls-file)")
    source = args.source or _infer_source(url)
    if source not in {"tidal", "beatport"}:
        raise SystemExit("source must be tidal or beatport")

    try:
        db_resolution = resolve_cli_env_db_path(args.db, purpose="write", source_label="--db")
    except DbResolutionError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    db = str(db_resolution.path)
    print(f"Resolved DB path: {db}")
    try:
        default_library = str(get_library_volume())
    except Exception:
        default_library = "/Volumes/MUSIC/LIBRARY"
    default_root = "/Users/georgeskhawam/Music/tiddl" if source == "tidal" else "/Users/georgeskhawam/Music/bpdl"

    library = args.library or default_library
    root = args.root or default_root

    root_path = Path(root)
    root_path.mkdir(parents=True, exist_ok=True)

    # Support multiple URLs passed in a single string (newline-separated)
    urls = [u.strip() for u in url.splitlines() if u.strip()]

    if source == "tidal":
        tiddl = Path(args.tiddl_bin)
        if not tiddl.exists():
            raise SystemExit(f"tiddl not found: {tiddl}")
        for u in urls:
            run([str(tiddl), "download", "url", u])
    else:
        bp = Path(args.beatport_bin)
        try:
            if bp.exists():
                # Beatportdl can drop into interactive prompt; run non-interactive and enforce timeout.
                for u in urls:
                    result = subprocess.run([str(bp), u], stdin=subprocess.DEVNULL, timeout=args.bpdl_timeout)
            else:
                for u in urls:
                    result = subprocess.run(["bdl", u], stdin=subprocess.DEVNULL, timeout=args.bpdl_timeout)
            if result.returncode != 0:
                print("Warning: beatportdl exited non-zero (likely EOF after download). Continuing.")
        except subprocess.TimeoutExpired:
            print("Warning: beatportdl timed out after download prompt. Continuing.")

    # Detect root if default has no audio files
    root_path = Path(root)
    if not list(root_path.rglob("*.flac")):
        candidates = [
            Path("/Users/georgeskhawam/Music/bpdl"),
            Path("/Users/georgeskhawam/Music/tiddl"),
            Path("/Volumes/MUSIC/CLEAN"),
        ]
        found = None
        for c in candidates:
            if c.exists() and list(c.rglob("*.flac")):
                found = c
                break
        if found:
            root_path = found
        else:
            print(f"Warning: download root has no FLAC files: {root_path}")

    # Process downloaded files
    proc_cmd = [
        "python3",
        "tools/review/process_root.py",
        "--db",
        db,
        "--root",
        str(root_path),
        "--library",
        library,
        "--providers",
        args.providers,
    ]
    if args.force:
        proc_cmd.append("--force")
    if args.no_art:
        proc_cmd.append("--no-art")
    if args.art_force:
        proc_cmd.append("--art-force")
    if args.no_allow_duplicate_hash:
        pass
    else:
        proc_cmd.append("--allow-duplicate-hash")

    run(proc_cmd)


if __name__ == "__main__":
    main()
