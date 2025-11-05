from __future__ import annotations

import argparse
import binascii
import csv
import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple
import base64
import struct
import time

from lib import common
from lib.common import (
    CommandError,
    DiagnosticsManager,
    FileInfo,
    GroupResult,
    SegmentHashes,
    active_ffmpeg_pgids,
    active_pgid_lock,
    build_fuzzy_key,
    check_health,
    colorize_path,
    compute_fingerprint,
    compute_metaflac_md5,
    compute_pcm_sha1,
    compute_segment_hash,
    compute_segment_hashes,
    ensure_directory,
    ensure_schema,
    fingerprint_similarity,
    freeze_detector_stop,
    gay_flag_colors,
    heartbeat,
    human_size,
    insert_fp_bands,
    insert_segments,
    is_tool_available,
    last_progress_file,
    last_progress_timestamp,
    last_timestamp_color,
    load_file_from_db,
    load_slide_hashes,
    log,
    log_progress,
    log_skip,
    normalize_filename,
    parse_fpcalc_output,
    progress_color_index,
    progress_update_lock,
    progress_word_offset,
    probe_ffprobe,
    register_active_pgid,
    run_command,
    scan_processed_count,
    scan_progress_lock,
    scan_skipped_count,
    scan_total_files,
    sha1_hex,
    store_file_signals,
    timestamp_color_index,
    unregister_active_pgid,
    upsert_file,
)

###############################################################################
# Grouping and scoring
###############################################################################


def choose_winner(files: Sequence[FileInfo]) -> FileInfo:
    """Select the best candidate according to scoring rules."""

    def score(file: FileInfo) -> Tuple[int, int, float, float, float]:
        healthy = 1 if file.healthy else 0
        lossless = 1 if file.lossless else 0
        duration = file.duration or 0.0
        bitrate = file.bitrate_kbps or 0.0
        mtime = file.mtime
        return (healthy, lossless, duration, bitrate, mtime)

    return sorted(files, key=score, reverse=True)[0]


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

        # Stage C: FPRINT similarity
        fp_candidates = [file for file in files if file.id in remaining and file.fingerprint]
        used_pairs: Set[Tuple[int, int]] = set()
        for i, file_a in enumerate(fp_candidates):
            for file_b in fp_candidates[i + 1 :]:
                pair = tuple(sorted((file_a.id, file_b.id)))
                if pair in used_pairs:
                    continue
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

        for i, file_a in enumerate(seg_candidates):
            for file_b in seg_candidates[i + 1 :]:
                matches = 0
                if file_a.segments.head and file_a.segments.head == file_b.segments.head:
                    matches += 1
                if file_a.segments.middle and file_a.segments.middle == file_b.segments.middle:
                    matches += 1
                if file_a.segments.tail and file_a.segments.tail == file_b.segments.tail:
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
                key = "SEGWIN:" + ",".join(str(member.id) for member in sorted(members, key=lambda f: f.id))
                register_group(key, f"SEGWIN(m>={segwin_min_matches})", members)

    # Stage E: sliding windows (optional)
    if use_slide:
        slide_candidates = [
            file for file in files if file.id in remaining and file.segments.slide_hashes
        ]
        parent: Dict[int, int] = {file.id: file.id for file in slide_candidates}
        seen: Dict[str, int] = {}

        def find_slide(node: int) -> int:
            while parent[node] != node:
                parent[node] = parent[parent[node]]
                node = parent[node]
            return node

        def union_slide(a: int, b: int) -> None:
            root_a = find_slide(a)
            root_b = find_slide(b)
            if root_a != root_b:
                parent[root_b] = root_a

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


###############################################################################
# CSV report generation
###############################################################################


CSV_HEADERS = [
    "group_key",
    "method",
    "keep",
    "path",
    "name",
    "ext",
    "codec",
    "lossless",
    "size_bytes",
    "size_human",
    "duration_sec",
    "bitrate_kbps",
    "healthy",
    "health_note",
    "exact_key_type",
    "action",
    "dest",
]


