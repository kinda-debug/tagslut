#!/usr/bin/env python3
"""
Sequentially scan MUSIC, Quarantine, and Garbage using the fast MD5 scanner,
writing hashes into a shared SQLite DB, and produce a combined duplicate
report across all three roots.

This is a thin orchestrator around scripts/find_dupes_fast.py utilities. It:
- Loads roots from config.toml (with sensible defaults)
- Runs scan_directory() for each existing root (skips missing by default)
- Emits per-root snapshot CSVs and heartbeats
- Writes a unified duplicate report from the DB at the end

Usage:
  python3 scripts/scan_all_roots.py \
    --db ~/.cache/file_dupes.db \
    --snapshot-dir /tmp \
    --output artifacts/reports/dupes_all.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pathlib import Path as _P
import re as _re
from dataclasses import dataclass as _dataclass

try:
    from dedupe.config import load_path_config
except Exception:
    # Fallback minimal config loader to avoid package import issues when
    # executing this script directly via `python3 scripts/scan_all_roots.py`.
    DEFAULT_LIBRARY_ROOT = _P("/Volumes/dotad/MUSIC")
    DEFAULT_QUARANTINE_ROOT = _P("/Volumes/dotad/Quarantine")
    DEFAULT_GARBAGE_ROOT = _P("/Volumes/dotad/Garbage")

    @_dataclass(frozen=True)
    class _PathConfig:
        library_root: _P
        quarantine_root: _P
        garbage_root: _P

    def _extract_path(text: str, key: str, default: _P) -> _P:
        pat = _re.compile(rf"^\s*{_re.escape(key)}\s*=\s*\"([^\"]+)\"",
                          _re.MULTILINE)
        m = pat.search(text)
        return _P(m.group(1)) if m else default

    def _load_path_config_fallback(config_path: _P):
        try:
            text = config_path.read_text(encoding="utf-8")
        except Exception:
            text = ""
        return _PathConfig(
            library_root=_extract_path(text, "root", DEFAULT_LIBRARY_ROOT),
            quarantine_root=_extract_path(
                text, "quarantine", DEFAULT_QUARANTINE_ROOT
            ),
            garbage_root=_extract_path(text, "garbage", DEFAULT_GARBAGE_ROOT),
        )
    # expose under the expected name
    load_path_config = _load_path_config_fallback

try:
    from scripts.find_dupes_fast import (
        init_db,
        scan_directory,
        report_cross_dupes,
    )
except ModuleNotFoundError:
    from importlib.machinery import SourceFileLoader as _SFL
    _fdf_path = _P(__file__).with_name("find_dupes_fast.py")
    _mod = _SFL("find_dupes_fast_local", str(_fdf_path)).load_module()
    init_db = _mod.init_db
    scan_directory = _mod.scan_directory
    report_cross_dupes = _mod.report_cross_dupes


def _hb(path: Path, tag: str) -> Path:
    return path / f"find_dupes_fast.{tag}.hb"


def _snap(path: Path, tag: str) -> Path:
    return path / f"file_dupes_{tag}.csv"


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Scan MUSIC, Quarantine, and Garbage with fast MD5 and write a"
            " combined duplicate report using a shared DB."
        )
    )
    ap.add_argument(
        "--config",
        type=Path,
        default=Path("config.toml"),
        help="Config file providing roots (defaults used if missing)",
    )
    ap.add_argument(
        "--db",
        type=Path,
        default=Path.home() / ".cache" / "file_dupes.db",
        help="SQLite DB destination (shared across scans)",
    )
    ap.add_argument(
        "--snapshot-dir",
        type=Path,
        default=Path("/tmp"),
        help="Directory for per-root CSV snapshots and heartbeats",
    )
    ap.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/reports/dupes_all.csv"),
        help="Unified duplicate report CSV (from DB)",
    )
    ap.add_argument(
        "--quiet",
        action="store_true",
        help="Reduce per-file logging during scans",
    )
    ap.add_argument(
        "--skip-missing-roots",
        action="store_true",
        help="Skip a root if its directory is missing",
    )

    args = ap.parse_args()

    paths = load_path_config(args.config)
    todo = [
        ("music", paths.library_root),
        ("quarantine", paths.quarantine_root),
        ("garbage", paths.garbage_root),
    ]

    conn = init_db(args.db)

    try:
        for tag, root in todo:
            if not root.exists():
                if args.skip_missing_roots:
                    print(
                        f"[WARN] Skipping missing root '{tag}': {root}",
                        file=sys.stderr,
                    )
                    continue
                msg = (
                    f"❌ Root '{tag}' not found: {root} "
                    f"(pass --skip-missing-roots to ignore)"
                )
                print(msg, file=sys.stderr)
                return 2

            print(f"[INFO] Scanning {tag}: {root}", file=sys.stderr)
            heartbeat = _hb(args.snapshot_dir, tag)
            snapshot = _snap(args.snapshot_dir, tag)
            scan_directory(
                root,
                conn,
                verbose=not args.quiet,
                output_csv=snapshot,
                checkpoint=200,
                heartbeat_path=heartbeat,
            )

        # Write the combined report from DB covering all roots
        args.output.parent.mkdir(parents=True, exist_ok=True)
        report_cross_dupes(conn, args.output)
        print(
            f"[INFO] Combined report written: {args.output}",
            file=sys.stderr,
        )
        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
