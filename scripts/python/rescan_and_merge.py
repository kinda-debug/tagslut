#!/usr/bin/env python3
from pathlib import Path
import argparse
import sqlite3
import subprocess
import sys

try:
    from dedupe.utils.config import get_config
    from dedupe.utils.db import open_db, resolve_db_path
except ModuleNotFoundError:  # pragma: no cover
    repo_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo_root))
    from dedupe.utils.config import get_config
    from dedupe.utils.db import open_db, resolve_db_path


def _parse_scan_arg(value: str) -> tuple[str, str]:
    if ":" not in value:
        raise argparse.ArgumentTypeError("Expected --scan PATH:ZONE")
    path, zone = value.split(":", 1)
    if not path or not zone:
        raise argparse.ArgumentTypeError("Expected --scan PATH:ZONE")
    return path, zone


def run_scan(path: str, zone: str, scan_db: Path, allow_repo_db: bool, create_db: bool) -> None:
    print(f"Scanning: {path} ({zone})")
    cmd = [
        "python3",
        "-m",
        "dedupe.cli",
        "scan-library",
        "--root",
        path,
        "--db",
        str(scan_db),
        "--zone",
        zone,
    ]
    if create_db:
        cmd.append("--create-db")
    if allow_repo_db:
        cmd.append("--allow-repo-db")
    subprocess.run(cmd, check=True)


def merge_scan(scan_db: Path, canon_db: Path, allow_repo_db: bool) -> None:
    resolution = resolve_db_path(
        canon_db,
        config=get_config(),
        allow_repo_db=allow_repo_db,
        repo_root=Path(__file__).resolve().parents[2],
        purpose="write",
        allow_create=False,
        source_label="explicit",
    )
    conn = open_db(resolution)
    cur = conn.cursor()
    cur.execute(f"ATTACH '{scan_db}' AS scan;")
    cur.execute(
        """
        INSERT INTO library_files (path, tags_json, extra_json)
        SELECT path, tags_json, extra_json FROM scan.library_files;
        """
    )
    cur.execute("DETACH scan;")
    conn.commit()
    conn.close()
    print("Merged into canonical DB.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Rescan and merge multiple zones.")
    parser.add_argument(
        "--scan",
        action="append",
        type=_parse_scan_arg,
        required=True,
        help="Scan target in the form PATH:ZONE (repeatable)",
    )
    parser.add_argument("--scan-db", type=Path, required=True, help="Temporary scan DB path")
    parser.add_argument("--canon-db", type=Path, required=True, help="Canonical DB path")
    parser.add_argument("--create-db", action="store_true", help="Allow creating the scan DB file")
    parser.add_argument("--allow-repo-db", action="store_true", help="Allow repo-local DB paths")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    scan_resolution = resolve_db_path(
        args.scan_db,
        config=get_config(),
        allow_repo_db=args.allow_repo_db,
        repo_root=repo_root,
        purpose="write",
        allow_create=args.create_db,
        source_label="explicit",
    )
    canon_resolution = resolve_db_path(
        args.canon_db,
        config=get_config(),
        allow_repo_db=args.allow_repo_db,
        repo_root=repo_root,
        purpose="write",
        allow_create=False,
        source_label="explicit",
    )

    for path, zone in args.scan:
        run_scan(path, zone, scan_resolution.path, args.allow_repo_db, args.create_db)
        merge_scan(scan_resolution.path, canon_resolution.path, args.allow_repo_db)
        scan_resolution.path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
