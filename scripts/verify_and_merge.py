#!/usr/bin/env python3
import argparse
import sqlite3
import subprocess
import os
from pathlib import Path
import shutil

FINAL_DB = Path("artifacts/db/library_final.db")
REPORT_DIR = Path("artifacts/reports/verify")
TMP_DB_DIR = Path("artifacts/db/tmp_verify")


def ensure_dirs():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    TMP_DB_DIR.mkdir(parents=True, exist_ok=True)


def scan_to_temp_db(root: Path) -> Path:
    temp_db = TMP_DB_DIR / f"{root.name}.db"
    if temp_db.exists():
        temp_db.unlink()

    cmd = [
        "python3", "-m", "dedupe.cli", "scan-library",
        "--root", str(root),
        "--out", str(temp_db),
        "--progress"
    ]

    subprocess.run(cmd, check=True)
    return temp_db


def merge_into_final(temp_db: Path):
    sql = f"""
    ATTACH '{temp_db}' AS tmp;
    INSERT OR IGNORE INTO library_files
    SELECT * FROM tmp.library_files;
    DETACH tmp;
    """
    subprocess.run(["sqlite3", str(FINAL_DB), sql])


def db_count_for_prefix(prefix: str) -> int:
    sql = f"""
        SELECT COUNT(*) FROM library_files
        WHERE path LIKE '{prefix}%';
    """
    out = subprocess.check_output(["sqlite3", str(FINAL_DB), sql]).decode().strip()
    return int(out or 0)


def collect_fs_list(root: Path) -> list[str]:
    cmd = ["find", str(root), "-type", "f"]
    out = subprocess.check_output(cmd).decode().splitlines()
    out = sorted(out)
    return out


def write_list(path: Path, lines: list[str]):
    with path.open("w") as f:
        for line in lines:
            f.write(line + "\n")


def load_db_paths(prefix: str) -> list[str]:
    sql = f"""
        SELECT path FROM library_files
        WHERE path LIKE '{prefix}%'
        ORDER BY path;
    """
    out = subprocess.check_output(["sqlite3", str(FINAL_DB), sql]).decode().splitlines()
    return out


def verify(root: Path):
    prefix = str(root)
    name = root.name

    # Lists
    fs_list = collect_fs_list(root)
    db_list = load_db_paths(prefix)

    # Missing = on FS but not in DB
    missing = sorted(set(fs_list) - set(db_list))

    # Duplicates-already-present = in DB before merge
    duplicates = sorted(set(db_list) - set(fs_list))

    # Write reports
    report_dir = REPORT_DIR / name
    report_dir.mkdir(parents=True, exist_ok=True)

    write_list(report_dir / "fs.txt", fs_list)
    write_list(report_dir / "db.txt", db_list)
    write_list(report_dir / "missing.txt", missing)
    write_list(report_dir / "duplicates_in_db_before_merge.txt", duplicates)

    return {
        "fs_count": len(fs_list),
        "db_count": len(db_list),
        "missing": len(missing),
        "duplicates": len(duplicates),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        action="append",
        required=True,
        help="Directory to scan and merge into final DB"
    )
    args = parser.parse_args()

    ensure_dirs()

    for root_str in args.root:
        root = Path(root_str)

        print(f"\n=== PROCESSING {root} ===")

        print("→ Scanning…")
        temp_db = scan_to_temp_db(root)

        print("→ Merging into final DB…")
        merge_into_final(temp_db)

        print("→ Verifying…")
        summary = verify(root)

        print(f"""
DONE: {root}
  Files on disk:     {summary['fs_count']}
  Rows in DB:        {summary['db_count']}
  Missing in DB:     {summary['missing']}
  Already in DB:     {summary['duplicates']}
Reports under:        {REPORT_DIR/root.name}
""")


if __name__ == "__main__":
    main()