def group_to_rows(group: GroupResult, trash_dir: Path, commit: bool) -> List[List[str]]:
    """Convert a group into CSV rows."""

    rows: List[List[str]] = []
    for file in [group.keeper] + group.losers:
        name = file.path.name
        ext = file.path.suffix.lower().lstrip(".")
        action = "keep" if file == group.keeper else ("move" if commit else "plan")
        dest = ""
        if file != group.keeper:
            dest_path = plan_trash_destination(trash_dir, file.path)
            dest = dest_path.as_posix()
        row = [
            group.key,
            group.method,
            "yes" if file == group.keeper else "no",
            file.path.as_posix(),
            name,
            ext,
            file.codec or "",
            "yes" if file.lossless else "no",
            str(file.size_bytes),
            human_size(file.size_bytes),
            f"{file.duration:.3f}" if file.duration is not None else "",
            f"{file.bitrate_kbps:.1f}" if file.bitrate_kbps is not None else "",
            "yes" if file.healthy else ("no" if file.healthy is False else ""),
            file.health_note or "",
            file.exact_key_type or "",
            action,
            dest,
        ]
        rows.append(row)
    return rows


def write_csv(
    report_path: Path, groups: Sequence[GroupResult], trash_dir: Path, commit: bool
) -> None:
    """Write the deduplication plan to *report_path*."""

    ensure_directory(report_path.parent)
    with report_path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_HEADERS)
        for group in groups:
            for row in group_to_rows(group, trash_dir, commit):
                writer.writerow(row)


###############################################################################
# File operations
###############################################################################


def plan_trash_destination(trash_dir: Path, file_path: Path) -> Path:
    """Return the destination inside the trash directory preserving structure."""

    try:
        rel = file_path.relative_to(file_path.anchor)
    except ValueError:
        rel = Path(file_path.name)
    return trash_dir.joinpath(rel)


