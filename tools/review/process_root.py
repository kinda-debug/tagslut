#!/usr/bin/env python3
"""End-to-end processing for a single root folder.

Pipeline:
  1) scan_with_trust
  2) check_integrity_update_db
  3) hoard_tags (db-add)
  4) normalize_genres (db-add + execute)
  5) tag_normalized_genres (execute)
  6) tagslut index enrich (hoarding + execute) scoped to path
  7) embed_cover_art (from DB) scoped to move log or paths list
  8) promote_replace_merge (execute)

This script runs the pipeline in-order for a provided root folder.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tagslut.utils.db import DbResolutionError, resolve_cli_env_db_path


def run(cmd: list[str]) -> None:
    print("\n$ " + " ".join(cmd))
    subprocess.check_call(cmd)


def main() -> None:
    ap = argparse.ArgumentParser(description="Processing pipeline for a root folder")
    ap.add_argument("--db", help="DB path")
    ap.add_argument("--root", help="Root folder to process")
    ap.add_argument("--library", help="Library destination")
    ap.add_argument("--providers", default="beatport,deezer,apple_music,itunes")
    ap.add_argument("--force", action="store_true", help="Force re-enrichment")
    ap.add_argument("--no-art", action="store_true", help="Skip cover art embedding")
    ap.add_argument("--art-force", action="store_true", help="Force replace embedded art")
    ap.add_argument("--trust", type=int, default=3, help="Pre-scan trust (0-3). Default: 3")
    ap.add_argument("--trust-post", type=int, default=3, help="Post-scan trust (0-3). Default: 3")
    ap.add_argument(
        "--allow-duplicate-hash",
        action="store_true",
        help="Allow moving files even if identical hash exists in library",
    )
    args = ap.parse_args()

    default_library = "/Volumes/MUSIC/LIBRARY"

    try:
        db_resolution = resolve_cli_env_db_path(args.db, purpose="write", source_label="--db")
    except DbResolutionError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    db = str(db_resolution.path)
    print(f"Resolved DB path: {db}")
    root = args.root or ""
    library = args.library or default_library

    if not root:
        raise SystemExit("root is required (pass --root)")

    db_path = Path(db)
    root_path = Path(root)
    if root_path.exists() and not list(root_path.rglob("*.flac")):
        print(f"Warning: no FLAC files found under {root_path}")
    library_path = Path(library)

    if not root_path.exists():
        raise SystemExit(f"Root not found: {root_path}")
    if not library_path.exists():
        print(f"Warning: library path does not exist yet: {library_path}")

    # 1) scan_with_trust
    run([
        "python3",
        "tools/review/scan_with_trust.py",
        "--db",
        str(db_path),
        "--trust",
        str(args.trust),
        "--trust-post",
        str(args.trust_post),
        str(root_path),
    ])

    # 2) integrity (write flac_ok to DB)
    run(["python3", "tools/review/check_integrity_update_db.py", "--db", str(db_path), "--execute", str(root_path)])

    # 3) hoard tags
    run(["python3", "tools/review/hoard_tags.py", "--db", str(db_path), "--db-add", str(root_path)])

    # 4) normalize genres
    run(["python3", "tools/review/normalize_genres.py", "--db", str(db_path), "--execute", str(root_path)])

    # 5) tag normalized genres
    run(["python3", "tools/review/tag_normalized_genres.py", "--execute", str(root_path)])

    # 6) metadata enrichment (hoarding)
    enrich_cmd = [
        "python3",
        "-m",
        "tagslut.cli.main",
        "_metadata",
        "enrich",
        "--db",
        str(db_path),
        "--hoarding",
        "--providers",
        args.providers,
        "--execute",
        "--path",
        f"{root_path}%",
    ]
    if args.force:
        enrich_cmd.append("--force")
    run(enrich_cmd)

    # 7) embed cover art (optional)
    if not args.no_art:
        embed_cmd = [
            "python3",
            "tools/review/embed_cover_art.py",
            "--db",
            str(db_path),
            "--root",
            str(root_path),
            "--execute",
        ]
        if args.art_force:
            embed_cmd.append("--force")
        run(embed_cmd)

    # 8) promote/replace into library
    promote_cmd = [
        "python3",
        "tools/review/promote_replace_merge.py",
        "--db",
        str(db_path),
        "--dest",
        str(library_path),
        "--execute",
        str(root_path),
    ]
    if args.allow_duplicate_hash:
        promote_cmd.append("--allow-duplicate-hash")
    run(promote_cmd)


if __name__ == "__main__":
    main()
