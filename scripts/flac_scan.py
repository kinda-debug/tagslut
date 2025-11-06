from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import signal
import sqlite3
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from types import FrameType
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple
import pathlib

# When this script is executed directly (python scripts/flac_scan.py) the
# package root (workspace root) isn't on sys.path which makes imports like
# `from scripts.lib import common` fail with ModuleNotFoundError. Ensure the
# repository root is on sys.path so package imports work when run as a script.
if __package__ is None:  # pragma: no cover - only for direct script runs
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

from scripts.lib import common
from scripts.lib.common import (
    DiagnosticsManager,
    FileInfo,
    GroupResult,
    SegmentHashes,
    append_broken_playlist_entry,
    build_fuzzy_key,
    check_health,
    compute_fingerprint,
    compute_metaflac_md5,
    compute_pcm_sha1,
    compute_segment_hashes,
    ensure_directory,
    ensure_schema,
    freeze_detector_stop,
    heartbeat,
    insert_segments,
    is_tool_available,
    load_broken_playlist_set,
    load_file_from_db,
    load_slide_hashes,
    log,
    probe_ffprobe,
    start_freeze_detector_watcher,
    start_watchdog_thread,
    store_file_signals,
    upsert_file,
)

###############################################################################
# CSV report generation
###############################################################################


###############################################################################
# File operations
###############################################################################


###############################################################################
# Run orchestration
###############################################################################


class GracefulShutdown:
    """Signal handler that allows the script to stop gracefully."""

    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._sigint_count = 0

    def install(self) -> None:
        signal.signal(signal.SIGINT, self._handler)

    def should_stop(self) -> bool:
        return self._stop_event.is_set()

    def _handler(self, signum: int, frame: FrameType | None) -> None:  # pragma: no cover
        self._sigint_count += 1
        if self._sigint_count == 1:
            log(
                "Received Ctrl-C — finishing current tasks then stopping… (press Ctrl-C again to abort now)"
            )
            self._stop_event.set()
        else:
            log("Second Ctrl-C — aborting immediately.")
            os._exit(130)


