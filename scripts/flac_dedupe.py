#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
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

from scripts.lib import common
from scripts.lib.common import (
    FileInfo,
    GroupResult,
    SegmentHashes,
    build_fuzzy_key,
    check_health,
    compute_fingerprint,
    compute_metaflac_md5,
    compute_pcm_sha1,
    compute_segment_hashes,
    ensure_schema,
    fingerprint_similarity,
    freeze_detector_stop,
    heartbeat,
    insert_segments,
    last_timestamp_color,
    load_all_files_from_db,
    load_file_from_db,
    load_slide_hashes,
    log,
    probe_ffprobe,
    store_file_signals,
    upsert_file,
)
from scripts.lib.common import (
    append_broken_playlist_entry,
    load_broken_playlist_set,
    start_watchdog_thread,
    start_freeze_detector_watcher,
    choose_winner,
    write_csv,
    move_duplicates,
)

###############################################################################
# Grouping and scoring
###############################################################################


def build_groups(
    files: Sequence[FileInfo],
    fp_sim_ratio: float,
    fp_sim_shift: int,
    fp_sim_min_overlap: int,
    use_fingerprint: bool,
    use_segwin: bool,
    segwin_min_matches: int,
    use_slide: bool,
    fuzzy_duration_tol: float,
    verbose: bool = False,
    fp_duration_window: float = 2.0,
    fp_size_percent: float = 1.0,
) -> List[GroupResult]:
    """Group files using the staged deduplication pipeline."""

    by_id = {file.id: file for file in files}
    remaining = set(by_id.keys())
    groups: List[GroupResult] = []
    segwin_min_matches = max(1, segwin_min_matches)

    def register_group(key: str, method: str, members: List[FileInfo]) -> None:
        keeper = choose_winner(members)
        losers = [file for file in members if file != keeper]
        if not losers:
            return
        for member in members:
            remaining.discard(member.id)
        groups.append(GroupResult(key=key, method=method, keeper=keeper, losers=losers))

    # Stage A: EXACT
    key_to_members: Dict[str, List[FileInfo]] = {}
    for file in files:
        if file.id not in remaining:
            continue
        if file.stream_md5:
            key_to_members.setdefault(f"MD5:{file.stream_md5}", []).append(file)
            file.exact_key_type = "stream_md5"
        elif file.pcm_sha1:
            key_to_members.setdefault(f"PCM:{file.pcm_sha1}", []).append(file)
            file.exact_key_type = "pcm_sha1"
    for key, members in key_to_members.items():
        if len(members) > 1:
            register_group(key, "EXACT", members)

    if use_fingerprint:
        # Stage B: FPRINT equality
        key_to_members = {}
        for file in files:
            if file.id not in remaining:
                continue
            if file.fingerprint_hash:
                key_to_members.setdefault(file.fingerprint_hash, []).append(file)
        for key, members in key_to_members.items():
            if len(members) > 1:
                register_group(f"FP:{key}", "FPRINT", members)

        # Stage C: FPRINT similarity (pairwise compare — potentially expensive)
        fp_candidates = [
            file for file in files if file.id in remaining and file.fingerprint
        ]
        used_pairs: Set[Tuple[int, int]] = set()
        n_fp = len(fp_candidates)
        if verbose:
            log(
                f"FPRINT_SIM: comparing {n_fp} candidates (applying duration window {fp_duration_window}s and size percent {fp_size_percent}%)"
            )
        pair_count = 0
        log_interval = max(1, n_fp // 10)
        # Only actually compare fingerprints when files pass the pre-filter
        for i, file_a in enumerate(fp_candidates):
            for file_b in fp_candidates[i + 1 :]:
                # Pre-filter by duration when both durations are known
                allowed = False
                if file_a.duration is not None and file_b.duration is not None:
                    if (
                        abs((file_a.duration or 0.0) - (file_b.duration or 0.0))
                        <= fp_duration_window
                    ):
                        allowed = True
                else:
                    # Fallback to size-based relative difference
                    try:
                        sa = file_a.size_bytes or 0
                        sb = file_b.size_bytes or 0
                        if sa > 0 and sb > 0:
                            rel = abs(sa - sb) / max(sa, sb) * 100.0
                            if rel <= fp_size_percent:
                                allowed = True
                    except (TypeError, ValueError):
                        allowed = False
                if not allowed:
                    continue
                pair = (min(file_a.id, file_b.id), max(file_a.id, file_b.id))
                if pair in used_pairs:
                    continue
                pair_count += 1
                if verbose and pair_count % (log_interval * 100) == 0:
                    log(f"  FPRINT_SIM progress: compared {pair_count} pairs")
                ratio, shift, overlap = fingerprint_similarity(
                    file_a.fingerprint or [],
                    file_b.fingerprint or [],
                    fp_sim_shift,
                    fp_sim_min_overlap,
                )
                if ratio >= fp_sim_ratio and overlap >= fp_sim_min_overlap:
                    register_group(
                        key=f"FPS:{file_a.id}:{file_b.id}",
                        method=f"FPRINT_SIM(r={ratio:.2f},s={shift})",
                        members=[file_a, file_b],
                    )
                    used_pairs.add(pair)

    # Stage D: segment windows head/mid/tail
    if use_segwin:
        seg_candidates = [
            file
            for file in files
            if file.id in remaining
            and any([file.segments.head, file.segments.middle, file.segments.tail])
        ]
        parent: Dict[int, int] = {file.id: file.id for file in seg_candidates}

        def find(node: int) -> int:
            while parent[node] != node:
                parent[node] = parent[parent[node]]
                node = parent[node]
            return node

        def union(a: int, b: int) -> None:
            root_a = find(a)
            root_b = find(b)
            if root_a != root_b:
                parent[root_b] = root_a

        if verbose:
            log(f"SEGWIN: comparing {len(seg_candidates)} candidates")
        for i, file_a in enumerate(seg_candidates):
            for file_b in seg_candidates[i + 1 :]:
                matches = 0
                if (
                    file_a.segments.head
                    and file_a.segments.head == file_b.segments.head
                ):
                    matches += 1
                if (
                    file_a.segments.middle
                    and file_a.segments.middle == file_b.segments.middle
                ):
                    matches += 1
                if (
                    file_a.segments.tail
                    and file_a.segments.tail == file_b.segments.tail
                ):
                    matches += 1
                if (
                    file_a.segments.trimmed_head
                    and file_b.segments.trimmed_head
                    and file_a.segments.trimmed_head == file_b.segments.trimmed_head
                ):
                    matches += 1
                if matches >= segwin_min_matches:
                    union(file_a.id, file_b.id)

        groups_by_root: Dict[int, List[FileInfo]] = {}
        for candidate in seg_candidates:
            root = find(candidate.id)
            groups_by_root.setdefault(root, []).append(candidate)
        for members in groups_by_root.values():
            if len(members) > 1 and all(member.id in remaining for member in members):
                key = "SEGWIN:" + ",".join(
                    str(member.id) for member in sorted(members, key=lambda f: f.id)
                )
                register_group(key, f"SEGWIN(m>={segwin_min_matches})", members)

    # Stage E: sliding windows (optional)
    if use_slide:
        slide_candidates = [
            file
            for file in files
            if file.id in remaining and file.segments.slide_hashes
        ]
        if verbose:
            log(f"SEGWIN_SLIDE: processing {len(slide_candidates)} candidates")
        slide_parent: Dict[int, int] = {file.id: file.id for file in slide_candidates}
        seen: Dict[str, int] = {}

        def find_slide(node: int) -> int:
            while slide_parent[node] != node:
                slide_parent[node] = slide_parent[slide_parent[node]]
                node = slide_parent[node]
            return node

        def union_slide(a: int, b: int) -> None:
            root_a = find_slide(a)
            root_b = find_slide(b)
            if root_a != root_b:
                slide_parent[root_b] = root_a

        for file in slide_candidates:
            for slide_hash in file.segments.slide_hashes:
                if slide_hash in seen:
                    union_slide(file.id, seen[slide_hash])
                else:
                    seen[slide_hash] = file.id

        slide_groups: Dict[int, List[FileInfo]] = {}
        for file in slide_candidates:
            root = find_slide(file.id)
            slide_groups.setdefault(root, []).append(file)
        for members in slide_groups.values():
            if len(members) > 1 and all(member.id in remaining for member in members):
                key = "SEGWIN_SLIDE:" + ",".join(
                    str(member.id) for member in sorted(members, key=lambda f: f.id)
                )
                register_group(key, "SEGWIN_SLIDE", members)

    # Stage F: fuzzy key
    fuzzy_map: Dict[str, List[FileInfo]] = {}
    for file in files:
        if file.id not in remaining:
            continue
        if not file.fuzzy_key or file.duration is None:
            continue
        fuzzy_map.setdefault(file.fuzzy_key, []).append(file)
    for key, members in fuzzy_map.items():
        bucket: List[FileInfo] = []
        for file in members:
            added = False
            for candidate in bucket:
                dur_a = file.duration or 0.0
                dur_b = candidate.duration or 0.0
                if abs(dur_a - dur_b) <= fuzzy_duration_tol:
                    register_group(
                        key=f"FUZZY:{key}", method="FUZZY", members=[file, candidate]
                    )
                    added = True
                    break
            if not added:
                bucket.append(file)

    return groups


def estimate_fp_pairs(
    files: Sequence[FileInfo],
    fp_duration_window: float,
    fp_size_percent: float,
) -> Tuple[int, int]:
    """Estimate the number of fingerprint candidates and allowed pairs after pre-filter.

    Returns (n_candidates, allowed_pairs)
    """
    fp_candidates = [file for file in files if file.fingerprint]
    n_fp = len(fp_candidates)
    allowed = 0
    # Count pairs that would pass the duration/size pre-filter
    for i, a in enumerate(fp_candidates):
        for b in fp_candidates[i + 1 :]:
            allowed_flag = False
            if a.duration is not None and b.duration is not None:
                if abs((a.duration or 0.0) - (b.duration or 0.0)) <= fp_duration_window:
                    allowed_flag = True
            else:
                try:
                    sa = a.size_bytes or 0
                    sb = b.size_bytes or 0
                    if sa > 0 and sb > 0:
                        rel = abs(sa - sb) / max(sa, sb) * 100.0
                        if rel <= fp_size_percent:
                            allowed_flag = True
                except (TypeError, ValueError):
                    allowed_flag = False
            if allowed_flag:
                allowed += 1
    return n_fp, allowed


###############################################################################
# CSV report generation
###############################################################################


def group_to_rows(group: GroupResult, trash_dir: Path, commit: bool) -> List[List[str]]:
    """Thin adapter that delegates to the canonical implementation in lib.common."""

    return common.group_to_rows(group, trash_dir, commit)


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

    # Helper to append to broken playlist, avoiding duplicates
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
            log("Skipping broken file (cached metadata)")
            # Do not early-return None; return the populated info so the outer loop
            # will upsert it into the DB and future runs will treat it as cached.
            return info

        return info

    def print_progress(completed: int, total: int, width: int = 50) -> None:
        global last_timestamp_color
        percent = completed / total if total > 0 else 0
        color = last_timestamp_color
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
                    log("[DIAG] Upserted broken file to DB")
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


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dedupe FLAC files using database index",
    )
    parser.add_argument(
        "--root",
        default="/Volumes/dotad/MUSIC",
        help="Root directory to scan (default: /Volumes/dotad/MUSIC)",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Actually move duplicate files to trash directory",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=True,
        help="Log additional progress information",
    )
    parser.add_argument(
        "--fp-sim-ratio",
        type=float,
        default=0.62,
        help="Minimum similarity ratio for fingerprint grouping",
    )
    parser.add_argument(
        "--no-fp",
        "--skip-fingerprint",
        dest="use_fingerprint",
        action="store_false",
        help="Skip the expensive fingerprint similarity stage (speeds up dedupe)",
    )
    parser.add_argument(
        "--fp-duration-window",
        type=float,
        default=2.0,
        help="Maximum duration difference in seconds to allow fingerprint comparison (default: 2.0)",
    )
    parser.add_argument(
        "--fp-size-percent",
        type=float,
        default=1.0,
        help="Maximum relative size difference (percent) to allow fingerprint comparison when duration is unknown (default: 1.0)",
    )
    parser.add_argument(
        "--fp-estimate",
        action="store_true",
        help="Estimate how many fingerprint pair comparisons would run with current filters and exit",
    )
    parser.add_argument(
        "--fp-rate",
        type=float,
        default=300.0,
        help="Pairs-per-second estimate used to compute ETA when --fp-estimate is used (default: 300)",
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
        "--segwin-min-matches",
        type=int,
        default=3,
        help="Required number of matching segments for SEGWIN grouping",
    )
    parser.add_argument(
        "--fuzzy-seconds",
        type=float,
        default=2.0,
        help="Duration tolerance for fuzzy filename matching",
    )
    parser.add_argument(
        "--trash-dir",
        type=str,
        help="Optional custom directory for moving duplicate losers",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Force dry-run mode even if --commit is provided",
    )
    parser.add_argument(
        "--audit-report", type=Path, help="Audit an existing dedupe CSV report and exit"
    )
    return parser.parse_args(argv)


