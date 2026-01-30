import sys
import argparse
import time
from pathlib import Path

# Ensure we can import dedupe from root
sys.path.insert(0, str(Path(__file__).parents[2]))

from dedupe.integrity_scanner import scan_library
from dedupe.core.metadata import extract_metadata
from dedupe.utils import env_paths
from dedupe.utils.paths import list_files
from dedupe.utils.cli_helper import configure_execution
from dedupe.utils.config import get_config
from dedupe.utils.db import resolve_db_path


def main():
    parser = argparse.ArgumentParser(description="Scans a library folder for FLAC files and populates the database.")
    parser.add_argument("library_path", nargs="?", help="Path to the library to scan.")
    parser.add_argument("--db", required=False, help="Path to SQLite database.")
    parser.add_argument("--create-db", action="store_true", help="Allow creating a new DB file.")
    parser.add_argument("--paths-from-file", help="Read specific file paths from this file (one per line).")
    parser.add_argument("--library", help="Logical library name (e.g. COMMUNE).")
    parser.add_argument("--no-incremental", action="store_true", help="Disable incremental scanning.")
    parser.add_argument("--recheck", action="store_true", help="Re-run requested checks for missing/stale/failed files.")
    parser.add_argument("--force-all", action="store_true", help="Force all requested checks on all files.")
    parser.add_argument("--progress", action="store_true", help="Log periodic progress.")
    parser.add_argument("--progress-interval", type=int, default=250, help="Progress interval in number of files.")
    parser.add_argument("--limit", type=int, help="Stop after processing N files.")
    parser.add_argument("--check-integrity", action="store_true", help="Run flac -t verification.")
    parser.add_argument("--check-hash", action="store_true", help="Calculate full-file SHA256.")
    parser.add_argument("--hard-skip", action="store_true", help="Alias for --no-check-integrity --no-check-hash.")
    parser.add_argument("--allow-repo-db", action="store_true", help="Allow writing to a repo-local DB path.")
    parser.add_argument("--stale-days", type=int, help="Treat results older than N days as stale.")
    parser.add_argument("--error-log", help="Path to append scan error details.")
    parser.add_argument("--standalone", action="store_true", help="Run without a database (prints summary only).")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging.")
    parser.add_argument("--config", help="Path to a TOML config file.")

    args = parser.parse_args()
    
    app_config = get_config(Path(args.config) if args.config else None)
    configure_execution(args.verbose, args.config)

    if not args.library_path and not args.paths_from_file:
        parser.error("Either library_path or --paths-from-file must be provided.")

    if args.library_path and args.paths_from_file:
        parser.error("Cannot use both library_path and --paths-from-file.")

    if args.hard_skip:
        args.check_integrity = False
        args.check_hash = False

    specific_paths = None
    if args.paths_from_file:
        paths_file = Path(args.paths_from_file).expanduser().resolve()
        print(f"Loading paths from: {paths_file}")
        with open(paths_file) as f:
            specific_paths = [Path(line.strip()).expanduser().resolve() for line in f if line.strip()]
        print(f"Loaded {len(specific_paths)} paths to scan")
        lib_path = None
    else:
        lib_path = Path(args.library_path).expanduser().resolve()

    error_log_path = Path(args.error_log) if args.error_log else env_paths.get_log_path("scan_errors.log")
    error_log_path.parent.mkdir(parents=True, exist_ok=True)

    if args.standalone:
        # Standalone scan: no DB writes, just metadata extraction + summary
        if args.paths_from_file:
            paths = specific_paths or []
        else:
            paths = list(list_files(lib_path, {".flac"}))

        if args.limit:
            paths = paths[:args.limit]

        total = len(paths)
        if total == 0:
            print("No files to scan.")
            return

        stats = {"total": 0, "valid": 0, "corrupt": 0, "recoverable": 0}
        start = time.time()

        for idx, path in enumerate(paths, start=1):
            try:
                audio = extract_metadata(
                    path,
                    scan_integrity=args.check_integrity,
                    scan_hash=args.check_hash,
                    library=args.library,
                )
                integrity_state = audio.integrity_state
                if integrity_state is None:
                    if audio.flac_ok is False:
                        integrity_state = "corrupt"
                    else:
                        integrity_state = "valid"
            except Exception as e:
                integrity_state = "corrupt"
                with open(error_log_path, "a") as f:
                    f.write(f"{path}\t{type(e).__name__}: {e}\n")

            stats["total"] += 1
            stats[integrity_state] += 1

            if args.progress and (idx % args.progress_interval == 0 or idx == total):
                print(f"Scanned {idx}/{total} files...")

        duration = time.time() - start
        print("\nScan summary:")
        print(f"  Total:       {stats['total']}")
        print(f"  Valid:       {stats['valid']}")
        print(f"  Recoverable: {stats['recoverable']}")
        print(f"  Corrupt:     {stats['corrupt']}")
        print(f"  Time:        {duration:.1f}s")
        return

    try:
        resolution = resolve_db_path(
            args.db,
            config=app_config,
            allow_repo_db=args.allow_repo_db,
            repo_root=Path(__file__).parents[2].resolve(),
            purpose="write",
            allow_create=args.create_db,
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
        
    db_path = resolution.path
    db_source = resolution.source

    print(f"Database: {db_path} (source={db_source})")

    try:
        scan_library(
            library_path=lib_path,
            db_path=db_path,
            db_source=db_source,
            library=args.library,
            recheck=args.recheck,
            force_all=args.force_all,
            progress=args.progress,
            progress_interval=args.progress_interval,
            scan_integrity=args.check_integrity,
            scan_hash=args.check_hash,
            specific_paths=specific_paths,
            limit=args.limit,
            stale_days=args.stale_days,
            paths_source="paths-from-file" if args.paths_from_file else None,
            paths_from_file=Path(args.paths_from_file) if args.paths_from_file else None,
            create_db=args.create_db,
            allow_repo_db=args.allow_repo_db,
            error_log=error_log_path,
        )
        print("Scan complete.")
    except Exception as e:
        print(f"Scan failed: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
