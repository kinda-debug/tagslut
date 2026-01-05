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


def _print_scan_summary(
    total: int,
    succeeded: int,
    failed: int,
    duration: float,
    scan_integrity: bool,
    scan_hash: bool,
    library_name: str,
    zone_name: str,
    db_path: Path,
    interrupted: bool,
    failure_reasons: dict[str, int] = None
) -> None:
    """Print a human-readable summary of the scan results."""
    
    print("\n" + "=" * 70)
    if interrupted:
        print("⚠️  SCAN INTERRUPTED")
    else:
        print("✓ SCAN COMPLETE")
    print("=" * 70)
    
    print(f"\nLibrary: {library_name} / Zone: {zone_name}")
    print(f"Database: {db_path}")
    print(f"\nAttempted:  {total:,} files")
    print(f"Succeeded:  {succeeded:,} files")
    if failed > 0:
        print(f"Failed:     {failed:,} files")
        if failure_reasons:
            print(f"\nFailure breakdown:")
            for reason, count in sorted(failure_reasons.items(), key=lambda x: -x[1]):
                print(f"  • {reason}: {count}")
    if interrupted:
        print(f"Skipped:    {total - succeeded - failed:,} files (interrupted before processing)")
    
    if duration > 0 and succeeded > 0:
        print(f"\nTime:       {duration:.1f}s ({succeeded/duration:.1f} files/sec)")
    else:
        print(f"\nTime:       {duration:.1f}s")
    
    print(f"\nChecks performed:")
    print(f"  • Metadata extraction: ✓")
    print(f"  • STREAMINFO MD5:      ✓ (fast hash)")
    print(f"  • Full-file SHA256:    {'✓' if scan_hash else '✗'}")
    print(f"  • Integrity (flac -t): {'✓' if scan_integrity else '✗'}")
    
    if interrupted:
        print(f"\n⚠️  Transaction rolled back - no partial data committed")
        print(f"Re-run with --incremental to resume from where you left off")
    else:
        print(f"\n✓ All changes committed to database")
        if failed > 0:
            print(f"\n⚠️  {failed} files failed to process - check logs for details")
        print(f"\nNext steps:")
        if not scan_integrity and not scan_hash:
            print(f"  • This was a fast Phase 1 scan (STREAMINFO MD5 only)")
            print(f"  • Run duplicate clustering: tools/decide/recommend.py")
            print(f"  • Verify winners: --paths-from-file winners.txt --check-integrity")
        elif scan_integrity:
            print(f"  • Check for corrupt files: SELECT path FROM files WHERE flac_ok=0")
            print(f"  • Review integrity_state in database")
        else:
            print(f"  • Data ready for analysis")
    
    print("=" * 70 + "\n")


def _scan_one_file(args: tuple[Path, bool, bool, Optional[str], Optional[str], int, int]) -> Optional[AudioFile | tuple[None, str]]:
    path, scan_integrity, scan_hash, library_name, zone, index, total = args
    
    # Print visual separator and file info with progress
    print("\n" + "─" * 70)
    print(f"📁 [{index}/{total}] {path.name}")
    print(f"   {path.parent}")
    
    try:
        result = extract_metadata(
            path,
            scan_integrity=scan_integrity,
            scan_hash=scan_hash,
            library=library_name,
            zone=zone,
        )
        
        # Show what was extracted
        print(f"   ✓ Metadata extracted")
        if result.checksum and result.checksum.startswith("streaminfo:"):
            print(f"   ✓ STREAMINFO MD5: {result.checksum[11:19]}...")
        if result.checksum and result.checksum.startswith("sha256:"):
            print(f"   ✓ Full hash: {result.checksum[7:15]}...")
        if scan_integrity:
            status = "✓" if result.flac_ok else "✗"
            # Handle both string and tuple integrity_state
            state = result.integrity_state[0] if isinstance(result.integrity_state, tuple) else result.integrity_state
            print(f"   {status} Integrity: {state}")
        if result.duration:
            print(f"   ♫ Duration: {result.duration:.1f}s, {result.sample_rate}Hz, {result.bit_depth}bit")
        
        return result
        
    except ValueError as e:
        print(f"   ✗ Invalid FLAC: {e}")
        logger.error(f"Failed to process {path}: {e}")
        return (None, f"Invalid FLAC: {str(e)[:50]}")
    except FileNotFoundError as e:
        print(f"   ✗ File not found")
        logger.error(f"File not found {path}: {e}")
        return (None, "File not found")
    except PermissionError as e:
        print(f"   ✗ Permission denied")
        logger.error(f"Permission denied {path}: {e}")
        return (None, "Permission denied")
    except Exception as e:
        print(f"   ✗ Error: {type(e).__name__}: {str(e)[:50]}")
        logger.error(f"Failed to process {path}: {e}")
        return (None, f"Unexpected error: {type(e).__name__}")


