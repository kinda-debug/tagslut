#!/usr/bin/env python3
"""
Scan a directory with a trust score (0-3) and apply zone rules post-scan.

Trust score meanings:
0 = known bad (quarantine)
1 = likely bad (suspect)
2 = uncertain but possibly good (staging)
3 = new/likely good (staging by default, accepted if --allow-accepted)
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parents[2]))

from tagslut.integrity_scanner import scan_library
from tagslut.utils.db import resolve_db_path
from tagslut.utils.config import get_config
from tagslut.utils.cli_helper import configure_execution


def prompt_trust(label: str) -> int:
    prompt = (
        f"{label} trust score [0=bad,1=probably bad,2=maybe good,3=new/likely good]: "
    )
    while True:
        value = input(prompt).strip()
        if value.isdigit() and int(value) in (0, 1, 2, 3):
            return int(value)
        print("Enter 0, 1, 2, or 3.")


def map_trust_to_zone(trust: int, allow_accepted: bool) -> str:
    if trust <= 0:
        return "quarantine"
    if trust == 1:
        return "suspect"
    if trust == 2:
        return "staging"
    return "accepted" if allow_accepted else "staging"


def apply_trust_zones(db_path: Path, root: Path, trust: int, allow_accepted: bool) -> None:
    zone_target = map_trust_to_zone(trust, allow_accepted)
    conn = sqlite3.connect(db_path)
    try:
        # Always keep integrity failures in suspect unless trust=0 (quarantine)
        if trust == 0:
            conn.execute(
                "UPDATE files SET zone = ? WHERE path LIKE ?",
                (zone_target, f"{root}%"),
            )
        else:
            conn.execute(
                """
                UPDATE files
                SET zone = CASE
                    WHEN flac_ok = 0 OR integrity_state IN ('corrupt','recoverable') THEN 'suspect'
                    ELSE ?
                END
                WHERE path LIKE ?
                """,
                (zone_target, f"{root}%"),
            )
        conn.commit()
    finally:
        conn.close()


def ensure_trust_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scan_trust_batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT,
            root_path TEXT,
            trust_pre INTEGER,
            trust_post INTEGER,
            allow_accepted INTEGER,
            db_path TEXT
        )
        """
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Scan a directory with trust scoring.")
    ap.add_argument("root", type=Path, help="Directory to scan")
    ap.add_argument("--db", required=True, help="Path to SQLite database")
    ap.add_argument("--create-db", action="store_true", help="Allow creating a new DB file.")
    ap.add_argument("--library", help="Logical library name (optional)")
    ap.add_argument("--check-integrity", action="store_true", help="Run flac -t verification.")
    ap.add_argument("--check-hash", action="store_true", help="Calculate full-file SHA256.")
    ap.add_argument("--recheck", action="store_true", help="Re-run requested checks for missing/stale/failed files.")
    ap.add_argument("--force-all", action="store_true", help="Force all requested checks on all files.")
    ap.add_argument("--progress", action="store_true", help="Log periodic progress.")
    ap.add_argument("--progress-interval", type=int, default=250, help="Progress interval in number of files.")
    ap.add_argument("--limit", type=int, help="Stop after processing N files.")
    ap.add_argument("--allow-accepted", action="store_true",
                    help="Allow trust=3 to map to accepted (default maps to staging).")
    ap.add_argument("--trust", type=int, choices=[0, 1, 2, 3],
                    help="Trust score (0-3). If omitted, prompt.")
    ap.add_argument("--trust-post", type=int, choices=[0, 1, 2, 3],
                    help="Post-scan trust score (0-3). If omitted, prompt.")
    ap.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging.")
    ap.add_argument("--config", help="Path to a TOML config file.")
    args = ap.parse_args()

    app_config = get_config(Path(args.config) if args.config else None)
    configure_execution(args.verbose, args.config)

    root = args.root.expanduser().resolve()

    resolution = resolve_db_path(
        args.db,
        config=app_config,
        allow_repo_db=False,
        repo_root=Path(__file__).parents[2].resolve(),
        purpose="write",
        allow_create=args.create_db,
    )
    db_path = resolution.path

    trust_pre = args.trust if args.trust is not None else prompt_trust("Pre-scan")

    scan_library(
        library_path=root,
        db_path=db_path,
        db_source=resolution.source,
        library=args.library,
        recheck=args.recheck,
        force_all=args.force_all,
        progress=args.progress,
        progress_interval=args.progress_interval,
        scan_integrity=args.check_integrity,
        scan_hash=args.check_hash,
        limit=args.limit,
        create_db=args.create_db,
        allow_repo_db=False,
    )

    apply_trust_zones(db_path, root, trust_pre, args.allow_accepted)

    trust_post = args.trust_post if args.trust_post is not None else prompt_trust("Post-scan")
    apply_trust_zones(db_path, root, trust_post, args.allow_accepted)

    conn = sqlite3.connect(db_path)
    try:
        ensure_trust_table(conn)
        conn.execute(
            "INSERT INTO scan_trust_batches (created_at, root_path, trust_pre, trust_post, allow_accepted, db_path) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                str(root),
                trust_pre,
                trust_post,
                1 if args.allow_accepted else 0,
                str(db_path),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    print("Scan complete; trust-based zones applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
