#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


AUDIO_EXTS = {".flac", ".mp3", ".m4a"}

DEFAULT_DB = "/Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db"

MUSIC_VOLUME = Path("/Volumes/MUSIC")
MASTER_LIBRARY_PREFIX = str(MUSIC_VOLUME / "MASTER_LIBRARY")

STEP1_TRACKS = MUSIC_VOLUME / "_work/quarantine/MUSIC/_quarantine/tracks"
STEP1_QUARANTINE = MUSIC_VOLUME / "_work/quarantine/MUSIC/_quarantine/quarantine"

STEP2_TAGSLUT_CLONE = MUSIC_VOLUME / "_work/fix/tagslut_clone"

SCAN_DIRS = [
    MUSIC_VOLUME / "_work/quarantine/MUSIC/_quarantine/quarantine",
    MUSIC_VOLUME / "_work/fix/_quarantine",
    MUSIC_VOLUME / "_work/fix/_DISCARDED_20260225_171845",
    MUSIC_VOLUME / "_work/fix/rejected_because_existing_24bit",
    MUSIC_VOLUME / "_work/fix/conflict_same_dest",
    MUSIC_VOLUME / "_work/fix/missing_tags",
    MUSIC_VOLUME / "_work/fix/path_too_long",
]

DELETE_CANDIDATES_OUT = Path(
    "/Users/georgeskhawam/Projects/tagslut/artifacts/triage_work_delete_candidates.txt"
)
KEEP_OUT = Path("/Users/georgeskhawam/Projects/tagslut/artifacts/triage_work_keep.txt")


def _human_bytes(num_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num_bytes)
    for unit in units:
        if size < 1024.0:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"


def _iter_audio_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    out: list[Path] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            p = Path(dirpath) / name
            if p.suffix.lower() in AUDIO_EXTS:
                out.append(p)
    out.sort()
    return out


def _safe_realpath(p: Path) -> str:
    try:
        return str(p.resolve())
    except Exception:
        return str(p)


def _normalize_token(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^\w\s-]", "", s)
    return s


def _escape_like(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _extract_tags_mutagen(path: Path) -> tuple[str | None, str | None, str | None]:
    # Returns (isrc, artist, title). Best-effort; never raises.
    try:
        import mutagen  # type: ignore
    except Exception:
        return (None, None, None)

    try:
        audio = mutagen.File(str(path), easy=True)
        if audio is None:
            return (None, None, None)
        isrc = None
        artist = None
        title = None

        def first(key: str) -> str | None:
            v = audio.get(key)
            if not v:
                return None
            if isinstance(v, (list, tuple)):
                return str(v[0]) if v else None
            return str(v)

        # Easy tags can vary; try common keys for ISRC.
        for k in ("isrc", "TSRC", "tsrc"):
            cand = first(k)
            if cand:
                isrc = cand
                break
        artist = first("artist")
        title = first("title")

        if isrc:
            isrc = re.sub(r"\s+", "", str(isrc)).upper()
            if not re.fullmatch(r"[A-Z0-9]{12}", isrc):
                # Keep only if plausibly formatted; otherwise discard.
                isrc = None

        return (isrc, artist, title)
    except Exception:
        return (None, None, None)


def _parse_artist_title_from_filename(path: Path) -> tuple[str | None, str | None]:
    stem = path.stem
    # Common pattern: "Artist - Title"
    parts = [p.strip() for p in stem.split(" - ", 1)]
    if len(parts) == 2 and parts[0] and parts[1]:
        return (parts[0], parts[1])
    return (None, None)


def _ensure_music_mounted() -> None:
    if not MUSIC_VOLUME.exists():
        raise RuntimeError(f"{MUSIC_VOLUME} does not exist (volume not mounted)")
    # On macOS, /Volumes/<name> is a mountpoint when mounted.
    if not os.path.ismount(str(MUSIC_VOLUME)):
        raise RuntimeError(f"{MUSIC_VOLUME} is not a mountpoint (volume not mounted)")


def _dir_tree_signature(root: Path) -> dict[str, tuple[int, int]]:
    # relpath -> (size, mtime_ns) for regular files
    sig: dict[str, tuple[int, int]] = {}
    if not root.exists():
        return sig
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            p = Path(dirpath) / name
            try:
                st = p.stat()
            except FileNotFoundError:
                continue
            if not p.is_file():
                continue
            rel = str(p.relative_to(root))
            sig[rel] = (int(st.st_size), int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))))
    return sig