def scan_library(
    library_path: Optional[Path],
    db_path: Path,
    library: Optional[str] = None,
    zone: Optional[str] = None,
    incremental: bool = False,
    scan_integrity: bool = False,
    scan_hash: bool = False,
    recheck: bool = False,
    progress: bool = False,
    progress_interval: int = 250,
    specific_paths: Optional[List[Path]] = None,
    limit: Optional[int] = None,
) -> None:
    """Scan a library folder and upsert file metadata into the integrity DB.
    
    If specific_paths is provided, scans only those files instead of discovering from library_path.
    """

    db_path = db_path.expanduser().resolve()
    if library_path:
        library_path = library_path.expanduser().resolve()

    config = get_config()
    workers = config.get("integrity.parallel_workers", None)
    
    # Handle specific paths mode (e.g., from --paths-from-file)
    if specific_paths:
        logger.info(f"Processing {len(specific_paths)} specific paths")
        all_files = [p for p in specific_paths if p.suffix.lower() == '.flac']
        library_name = library or "adhoc"
        zone_name = zone or "adhoc"
        zone_paths = None  # Not needed for specific paths
    else:
        if not library_path:
            raise ValueError("Either library_path or specific_paths must be provided")
        
        zone_paths = load_zone_paths(config)
        if zone_paths is None:
            raise ValueError("COMMUNE library zones are not configured.")

        library_name = library or config.get("library.name", "COMMUNE")
        if library_name:
            logger.info("Library tag: %s", library_name)

        if zone:
            # Accept any zone name for multi-source scanning
            zone_name = zone
        else:
            zone_name = ensure_dedupe_zone(library_path, zone_paths)

        logger.info(f"Scanning library: {library_path}")
        logger.info("Using DB: %s (cwd=%s)", db_path, Path.cwd())

    # 1. Initialize DB
    conn = get_connection(db_path)
    init_db(conn)

    table = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='files'"
    ).fetchone()
    if not table:
        legacy = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='library_files'"
        ).fetchone()
        conn.close()
        hint = ""
        if legacy:
            hint = (
                " (this DB has 'library_files' so it looks like the legacy library DB; "
                "did you mean to use artifacts/db/music.db?)"
            )
        raise RuntimeError(
            f"Integrity DB schema not initialized: missing 'files' table in {db_path}{hint}"
        )
    conn.close()

    # 2. Find files (or use provided specific_paths)
    if specific_paths:
        flac_files = all_files  # Already filtered to .flac
    else:
        flac_files = list(list_files(library_path, {".flac"}))
    
    total_discovered = len(flac_files)
    logger.info(f"Found {total_discovered} FLAC files.")

    if not flac_files:
        return
    
    # Show global progress before starting
    conn_temp = get_connection(db_path)
    already_in_db = conn_temp.execute(
        "SELECT COUNT(*) FROM files WHERE library = ? AND zone = ?",
        (library_name, zone_name)
    ).fetchone()[0]
    conn_temp.close()
    
    print("\n" + "=" * 70)
    print("GLOBAL PROGRESS")
    print("=" * 70)
    print(f"Total files in library:     {total_discovered:,}")
    print(f"Already in database:        {already_in_db:,}")
    print(f"Remaining to process:       {total_discovered - already_in_db:,}")
    if limit:
        print(f"This batch limit:           {limit}")
    print("=" * 70 + "\n")

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

    # Apply batch limit if specified
    if limit and limit > 0:
        original_count = len(to_process)
        to_process = to_process[:limit]
        logger.info(f"Batch limit: processing first {len(to_process)} of {original_count} files")

    # Integrity scope filtering: don't re-check files with existing integrity status
    # unless --recheck is explicitly set
    def should_run_integrity(path: Path, scan_integrity: bool, recheck: bool) -> bool:
        if not scan_integrity:
            return False
        if recheck:
            return True
        # Only run integrity check if no prior status exists
        key = str(path)
        row = existing.get(key)
        return row is None or row.get("integrity_state") is None

    scan_args = [
        (p, should_run_integrity(p, scan_integrity, recheck), scan_hash, library_name, zone_name, idx + 1, limit if limit else len(to_process))
        for idx, p in enumerate(to_process)
    ]

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

    # 5. Write to DB (Serial operation with transaction safety)
    conn = get_connection(db_path)
    count = 0
    failed = 0
    failure_reasons = {}
    try:
        with conn:
            for result in results:
                if result and not isinstance(result, tuple):
                    upsert_file(conn, result)
                    count += 1
                    if progress and (count % 1000 == 0):
                        logger.info("DB upsert progress: %d records", count)
                elif isinstance(result, tuple):
                    # Failed with reason
                    _, reason = result
                    failed += 1
                    failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
                else:
                    # Failed without specific reason
                    failed += 1
                    failure_reasons["Unknown error"] = failure_reasons.get("Unknown error", 0) + 1
        logger.info(f"Upserted {count} records to database.")
        
        # Show updated global progress
        already_in_db_after = conn.execute(
            "SELECT COUNT(*) FROM files WHERE library = ? AND zone = ?",
            (library_name, zone_name)
        ).fetchone()[0]
        
        print("\n" + "=" * 70)
        print("UPDATED GLOBAL PROGRESS")
        print("=" * 70)
        print(f"Total files in library:     {total_discovered:,}")
        print(f"Now in database:            {already_in_db_after:,}")
        print(f"Remaining to process:       {total_discovered - already_in_db_after:,}")
        completion_pct = (already_in_db_after / total_discovered * 100) if total_discovered > 0 else 0
        print(f"Completion:                 {completion_pct:.1f}%")
        print("=" * 70 + "\n")
        
        # Human-readable summary
        _print_scan_summary(
            total=len(to_process),
            succeeded=count,
            failed=failed,
            duration=duration,
            scan_integrity=scan_integrity,
            scan_hash=scan_hash,
            library_name=library_name,
            zone_name=zone_name,
            db_path=db_path,
            interrupted=False,
            failure_reasons=failure_reasons if failure_reasons else None
        )
    except KeyboardInterrupt:
        logger.warning("Interrupted by user, rolling back DB transaction")
        conn.rollback()
        _print_scan_summary(
            total=len(to_process),
            succeeded=count,
            failed=len(results) - count,
            duration=time.time() - start_time,
            scan_integrity=scan_integrity,
            scan_hash=scan_hash,
            library_name=library_name,
            zone_name=zone_name,
            db_path=db_path,
            interrupted=True,
            failure_reasons=failure_reasons if failure_reasons else None
        )
        raise
    except Exception as e:
        logger.error(f"Database write failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()
