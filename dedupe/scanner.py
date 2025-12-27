import logging
import time
from pathlib import Path
from typing import List, Optional

from dedupe.core.metadata import extract_metadata
from dedupe.storage.models import AudioFile
from dedupe.storage.queries import upsert_file
from dedupe.storage.schema import get_connection, init_db
from dedupe.utils.paths import list_files
from dedupe.utils.parallel import process_map
from dedupe.utils.config import get_config

logger = logging.getLogger("dedupe")

def scan_library(
    library_path: Path, 
    db_path: Path,
    scan_integrity: bool = False,
    scan_hash: bool = False,
    recheck: bool = False
) -> None:
    """
    Scans a library folder and updates the SQLite database.

    Args:
        library_path: Root folder to scan.
        db_path: Path to the SQLite database.
        scan_integrity: Run 'flac -t' on files.
        scan_hash: Calculate SHA256 checksums.
        recheck: If True, re-scan files even if they are in DB (not fully impl yet).
    """
    config = get_config()
    workers = config.get("integrity.parallel_workers", None)

    logger.info(f"Scanning library: {library_path}")
    
    # 1. Initialize DB
    conn = get_connection(db_path)
    init_db(conn)
    conn.close() 

    # 2. Find files
    flac_files = list(list_files(library_path, {".flac"}))
    logger.info(f"Found {len(flac_files)} FLAC files.")

    if not flac_files:
        return

    # 3. Define the worker function (must be pickleable)
    def process_one(path: Path) -> Optional[AudioFile]:
        try:
            return extract_metadata(
                path, 
                scan_integrity=scan_integrity, 
                scan_hash=scan_hash
            )
        except Exception as e:
            logger.error(f"Failed to process {path}: {e}")
            return None

    # 4. Run Parallel Extraction
    start_time = time.time()
    results = process_map(process_one, flac_files, max_workers=workers)
    duration = time.time() - start_time
    
    logger.info(f"Metadata extraction complete in {duration:.2f}s")

    # 5. Write to DB (Serial operation)
    conn = get_connection(db_path)
    count = 0
    try:
        with conn: 
            for audio_file in results:
                if audio_file:
                    upsert_file(conn, audio_file)
                    count += 1
        logger.info(f"Upserted {count} records to database.")
    except Exception as e:
        logger.error(f"Database write failed: {e}")
    finally:
        conn.close()
