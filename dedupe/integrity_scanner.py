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
from dedupe.utils.library import load_zone_paths, ensure_dedupe_zone

logger = logging.getLogger("dedupe")


def _scan_one_file(args: tuple[Path, bool, bool, Optional[str], Optional[str]]) -> Optional[AudioFile]:
    path, scan_integrity, scan_hash, library_name, zone = args
    try:
        return extract_metadata(
            path,
            scan_integrity=scan_integrity,
            scan_hash=scan_hash,
            library=library_name,
            zone=zone,
        )
    except Exception as e:
        logger.error(f"Failed to process {path}: {e}")
        return None


def scan_library(
    library_path: Path,
    db_path: Path,
    library: Optional[str] = None,
    zone: Optional[str] = None,
    incremental: bool = False,
    scan_integrity: bool = False,
    scan_hash: bool = False,
    recheck: bool = False,
    progress: bool = False,
    progress_interval: int = 250,
) -> None:
    """Scan a library folder and upsert file metadata into the integrity DB."""

    config = get_config()
    workers = config.get("integrity.parallel_workers", None)
    zone_paths = load_zone_paths(config)
    if zone_paths is None:
        raise ValueError("COMMUNE library zones are not configured.")

    library_name = library or config.get("library.name", "COMMUNE")
    if library_name:
        logger.info("Library tag: %s", library_name)

    if zone:
        if zone not in zone_paths.zones:
            raise ValueError(f"Unknown zone '{zone}' for {library_path}")
        zone_name = zone
    else:
        zone_name = ensure_dedupe_zone(library_path, zone_paths)

    if zone_name not in ("staging", "accepted"):
        raise ValueError(f"Zone '{zone_name}' is out of scope for dedupe.")

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

    # 3. Optionally skip unchanged files
    to_process = flac_files
    if incremental and not recheck:
        prefix = str(library_path)
        if not prefix.endswith("/"):
            prefix = prefix + "/"

        conn = get_connection(db_path)
        try:
            rows = conn.execute(
                "SELECT path, mtime, size, library, zone FROM files WHERE path LIKE ?",
                (prefix + "%",),
            ).fetchall()
        finally:
            conn.close()

        existing = {row["path"]: row for row in rows}
        changed: List[Path] = []
        skipped = 0

        for p in flac_files:
            key = str(p)
            row = existing.get(key)
            if not row:
                changed.append(p)
                continue

            try:
                st = p.stat()
                cur_mtime = float(st.st_mtime)
                cur_size = int(st.st_size)
            except Exception:
                changed.append(p)
                continue

            db_mtime = row["mtime"]
            db_size = row["size"]
            db_library = row["library"]
            db_zone = row["zone"]

            if library_name and db_library != library_name:
                changed.append(p)
                continue
            if zone_name and db_zone != zone_name:
                changed.append(p)
                continue

            if db_mtime == cur_mtime and db_size == cur_size:
                skipped += 1
            else:
                changed.append(p)

        to_process = changed
        logger.info(
            "Incremental scan: processing %d changed/new files (skipping %d unchanged).",
            len(to_process),
            skipped,
        )
        if not to_process:
            logger.info("No changes detected; nothing to do.")
            return

    scan_args = [(p, scan_integrity, scan_hash, library_name, zone_name) for p in to_process]

    # 4. Run Parallel Extraction
    start_time = time.time()
    results = process_map(
        _scan_one_file,
        scan_args,
        max_workers=workers,
        progress=progress,
        progress_interval=progress_interval,
    )
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
                    if progress and (count % 1000 == 0):
                        logger.info("DB upsert progress: %d records", count)
        logger.info(f"Upserted {count} records to database.")
    except Exception as e:
        logger.error(f"Database write failed: {e}")
        raise
    finally:
        conn.close()
