#!/usr/bin/env python3
"""Fast folder triage against DB by tags.

Purpose:
- Scan a folder of audio files (default: FLAC)
- Identify files already represented in the DB using tag-based matching
- Process only unmatched files via an optional command

Matching priority:
1) ISRC
2) Beatport track ID
3) Normalized title+artist+album
4) Normalized title+artist (duration-gated when possible)

This tool is intentionally hash-free for speed.
"""

from __future__ import annotations

import argparse
import csv
import json
import shlex
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from collections import Counter

from mutagen import File as MutagenFile

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tagslut.utils.db import DbResolutionError, resolve_cli_env_db_path

DURATION_TOLERANCE_S = 2.0
TRACKER_SCHEMA = "tag_triage_tracker_v1"


@dataclass
class DbRow:
    path: str
    isrc: str
    beatport_id: str
    title: str
    artist: str
    album: str
    duration_s: float | None
    download_source: str


def _human_seconds(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    mins, sec = divmod(total, 60)
    hours, mins = divmod(mins, 60)
    if hours:
        return f"{hours}h{mins:02d}m{sec:02d}s"
    if mins:
        return f"{mins}m{sec:02d}s"
    return f"{sec}s"


def _print_stage(title: str) -> None:
    print("")
    print("=" * 72)
    print(title)
    print("=" * 72)


def _load_tracker(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema": TRACKER_SCHEMA,
            "run_key": "",
            "triage_cache": {},
            "process": {},
            "last_outputs": {},
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("tracker root is not object")
    except Exception:
        return {
            "schema": TRACKER_SCHEMA,
            "run_key": "",
            "triage_cache": {},
            "process": {},
            "last_outputs": {},
        }

    payload.setdefault("schema", TRACKER_SCHEMA)
    payload.setdefault("run_key", "")
    payload.setdefault("triage_cache", {})
    payload.setdefault("process", {})
    payload.setdefault("last_outputs", {})
    return payload


def _save_tracker(path: Path, tracker: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(tracker, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _build_run_key(folder: Path, db_path: Path, recursive: bool, extensions: set[str]) -> str:
    ext_key = ",".join(sorted(extensions))
    return f"{folder}|{db_path}|recursive={int(recursive)}|ext={ext_key}"


def _file_stat(path: Path) -> tuple[int, int]:
    st = path.stat()
    return int(st.st_size), int(st.st_mtime_ns)


def norm_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(str(value).strip().lower().split())


def norm_isrc(value: str | None) -> str:
    if not value:
        return ""
    return str(value).upper().replace("-", "").replace(" ", "").strip()


def parse_json(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def first_meta(meta: dict[str, Any], keys: list[str]) -> str:
    lower = {str(k).lower(): v for k, v in meta.items()}
    for key in keys:
        raw = lower.get(key.lower())
        if isinstance(raw, list) and raw:
            val = str(raw[0]).strip()
            if val:
                return val
        elif raw is not None:
            val = str(raw).strip()
            if val:
                return val
    return ""


def load_db_indexes(
    db_path: Path,
) -> tuple[
    dict[str, list[DbRow]],
    dict[str, list[DbRow]],
    dict[str, list[DbRow]],
    dict[str, list[DbRow]],
]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            path,
            canonical_isrc,
            isrc,
            beatport_id,
            canonical_title,
            canonical_artist,
            canonical_album,
            canonical_duration,
            duration,
            metadata_json,
            download_source
        FROM files
        """
    )

    by_isrc: dict[str, list[DbRow]] = {}
    by_beatport: dict[str, list[DbRow]] = {}
    by_exact3: dict[str, list[DbRow]] = {}
    by_exact2: dict[str, list[DbRow]] = {}

    def add_idx(idx: dict[str, list[DbRow]], key: str, row: DbRow) -> None:
        if not key or not key.strip("|"):
            return
        idx.setdefault(key, []).append(row)

    for rec in cur.fetchall():
        meta = parse_json(rec["metadata_json"])

        isrc = norm_isrc(
            rec["canonical_isrc"]
            or rec["isrc"]
            or first_meta(meta, ["isrc", "tsrc"])
        )
        beatport_id = (
            str(
                rec["beatport_id"]
                or first_meta(meta, ["beatport_id", "beatport_track_id", "bp_track_id"])
            )
            .strip()
        )
        title = (
            str(
                rec["canonical_title"]
                or first_meta(meta, ["title", "track_title", "name"])
            )
            .strip()
        )
        artist = (
            str(
                rec["canonical_artist"]
                or first_meta(meta, ["artist", "albumartist"])
            )
            .strip()
        )
        album = (
            str(
                rec["canonical_album"]
                or first_meta(meta, ["album", "release"])
            )
            .strip()
        )
        duration_s: float | None = None
        raw_duration = rec["canonical_duration"] or rec["duration"]
        try:
            if raw_duration is not None:
                duration_s = float(raw_duration)
        except Exception:
            duration_s = None

        row = DbRow(
            path=str(rec["path"]),
            isrc=isrc,
            beatport_id=beatport_id,
            title=title,
            artist=artist,
            album=album,
            duration_s=duration_s,
            download_source=(rec["download_source"] or "").strip(),
        )

        add_idx(by_isrc, row.isrc, row)
        add_idx(by_beatport, row.beatport_id, row)
        add_idx(by_exact3, "|".join([norm_text(row.title), norm_text(row.artist), norm_text(row.album)]), row)
        add_idx(by_exact2, "|".join([norm_text(row.title), norm_text(row.artist)]), row)

    conn.close()
    return by_isrc, by_beatport, by_exact3, by_exact2


def list_files(root: Path, recursive: bool, exts: set[str]) -> list[Path]:
    if recursive:
        files = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in exts]
    else:
        files = [p for p in root.iterdir() if p.is_file() and p.suffix.lower() in exts]
    return sorted(files)


def read_local_tags(path: Path) -> dict[str, Any]:
    audio = MutagenFile(path, easy=True)
    if audio is None:
        raise RuntimeError("mutagen returned None")
    tags = audio.tags or {}
    normalized: dict[str, list[str]] = {}
    if hasattr(tags, "items"):
        for key, value in tags.items():
            k = str(key).lower()
            if isinstance(value, list):
                normalized[k] = [str(x).strip() for x in value if str(x).strip()]
            elif value is not None:
                v = str(value).strip()
                normalized[k] = [v] if v else []
    duration_s = getattr(audio.info, "length", None)
    return {"tags": normalized, "duration_s": float(duration_s) if duration_s else None}


def first_tag(tags: dict[str, list[str]], keys: list[str]) -> str:
    for key in keys:
        values = tags.get(key.lower(), [])
        if values:
            return values[0].strip()
    return ""


def choose_best_duration_match(rows: list[DbRow], duration_s: float | None) -> DbRow | None:
    if not rows:
        return None
    if duration_s is None:
        return rows[0]
    best: tuple[DbRow, float] | None = None
    for row in rows:
        if row.duration_s is None:
            continue
        delta = abs(row.duration_s - duration_s)
        if delta <= DURATION_TOLERANCE_S:
            if best is None or delta < best[1]:
                best = (row, delta)
    if best is not None:
        return best[0]
    return None


def run_process_command(template: str, file_path: Path) -> int:
    formatted = template.format(path=str(file_path), qpath=shlex.quote(str(file_path)))
    if "{path}" not in template and "{qpath}" not in template:
        formatted = f"{formatted} {shlex.quote(str(file_path))}"
    print(f"[process] {formatted}")
    return subprocess.run(formatted, shell=True).returncode


def flac_probe(path: Path) -> tuple[bool | None, str]:
    """Optional FLAC integrity probe for promotion diagnostics."""
    try:
        res = subprocess.run(
            ["flac", "-t", "--silent", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None, "flac binary missing"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"

    if res.returncode == 0:
        return True, ""
    err = (res.stderr or res.stdout or "").strip()
    return False, err[:300] or "flac -t failed"


def build_promotion_report(
    db_path: Path,
    files: list[Path],
    out_path: Path,
    verify_flac: bool,
) -> tuple[int, int, Counter[str]]:
    """Evaluate promote-by-tags style blockers for a list of files."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    ready = 0
    blocked = 0
    blocker_counts: Counter[str] = Counter()

    with out_path.open("w", encoding="utf-8", newline="") as fout:
        writer = csv.DictWriter(
            fout,
            fieldnames=[
                "file_path",
                "db_row_exists",
                "duration_status",
                "flac_ok_db",
                "dj_flag",
                "is_dj_material",
                "mgmt_status",
                "download_source",
                "flac_probe_ok",
                "flac_probe_note",
                "promotable_default",
                "blockers",
            ],
        )
        writer.writeheader()

        for file_path in files:
            row = conn.execute(
                """
                SELECT
                    duration_status,
                    flac_ok,
                    dj_flag,
                    is_dj_material,
                    mgmt_status,
                    download_source
                FROM files
                WHERE path = ?
                """,
                (str(file_path),),
            ).fetchone()

            blockers: list[str] = []
            duration_status = ""
            flac_ok_db = ""
            dj_flag = ""
            is_dj_material = ""
            mgmt_status = ""
            download_source = ""
            db_row_exists = bool(row)

            if row:
                duration_status = str(row["duration_status"] or "").strip().lower()
                flac_ok_db = "" if row["flac_ok"] is None else str(row["flac_ok"])
                dj_flag = "" if row["dj_flag"] is None else str(row["dj_flag"])
                is_dj_material = "" if row["is_dj_material"] is None else str(row["is_dj_material"])
                mgmt_status = str(row["mgmt_status"] or "").strip()
                download_source = str(row["download_source"] or "").strip()

                # Default promote-by-tags gate: duration_status must be ok when DB is available.
                if duration_status != "ok":
                    blockers.append(f"duration_status={duration_status or 'missing'}")
            else:
                blockers.append("db_row_missing")
                blockers.append("duration_status=missing")

            flac_probe_ok: str = ""
            flac_probe_note: str = ""
            if verify_flac:
                probe_ok, probe_note = flac_probe(file_path)
                flac_probe_ok = "" if probe_ok is None else ("1" if probe_ok else "0")
                flac_probe_note = probe_note
                if probe_ok is False:
                    blockers.append("flac_probe_failed")

            promotable = len(blockers) == 0
            if promotable:
                ready += 1
            else:
                blocked += 1
                for b in blockers:
                    blocker_counts[b] += 1

            writer.writerow(
                {
                    "file_path": str(file_path),
                    "db_row_exists": "1" if db_row_exists else "0",
                    "duration_status": duration_status,
                    "flac_ok_db": flac_ok_db,
                    "dj_flag": dj_flag,
                    "is_dj_material": is_dj_material,
                    "mgmt_status": mgmt_status,
                    "download_source": download_source,
                    "flac_probe_ok": flac_probe_ok,
                    "flac_probe_note": flac_probe_note,
                    "promotable_default": "1" if promotable else "0",
                    "blockers": ";".join(blockers),
                }
            )

    conn.close()
    return ready, blocked, blocker_counts


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fast tag-only folder triage against DB; process unmatched files only."
    )
    parser.add_argument("folder", help="Folder to scan")
    parser.add_argument(
        "--db",
        help="Path to music.db (or set TAGSLUT_DB)",
    )
    parser.add_argument("--out-dir", default="artifacts/tag_triage", help="Output directory")
    parser.add_argument("--extensions", default=".flac", help="Comma-separated extensions (default: .flac)")
    parser.add_argument("--no-recursive", action="store_true", help="Scan only top-level folder")
    parser.add_argument("--limit", type=int, help="Only scan first N files")
    parser.add_argument("--progress-every", type=int, default=100, help="Progress line every N files")
    parser.add_argument("--quiet", action="store_true", help="Reduce per-file output")
    parser.add_argument(
        "--process-cmd",
        help='Run this command for each unmatched file (supports {path} and {qpath} placeholders)',
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue processing unmatched files even if a command fails",
    )
    parser.add_argument(
        "--promotion-report",
        action="store_true",
        help="Write promotion eligibility report for unmatched files",
    )
    parser.add_argument(
        "--promotion-verify-flac",
        action="store_true",
        help="With --promotion-report, run `flac -t` probe per unmatched file (slower)",
    )
    parser.add_argument(
        "--tracker-file",
        default="",
        help="Tracker JSON path (default: <out-dir>/tag_triage_tracker.json)",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Disable tracker resume cache for triage/processing",
    )
    parser.add_argument(
        "--reset-tracker",
        action="store_true",
        help="Reset tracker state before running",
    )

    args = parser.parse_args()
    run_started_at = time.time()

    try:
        db_resolution = resolve_cli_env_db_path(args.db, purpose="read", source_label="--db")
    except DbResolutionError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    db_path = db_resolution.path
    print(f"Resolved DB path: {db_path}")
    folder = Path(args.folder).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if not folder.exists() or not folder.is_dir():
        raise SystemExit(f"Folder not found or not a directory: {folder}")

    extensions = {ext.strip().lower() if ext.strip().startswith(".") else f".{ext.strip().lower()}" for ext in args.extensions.split(",") if ext.strip()}
    if not extensions:
        raise SystemExit("No valid extensions provided")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    decisions_csv = out_dir / f"tag_triage_decisions_{ts}.csv"
    unmatched_txt = out_dir / f"tag_triage_unmatched_{ts}.txt"
    matched_txt = out_dir / f"tag_triage_matched_{ts}.txt"
    promotion_csv = out_dir / f"tag_triage_promotion_report_{ts}.csv"

    recursive = not args.no_recursive
    tracker_enabled = not args.no_resume
    tracker_path = (
        Path(args.tracker_file).expanduser().resolve()
        if args.tracker_file
        else (out_dir / "tag_triage_tracker.json").resolve()
    )
    run_key = _build_run_key(folder=folder, db_path=db_path, recursive=recursive, extensions=extensions)

    def _fresh_tracker() -> dict[str, Any]:
        return {
            "schema": TRACKER_SCHEMA,
            "run_key": run_key,
            "triage_cache": {},
            "process": {},
            "last_outputs": {},
        }

    tracker = _fresh_tracker()
    if tracker_enabled:
        tracker = _load_tracker(tracker_path)
        if args.reset_tracker:
            tracker = _fresh_tracker()
            print(f"[tracker] reset: {tracker_path}")
        elif tracker.get("schema") != TRACKER_SCHEMA:
            tracker = _fresh_tracker()
            print(f"[tracker] schema mismatch -> reset: {tracker_path}")
        elif tracker.get("run_key") != run_key:
            tracker = _fresh_tracker()
            print("[tracker] run configuration changed -> starting fresh cache")

        tracker["schema"] = TRACKER_SCHEMA
        tracker["run_key"] = run_key
        tracker["last_outputs"] = {
            "decisions_csv": str(decisions_csv),
            "matched_txt": str(matched_txt),
            "unmatched_txt": str(unmatched_txt),
        }
        _save_tracker(tracker_path, tracker)
        print(f"[tracker] enabled: {tracker_path}")
    else:
        print("[tracker] disabled (--no-resume)")

    _print_stage("Stage 1/4: Load DB Indexes")
    stage_started = time.time()
    by_isrc, by_beatport, by_exact3, by_exact2 = load_db_indexes(db_path)
    print(
        "DB indexes:"
        f" isrc={len(by_isrc)}"
        f" beatport={len(by_beatport)}"
        f" title+artist+album={len(by_exact3)}"
        f" title+artist={len(by_exact2)}"
    )
    print(f"index_load_elapsed: {_human_seconds(time.time() - stage_started)}")

    _print_stage("Stage 2/4: Tag Triage")
    files = list_files(folder, recursive=recursive, exts=extensions)
    if args.limit:
        files = files[: args.limit]
    total_files = len(files)
    print(f"folder: {folder}")
    print(f"files_discovered: {total_files}")
    if total_files == 0:
        print("No files found for selected extensions.")

    matched_count = 0
    unmatched_count = 0
    errors_count = 0
    process_failures = 0
    unmatched_files: list[Path] = []
    matched_files: list[Path] = []
    cache_hits = 0
    cache_misses = 0
    match_method_counts: Counter[str] = Counter()

    triage_cache: dict[str, dict[str, Any]]
    if tracker_enabled:
        triage_cache = tracker.setdefault("triage_cache", {})
    else:
        triage_cache = {}

    triage_started = time.time()

    with decisions_csv.open("w", encoding="utf-8", newline="") as fout:
        writer = csv.DictWriter(
            fout,
            fieldnames=[
                "file_path",
                "decision",
                "match_method",
                "db_path",
                "db_source",
                "isrc",
                "beatport_id",
                "title",
                "artist",
                "album",
                "duration_s",
                "error",
            ],
        )
        writer.writeheader()

        for idx, file_path in enumerate(files, start=1):
            cache_key = str(file_path)
            file_size: int | None = None
            file_mtime_ns: int | None = None
            cached_row: dict[str, Any] | None = None
            try:
                file_size, file_mtime_ns = _file_stat(file_path)
                if tracker_enabled:
                    candidate = triage_cache.get(cache_key)
                    if (
                        isinstance(candidate, dict)
                        and candidate.get("size") == file_size
                        and candidate.get("mtime_ns") == file_mtime_ns
                    ):
                        cached_row = candidate
            except Exception as exc:
                cached_row = None
                row = {
                    "file_path": str(file_path),
                    "decision": "unmatched",
                    "match_method": "",
                    "db_path": "",
                    "db_source": "",
                    "isrc": "",
                    "beatport_id": "",
                    "title": "",
                    "artist": "",
                    "album": "",
                    "duration_s": "",
                    "error": f"stat error: {exc}",
                }
                cache_misses += 1
                unmatched_count += 1
                errors_count += 1
                unmatched_files.append(file_path)
                writer.writerow(row)
                if not args.quiet:
                    print(f"[UNMATCHED] {file_path.name} (stat error)")
                continue

            if cached_row is not None:
                cache_hits += 1
                row = {
                    "file_path": cache_key,
                    "decision": str(cached_row.get("decision", "unmatched")),
                    "match_method": str(cached_row.get("match_method", "")),
                    "db_path": str(cached_row.get("db_path", "")),
                    "db_source": str(cached_row.get("db_source", "")),
                    "isrc": str(cached_row.get("isrc", "")),
                    "beatport_id": str(cached_row.get("beatport_id", "")),
                    "title": str(cached_row.get("title", "")),
                    "artist": str(cached_row.get("artist", "")),
                    "album": str(cached_row.get("album", "")),
                    "duration_s": str(cached_row.get("duration_s", "")),
                    "error": str(cached_row.get("error", "")),
                }
            else:
                cache_misses += 1
                try:
                    local = read_local_tags(file_path)
                    tags = local["tags"]
                    duration_s = local["duration_s"]
                    isrc = norm_isrc(first_tag(tags, ["isrc", "tsrc"]))
                    beatport_id = first_tag(tags, ["beatport_track_id", "bp_track_id", "beatport_id"]).strip()
                    title = first_tag(tags, ["title", "tracktitle", "name"])
                    artist = first_tag(tags, ["artist", "albumartist"])
                    album = first_tag(tags, ["album"])
                except Exception as exc:
                    row = {
                        "file_path": str(file_path),
                        "decision": "unmatched",
                        "match_method": "",
                        "db_path": "",
                        "db_source": "",
                        "isrc": "",
                        "beatport_id": "",
                        "title": "",
                        "artist": "",
                        "album": "",
                        "duration_s": "",
                        "error": str(exc),
                    }
                else:
                    matched_row: DbRow | None = None
                    method = ""

                    if isrc and isrc in by_isrc:
                        matched_row = by_isrc[isrc][0]
                        method = "isrc"
                    elif beatport_id and beatport_id in by_beatport:
                        matched_row = by_beatport[beatport_id][0]
                        method = "beatport_id"
                    else:
                        key3 = "|".join([norm_text(title), norm_text(artist), norm_text(album)])
                        if key3.strip("|") and key3 in by_exact3:
                            matched_row = choose_best_duration_match(by_exact3[key3], duration_s) or by_exact3[key3][0]
                            method = "title_artist_album"
                        else:
                            key2 = "|".join([norm_text(title), norm_text(artist)])
                            if key2.strip("|") and key2 in by_exact2:
                                duration_match = choose_best_duration_match(by_exact2[key2], duration_s)
                                if duration_match is not None:
                                    matched_row = duration_match
                                    method = "title_artist_duration"
                                else:
                                    matched_row = by_exact2[key2][0]
                                    method = "title_artist"

                    row = {
                        "file_path": str(file_path),
                        "decision": "matched" if matched_row is not None else "unmatched",
                        "match_method": method if matched_row is not None else "",
                        "db_path": matched_row.path if matched_row is not None else "",
                        "db_source": matched_row.download_source if matched_row is not None else "",
                        "isrc": isrc,
                        "beatport_id": beatport_id,
                        "title": title,
                        "artist": artist,
                        "album": album,
                        "duration_s": f"{duration_s:.3f}" if isinstance(duration_s, float) else "",
                        "error": "",
                    }

                if tracker_enabled and file_size is not None and file_mtime_ns is not None:
                    triage_cache[cache_key] = {
                        "size": file_size,
                        "mtime_ns": file_mtime_ns,
                        "decision": row["decision"],
                        "match_method": row["match_method"],
                        "db_path": row["db_path"],
                        "db_source": row["db_source"],
                        "isrc": row["isrc"],
                        "beatport_id": row["beatport_id"],
                        "title": row["title"],
                        "artist": row["artist"],
                        "album": row["album"],
                        "duration_s": row["duration_s"],
                        "error": row["error"],
                    }

            writer.writerow(row)
            if row["decision"] == "matched":
                matched_count += 1
                matched_files.append(file_path)
                method = str(row["match_method"] or "")
                if method:
                    match_method_counts[method] += 1
                if not args.quiet:
                    print(f"[MATCH {method or 'cached'}] {file_path.name}")
            else:
                unmatched_count += 1
                unmatched_files.append(file_path)
                if row["error"]:
                    errors_count += 1
                if not args.quiet:
                    print(f"[UNMATCHED] {file_path.name}")

            if args.progress_every > 0 and (idx % args.progress_every == 0 or idx == total_files):
                elapsed = max(0.001, time.time() - triage_started)
                rate = idx / elapsed
                eta = (total_files - idx) / rate if rate > 0 else 0
                pct = (idx / total_files * 100) if total_files else 100.0
                print(
                    f"[triage {idx}/{total_files} {pct:5.1f}%] "
                    f"matched={matched_count} unmatched={unmatched_count} errors={errors_count} "
                    f"cache_hit={cache_hits} cache_miss={cache_misses} eta={_human_seconds(eta)}"
                )

            if tracker_enabled and idx % 25 == 0:
                tracker["last_outputs"] = {
                    "decisions_csv": str(decisions_csv),
                    "matched_txt": str(matched_txt),
                    "unmatched_txt": str(unmatched_txt),
                }
                _save_tracker(tracker_path, tracker)

    unmatched_txt.write_text("\n".join(str(p) for p in unmatched_files) + ("\n" if unmatched_files else ""), encoding="utf-8")
    matched_txt.write_text("\n".join(str(p) for p in matched_files) + ("\n" if matched_files else ""), encoding="utf-8")

    if tracker_enabled:
        tracker["last_outputs"] = {
            "decisions_csv": str(decisions_csv),
            "matched_txt": str(matched_txt),
            "unmatched_txt": str(unmatched_txt),
        }
        _save_tracker(tracker_path, tracker)

    print("")
    print("Tag triage complete")
    print(f"  folder:        {folder}")
    print(f"  db:            {db_path}")
    print(f"  scanned:       {total_files}")
    print(f"  matched:       {matched_count}")
    print(f"  unmatched:     {unmatched_count}")
    print(f"  read_errors:   {errors_count}")
    print(f"  cache_hits:    {cache_hits}")
    print(f"  cache_misses:  {cache_misses}")
    print(f"  elapsed:       {_human_seconds(time.time() - triage_started)}")
    print(f"  decisions_csv: {decisions_csv}")
    print(f"  matched_txt:   {matched_txt}")
    print(f"  unmatched_txt: {unmatched_txt}")
    if tracker_enabled:
        print(f"  tracker:       {tracker_path}")
    if match_method_counts:
        print("  match_breakdown:")
        for method, count in match_method_counts.most_common():
            print(f"    {method}: {count}")

    if args.process_cmd:
        _print_stage("Stage 3/4: Process Unmatched Files")
        if not unmatched_files:
            print("No unmatched files to process.")
        else:
            process_started = time.time()
            process_attempted = 0
            process_success = 0
            process_resumed = 0
            process_cache: dict[str, dict[str, Any]]
            if tracker_enabled:
                process_meta = tracker.setdefault("process_meta", {})
                process_key = f"{run_key}|cmd={args.process_cmd}"
                if process_meta.get("key") != process_key:
                    tracker["process"] = {}
                    process_meta["key"] = process_key
                    process_meta["updated_at"] = datetime.now().isoformat(timespec="seconds")
                    _save_tracker(tracker_path, tracker)
                process_cache = tracker.setdefault("process", {})
            else:
                process_cache = {}

            for idx, file_path in enumerate(unmatched_files, start=1):
                cache_key = str(file_path)
                file_size: int | None = None
                file_mtime_ns: int | None = None
                can_skip = False
                if tracker_enabled:
                    try:
                        file_size, file_mtime_ns = _file_stat(file_path)
                    except Exception:
                        file_size = None
                        file_mtime_ns = None
                    cached = process_cache.get(cache_key)
                    if (
                        isinstance(cached, dict)
                        and file_size is not None
                        and file_mtime_ns is not None
                        and cached.get("size") == file_size
                        and cached.get("mtime_ns") == file_mtime_ns
                        and cached.get("status") == "ok"
                    ):
                        can_skip = True

                if can_skip:
                    process_resumed += 1
                    if not args.quiet:
                        print(f"[resume-skip {idx}/{len(unmatched_files)}] {file_path.name}")
                    continue

                process_attempted += 1
                print(f"[process {idx}/{len(unmatched_files)}] {file_path}")
                rc = run_process_command(args.process_cmd, file_path)
                ok = rc == 0
                if ok:
                    process_success += 1
                else:
                    process_failures += 1
                    print(f"[process-error] exit={rc} file={file_path}")

                if tracker_enabled and file_size is not None and file_mtime_ns is not None:
                    process_cache[cache_key] = {
                        "size": file_size,
                        "mtime_ns": file_mtime_ns,
                        "status": "ok" if ok else "fail",
                        "exit_code": rc,
                        "updated_at": datetime.now().isoformat(timespec="seconds"),
                    }
                    if idx % 10 == 0 or not ok:
                        _save_tracker(tracker_path, tracker)

                if not ok and not args.continue_on_error:
                    print("Stopping due to command failure (use --continue-on-error to continue).")
                    break

            if tracker_enabled:
                _save_tracker(tracker_path, tracker)

            print("Processing summary:")
            print(f"  unmatched_total: {len(unmatched_files)}")
            print(f"  attempted_now:   {process_attempted}")
            print(f"  resumed_skips:   {process_resumed}")
            print(f"  succeeded:       {process_success}")
            print(f"  failures:        {process_failures}")
            print(f"  elapsed:         {_human_seconds(time.time() - process_started)}")
    else:
        _print_stage("Stage 3/4: Process Unmatched Files")
        print("Skipped: no --process-cmd provided.")

    if args.promotion_report:
        _print_stage("Stage 4/4: Promotion Eligibility Report")
        ready, blocked, blocker_counts = build_promotion_report(
            db_path=db_path,
            files=unmatched_files,
            out_path=promotion_csv,
            verify_flac=bool(args.promotion_verify_flac),
        )
        print(f"  promotion_report: {promotion_csv}")
        print(f"  promotion_ready:  {ready}")
        print(f"  promotion_blocked:{blocked}")
        if blocker_counts:
            print("  blockers:")
            for blocker, count in blocker_counts.most_common():
                print(f"    {blocker}: {count}")
        if tracker_enabled:
            tracker["last_outputs"]["promotion_report"] = str(promotion_csv)
            _save_tracker(tracker_path, tracker)
    else:
        _print_stage("Stage 4/4: Promotion Eligibility Report")
        print("Skipped: no --promotion-report provided.")

    _print_stage("Run Complete")
    print(f"total_elapsed: {_human_seconds(time.time() - run_started_at)}")
    print(f"decisions_csv: {decisions_csv}")
    print(f"matched_txt:   {matched_txt}")
    print(f"unmatched_txt: {unmatched_txt}")
    if args.promotion_report:
        print(f"promotion_csv: {promotion_csv}")
    if tracker_enabled:
        print(f"tracker_file:  {tracker_path}")

    return 1 if process_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
