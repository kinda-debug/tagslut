#!/usr/bin/env python3
"""OneTagger workflow helpers for tagslut operations.

Modes:
  - build: create an M3U of library FLAC files missing canonical ISRC in DB
  - run: run OneTagger on an M3U via symlink batch directory
  - sync: build + run in one command
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from mutagen.flac import FLAC
except Exception as exc:  # pragma: no cover
    raise SystemExit(f"mutagen is required: {exc}") from exc


DEFAULT_DB = os.environ.get(
    "TAGSLUT_DB",
    "/Users/georgeskhawam/Projects/tagslut_db/EPOCH_2026-02-08/music.db",
)
DEFAULT_LIBRARY_ROOT = Path("/Volumes/MUSIC/LIBRARY")
DEFAULT_WORK_ROOT = Path("/Volumes/MUSIC/_work")
DEFAULT_OUT_DIR = Path("/Users/georgeskhawam/Projects/tagslut/artifacts/compare")
DEFAULT_ONETAGGER_BIN = Path("/Users/georgeskhawam/Downloads/onetagger-cli")
DEFAULT_CONFIG_PATH = Path("/Users/georgeskhawam/.config/onetagger/config.tagslut-missing-isrc.json")
DEFAULT_BASE_CONFIG_PATH = Path("/Users/georgeskhawam/.config/onetagger/config.json")
DEFAULT_RUNS_DIR = Path("/Users/georgeskhawam/Library/Preferences/com.OneTagger.OneTagger/runs")


@dataclass
class BuildResult:
    m3u_path: Path
    total_rows: int
    existing_files: int
    missing_on_disk: int


def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _resolve_db(path: str) -> Path:
    db = Path(path).expanduser().resolve()
    if not db.exists():
        raise SystemExit(f"DB not found: {db}")
    return db


def _normalize_path_line(line: str) -> str:
    value = line.strip()
    if not value or value.startswith("#"):
        return ""
    return value


def _read_m3u_lines(m3u_path: Path) -> list[Path]:
    paths: list[Path] = []
    for raw in m3u_path.read_text(encoding="utf-8", errors="replace").splitlines():
        value = _normalize_path_line(raw)
        if not value:
            continue
        paths.append(Path(value).expanduser())
    return paths


def _write_m3u_lines(paths: list[Path], out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        for path in paths:
            handle.write(f"{path}\n")
    return out_path


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out


def _query_missing_isrc_paths(db_path: Path, library_root: Path) -> list[Path]:
    sql = """
    SELECT path
    FROM files
    WHERE path LIKE ?
      AND lower(path) LIKE '%.flac'
      AND (canonical_isrc IS NULL OR trim(canonical_isrc) = '')
    ORDER BY path
    """
    prefix = f"{library_root.as_posix().rstrip('/')}/%"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(sql, (prefix,)).fetchall()
    finally:
        conn.close()
    return [Path(str(row["path"])) for row in rows]


def build_missing_isrc_m3u(
    db_path: Path,
    library_root: Path,
    out_m3u: Path,
    limit: int = 0,
) -> BuildResult:
    rows = _query_missing_isrc_paths(db_path, library_root)
    if limit > 0:
        rows = rows[:limit]

    existing: list[Path] = []
    missing_count = 0
    for path in rows:
        if path.exists():
            existing.append(path.resolve())
        else:
            missing_count += 1

    _write_m3u_lines(existing, out_m3u)
    return BuildResult(
        m3u_path=out_m3u,
        total_rows=len(rows),
        existing_files=len(existing),
        missing_on_disk=missing_count,
    )


def _safe_link_name(index: int, src: Path) -> str:
    base = src.name.replace("/", "_").replace("\x00", "")
    if len(base) > 180:
        stem = src.stem[:140]
        suffix = src.suffix
        base = f"{stem}{suffix}"
    return f"{index:05d}__{base}"


def create_symlink_batch_from_paths(items: list[Path], link_dir: Path, limit: int = 0) -> tuple[list[Path], int]:
    if limit > 0:
        items = items[:limit]
    link_dir.mkdir(parents=True, exist_ok=True)

    links: list[Path] = []
    missing = 0
    for idx, src in enumerate(items, start=1):
        resolved = src.expanduser()
        if not resolved.exists():
            missing += 1
            continue
        link_path = link_dir / _safe_link_name(idx, resolved)
        if link_path.exists():
            links.append(link_path)
            continue
        try:
            link_path.symlink_to(resolved)
            links.append(link_path)
        except FileExistsError:
            links.append(link_path)
    return links, missing


def create_symlink_batch(m3u_path: Path, link_dir: Path, limit: int = 0) -> tuple[list[Path], int]:
    return create_symlink_batch_from_paths(_read_m3u_lines(m3u_path), link_dir, limit=limit)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return {}


def write_onetagger_config(
    base_config: Path,
    out_config: Path,
    threads: int,
    *,
    strictness: float,
    platforms: list[str],
) -> Path:
    cfg = _load_json(base_config)
    cfg["tags"] = ["isrc"]
    cfg["overwrite"] = False
    cfg["skipTagged"] = False
    cfg["strictness"] = strictness
    cfg["matchDuration"] = True
    cfg["threads"] = max(1, threads)
    cfg["platforms"] = platforms
    cfg["enableShazam"] = True
    out_config.parent.mkdir(parents=True, exist_ok=True)
    out_config.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return out_config


def _list_run_files(runs_dir: Path, prefix: str) -> set[Path]:
    return set(runs_dir.glob(f"{prefix}-*.m3u"))


def _latest_file(paths: set[Path]) -> Path | None:
    if not paths:
        return None
    return max(paths, key=lambda path: path.stat().st_mtime)


def _resolve_result_file(before: set[Path], after: set[Path]) -> Path | None:
    new_files = after - before
    if new_files:
        return _latest_file(new_files)
    return _latest_file(after)


def _count_isrc(path: Path) -> str:
    try:
        tags = FLAC(str(path))
    except Exception:
        return ""
    values = tags.get("isrc", []) or tags.get("ISRC", [])
    normalized = [str(value).strip() for value in values if str(value).strip()]
    return ";".join(normalized)


def _paths_missing_isrc(paths: list[Path]) -> list[Path]:
    missing: list[Path] = []
    for path in paths:
        if not path.exists():
            continue
        if not _count_isrc(path):
            missing.append(path)
    return missing


def _run_with_tee(cmd: list[str], log_path: Path) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            print(line, end="")
            log.write(line)
        return proc.wait()


def _update_db_isrc_from_rows(db_path: Path, rows: list[dict[str, Any]]) -> int:
    updates: list[tuple[str, str]] = []
    for row in rows:
        isrc_value = str(row.get("isrc_after", "")).strip()
        path = str(row.get("target_path", "")).strip()
        if not isrc_value or not path:
            continue
        canonical = isrc_value.split(";", 1)[0].strip()
        if not canonical:
            continue
        updates.append((canonical, path))

    if not updates:
        return 0

    conn = sqlite3.connect(str(db_path))
    try:
        before_changes = conn.total_changes
        conn.executemany(
            "UPDATE files SET canonical_isrc = ?, enriched_at = datetime('now') WHERE path = ?",
            updates,
        )
        conn.commit()
        return conn.total_changes - before_changes
    finally:
        conn.close()


def run_onetagger(
    *,
    m3u_path: Path,
    link_root: Path,
    out_dir: Path,
    onetagger_bin: Path,
    config_path: Path,
    base_config: Path,
    runs_dir: Path,
    threads: int,
    limit: int,
    max_passes: int,
    strictness: float,
    platforms: list[str],
    db_path: Path | None,
    db_refresh: bool,
    db_refresh_only: bool,
) -> tuple[Path, Path]:
    stamp = _now_stamp()
    raw_items = _read_m3u_lines(m3u_path)
    if limit > 0:
        raw_items = raw_items[:limit]

    existing_items: list[Path] = []
    missing_input = 0
    for item in raw_items:
        resolved = item.expanduser().resolve()
        if resolved.exists():
            existing_items.append(resolved)
        else:
            missing_input += 1
    existing_items = _dedupe_paths(existing_items)
    if not existing_items:
        raise SystemExit("No existing files resolved from M3U; nothing to tag.")

    unresolved = _paths_missing_isrc(existing_items)
    initial_missing = len(unresolved)

    success_paths: set[Path] = set()
    failed_paths: set[Path] = set()
    pass_results: list[dict[str, Any]] = []
    latest_log_path = out_dir / f"onetagger_run_{stamp}_p00.log"
    final_success_m3u: Path | None = None
    final_failed_m3u: Path | None = None

    effective_max_passes = max(0, max_passes)
    if db_refresh_only:
        effective_max_passes = 0

    for pass_index in range(1, effective_max_passes + 1):
        if not unresolved:
            break

        pass_stamp = f"{stamp}_p{pass_index:02d}"
        pass_input_m3u = out_dir / f"onetagger_input_{pass_stamp}.m3u"
        link_dir = link_root / f"onetagger_links_{pass_stamp}"
        log_path = out_dir / f"onetagger_run_{pass_stamp}.log"
        latest_log_path = log_path
        _write_m3u_lines(unresolved, pass_input_m3u)

        links, missing_from_pass_m3u = create_symlink_batch(pass_input_m3u, link_dir, limit=0)
        if not links:
            pass_results.append(
                {
                    "pass": pass_index,
                    "input_unresolved": len(unresolved),
                    "linked_files": 0,
                    "missing_from_pass_m3u_on_disk": missing_from_pass_m3u,
                    "unresolved_after": len(unresolved),
                    "progress": "no_links",
                }
            )
            break

        write_onetagger_config(
            base_config,
            config_path,
            threads=threads,
            strictness=strictness,
            platforms=platforms,
        )

        success_before = _list_run_files(runs_dir, "success")
        failed_before = _list_run_files(runs_dir, "failed")

        cmd = [
            str(onetagger_bin),
            "autotagger",
            "--config",
            str(config_path),
            "--path",
            str(link_dir),
        ]
        print(f"Running pass {pass_index}/{effective_max_passes}:", " ".join(cmd))
        exit_code = _run_with_tee(cmd, log_path)
        if exit_code != 0:
            raise SystemExit(f"OneTagger failed (exit={exit_code}). Log: {log_path}")

        success_after = _list_run_files(runs_dir, "success")
        failed_after = _list_run_files(runs_dir, "failed")
        success_m3u = _resolve_result_file(success_before, success_after)
        failed_m3u = _resolve_result_file(failed_before, failed_after)
        final_success_m3u = success_m3u
        final_failed_m3u = failed_m3u

        pass_success = set()
        pass_failed = set()
        if success_m3u and success_m3u.exists():
            pass_success = {path.resolve() for path in _read_m3u_lines(success_m3u) if path.exists()}
            success_paths |= pass_success
        if failed_m3u and failed_m3u.exists():
            pass_failed = {path.resolve() for path in _read_m3u_lines(failed_m3u) if path.exists()}
            failed_paths |= pass_failed

        unresolved_after = _paths_missing_isrc(unresolved)
        progress = "ok" if len(unresolved_after) < len(unresolved) else "stalled"
        pass_results.append(
            {
                "pass": pass_index,
                "input_unresolved": len(unresolved),
                "linked_files": len(links),
                "missing_from_pass_m3u_on_disk": missing_from_pass_m3u,
                "pass_success_count": len(pass_success),
                "pass_failed_count": len(pass_failed),
                "unresolved_after": len(unresolved_after),
                "progress": progress,
            }
        )
        unresolved = unresolved_after
        if progress == "stalled":
            break

    rows: list[dict[str, Any]] = []
    isrc_present = 0
    still_missing_sample: list[str] = []
    for target in existing_items:
        isrc_value = _count_isrc(target)
        has_isrc = bool(isrc_value)
        if has_isrc:
            isrc_present += 1
        elif len(still_missing_sample) < 30:
            still_missing_sample.append(target.name)
        rows.append(
            {
                "target_path": str(target),
                "has_isrc_after": 1 if has_isrc else 0,
                "isrc_after": isrc_value,
                "in_success_m3u": 1 if target in success_paths else 0,
                "in_failed_m3u": 1 if target in failed_paths else 0,
            }
        )

    summary = {
        "m3u_input": str(m3u_path),
        "log_path": str(latest_log_path),
        "config_path": str(config_path),
        "total_files": len(existing_items),
        "missing_from_m3u_on_disk": missing_input,
        "max_passes": effective_max_passes,
        "passes_executed": len(pass_results),
        "initial_missing_isrc_count": initial_missing,
        "success_m3u": str(final_success_m3u) if final_success_m3u else "",
        "failed_m3u": str(final_failed_m3u) if final_failed_m3u else "",
        "success_count": len(success_paths),
        "failed_count": len(failed_paths),
        "isrc_present_after_count": isrc_present,
        "isrc_present_after_pct": round((isrc_present / len(existing_items)) * 100, 2) if existing_items else 0.0,
        "isrc_still_missing_after_count": len(existing_items) - isrc_present,
        "isrc_still_missing_sample": still_missing_sample,
        "pass_results": pass_results,
        "db_refresh_only": bool(db_refresh_only),
    }

    db_updates = 0
    if db_refresh and db_path is not None and db_path.exists():
        db_updates = _update_db_isrc_from_rows(db_path, rows)
    summary["db_isrc_rows_updated"] = db_updates

    summary_path = out_dir / f"onetagger_summary_{stamp}.json"
    rows_path = out_dir / f"onetagger_file_status_{stamp}.csv"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with rows_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else ["target_path"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote: {summary_path}")
    print(f"Wrote: {rows_path}")
    return summary_path, rows_path


def _build_default_m3u_path(library_root: Path) -> Path:
    return library_root / f"needs_tagging_missing_isrc_{_now_stamp()}.m3u"


def cmd_build(args: argparse.Namespace) -> int:
    db_path = _resolve_db(args.db)
    library_root = Path(args.library_root).expanduser()
    output_path = Path(args.output).expanduser() if args.output else _build_default_m3u_path(library_root)
    result = build_missing_isrc_m3u(
        db_path=db_path,
        library_root=library_root,
        out_m3u=output_path,
        limit=args.limit,
    )
    print(f"M3U: {result.m3u_path}")
    print(f"DB rows (missing ISRC): {result.total_rows}")
    print(f"Existing files written: {result.existing_files}")
    print(f"Missing on disk: {result.missing_on_disk}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    m3u_path = Path(args.m3u).expanduser().resolve()
    if not m3u_path.exists():
        raise SystemExit(f"M3U not found: {m3u_path}")
    onetagger_bin = Path(args.onetagger_bin).expanduser().resolve()
    if not onetagger_bin.exists():
        raise SystemExit(f"OneTagger binary not found: {onetagger_bin}")
    db_path = _resolve_db(args.db)

    run_onetagger(
        m3u_path=m3u_path,
        link_root=Path(args.link_root).expanduser(),
        out_dir=Path(args.out_dir).expanduser(),
        onetagger_bin=onetagger_bin,
        config_path=Path(args.config).expanduser(),
        base_config=Path(args.base_config).expanduser(),
        runs_dir=Path(args.runs_dir).expanduser(),
        threads=args.threads,
        limit=args.limit,
        max_passes=args.max_passes,
        strictness=args.strictness,
        platforms=[part.strip() for part in args.platforms.split(",") if part.strip()],
        db_path=db_path,
        db_refresh=args.db_refresh,
        db_refresh_only=args.db_refresh_only,
    )
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    db_path = _resolve_db(args.db)
    library_root = Path(args.library_root).expanduser()
    output_path = Path(args.output).expanduser() if args.output else _build_default_m3u_path(library_root)
    build_result = build_missing_isrc_m3u(
        db_path=db_path,
        library_root=library_root,
        out_m3u=output_path,
        limit=args.limit,
    )
    print(f"M3U: {build_result.m3u_path}")
    print(f"DB rows (missing ISRC): {build_result.total_rows}")
    print(f"Existing files written: {build_result.existing_files}")
    print(f"Missing on disk: {build_result.missing_on_disk}")
    if build_result.existing_files == 0:
        print("No files to tag.")
        return 0

    onetagger_bin = Path(args.onetagger_bin).expanduser().resolve()
    if not onetagger_bin.exists():
        raise SystemExit(f"OneTagger binary not found: {onetagger_bin}")

    run_onetagger(
        m3u_path=build_result.m3u_path,
        link_root=Path(args.link_root).expanduser(),
        out_dir=Path(args.out_dir).expanduser(),
        onetagger_bin=onetagger_bin,
        config_path=Path(args.config).expanduser(),
        base_config=Path(args.base_config).expanduser(),
        runs_dir=Path(args.runs_dir).expanduser(),
        threads=args.threads,
        limit=args.limit,
        max_passes=args.max_passes,
        strictness=args.strictness,
        platforms=[part.strip() for part in args.platforms.split(",") if part.strip()],
        db_path=db_path,
        db_refresh=args.db_refresh,
        db_refresh_only=args.db_refresh_only,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OneTagger helper workflow for missing ISRC enrichment.")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(parser_obj: argparse.ArgumentParser) -> None:
        parser_obj.add_argument("--db", default=str(DEFAULT_DB), help="Path to tagslut SQLite DB.")
        parser_obj.add_argument(
            "--library-root",
            default=str(DEFAULT_LIBRARY_ROOT),
            help="Library root used to filter DB paths.",
        )
        parser_obj.add_argument("--output", default="", help="M3U output path. Default: <library-root>/needs_tagging_missing_isrc_<ts>.m3u")
        parser_obj.add_argument("--limit", type=int, default=0, help="Limit number of files (0 = all).")

    build_cmd = sub.add_parser("build", help="Build missing-ISRC M3U from DB.")
    add_common(build_cmd)
    build_cmd.set_defaults(func=cmd_build)

    run_cmd = sub.add_parser("run", help="Run OneTagger for an existing M3U via symlink batch.")
    run_cmd.add_argument("--m3u", required=True, help="Input M3U path.")
    run_cmd.add_argument("--db", default=str(DEFAULT_DB), help="Path to tagslut SQLite DB.")
    run_cmd.add_argument("--onetagger-bin", default=str(DEFAULT_ONETAGGER_BIN), help="OneTagger CLI binary path.")
    run_cmd.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Generated OneTagger config path.")
    run_cmd.add_argument("--base-config", default=str(DEFAULT_BASE_CONFIG_PATH), help="Base OneTagger config path to copy/merge.")
    run_cmd.add_argument("--runs-dir", default=str(DEFAULT_RUNS_DIR), help="OneTagger runs directory containing success/failed M3Us.")
    run_cmd.add_argument("--link-root", default=str(DEFAULT_WORK_ROOT), help="Root dir for temporary symlink batches.")
    run_cmd.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="Output directory for logs/summaries.")
    run_cmd.add_argument("--threads", type=int, default=12, help="OneTagger thread count.")
    run_cmd.add_argument("--limit", type=int, default=0, help="Limit number of files from M3U (0 = all).")
    run_cmd.add_argument("--max-passes", type=int, default=4, help="Retry unresolved ISRC files for N passes.")
    run_cmd.add_argument("--strictness", type=float, default=0.8, help="OneTagger strictness.")
    run_cmd.add_argument(
        "--platforms",
        default="spotify,deezer,musicbrainz",
        help="Comma-separated providers for ISRC lookup.",
    )
    run_cmd.add_argument(
        "--db-refresh",
        dest="db_refresh",
        action="store_true",
        default=True,
        help="Write ISRC back to DB canonical_isrc (default: on).",
    )
    run_cmd.add_argument(
        "--no-db-refresh",
        dest="db_refresh",
        action="store_false",
        help="Do not update DB canonical_isrc.",
    )
    run_cmd.add_argument(
        "--db-refresh-only",
        action="store_true",
        help="Only sync embedded ISRC to DB; skip OneTagger provider passes.",
    )
    run_cmd.set_defaults(func=cmd_run)

    sync_cmd = sub.add_parser("sync", help="Build missing-ISRC M3U then run OneTagger.")
    add_common(sync_cmd)
    sync_cmd.add_argument("--onetagger-bin", default=str(DEFAULT_ONETAGGER_BIN), help="OneTagger CLI binary path.")
    sync_cmd.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Generated OneTagger config path.")
    sync_cmd.add_argument("--base-config", default=str(DEFAULT_BASE_CONFIG_PATH), help="Base OneTagger config path to copy/merge.")
    sync_cmd.add_argument("--runs-dir", default=str(DEFAULT_RUNS_DIR), help="OneTagger runs directory containing success/failed M3Us.")
    sync_cmd.add_argument("--link-root", default=str(DEFAULT_WORK_ROOT), help="Root dir for temporary symlink batches.")
    sync_cmd.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="Output directory for logs/summaries.")
    sync_cmd.add_argument("--threads", type=int, default=12, help="OneTagger thread count.")
    sync_cmd.add_argument("--max-passes", type=int, default=4, help="Retry unresolved ISRC files for N passes.")
    sync_cmd.add_argument("--strictness", type=float, default=0.8, help="OneTagger strictness.")
    sync_cmd.add_argument(
        "--platforms",
        default="spotify,deezer,musicbrainz",
        help="Comma-separated providers for ISRC lookup.",
    )
    sync_cmd.add_argument(
        "--db-refresh",
        dest="db_refresh",
        action="store_true",
        default=True,
        help="Write ISRC back to DB canonical_isrc (default: on).",
    )
    sync_cmd.add_argument(
        "--no-db-refresh",
        dest="db_refresh",
        action="store_false",
        help="Do not update DB canonical_isrc.",
    )
    sync_cmd.add_argument(
        "--db-refresh-only",
        action="store_true",
        help="Only sync embedded ISRC to DB; skip OneTagger provider passes.",
    )
    sync_cmd.set_defaults(func=cmd_sync)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