def run(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point used by :func:`main` and unit tests."""

    args = parse_args(argv)

    root = Path(args.root).expanduser()
    root_path = root.as_posix()
    if not os.path.exists(root_path) or not os.path.isdir(root_path):
        raise SystemExit(f"Root directory {root} does not exist")

    db_path = root / "_DEDUP_INDEX.db"
    if not db_path.exists():
        raise SystemExit(f"Database {db_path} does not exist. Run scan first.")

    conn = sqlite3.connect(db_path.as_posix(), timeout=30)
    ensure_schema(conn)

    run_id = record_run(conn, root, not args.commit, {})

    try:
        files = load_all_files_from_db(conn)

        if args.fp_estimate:
            n_fp, allowed = estimate_fp_pairs(
                files, args.fp_duration_window, args.fp_size_percent
            )
            total_pairs = n_fp * (n_fp - 1) // 2
            print(f"Estimated fingerprint candidates: {n_fp}")
            print(f"Total possible pairs (without pre-filter): {total_pairs}")
            print(f"Pairs passing pre-filter: {allowed}")
            rate = float(args.fp_rate or 300.0)
            if allowed > 0:
                secs = allowed / rate
                hrs = int(secs // 3600)
                mins = int((secs % 3600) // 60)
                secs_r = int(secs % 60)
                print(f"Estimated time at {rate:.0f} pairs/s: {hrs}h {mins}m {secs_r}s")
            else:
                print(
                    "No pairs would be compared with the current pre-filter settings."
                )
            return 0

        if args.verbose:
            log(f"Loaded {len(files)} files from database for deduplication…")

        groups = build_groups(
            files=files,
            fp_sim_ratio=args.fp_sim_ratio,
            fp_sim_shift=args.fp_sim_shift,
            fp_sim_min_overlap=args.fp_sim_min_overlap,
            use_fingerprint=args.use_fingerprint,  # Respect --no-fp / --skip-fingerprint
            use_segwin=True,
            segwin_min_matches=args.segwin_min_matches,
            use_slide=True,
            fuzzy_duration_tol=args.fuzzy_seconds,
            verbose=args.verbose,
            fp_duration_window=args.fp_duration_window,
            fp_size_percent=args.fp_size_percent,
        )

        if args.verbose:
            log(f"Formed {len(groups)} duplicate groups")

        persist_groups(conn, run_id, groups)

        timestamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        trash_dir = (
            Path(args.trash_dir).expanduser()
            if args.trash_dir
            else (root / f"_TRASH_DUPES_{timestamp}")
        )
        report_path = root / f"_DEDUP_REPORT_{timestamp}.csv"

        write_csv(report_path, groups, trash_dir, args.commit)

        if args.commit and not args.dry_run:
            move_duplicates(groups, trash_dir)
        else:
            log("Dry run mode: no files moved")

        log(f"CSV report written to {report_path}")
        log(f"Trash directory: {trash_dir}")
    finally:
        finalize_run(conn, run_id)
        conn.close()

    return 0


def main() -> None:
    """Console script entry point."""

    try:
        args = parse_args()
        if args.audit_report:
            dedupe_report_audit(args.audit_report)
            sys.exit(0)
        sys.exit(run())
    except KeyboardInterrupt:
        log("Interrupted")
        sys.exit(1)


def dedupe_report_audit(csv_path: Path):
    """Audit a dedupe CSV report for planned moves and unhealthy keepers."""
    import datetime as dt

    timestamp = dt.datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] Auditing dedupe report: {csv_path}")

    planned = 0
    unhealthy = []
    planned_moves: List[Tuple[str, str]] = []

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("action") == "plan":
                planned += 1
                if len(planned_moves) < 20:
                    src = row.get("path", "")
                    dst = row.get("dest", "")
                    planned_moves.append((src, dst))
            if row.get("keep") == "yes" and row.get("healthy") == "no":
                unhealthy.append(row.get("path", ""))

    timestamp = dt.datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {planned} planned moves found.")
    if planned_moves:
        print(f"[{timestamp}] Preview first 20 planned moves:")
        for src, dst in planned_moves:
            print(f"  {src} -> {dst}")
    if unhealthy:
        print(f"[{timestamp}] {len(unhealthy)} unhealthy keepers detected:")
        for path in unhealthy:
            print(f"  UNHEALTHY KEEPER: {path}")


if __name__ == "__main__":
    main()