def scan_files(
    root: Path,
    workers: int = 1,
    skip_broken: bool = False,
    auto_quarantine: bool = False,
    **kwargs,
) -> List[FileInfo]:
    """Walk the filesystem and update cached :class:`FileInfo` entries."""

    # Reset shared heartbeat/freeze state for this scan
    freeze_detector_stop.clear()
    heartbeat()

    broken_playlist_path = kwargs.get("broken_playlist_path")
    broken_playlist_set = load_broken_playlist_set(broken_playlist_path)

    # Use provided watchdog timeout when available; fallback to a generous default
    WATCHDOG_TIMEOUT = int(kwargs.get("watchdog_timeout", 300) or 300)
    # Start watchdog thread
    start_watchdog_thread(WATCHDOG_TIMEOUT, shutdown=kwargs.get("shutdown"))

    # Start freeze detector watcher
    start_freeze_detector_watcher(
        root if auto_quarantine else None,
        auto_quarantine,
        kill_in_terminal=bool(kwargs.get("kill_in_terminal", True)),
    )

    files: List[FileInfo] = []
    pending: List[Tuple[Path, os.stat_result, Optional[FileInfo], int]] = []
    conn = kwargs["conn"]
    recompute = kwargs["recompute"]
    seg_length = kwargs["seg_length"]
    segwin_sliding = kwargs["segwin_sliding"]
    slide_step = kwargs["slide_step"]
    slide_max_slices = kwargs["slide_max_slices"]
    include_trim_head = kwargs["include_trim_head"]
    aggressive_fuzzy = kwargs["aggressive_fuzzy"]
    no_fp = kwargs["no_fp"]
    no_segwin = kwargs["no_segwin"]
    hash_mode = kwargs["hash_mode"]
    shutdown = kwargs["shutdown"]
    verbose = kwargs.get("verbose", True)

    next_id = _next_file_id(conn)
    discovered = 0
    log_path = root / "_DEDUP_SCAN_LOG.txt"

    def log_scan_entry(path: Path, status: str) -> None:
        try:
            ts = _dt.datetime.now().isoformat()
            with open(log_path, "a") as f:
                f.write(f"{ts}\t{path}\t{status}\n")
        except OSError:
            # Logging must not crash the dedupe run
            pass
        heartbeat(path)

    # Precompute already cached files with valid size/mtime for resuming
    if shutdown.should_stop():
        log("Stop requested — skipping new tasks submission.")
        pending = []
    already_cached = 0
    ticker_interval = 100
    for dirpath, dirnames, filenames in os.walk(root, followlinks=True):
        if shutdown.should_stop():
            break
        dirnames[:] = [
            name for name in dirnames if not name.upper().startswith("_TRASH_DUPES")
        ]
        for filename in sorted(filenames):
            if shutdown.should_stop():
                break
            if not filename.lower().endswith(".flac"):
                continue  # Ignore non-FLAC files entirely
            path = Path(dirpath) / filename
            heartbeat(path)
            discovered += 1
            if discovered % ticker_interval == 0:
                log(f"Progress: {discovered} files processed...")
            path_str = path.as_posix()
            if not os.path.exists(path_str) or not os.path.isfile(path_str):
                log(f"SKIP (missing): {path}")
                log_scan_entry(path, "SKIPPED")
                heartbeat(path)
                continue
            try:
                stat_info = os.stat(path_str)
            except FileNotFoundError:
                log(f"SKIP (missing): {path}")
                log_scan_entry(path, "SKIPPED")
                heartbeat(path)
                continue

            cached = load_file_from_db(conn, path)
            if cached:
                load_slide_hashes(conn, cached.id, cached.segments)

            # If cached, up-to-date, and not recomputing, skip and reuse
            if (
                cached
                and not recompute
                and cached.size_bytes == stat_info.st_size
                and abs(cached.mtime - stat_info.st_mtime) < 1
            ):
                if verbose:
                    log("  Using cached analysis")
                files.append(cached)
                log_scan_entry(path, "CACHED")
                already_cached += 1
                heartbeat(path)
                continue

            file_id = cached.id if cached else next_id
            if not cached:
                next_id += 1

            pending.append((path, stat_info, cached, file_id))

    log(f"Resuming from previous scan: {already_cached} files already analyzed")
    if verbose:
        log(f"Discovered {discovered} .flac files under {root}")

    def analyze(
        task: Tuple[Path, os.stat_result, Optional[FileInfo], int],
    ) -> Optional[FileInfo]:
        path, stat_info, cached, file_id = task
        if shutdown.should_stop():
            return cached

        heartbeat(path)
        info = FileInfo(
            id=file_id,
            path=path,
            inode=stat_info.st_ino,
            size_bytes=stat_info.st_size,
            mtime=stat_info.st_mtime,
        )
        info.lossless = True

        metadata = probe_ffprobe(path)
        if metadata:
            codec_val = metadata.get("codec")
            info.codec = str(codec_val) if codec_val is not None else "flac"
            info.duration = metadata.get("duration")
            info.bitrate_kbps = metadata.get("bitrate_kbps")
            stream_md5 = metadata.get("stream_md5")
            if stream_md5 is not None:
                info.stream_md5 = str(stream_md5)

        md5 = compute_metaflac_md5(path)
        if md5:
            info.stream_md5 = md5
            info.exact_key_type = "stream_md5"

        if hash_mode == "file" or not info.stream_md5:
            pcm_sha1 = compute_pcm_sha1(path)
            if pcm_sha1:
                info.pcm_sha1 = pcm_sha1
                info.exact_key_type = "pcm_sha1"

        if not info.codec:
            info.codec = "flac"

        if not no_fp:
            fp, fp_hash = compute_fingerprint(path)
            info.fingerprint = fp
            info.fingerprint_hash = fp_hash
            if verbose:
                if fp:
                    log(f"  Fingerprint computed for {path}")
                else:
                    log(f"  Fingerprint unavailable for {path}")

        if no_segwin:
            info.segments = SegmentHashes()
        else:
            info.segments = compute_segment_hashes(
                path,
                info.duration,
                seg_length,
                segwin_sliding,
                slide_step,
                slide_max_slices,
                include_trim_head,
            )
            if verbose:
                if (
                    info.segments.head
                    or info.segments.middle
                    or info.segments.tail
                    or info.segments.slide_hashes
                ):
                    log(f"  Segment hashes computed for {path}")
                else:
                    log(f"  Segment hashes unavailable for {path}")

        info.fuzzy_key = build_fuzzy_key(path, aggressive_fuzzy)
        info.fuzzy_duration = info.duration

        info.healthy, info.health_note = check_health(path)
        if verbose:
            log(
                f"  Health check {info.healthy if info.healthy is not None else 'unknown'}"
                f" via {info.health_note or 'n/a'}"
            )

        # Enhanced skip logic for broken files
        # We still want to cache metadata for "broken" files so subsequent runs
        # count them as already analyzed (and don't keep re-testing forever).
        if skip_broken and info.healthy is False:
            broken_log = root / "_BROKEN_FILES.txt"
            try:
                with open(broken_log, "a") as f:
                    ts = _dt.datetime.now().isoformat()
                    hn = info.health_note or ""
                    f.write(f"{ts}\t{path}\t{hn}\n")
            except OSError:
                # don't let logging errors interrupt the run
                pass
            append_broken_playlist_entry(
                broken_playlist_path,
                broken_playlist_set,
                path,
            )
            log("Added broken file to playlist")
            log(f"Skipping broken file (cached metadata): {path}")
            # Do not early-return None; return the populated info so the outer loop
            # will upsert it into the DB and future runs will treat it as cached.
            return info

        return info

    def print_progress(completed: int, total: int, width: int = 50) -> None:
        percent = completed / total if total > 0 else 0
        color = common.last_timestamp_color
        print(
            f"\r{color}{completed}/{total}\033[0m \033[1;37m({percent:.1%})\033[0m",
            end="",
            flush=True,
        )

    if pending:
        import time

        max_workers = max(1, workers)
        total_files = len(pending)
        completed = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(analyze, task): task[0] for task in pending}
            print(
                f"\033[36m[DIAG] Submitted {len(future_map)} tasks to ThreadPoolExecutor\033[0m",
                flush=True,
            )
            for future in as_completed(future_map):
                if shutdown.should_stop():
                    log("Shutdown requested — cancelling remaining tasks.")
                    for f in future_map:
                        f.cancel()
                    break
                path = future_map[future]
                try:
                    # as_completed yields futures that are done; no per-future timeout needed
                    info = future.result()
                except Exception as exc:  # pragma: no cover - defensive
                    # worker raised; log and continue (keep defensive behaviour)
                    log(f"Error processing {path}: {exc}")
                    # Log as SKIPPED if processing failed
                    try:
                        log_scan_entry(path, "SKIPPED")
                    except OSError:
                        pass
                    continue
                if info is None:
                    # Log as SKIPPED if no info returned
                    try:
                        log_scan_entry(path, "SKIPPED")
                    except OSError:
                        pass
                    continue
                upsert_file(conn, info)
                if skip_broken and info.healthy is False:
                    log(f"[DIAG] Upserted broken file to DB: {path}")
                insert_segments(conn, info.id, info.segments)
                store_file_signals(conn, info)
                files.append(info)
                log(f"Processed: {path.name}")
                try:
                    log_scan_entry(path, "PROCESSED")
                except OSError:
                    pass
                completed += 1
                print_progress(completed, total_files)
                if completed % 100 == 0 or completed == total_files:
                    print(
                        f"[{time.strftime('%H:%M:%S')}] Processed {completed}/{total_files} files"
                    )
            print()  # End the progress bar line
            print("\033[32m[DIAG] All tasks completed.\033[0m", flush=True)

    # Stop the freeze detector watcher
    freeze_detector_stop.set()
    return files


