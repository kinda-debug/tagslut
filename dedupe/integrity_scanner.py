import logging
import platform
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from dedupe.core.metadata import extract_metadata
from dedupe.storage.models import AudioFile
from dedupe.storage.queries import (
    finalize_scan_session,
    insert_file_scan_run,
    insert_scan_session,
    upsert_file,
)
from dedupe.storage.schema import get_connection, init_db
from dedupe.utils.paths import list_files
from dedupe.utils.parallel import process_map, ProcessMapResult
from dedupe.utils.config import get_config
from dedupe.utils.zones import ZoneManager, load_zone_manager

logger = logging.getLogger("dedupe")


@dataclass(frozen=True)
class ScanTask:
    path: Path
    run_integrity: bool
    run_hash: bool
    library_name: Optional[str]
    zone_manager: Optional[ZoneManager]
    index: int
    total: int


@dataclass(frozen=True)
class ScanResult:
    path: Path
    run_integrity: bool
    run_hash: bool
    file: Optional[AudioFile] = None
    error_class: Optional[str] = None
    error_message: Optional[str] = None


@dataclass(frozen=True)
class ScanOutcome:
    session_id: int
    status: str
    discovered: int
    queued: int
    skipped: int


def _print_scan_summary(
    *,
    session_id: int,
    status: str,
    discovered: int,
    queued: int,
    skipped: int,
    succeeded: int,
    failed: int,
    duration: float,
    scan_integrity: bool,
    scan_hash: bool,
    library_name: str,
    zone_name: str,  # Will be "auto" to indicate auto-assignment
    db_path: Path,
    failure_reasons: dict[str, int] | None = None,
    skip_reasons: dict[str, int] | None = None,
) -> None:
    """Print a human-readable summary of the scan results."""

    print("\n" + "=" * 70)
    status_line = {
        "completed": "✓ SCAN COMPLETE",
        "aborted": "⚠️  SCAN ABORTED",
        "failed": "✗ SCAN FAILED",
    }.get(status, status.upper())
    print(status_line)
    print("=" * 70)

    print(f"\nSession: {session_id}")
    print(f"Library: {library_name} / Zone: {zone_name} (auto-assigned)")
    print(f"Database: {db_path}")
    print(f"\nDiscovered: {discovered:,}")
    print(f"Queued:     {queued:,}")
    print(f"Skipped:    {skipped:,}")
    if skip_reasons:
        print("\nSkip breakdown:")
        for reason, count in sorted(skip_reasons.items(), key=lambda x: (-x[1], x[0])):
            print(f"  • {reason}: {count}")

    print(f"\nSucceeded:  {succeeded:,}")
    print(f"Failed:     {failed:,}")
    if failure_reasons:
        print("\nFailure breakdown:")
        for reason, count in sorted(failure_reasons.items(), key=lambda x: (-x[1], x[0])):
            print(f"  • {reason}: {count}")

    if duration > 0 and succeeded > 0:
        print(f"\nTime:       {duration:.1f}s ({succeeded/duration:.1f} files/sec)")
    else:
        print(f"\nTime:       {duration:.1f}s")

    print("\nChecks performed:")
    print("  • Metadata extraction: ✓")
    print("  • STREAMINFO MD5:      ✓ (fast hash)")
    print(f"  • Full-file SHA256:    {'✓' if scan_hash else '✗'}")
    print(f"  • Integrity (flac -t): {'✓' if scan_integrity else '✗'}")

    if status == "aborted":
        print("\n⚠️  Partial results were committed in batches before interruption")
        print("Re-run with --incremental to resume from where you left off")
    elif status == "completed":
        print("\n✓ All changes committed to database")
        if failed > 0:
            print("\n⚠️  Some files failed to process - check logs for details")

    print("=" * 70 + "\n")