def _remove_tree(path: Path, execute: bool) -> None:
    if not path.exists():
        return
    if execute:
        shutil.rmtree(path)
    else:
        print(f"DRY-RUN: would delete directory tree: {_safe_realpath(path)}")


def _git_is_repo(path: Path) -> bool:
    if not path.exists() or not path.is_dir():
        return False
    try:
        r = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        return r.returncode == 0 and r.stdout.strip().lower() == "true"
    except FileNotFoundError:
        raise RuntimeError("git not found on PATH (needed for Step 2)")


def _connect_db(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise RuntimeError(f"DB not found: {db_path}")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _db_has_table(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (name,)
    ).fetchone()
    return row is not None


def _db_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(r["name"]) for r in rows}


def _db_isrc_for_file_path(conn: sqlite3.Connection, file_path: str) -> str | None:
    if not _db_has_table(conn, "asset_file"):
        return None
    cols = _db_columns(conn, "asset_file")
    if "file_path" not in cols or "isrc" not in cols:
        return None
    row = conn.execute(
        "SELECT isrc FROM asset_file WHERE file_path = ? AND isrc IS NOT NULL AND isrc != '' LIMIT 1",
        (file_path,),
    ).fetchone()
    if not row:
        return None
    isrc = str(row["isrc"]).strip().upper()
    isrc = re.sub(r"\s+", "", isrc)
    if not re.fullmatch(r"[A-Z0-9]{12}", isrc):
        return None
    return isrc


def _db_master_library_exists_for_isrc(conn: sqlite3.Connection, isrc: str) -> bool:
    if not _db_has_table(conn, "asset_file"):
        return False
    cols = _db_columns(conn, "asset_file")
    if "file_path" not in cols or "isrc" not in cols:
        return False
    row = conn.execute(
        "SELECT 1 FROM asset_file WHERE isrc = ? AND file_path LIKE ? ESCAPE '\\' LIMIT 1",
        (isrc, _escape_like(MASTER_LIBRARY_PREFIX) + "%"),
    ).fetchone()
    return row is not None


def _db_master_library_exists_for_artist_title(
    conn: sqlite3.Connection, artist: str, title: str
) -> bool:
    if not _db_has_table(conn, "asset_file"):
        return False
    cols = _db_columns(conn, "asset_file")
    if "file_path" not in cols:
        return False

    a = _normalize_token(artist)
    t = _normalize_token(title)
    if not a or not t:
        return False

    # Conservative LIKE matching: require both tokens to appear in file_path.
    # Use wide wildcards to tolerate separators and folder nesting.
    a_like = "%" + _escape_like(a).replace(" ", "%") + "%"
    t_like = "%" + _escape_like(t).replace(" ", "%") + "%"
    prefix_like = _escape_like(MASTER_LIBRARY_PREFIX) + "%"

    row = conn.execute(
        """
        SELECT 1
        FROM asset_file
        WHERE file_path LIKE ? ESCAPE '\\'
          AND lower(file_path) LIKE ? ESCAPE '\\'
          AND lower(file_path) LIKE ? ESCAPE '\\'
        LIMIT 1
        """,
        (prefix_like, a_like, t_like),
    ).fetchone()
    return row is not None


@dataclass(frozen=True)
class FileDecision:
    path: Path
    size: int
    decision: str  # "SAFE_TO_DELETE" | "KEEP"
    reason: str