def _next_file_id(conn: sqlite3.Connection) -> int:
    """Return the next available file identifier."""

    cursor = conn.execute("SELECT IFNULL(MAX(id), 0) FROM files")
    row = cursor.fetchone()
    return (row[0] or 0) + 1


def record_run(
    conn: sqlite3.Connection, root: Path, dry_run: bool, options: Dict[str, object]
) -> int:
    """Insert a run record and return its identifier."""

    now = _dt.datetime.now(_dt.timezone.utc).isoformat()
    cursor = conn.execute(
        """
        INSERT INTO runs (started_at, root, options_json, dry_run)
        VALUES (?, ?, ?, ?)
        """,
        (now, root.as_posix(), json.dumps(options), int(dry_run)),
    )
    conn.commit()
    rid = cursor.lastrowid
    return int(rid) if rid is not None else -1


def finalize_run(conn: sqlite3.Connection, run_id: int) -> None:
    """Update the run record with the finishing timestamp."""

    now = _dt.datetime.now(_dt.timezone.utc).isoformat()
    conn.execute("UPDATE runs SET finished_at=? WHERE id=?", (now, run_id))
    conn.commit()


def persist_groups(
    conn: sqlite3.Connection, run_id: int, groups: Sequence[GroupResult]
) -> None:
    """Persist deduplication groups in the database."""

    conn.execute("DELETE FROM groups WHERE run_id=?", (run_id,))
    conn.commit()

    for group in groups:
        cursor = conn.execute(
            """
            INSERT INTO groups (run_id, group_key, method, keeper_file_id)
            VALUES (?, ?, ?, ?)
            """,
            (run_id, group.key, group.method, group.keeper.id),
        )
        group_id = cursor.lastrowid
        entries = []
        for member in [group.keeper] + group.losers:
            role = "keeper" if member == group.keeper else "loser"
            entries.append((group_id, member.id, role, None, None))
        conn.executemany(
            """
            INSERT INTO group_members (group_id, file_id, role, action, dest_path)
            VALUES (?, ?, ?, ?, ?)
            """,
            entries,
        )
    conn.commit()