def _scan_one_file(task: ScanTask) -> ScanResult:
    path = task.path
    scan_integrity = task.run_integrity
    scan_hash = task.run_hash
    index = task.index
    total = task.total

    # Print visual separator and file info with progress
    print("\n" + "─" * 70)
    print(f"📁 [{index}/{total}] {path.name}")
    print(f"   {path.parent}")

    try:
        result = extract_metadata(
            path,
            scan_integrity=scan_integrity,
            scan_hash=scan_hash,
            library=task.library_name,
            zone_manager=task.zone_manager,
        )

        # Show what was extracted
        print(f"   ✓ Metadata extracted")
        if result.streaminfo_md5:
            print(f"   ✓ STREAMINFO MD5: {result.streaminfo_md5[:8]}...")
        if result.sha256:
            print(f"   ✓ Full hash: {result.sha256[:8]}...")
        if scan_integrity:
            status = "✓" if result.flac_ok else "✗"
            state = result.integrity_state or "unknown"
            print(f"   {status} Integrity: {state}")
        if result.duration:
            print(f"   ♫ Duration: {result.duration:.1f}s, {result.sample_rate}Hz, {result.bit_depth}bit")

        return ScanResult(
            path=path,
            run_integrity=scan_integrity,
            run_hash=scan_hash,
            file=result,
        )

    except ValueError as e:
        print(f"   ✗ Invalid FLAC: {e}")
        logger.error(f"Failed to process {path}: {e}")
        return ScanResult(
            path=path,
            run_integrity=scan_integrity,
            run_hash=scan_hash,
            error_class="InvalidFLAC",
            error_message=f"{str(e)[:120]}",
        )
    except FileNotFoundError as e:
        print(f"   ✗ File not found")
        logger.error(f"File not found {path}: {e}")
        return ScanResult(
            path=path,
            run_integrity=scan_integrity,
            run_hash=scan_hash,
            error_class="FileNotFound",
            error_message="File not found",
        )
    except PermissionError as e:
        print(f"   ✗ Permission denied")
        logger.error(f"Permission denied {path}: {e}")
        return ScanResult(
            path=path,
            run_integrity=scan_integrity,
            run_hash=scan_hash,
            error_class="PermissionDenied",
            error_message="Permission denied",
        )
    except Exception as e:
        print(f"   ✗ Error: {type(e).__name__}: {str(e)[:50]}")
        logger.error(f"Failed to process {path}: {e}")
        return ScanResult(
            path=path,
            run_integrity=scan_integrity,
            run_hash=scan_hash,
            error_class=type(e).__name__,
            error_message=f"Unexpected error: {str(e)[:120]}",
        )