def move_duplicates(groups: Sequence[GroupResult], trash_dir: Path) -> None:
    """Move loser files to the trash directory."""

    ensure_directory(trash_dir)
    for group in groups:
        for file in group.losers:
            dest = plan_trash_destination(trash_dir, file.path)
            ensure_directory(dest.parent)
            log(f"Moving {file.path} -> {dest}")
            shutil.move(file.path.as_posix(), dest.as_posix())


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

    def _handler(self, signum, frame) -> None:  # pragma: no cover
        self._sigint_count += 1
        if self._sigint_count == 1:
            log("Received Ctrl-C — finishing current tasks then stopping… (press Ctrl-C again to abort now)")
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
    broken_playlist_set = set()
    broken_playlist_path = kwargs.get("broken_playlist_path")
    if broken_playlist_path and os.path.exists(broken_playlist_path):
        with open(broken_playlist_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    broken_playlist_set.add(line)

    def append_broken_playlist(path: Path):
        if not broken_playlist_path:
            return
        abs_path = str(path.resolve())
        if abs_path in broken_playlist_set:
            return
        try:
            Path(broken_playlist_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        with open(broken_playlist_path, "a") as f:
            f.write(abs_path + "\n")
        broken_playlist_set.add(abs_path)

    # Use provided watchdog timeout when available; fallback to a generous default
    WATCHDOG_TIMEOUT = int(kwargs.get("watchdog_timeout", 300) or 300)
    def watchdog():
        import time
        while not freeze_detector_stop.is_set():
            time.sleep(5)
            if time.time() - last_progress_timestamp > WATCHDOG_TIMEOUT:
                # Prefer logging and requesting a graceful stop over hard-killing the process.
                print(f"[WATCHDOG] No progress for {WATCHDOG_TIMEOUT} seconds. Requesting shutdown.", flush=True)
                if common.DIAGNOSTICS is not None:
                    common.DIAGNOSTICS.record_watchdog(
                        f"No progress for {WATCHDOG_TIMEOUT} seconds",
                        context=last_progress_file,
                    )
                # Signal the freeze detector and request shutdown if available
                try:
                    freeze_detector_stop.set()
                except Exception:
                    pass
                # If a shutdown object was passed in kwargs, try to set its stop event
                try:
                    sd = kwargs.get("shutdown")
                    if sd and hasattr(sd, "_stop_event"):
                        sd._stop_event.set()
                except Exception:
                    pass
                # After requesting shutdown, exit the watchdog thread
                freeze_detector_stop.set()
                return

    threading.Thread(target=watchdog, daemon=True).start()
    """Walk the filesystem and update cached :class:`FileInfo` entries."""

    # Freeze detector watcher logic
    def freeze_detector_watcher(quarantine_dir=None):
        import time
        kill_in_terminal = bool(kwargs.get("kill_in_terminal", True))
        while not freeze_detector_stop.is_set():
            time.sleep(5)
            now = time.time()
            # print(f"\033[33m[FREEZE WATCH]\033[0m now={now:.1f}, last={last_progress_timestamp:.1f}, "
            #       f"diff={now - last_progress_timestamp:.1f}, file={last_progress_file}", flush=True)
            if now - last_progress_timestamp > 30 and last_progress_file:
                print(f"[FREEZE DETECTOR] Triggered: no progress for 30s on "
                      f"{last_progress_file}", flush=True)
                log(f"WARNING: No progress for 30s. Last file: {last_progress_file}")
                if common.DIAGNOSTICS is not None:
                    common.DIAGNOSTICS.record_watchdog(
                        "Freeze detector triggered",
                        context=last_progress_file,
                    )
                # Kill any stalled ffmpeg processes. Optionally run the pkill
                # command in a separate Terminal window on macOS so the action
                # is visible to the user. When not requested or unavailable we
                # fall back to running pkill in this process (non-fatal).
                try:
                    # First prefer targeted kills for pgids we know we spawned.
                    with active_pgid_lock:
                        pgids = list(active_ffmpeg_pgids)

                    if pgids:
                        log(f"Freeze detector: attempting targeted kill of {len(pgids)} ffmpeg pgid(s)")
                        # Send TERM first
                        for pgid in pgids:
                            try:
                                os.killpg(pgid, signal.SIGTERM)
                            except Exception:
                                pass
                        # Give processes a short grace period
                        time.sleep(0.5)
                        # Send KILL for any remaining
                        for pgid in pgids:
                            try:
                                # Check if any pid in the group still exists by attempting to send 0
                                os.killpg(pgid, 0)
                            except Exception:
                                # group gone
                                continue
                            try:
                                os.killpg(pgid, signal.SIGKILL)
                            except Exception:
                                pass
                        log("Freeze detector: targeted kill completed")
                    else:
                        # No tracked pgids — fall back to previous behavior which uses pkill.
                        # Prefer an absolute pkill path when available, otherwise try killall.
                        pkill_path = shutil.which("pkill")
                        killall_path = shutil.which("killall")
                        if kill_in_terminal and sys.platform == "darwin" and pkill_path:
                            # Use the absolute pkill path in the Terminal script for visibility
                            script = f"{pkill_path} ffmpeg; echo 'pkill (TERM) sent'; exit"
                            osa_cmd = [
                                "osascript",
                                "-e",
                                f'tell application "Terminal" to do script "{script}"',
                            ]
                            subprocess.run(osa_cmd, check=False, timeout=5)
                            log("Issued pkill (TERM) ffmpeg in a new Terminal window")
                        else:
                            if pkill_path:
                                subprocess.run([pkill_path, "ffmpeg"], check=False, timeout=5)
                                log("Sent TERM to stalled ffmpeg processes (pkill)")
                            elif killall_path:
                                # macOS killall accepts process names; use it as a fallback.
                                subprocess.run([killall_path, "ffmpeg"], check=False, timeout=5)
                                log("Sent TERM to stalled ffmpeg processes (killall)")
                            else:
                                log("No pkill/killall found in PATH; cannot run global pkill fallback")
                except Exception as e:
                    log(f"Failed to kill ffmpeg: {e}")
                if quarantine_dir and os.path.exists(last_progress_file):
                    try:
                        os.makedirs(quarantine_dir, exist_ok=True)
                        dest = os.path.join(quarantine_dir, os.path.basename(last_progress_file))
                        shutil.move(last_progress_file, dest)
                        log(f"Moved frozen file to quarantine: {dest}")
                    except Exception as e:
                        log(f"Failed to quarantine file: {e}")
                freeze_detector_stop.set()

    # Start freeze detector watcher after docstring
    quarantine_dir = None
    if auto_quarantine:
        quarantine_dir = os.path.join(str(root), '_BROKEN')
    watcher = threading.Thread(target=freeze_detector_watcher, args=(quarantine_dir,), daemon=True)
    watcher.start()

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

    def log_scan_entry(path: Path, status: str):
        try:
            ts = _dt.datetime.now().isoformat()
            with open(log_path, "a") as f:
                f.write(f"{ts}\t{path}\t{status}\n")
        except Exception:
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
            if not filename.lower().endswith('.flac'):
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

    def analyze(task: Tuple[Path, os.stat_result, Optional[FileInfo], int]) -> Optional[FileInfo]:
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
            info.codec = metadata.get("codec") or "flac"
            info.duration = metadata.get("duration")
            info.bitrate_kbps = metadata.get("bitrate_kbps")
            stream_md5 = metadata.get("stream_md5")
            if stream_md5:
                info.stream_md5 = stream_md5

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
            except Exception:
                # don't let logging errors interrupt the run
                pass
            append_broken_playlist(path)
            log("Added broken file to playlist")
            log(f"Skipping broken file (cached metadata): {path}")
            # Do not early-return None; return the populated info so the outer loop
            # will upsert it into the DB and future runs will treat it as cached.
            return info

        return info

    def print_progress(completed, total, width=50):
        global last_timestamp_color
        percent = completed / total if total > 0 else 0
        color = last_timestamp_color
        print(f"\r{color}{completed}/{total}\033[0m \033[1;37m({percent:.1%})\033[0m", end='', flush=True)

    if pending:
        import time
        max_workers = max(1, workers)
        total_files = len(pending)
        completed = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(analyze, task): task[0] for task in pending
            }
            print(f"\033[36m[DIAG] Submitted {len(future_map)} tasks to ThreadPoolExecutor\033[0m", flush=True)
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
                    except Exception:
                        pass
                    continue
                if info is None:
                    # Log as SKIPPED if no info returned
                    try:
                        log_scan_entry(path, "SKIPPED")
                    except Exception:
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
                except Exception:
                    pass
                completed += 1
                print_progress(completed, total_files)
                if completed % 100 == 0 or completed == total_files:
                    print(f"[{time.strftime('%H:%M:%S')}] Processed {completed}/{total_files} files")
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

    now = _dt.datetime.now(_dt.UTC).isoformat()
    cursor = conn.execute(
        """
        INSERT INTO runs (started_at, root, options_json, dry_run)
        VALUES (?, ?, ?, ?)
        """,
        (now, root.as_posix(), json.dumps(options), int(dry_run)),
    )
    conn.commit()
    return cursor.lastrowid


def finalize_run(conn: sqlite3.Connection, run_id: int) -> None:
    """Update the run record with the finishing timestamp."""

    now = _dt.datetime.now(_dt.UTC).isoformat()
    conn.execute("UPDATE runs SET finished_at=? WHERE id=?", (now, run_id))
    conn.commit()


def persist_groups(conn: sqlite3.Connection, run_id: int, groups: Sequence[GroupResult]) -> None:
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
        help="Seconds for short external commands (fpcalc, flac -t, ffprobe, metaflac)"
    )
    parser.add_argument(
        "--decode-timeout",
        type=int,
        default=30,
        help="Seconds allowed for decoding/streaming operations (ffmpeg hashing)"
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
    diag_root = Path(getattr(args, "diagnostic_root", "/Volumes/dotad/.dedupe_diagnostics")).expanduser()
    common.DIAGNOSTICS = DiagnosticsManager(
        root=diag_root,
        dump_fpcalc=getattr(args, "dump_fpcalc", True),
        dump_decode=getattr(args, "dump_decode", True),
        dump_watchdog=getattr(args, "dump_watchdog", True),
    )
    log(f"Diagnostics root: {common.DIAGNOSTICS.root}")
    if getattr(args, "fpcalc_dump_latest", False) or getattr(args, "check_fpcalc", False):
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
        if getattr(args, "fpcalc_dump_latest", False) and not getattr(args, "check_fpcalc", False):
            return 0
        if getattr(args, "check_fpcalc", False):
            return 0
    trash_dir = Path(args.trash_dir).expanduser() if getattr(args, "trash_dir", None) else None
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
        broken_playlist_path=str(args.broken_playlist) if getattr(args, "broken_playlist", None) else None,
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