def _decide_for_file(conn: sqlite3.Connection, path: Path) -> FileDecision:
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        return FileDecision(path=path, size=0, decision="KEEP", reason="missing_on_disk")

    real_path = _safe_realpath(path)
    if real_path.startswith(MASTER_LIBRARY_PREFIX):
        return FileDecision(path=path, size=size, decision="KEEP", reason="in_master_library")

    isrc_tag, artist_tag, title_tag = _extract_tags_mutagen(path)

    isrc = isrc_tag
    if not isrc:
        isrc = _db_isrc_for_file_path(conn, real_path)
        if isrc:
            return (
                FileDecision(path=path, size=size, decision="SAFE_TO_DELETE", reason="isrc_present_in_master_library")
                if _db_master_library_exists_for_isrc(conn, isrc)
                else FileDecision(path=path, size=size, decision="KEEP", reason="isrc_not_in_master_library")
            )

    if isrc:
        if _db_master_library_exists_for_isrc(conn, isrc):
            return FileDecision(
                path=path, size=size, decision="SAFE_TO_DELETE", reason="isrc_present_in_master_library"
            )
        return FileDecision(path=path, size=size, decision="KEEP", reason="isrc_not_in_master_library")

    artist = artist_tag
    title = title_tag
    if not artist or not title:
        artist2, title2 = _parse_artist_title_from_filename(path)
        artist = artist or artist2
        title = title or title2

    if artist and title and _db_master_library_exists_for_artist_title(conn, artist, title):
        return FileDecision(
            path=path, size=size, decision="SAFE_TO_DELETE", reason="artist_title_match_in_master_library"
        )

    return FileDecision(path=path, size=size, decision="KEEP", reason="no_db_confirmation")


def _write_list(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(l + "\n" for l in lines), encoding="utf-8")


def _remove_empty_dirs(root: Path, execute: bool) -> int:
    if not root.exists():
        return 0
    removed = 0
    # Bottom-up traversal.
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        if dirnames or filenames:
            continue
        p = Path(dirpath)
        if execute:
            try:
                p.rmdir()
                removed += 1
            except OSError:
                pass
        else:
            # Only report directories that would be removable.
            print(f"DRY-RUN: would remove empty directory: {_safe_realpath(p)}")
    return removed


def step1_remove_exact_duplicate_quarantine_tree(execute: bool) -> None:
    print("STEP 1: verify duplicate quarantine trees")
    if not STEP1_TRACKS.exists():
        print(f"- tracks tree missing; skipping: {_safe_realpath(STEP1_TRACKS)}")
        return
    if not STEP1_QUARANTINE.exists():
        print(f"- quarantine tree missing; skipping: {_safe_realpath(STEP1_QUARANTINE)}")
        return

    tracks_sig = _dir_tree_signature(STEP1_TRACKS)
    quarantine_sig = _dir_tree_signature(STEP1_QUARANTINE)

    tracks_files = len(tracks_sig)
    quarantine_files = len(quarantine_sig)
    print(f"- tracks files: {tracks_files}")
    print(f"- quarantine files: {quarantine_files}")

    if tracks_files != quarantine_files:
        raise RuntimeError("STEP 1 abort: file counts do not match")

    # Compare relative paths and sizes only (conservative, cheap).
    tracks_size_map = {k: v[0] for k, v in tracks_sig.items()}
    quarantine_size_map = {k: v[0] for k, v in quarantine_sig.items()}
    if tracks_size_map != quarantine_size_map:
        raise RuntimeError("STEP 1 abort: directory trees differ (path/size mismatch)")

    print("- trees match (path + size); deleting tracks tree only")
    _remove_tree(STEP1_TRACKS, execute=execute)


def step2_remove_tagslut_clone(execute: bool) -> None:
    print("STEP 2: remove _work/fix/tagslut_clone")
    if not STEP2_TAGSLUT_CLONE.exists():
        print(f"- missing; skipping: {_safe_realpath(STEP2_TAGSLUT_CLONE)}")
        return
    if not _git_is_repo(STEP2_TAGSLUT_CLONE):
        raise RuntimeError(
            f"STEP 2 abort: not detected as a git work tree: {_safe_realpath(STEP2_TAGSLUT_CLONE)}"
        )
    print("- confirmed git work tree; deleting directory")
    _remove_tree(STEP2_TAGSLUT_CLONE, execute=execute)