def scan_library(
    library_path: Optional[Path],
    db_path: Path,
    db_source: str = "unknown",
    library: Optional[str] = None,
    incremental: bool = True,
    scan_integrity: bool = False,
    scan_hash: bool = False,
    recheck: bool = False,
    force_all: bool = False,
    progress: bool = False,
    progress_interval: int = 250,
    specific_paths: Optional[List[Path]] = None,
    limit: Optional[int] = None,
    stale_days: Optional[int] = None,
    paths_source: Optional[str] = None,
    paths_from_file: Optional[Path] = None,
    create_db: bool = False,
    allow_repo_db: bool = False,
    error_log: Path | None = None,
) -> ScanOutcome:
    """Scan a library folder and upsert file metadata into the integrity DB.

    If specific_paths is provided, scans only those files instead of discovering from library_path.
    Zone assignment is now automatic based on scan results and file location.
    """

    db_path = db_path.expanduser().resolve()
    if library_path:
        library_path = library_path.expanduser().resolve()

    config = get_config()
    workers = config.get("integrity.parallel_workers", None)
    db_write_batch_size = config.get("integrity.db_write_batch_size", 500)
    db_flush_interval = config.get("integrity.db_flush_interval_seconds", None)
    if db_flush_interval is None:
        db_flush_interval = config.get("integrity.db_flush_interval", 60)
    if db_flush_interval is not None:
        try:
            db_flush_interval = int(db_flush_interval)
        except (TypeError, ValueError):
            db_flush_interval = 60
    if db_flush_interval is not None and db_flush_interval < 0:
        db_flush_interval = 0

    zone_manager = load_zone_manager(config=getattr(config, "_data", None))

    flac_files: list[Path]
    # Handle specific paths mode (e.g., from --paths-from-file)
    if specific_paths:
        logger.info("Processing %d specific paths", len(specific_paths))
        flac_files = [p for p in specific_paths if p.suffix.lower() == ".flac"]
        library_name = library or "adhoc"
        root_path = None
        paths_source = paths_source or "paths-from-file"
    else:
        if not library_path:
            raise ValueError("Either library_path or specific_paths must be provided")

        library_name = library or config.get("library.name", "COMMUNE")
        if library_name:
            logger.info("Library tag: %s", library_name)

        root_path = library_path
        logger.info("Scanning library: %s", library_path)
        logger.info("Using DB: %s (cwd=%s)", db_path, Path.cwd())
        flac_files = list(list_files(library_path, {".flac"}))

    # Zone is now auto-assigned based on scan results
    zone_name = "auto"  # For logging purposes only

    # 1. Initialize DB
    conn = get_connection(
        db_path,
        purpose="write",
        allow_create=create_db,
        allow_repo_db=allow_repo_db,
    )
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
                " (this DB has 'library_files' so it looks like a legacy library DB; "
                "use the canonical integrity DB resolved via --db/DEDUPE_DB/config)"
            )
        raise RuntimeError(
            f"Integrity DB schema not initialized: missing 'files' table in {db_path}{hint}"
        )
    conn.close()

    total_discovered = len(flac_files)
    logger.info("Found %d FLAC files.", total_discovered)

    if not flac_files:
        conn = get_connection(
            db_path,
            purpose="write",
            allow_create=create_db,
            allow_repo_db=allow_repo_db,
        )
        try:
            session_id = insert_scan_session(
                conn,
                db_path=db_path,
                library=library_name,
                zone=zone_name,
                root_path=root_path,
                paths_source=paths_source,
                paths_from_file=str(paths_from_file) if paths_from_file else None,
                scan_integrity=scan_integrity,
                scan_hash=scan_hash,
                recheck=recheck,
                incremental=incremental,
                force_all=force_all,
                discovered=0,
                considered=0,
                skipped=0,
                scan_limit=limit,
                host=platform.node(),
            )
            ended_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            finalize_scan_session(
                conn,
                session_id=session_id,
                status="completed",
                succeeded=0,
                failed=0,
                ended_at=ended_at,
            )
            conn.commit()
        finally:
            conn.close()
        _print_scan_summary(
            session_id=session_id,
            status="completed",
            discovered=0,
            queued=0,
            skipped=0,
            succeeded=0,
            failed=0,
            duration=0.0,
            scan_integrity=scan_integrity,
            scan_hash=scan_hash,
            library_name=library_name,
            zone_name=zone_name,
            db_path=db_path,
        )
        return ScanOutcome(
            session_id=session_id,
            status="completed",
            discovered=0,
            queued=0,
            skipped=0,
        )

    def _is_stale_by_time(checked_at: Optional[str]) -> bool:
        if not (recheck and stale_days and checked_at):
            return False
        try:
            parsed = datetime.fromisoformat(checked_at)
        except ValueError:
            return True
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - parsed
        return age.days >= stale_days

    def _infer_checksums(row: sqlite3.Row | None) -> tuple[Optional[str], Optional[str]]:
        if row is None:
            return None, None
        streaminfo_md5 = row["streaminfo_md5"]
        sha256 = row["sha256"]
        checksum = row["checksum"]
        if not streaminfo_md5 and checksum and checksum.startswith("streaminfo:"):
            streaminfo_md5 = checksum.split(":", 1)[1]
        if not sha256 and checksum:
            if checksum.startswith("sha256:"):
                sha256 = checksum.split(":", 1)[1]
            elif checksum not in ("NOT_SCANNED",) and not checksum.startswith("streaminfo:"):
                sha256 = checksum
        return streaminfo_md5, sha256

    def _metadata_missing(row: sqlite3.Row | None) -> bool:
        if not row:
            return True
        if row["mtime"] is None or row["size"] is None:
            return True
        checksum = row["checksum"]
        return not checksum or checksum == "NOT_SCANNED"

    def _integrity_done(row: sqlite3.Row | None) -> bool:
        if not row:
            return False
        return row["integrity_checked_at"] is not None

    def _integrity_failed(row: sqlite3.Row | None) -> bool:
        if not row:
            return False
        if row["integrity_checked_at"] is None:
            return False
        if row["flac_ok"] == 0:
            return True
        return row["integrity_state"] in ("corrupt", "recoverable")

    # 2. Load existing rows
    conn = get_connection(
        db_path,
        purpose="read",
        allow_repo_db=allow_repo_db,
    )
    try:
        if specific_paths:
            existing_rows = {}
            chunk_size = 900
            columns = (
                "path, mtime, size, library, zone, checksum, flac_ok, integrity_state, "
                "integrity_checked_at, streaminfo_md5, sha256, streaminfo_checked_at, sha256_checked_at"
            )
            for i in range(0, len(flac_files), chunk_size):
                chunk = [str(p) for p in flac_files[i : i + chunk_size]]
                placeholders = ",".join(["?"] * len(chunk))
                rows = conn.execute(
                    f"SELECT {columns} FROM files WHERE path IN ({placeholders})",
                    chunk,
                ).fetchall()
                existing_rows.update({row["path"]: row for row in rows})
        else:
            prefix = str(library_path)
            if not prefix.endswith("/"):
                prefix = prefix + "/"
            rows = conn.execute(
                """
                SELECT path, mtime, size, library, zone, checksum, flac_ok, integrity_state,
                       integrity_checked_at, streaminfo_md5, sha256, streaminfo_checked_at,
                       sha256_checked_at
                FROM files WHERE path LIKE ?
                """,
                (prefix + "%",),
            ).fetchall()
            existing_rows = {row["path"]: row for row in rows}
    finally:
        conn.close()

    # 3. Determine scan plan
    scan_tasks: List[ScanTask] = []
    skip_reasons: dict[str, int] = {"up_to_date": 0}

    for idx, path in enumerate(flac_files, start=1):
        key = str(path)
        row = existing_rows.get(key)

        try:
            st = path.stat()
            cur_mtime = float(st.st_mtime)
            cur_size = int(st.st_size)
        except Exception:
            cur_mtime = None
            cur_size = None

        file_changed = row is None
        if cur_mtime is None or cur_size is None:
            file_changed = True
        elif row and cur_mtime is not None and cur_size is not None:
            if row["mtime"] != cur_mtime or row["size"] != cur_size:
                file_changed = True
        if row and library_name and row["library"] != library_name:
            file_changed = True
        # Zone reassignment check removed - zones are now auto-assigned during each scan
        # based on integrity results and file location

        integrity_stale = _is_stale_by_time(row["integrity_checked_at"] if row else None)
        streaminfo_md5, sha256 = _infer_checksums(row) if row else (None, None)
        hash_stale = _is_stale_by_time(row["sha256_checked_at"] if row else None)

        needs_metadata = force_all or (not incremental) or file_changed or _metadata_missing(row)
        needs_integrity = False
        if scan_integrity:
            if force_all:
                needs_integrity = True
            else:
                needs_integrity = (not _integrity_done(row)) or file_changed
                if recheck:
                    needs_integrity = needs_integrity or _integrity_failed(row) or integrity_stale

        needs_hash = False
        if scan_hash:
            if force_all:
                needs_hash = True
            else:
                needs_hash = (sha256 is None) or file_changed
                if recheck:
                    needs_hash = needs_hash or hash_stale

        if needs_metadata or needs_integrity or needs_hash:
            scan_tasks.append(
                ScanTask(
                    path=path,
                    run_integrity=needs_integrity,
                    run_hash=needs_hash,
                    library_name=library_name,
                    zone_manager=zone_manager,
                    index=0,
                    total=0,
                )
            )
        else:
            skip_reasons["up_to_date"] += 1

    if limit and limit > 0 and len(scan_tasks) > limit:
        skip_reasons["limit"] = len(scan_tasks) - limit
        scan_tasks = scan_tasks[:limit]

    if scan_tasks:
        total_tasks = len(scan_tasks)
        scan_tasks = [
            ScanTask(
                path=task.path,
                run_integrity=task.run_integrity,
                run_hash=task.run_hash,
                library_name=task.library_name,
                zone_manager=task.zone_manager,
                index=idx + 1,
                total=total_tasks,
            )
            for idx, task in enumerate(scan_tasks)
        ]

    skipped = sum(skip_reasons.values())
    queued = len(scan_tasks)
    considered = total_discovered

    # 4. Create scan session
    conn = get_connection(
        db_path,
        purpose="write",
        allow_create=create_db,
        allow_repo_db=allow_repo_db,
    )
    try:
        session_id = insert_scan_session(
            conn,
            db_path=db_path,
            library=library_name,
            zone=zone_name,
            root_path=root_path,
            paths_source=paths_source,
            paths_from_file=str(paths_from_file) if paths_from_file else None,
            scan_integrity=scan_integrity,
            scan_hash=scan_hash,
            recheck=recheck,
            incremental=incremental,
            force_all=force_all,
            discovered=total_discovered,
            considered=considered,
            skipped=skipped,
            scan_limit=limit,
            host=platform.node(),
        )
        conn.commit()
    finally:
        conn.close()

    print("\n" + "=" * 70)
    print("SCAN PLAN")
    print("=" * 70)
    print(f"Database: {db_path} (source={db_source})")
    print(f"Session:  {session_id}")
    print(f"Discovered: {total_discovered:,}")
    print(f"Queued:     {queued:,}")
    print(f"Skipped:    {skipped:,}")
    for reason, count in sorted(skip_reasons.items(), key=lambda x: (-x[1], x[0])):
        if count:
            print(f"  • {reason}: {count}")
    if limit:
        print(f"Limit:      {limit}")
    print("=" * 70 + "\n")

    if not scan_tasks:
        ended_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        conn = get_connection(
            db_path,
            purpose="write",
            allow_create=create_db,
            allow_repo_db=allow_repo_db,
        )
        try:
            finalize_scan_session(
                conn,
                session_id=session_id,
                status="completed",
                succeeded=0,
                failed=0,
                ended_at=ended_at,
            )
            conn.commit()
        finally:
            conn.close()
        _print_scan_summary(
            session_id=session_id,
            status="completed",
            discovered=total_discovered,
            queued=0,
            skipped=skipped,
            succeeded=0,
            failed=0,
            duration=0.0,
            scan_integrity=scan_integrity,
            scan_hash=scan_hash,
            library_name=library_name,
            zone_name=zone_name,
            db_path=db_path,
            skip_reasons=skip_reasons,
        )
        return ScanOutcome(
            session_id=session_id,
            status="completed",
            discovered=total_discovered,
            queued=0,
            skipped=skipped,
        )

    # 5. Run Parallel Extraction
    start_time = time.time()
    process_result_raw = process_map(
        _scan_one_file,
        scan_tasks,
        max_workers=workers,
        progress=progress,
        progress_interval=progress_interval,
        return_interrupt_status=True,
    )
    if isinstance(process_result_raw, ProcessMapResult):
        results = process_result_raw.results
        interrupted = process_result_raw.interrupted
    else:
        results = process_result_raw
        interrupted = False
    if error_log:
        try:
            error_log_path = error_log
            error_log_path.parent.mkdir(parents=True, exist_ok=True)
            with error_log_path.open("a", encoding="utf-8") as log_handle:
                for result in results:
                    if result.error_class:
                        message = result.error_message or ""
                        log_handle.write(f"{result.error_class}: {result.path} {message}\n")
        except Exception as exc:
            logger.warning("Unable to write error log %s: %s", error_log, exc)
    duration = time.time() - start_time
    logger.info("Metadata extraction complete in %.2fs", duration)

    # 6. Write to DB with chunked commits + savepoints
    conn = get_connection(
        db_path,
        purpose="write",
        allow_create=create_db,
        allow_repo_db=allow_repo_db,
    )
    succeeded = 0
    failed = 0
    failure_reasons: dict[str, int] = {}
    status = "completed"
    last_flush_time = time.monotonic()
    try:
        conn.execute("BEGIN")
        for idx, result in enumerate(results, start=1):
            conn.execute("SAVEPOINT scan_row")
            try:
                if result.file:
                    upsert_file(conn, result.file)
                    insert_file_scan_run(
                        conn,
                        session_id=session_id,
                        path=result.path,
                        file=result.file,
                        outcome="succeeded",
                        checked_metadata=True,
                        checked_streaminfo=True,
                        checked_integrity=result.run_integrity,
                        checked_hash=result.run_hash,
                    )
                    succeeded += 1
                else:
                    insert_file_scan_run(
                        conn,
                        session_id=session_id,
                        path=result.path,
                        error_class=result.error_class,
                        error_message=result.error_message,
                        outcome="failed",
                        checked_metadata=False,
                        checked_streaminfo=False,
                        checked_integrity=False,
                        checked_hash=False,
                    )
                    failed += 1
                    reason = result.error_class or "UnknownError"
                    failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
                conn.execute("RELEASE SAVEPOINT scan_row")
            except Exception as row_error:
                conn.execute("ROLLBACK TO SAVEPOINT scan_row")
                conn.execute("RELEASE SAVEPOINT scan_row")
                failed += 1
                reason = type(row_error).__name__
                failure_reasons[reason] = failure_reasons.get(reason, 0) + 1

            # Commit if we reached batch size OR flush interval has passed
            time_due = False
            if db_flush_interval:
                time_due = (time.monotonic() - last_flush_time) >= db_flush_interval
            if idx % db_write_batch_size == 0 or time_due:
                conn.commit()
                conn.execute("BEGIN")
                last_flush_time = time.monotonic()
    except KeyboardInterrupt:
        logger.warning("Interrupted by user during DB write")
        status = "aborted"
        conn.rollback()
        interrupted = True
    except Exception as e:
        logger.error("Database write failed: %s", e)
        status = "failed"
        conn.rollback()
        raise
    finally:
        if status != "failed":
            conn.commit()
        conn.close()

    if interrupted and status == "completed":
        status = "aborted"

    ended_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn = get_connection(
        db_path,
        purpose="write",
        allow_create=create_db,
        allow_repo_db=allow_repo_db,
    )
    try:
        finalize_scan_session(
            conn,
            session_id=session_id,
            status=status,
            succeeded=succeeded,
            failed=failed,
            ended_at=ended_at,
            updated=succeeded,
        )
        conn.commit()
    finally:
        conn.close()

    _print_scan_summary(
        session_id=session_id,
        status=status,
        discovered=total_discovered,
        queued=queued,
        skipped=skipped,
        succeeded=succeeded,
        failed=failed,
        duration=duration,
        scan_integrity=scan_integrity,
        scan_hash=scan_hash,
        library_name=library_name,
        zone_name=zone_name,
        db_path=db_path,
        failure_reasons=failure_reasons if failure_reasons else None,
        skip_reasons=skip_reasons,
    )

    return ScanOutcome(
        session_id=session_id,
        status=status,
        discovered=total_discovered,
        queued=queued,
        skipped=skipped,
    )