###############################################################################
# CLI parsing and main entry point
###############################################################################


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan FLAC files and build database index",
    )
    parser.add_argument(
        "--auto-quarantine",
        action="store_true",
        help="Automatically move files that cause a freeze to a _BROKEN folder",
    )
    parser.add_argument(
        "--cmd-timeout",
        type=int,
        default=10,
        help="Seconds for short external commands (fpcalc, flac -t, ffprobe, metaflac)",
    )
    parser.add_argument(
        "--decode-timeout",
        type=int,
        default=30,
        help="Seconds allowed for decoding/streaming operations (ffmpeg hashing)",
    )
    parser.add_argument(
        "--skip-broken",
        action="store_true",
        default=False,
        help="Skip files that fail health check (do not abort run)",
    )
    parser.add_argument(
        "--root",
        default="/Volumes/dotad/MUSIC",
        help="Root directory to scan (default: /Volumes/dotad/MUSIC)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Log additional progress information",
    )
    parser.add_argument(
        "--recompute",
        action="store_true",
        help="Force recomputation of fingerprints and segment hashes",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Number of worker threads for audio analysis",
    )
    parser.add_argument(
        "--hash-mode",
        choices=["auto", "file"],
        default="auto",
        help="Hashing mode: auto prefers FLAC MD5, file always recomputes PCM hash",
    )
    parser.add_argument(
        "--segwin-seconds",
        type=float,
        default=30.0,
        help="Length of PCM excerpts used for segment hashing",
    )
    parser.add_argument(
        "--segwin-sliding",
        action="store_true",
        help="Enable sliding window segment comparison",
    )
    parser.add_argument(
        "--segwin-step",
        type=float,
        default=5.0,
        help="Seconds between sliding segment hashes",
    )
    parser.add_argument(
        "--segwin-max-slices",
        type=int,
        default=6,
        help="Maximum number of sliding segment hashes to compute",
    )
    parser.add_argument(
        "--segwin-min-matches",
        type=int,
        default=3,
        help="Required number of matching segments for SEGWIN grouping",
    )
    parser.add_argument(
        "--segwin-trim-head",
        action="store_true",
        help="Compute an additional trimmed head segment hash",
    )
    parser.add_argument(
        "--aggressive",
        action="store_true",
        help="Use aggressive normalization when building fuzzy keys",
    )
    parser.add_argument(
        "--fuzzy-seconds",
        type=float,
        default=2.0,
        help="Duration tolerance for fuzzy filename matching",
    )
    parser.add_argument(
        "--no-fp",
        action="store_true",
        help="Skip fingerprint computation",
    )
    parser.add_argument(
        "--fp-sim-ratio",
        type=float,
        default=0.62,
        help="Minimum similarity ratio for fingerprint grouping",
    )
    parser.add_argument(
        "--fp-sim-shift",
        type=int,
        default=25,
        help="Maximum absolute fingerprint shift for similarity",
    )
    parser.add_argument(
        "--fp-sim-min-overlap",
        type=int,
        default=50,
        help="Minimum overlapping frames for fingerprint similarity",
    )
    parser.add_argument(
        "--no-segwin",
        action="store_true",
        help="Skip segment window hashing",
    )
    parser.add_argument(
        "--broken-playlist",
        type=str,
        default="/Volumes/dotad/MUSIC/broken_files_unrepaired.m3u",
        help="Path to write playlist of broken files for repair (default: /Volumes/dotad/MUSIC/broken_files_unrepaired.m3u)",
    )
    parser.add_argument(
        "--watchdog-timeout",
        type=int,
        default=300,
        help="Seconds of inactivity before watchdog warns and requests shutdown (default: 300)",
    )
    parser.add_argument(
        "--kill-in-terminal",
        action="store_true",
        default=True,
        help="When the freeze detector kills stalled ffmpeg, run the pkill in a new Terminal window (macOS only)",
    )
    parser.add_argument(
        "--diagnostic-root",
        type=str,
        default="/Volumes/dotad/.dedupe_diagnostics",
        help="Directory for diagnostic dumps (default: /Volumes/dotad/.dedupe_diagnostics)",
    )
    parser.add_argument(
        "--dump-fpcalc",
        dest="dump_fpcalc",
        action="store_true",
        default=True,
        help="Enable fpcalc stdout dumps (default)",
    )
    parser.add_argument(
        "--no-dump-fpcalc",
        dest="dump_fpcalc",
        action="store_false",
        help="Disable fpcalc stdout dumps",
    )
    parser.add_argument(
        "--dump-decode",
        dest="dump_decode",
        action="store_true",
        default=True,
        help="Enable decode diagnostics dumps (default)",
    )
    parser.add_argument(
        "--no-dump-decode",
        dest="dump_decode",
        action="store_false",
        help="Disable decode diagnostics dumps",
    )
    parser.add_argument(
        "--dump-watchdog",
        dest="dump_watchdog",
        action="store_true",
        default=True,
        help="Enable watchdog diagnostic dumps (default)",
    )
    parser.add_argument(
        "--no-dump-watchdog",
        dest="dump_watchdog",
        action="store_false",
        help="Disable watchdog diagnostic dumps",
    )
    return parser.parse_args(argv)