def step3_scan_and_write_lists(db_path: Path) -> tuple[list[Path], dict[str, dict[str, int]]]:
    print("STEP 3: DB cross-check (no deletion)")
    conn = _connect_db(db_path)
    try:
        if not _db_has_table(conn, "asset_file"):
            raise RuntimeError("DB missing required table: asset_file")
        cols = _db_columns(conn, "asset_file")
        if "file_path" not in cols:
            raise RuntimeError("DB asset_file missing required column: file_path")
        if "isrc" not in cols:
            print("WARNING: DB asset_file has no isrc column; ISRC checks will rely on tags only")

        delete_candidates: list[FileDecision] = []
        keep: list[FileDecision] = []
        per_dir_stats: dict[str, dict[str, int]] = {}

        for d in SCAN_DIRS:
            key = _safe_realpath(d)
            files = _iter_audio_files(d)
            per_dir_stats[key] = {
                "total_count": len(files),
                "safe_count": 0,
                "keep_count": 0,
                "safe_bytes": 0,
                "keep_bytes": 0,
            }

            for f in files:
                decision = _decide_for_file(conn, f)
                if decision.decision == "SAFE_TO_DELETE":
                    delete_candidates.append(decision)
                    per_dir_stats[key]["safe_count"] += 1
                    per_dir_stats[key]["safe_bytes"] += int(decision.size)
                else:
                    keep.append(decision)
                    per_dir_stats[key]["keep_count"] += 1
                    per_dir_stats[key]["keep_bytes"] += int(decision.size)

        delete_lines = [
            f"{_safe_realpath(d.path)}\t{d.size}\t{d.reason}" for d in delete_candidates
        ]
        keep_lines = [f"{_safe_realpath(d.path)}\t{d.size}\t{d.reason}" for d in keep]

        _write_list(DELETE_CANDIDATES_OUT, delete_lines)
        _write_list(KEEP_OUT, keep_lines)

        print(f"- wrote delete candidates: {_safe_realpath(DELETE_CANDIDATES_OUT)}")
        print(f"- wrote keep list: {_safe_realpath(KEEP_OUT)}")

        # Report
        for dir_key, st in per_dir_stats.items():
            print(f"\nDIR: {dir_key}")
            print(f"- total files: {st['total_count']}")
            print(f"- SAFE_TO_DELETE: {st['safe_count']} ({_human_bytes(st['safe_bytes'])})")
            print(f"- KEEP: {st['keep_count']} ({_human_bytes(st['keep_bytes'])})")

        keep_paths = [d.path for d in keep]
        keep_paths.sort()
        sample = keep_paths[:10]
        print("\nKEEP sample (first 10):")
        for p in sample:
            print(f"- {_safe_realpath(p)}")

        return ([d.path for d in delete_candidates], per_dir_stats)
    finally:
        conn.close()


def step4_execute_deletions(delete_paths: list[Path], execute: bool) -> None:
    safe_count = len(delete_paths)
    safe_bytes = 0
    for p in delete_paths:
        try:
            safe_bytes += int(p.stat().st_size)
        except FileNotFoundError:
            pass

    print()
    print(f"READY TO DELETE: {safe_count} files ({_human_bytes(safe_bytes)})")
    print("Run with --execute to proceed.")

    if not execute:
        return

    for p in delete_paths:
        real_path = _safe_realpath(p)
        if real_path.startswith(MASTER_LIBRARY_PREFIX):
            raise RuntimeError(f"Refusing to delete MASTER_LIBRARY file: {real_path}")
        if not p.exists():
            continue
        try:
            p.unlink()
        except IsADirectoryError:
            raise RuntimeError(f"Expected file but found directory: {real_path}")

    # Cleanup empty dirs in scan roots.
    for d in SCAN_DIRS:
        _remove_empty_dirs(d, execute=True)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="triage_work_dirs",
        description="Safe, DB-verified cleanup of /Volumes/MUSIC/_work trees.",
    )
    parser.add_argument("--db", default=DEFAULT_DB, help="Path to sqlite DB")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete verified-safe files/dirs (default is dry-run).",
    )
    args = parser.parse_args(argv)

    try:
        _ensure_music_mounted()
        step1_remove_exact_duplicate_quarantine_tree(execute=args.execute)
        step2_remove_tagslut_clone(execute=args.execute)
        delete_paths, _stats = step3_scan_and_write_lists(Path(args.db))
        step4_execute_deletions(delete_paths, execute=args.execute)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    if args.execute:
        print()
        print(
            "Commit message to use after the run:\n"
            "chore(filesystem): triage _work dirs — delete N files verified in MASTER_LIBRARY"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

