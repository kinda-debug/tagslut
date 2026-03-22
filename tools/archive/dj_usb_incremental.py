#!/usr/bin/env python3
"""
Weekly DJUSB sync: last 14d FLACs → DJUSB (deduped).
Logs: artifacts/dj_usb_incr_YYYYMMDD.log
"""
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
import logging
import tomllib

REPO_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = REPO_ROOT / "artifacts"
USB_PATH = Path("/Volumes/MUSIC/DJ")
LIB_PATH = Path("/Volumes/MUSIC/LIBRARY")
POLICY = str(REPO_ROOT / "config/dj/dj_curation_usb.yaml")
M3U = LOG_DIR / "incr_safe.m3u8"
DAYS = 14
DOWNLOAD_SOURCE = os.environ.get("DJUSB_SOURCE", "tidal").strip() or None
REQUIRE_DJ_MATERIAL = os.environ.get("DJUSB_REQUIRE_DJ_MATERIAL", "").strip().lower() in {"1", "true", "yes"}

def main():
    log_file = LOG_DIR / f"dj_usb_incr_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(message)s",
        handlers=[
            logging.FileHandler(log_file, mode="w"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    
    # Safety: Check mounts
    if not USB_PATH.exists():
        logging.error("DJUSB not mounted!")
        sys.exit(1)
    if not LIB_PATH.exists():
        logging.error("LIBRARY not mounted!")
        sys.exit(1)
    
    logging.info(
        "Incremental sync start | USB: %s | Lib: %s | Days: %s | source=%s | dj_only=%s",
        USB_PATH,
        LIB_PATH,
        DAYS,
        DOWNLOAD_SOURCE or "*",
        REQUIRE_DJ_MATERIAL,
    )

    # Resolve DB path
    db_path = os.environ.get("TAGSLUT_DB")
    if not db_path:
        config_path = REPO_ROOT / "config.toml"
        if config_path.exists():
            data = tomllib.loads(config_path.read_text(encoding="utf-8"))
            db_path = (data.get("db") or {}).get("path")
    if not db_path:
        logging.error("No DB path found (TAGSLUT_DB or config.toml)")
        sys.exit(1)
    db_path = str(Path(db_path).expanduser())

    # Build incremental list from DB (duration-safe, recent, library root)
    cutoff_ts = (datetime.now() - timedelta(days=DAYS)).timestamp()
    clauses = [
        "duration_status = 'ok'",
        "mtime >= ?",
        "path LIKE ?",
        "path LIKE '%.flac'",
    ]
    params = [cutoff_ts, f"{LIB_PATH}%"]
    if REQUIRE_DJ_MATERIAL:
        clauses.append("is_dj_material = 1")
    if DOWNLOAD_SOURCE:
        clauses.append("download_source = ?")
        params.append(DOWNLOAD_SOURCE)
    query = "SELECT path FROM files WHERE " + " AND ".join(clauses) + " ORDER BY mtime DESC"

    paths = []
    conn = sqlite3.connect(db_path)
    try:
        for row in conn.execute(query, params):
            paths.append(row[0])
    finally:
        conn.close()

    M3U.write_text("\n".join(paths) + ("\n" if paths else ""), encoding="utf-8")
    count = len(paths)
    logging.info(f"Found {count} new FLACs ({DAYS}d)")
    
    if count == 0:
        logging.info("Nothing new. Done.")
        return
    
    # Sync
    sync_cmd = [
        sys.executable, str(REPO_ROOT / "tools/dj_usb_sync.py"),
        "--source", str(M3U.resolve()),
        "--usb", str(USB_PATH),
        "--policy", POLICY
    ]
    result = subprocess.run(sync_cmd, capture_output=True, text=True)
    logging.info(f"Sync complete. STDOUT:\n{result.stdout}")
    if result.stderr:
        logging.warning(f"STDERR:\n{result.stderr}")
    
    # Cleanup
    M3U.unlink(missing_ok=True)
    logging.info("Incremental sync done.")

if __name__ == "__main__":
    main()