def run(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point used by :func:`main` and unit tests."""

    args = parse_args(argv)
    common.CMD_TIMEOUT = max(5, int(args.cmd_timeout))
    common.DECODE_TIMEOUT = max(10, int(args.decode_timeout))
    diag_root = Path(
        getattr(args, "diagnostic_root", "/Volumes/dotad/.dedupe_diagnostics")
    ).expanduser()
    common.DIAGNOSTICS = common.wrap_diagnostics(
        DiagnosticsManager(
            root=diag_root,
            dump_fpcalc=getattr(args, "dump_fpcalc", True),
            dump_decode=getattr(args, "dump_decode", True),
            dump_watchdog=getattr(args, "dump_watchdog", True),
        )
    )
    log(f"Diagnostics root: {common.DIAGNOSTICS.root}")
    if getattr(args, "fpcalc_dump_latest", False) or getattr(
        args, "check_fpcalc", False
    ):
        latest = common.DIAGNOSTICS.latest("fpcalc")
        if latest is None:
            print(f"No fpcalc dumps found under {common.DIAGNOSTICS.root / 'fpcalc'}")
            return 0
        print(f"Latest fpcalc dump: {latest}")
        if getattr(args, "check_fpcalc", False):
            try:
                print(latest.read_text(encoding="utf-8"))
            except OSError as exc:
                print(f"Failed to read {latest}: {exc}")
        if getattr(args, "fpcalc_dump_latest", False) and not getattr(
            args, "check_fpcalc", False
        ):
            return 0
        if getattr(args, "check_fpcalc", False):
            return 0
    trash_dir = (
        Path(args.trash_dir).expanduser() if getattr(args, "trash_dir", None) else None
    )
    if trash_dir:
        ensure_directory(trash_dir)
    for tool in ["ffmpeg", "fpcalc", "flac", "metaflac", "ffprobe"]:
        status = "available" if is_tool_available(tool) else "missing"
        log(f"Tool {tool}: {status}")

    root = Path(args.root).expanduser()
    root_path = root.as_posix()
    if not os.path.exists(root_path) or not os.path.isdir(root_path):
        raise SystemExit(f"Root directory {root} does not exist")

    db_path = root / "_DEDUP_INDEX.db"
    ensure_directory(db_path.parent)
    conn = sqlite3.connect(db_path.as_posix(), timeout=30)
    ensure_schema(conn)

    shutdown = GracefulShutdown()
    shutdown.install()

    options = {
        "hash_mode": args.hash_mode,
        "no_fp": args.no_fp,
        "no_segwin": args.no_segwin,
        "fp_sim_ratio": args.fp_sim_ratio,
        "fp_sim_shift": args.fp_sim_shift,
        "fp_sim_min_overlap": args.fp_sim_min_overlap,
        "segwin_seconds": args.segwin_seconds,
        "segwin_min_matches": args.segwin_min_matches,
        "segwin_sliding": args.segwin_sliding,
        "segwin_step": args.segwin_step,
        "segwin_max_slices": args.segwin_max_slices,
        "segwin_trim_head": args.segwin_trim_head,
        "fuzzy_seconds": args.fuzzy_seconds,
        "aggressive": args.aggressive,
        "workers": args.workers,
        "recompute": args.recompute,
        "cmd_timeout": common.CMD_TIMEOUT,
        "decode_timeout": common.DECODE_TIMEOUT,
    }

    run_id = record_run(conn, root, True, options)
    files = scan_files(
        root=root,
        workers=getattr(args, "workers", 1),
        skip_broken=getattr(args, "skip_broken", False),
        auto_quarantine=getattr(args, "auto_quarantine", False),
        conn=conn,
        recompute=args.recompute,
        seg_length=args.segwin_seconds,
        segwin_sliding=args.segwin_sliding,
        slide_step=args.segwin_step,
        slide_max_slices=args.segwin_max_slices,
        include_trim_head=args.segwin_trim_head,
        aggressive_fuzzy=args.aggressive,
        no_fp=args.no_fp,
        no_segwin=args.no_segwin,
        hash_mode=args.hash_mode,
        shutdown=shutdown,
        verbose=args.verbose,
        watchdog_timeout=getattr(args, "watchdog_timeout", None),
        kill_in_terminal=getattr(args, "kill_in_terminal", False),
        broken_playlist_path=(
            str(args.broken_playlist)
            if getattr(args, "broken_playlist", None)
            else None
        ),
    )

    # Scan completed
    finalize_run(conn, run_id)
    conn.close()
    log(f"Scan completed. {len(files)} files processed. DB updated: {db_path}")
    return 0


def main() -> None:
    """Console script entry point."""

    try:
        sys.exit(run())
    except KeyboardInterrupt:
        log("Interrupted")
        sys.exit(1)


if __name__ == "__main__":
    main()
