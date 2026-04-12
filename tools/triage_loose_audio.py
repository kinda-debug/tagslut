#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import pathlib
import re
import shutil
import sqlite3
import sys
from dataclasses import dataclass
from typing import IO, Any, Iterable, Optional


AUDIO_EXTS = {".flac", ".mp3", ".m4a", ".aiff", ".wav"}
ISRC_RE = re.compile(r"\[([A-Z]{2}[A-Z0-9]{3}\d{7})\]")
PREFIX_STRIP_RE = re.compile(r"^\d+[\.\s\-]+")


def normalize_basename(name: str) -> str:
    return PREFIX_STRIP_RE.sub("", name).lower()


def is_double_extension(path: pathlib.Path) -> bool:
    lower = path.name.lower()
    for ext in AUDIO_EXTS:
        if lower.endswith(ext + ext):
            return True
    return False


def iter_audio_files(root: pathlib.Path) -> Iterable[pathlib.Path]:
    for dirpath, _, filenames in os.walk(root):
        for filename in filenames:
            p = pathlib.Path(dirpath) / filename
            suffix = p.suffix.lower()
            if suffix in AUDIO_EXTS or is_double_extension(p):
                yield p


def build_master_index(master_library_root: pathlib.Path) -> dict[str, str]:
    index: dict[str, str] = {}
    for p in iter_audio_files(master_library_root):
        if p.is_dir():
            continue
        if p.suffix.lower() not in AUDIO_EXTS:
            continue
        key = normalize_basename(p.stem)
        index.setdefault(key, str(p))
    return index


def load_rules(rules_path: pathlib.Path) -> list[dict[str, Any]]:
    with rules_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("Rules config must be a JSON array.")
    for i, rule in enumerate(data):
        if not isinstance(rule, dict):
            raise ValueError(f"Rule {i} must be an object.")
        for required_key in ("match_prefix", "action", "only_if_status", "rescue_dest", "note"):
            if required_key not in rule:
                raise ValueError(f"Rule {i} missing key: {required_key}")
        if rule["action"] not in ("delete", "rescue", "skip"):
            raise ValueError(f"Rule {i} has invalid action: {rule['action']}")
        if rule["action"] == "rescue" and not rule["rescue_dest"]:
            raise ValueError(f"Rule {i} action=rescue requires rescue_dest.")
    return data


def match_rule(path_str: str, rules: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    for rule in rules:
        if path_str.startswith(rule["match_prefix"]):
            return rule
    return None


def extract_isrc(filename: str) -> Optional[str]:
    m = ISRC_RE.search(filename)
    if not m:
        return None
    return m.group(1).upper()


def classify_path(path: pathlib.Path, conn: sqlite3.Connection, master_index: dict[str, str]) -> str:
    path_str = str(path)
    if conn.execute("select 1 from asset_file where path = ? limit 1", (path_str,)).fetchone():
        return "in_db_path"
    isrc = extract_isrc(path.name)
    if isrc and conn.execute("select 1 from track_identity where isrc = ? limit 1", (isrc,)).fetchone():
        return "in_db_isrc"
    if normalize_basename(path.stem) in master_index:
        return "in_master_library"
    return "unknown"


def unique_destination(dest_dir: pathlib.Path, filename: str) -> pathlib.Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    src = pathlib.Path(filename)
    base_stem = src.stem
    suffix = src.suffix
    candidate = dest_dir / (base_stem + suffix)
    if not candidate.exists():
        return candidate
    i = 1
    while True:
        candidate = dest_dir / f"{base_stem}_{i}{suffix}"
        if not candidate.exists():
            return candidate
        i += 1


@dataclass(frozen=True)
class ReportRow:
    path: str
    subdir: str
    filename: str
    size_mb: str
    status: str
    action_taken: str
    dest_path: str


@dataclass
class RootSummary:
    deleted: list[str]
    rescued: list[tuple[str, str]]
    skipped: int
    malformed_deleted: list[str]
    errors: list[str]


def triage_root(
    *,
    scan_root: pathlib.Path,
    rules: list[dict[str, Any]],
    conn: sqlite3.Connection,
    master_index: dict[str, str],
    execute: bool,
) -> tuple[list[ReportRow], RootSummary]:
    rows: list[ReportRow] = []
    summary = RootSummary(deleted=[], rescued=[], skipped=0, malformed_deleted=[], errors=[])

    scan_root = scan_root.resolve()
    for p in iter_audio_files(scan_root):
        try:
            rel_parent = p.parent.relative_to(scan_root)
        except Exception:
            rel_parent = pathlib.Path(".")

        subdir = "." if str(rel_parent) == "." else str(rel_parent)
        size_mb = f"{(p.stat().st_size / (1024 * 1024)):.3f}"
        path_str = str(p)

        dest_path = ""
        if is_double_extension(p):
            status = "malformed_extension"
            if execute:
                os.remove(p)
                action_taken = "delete"
                summary.malformed_deleted.append(path_str)
            else:
                action_taken = "delete(dry)"
            rows.append(
                ReportRow(
                    path=path_str,
                    subdir=subdir,
                    filename=p.name,
                    size_mb=size_mb,
                    status=status,
                    action_taken=action_taken,
                    dest_path=dest_path,
                )
            )
            continue

        status = classify_path(p, conn, master_index)
        rule = match_rule(path_str, rules)

        action_taken = "skip" if execute else "skip(dry)"
        if not rule:
            summary.skipped += 1
            rows.append(
                ReportRow(
                    path=path_str,
                    subdir=subdir,
                    filename=p.name,
                    size_mb=size_mb,
                    status=status,
                    action_taken=action_taken,
                    dest_path=dest_path,
                )
            )
            continue

        action = rule["action"]
        only_if_status = rule["only_if_status"]
        rescue_dest = rule["rescue_dest"]

        if action == "skip":
            summary.skipped += 1

        elif action == "rescue":
            if status != "unknown":
                summary.skipped += 1
            else:
                dest = unique_destination(pathlib.Path(rescue_dest), p.name)
                dest_path = str(dest)
                if execute:
                    shutil.move(str(p), str(dest))
                    summary.rescued.append((path_str, dest_path))
                    action_taken = "rescue"
                else:
                    action_taken = "rescue(dry)"

        elif action == "delete":
            should_delete = True if only_if_status is None else status in set(only_if_status)
            if should_delete:
                if execute:
                    os.remove(p)
                    summary.deleted.append(path_str)
                    action_taken = "delete"
                else:
                    action_taken = "delete(dry)"
            else:
                if rescue_dest:
                    dest = unique_destination(pathlib.Path(rescue_dest), p.name)
                    dest_path = str(dest)
                    if execute:
                        shutil.move(str(p), str(dest))
                        summary.rescued.append((path_str, dest_path))
                        action_taken = "rescue"
                    else:
                        action_taken = "rescue(dry)"
                else:
                    summary.skipped += 1

        rows.append(
            ReportRow(
                path=path_str,
                subdir=subdir,
                filename=p.name,
                size_mb=size_mb,
                status=status,
                action_taken=action_taken,
                dest_path=dest_path,
            )
        )

    if execute:
        # Empty directory cleanup (bottom-up), but never remove scan_root itself.
        for dirpath, dirnames, filenames in os.walk(scan_root, topdown=False):
            if dirpath == str(scan_root):
                continue
            try:
                if os.listdir(dirpath):
                    continue
                os.rmdir(dirpath)
            except OSError:
                pass

    return rows, summary


def write_root_outputs(
    *,
    scan_root: pathlib.Path,
    stamp: str,
    rows: list[ReportRow],
    summary: RootSummary,
    execute: bool,
) -> None:
    scan_root = scan_root.resolve()
    report_path = scan_root / f"_triage_report_{stamp}.tsv"
    log_path = scan_root / f"_triage_log_{stamp}.txt"

    header = "path\tsubdir\tfilename\tsize_mb\tstatus\taction_taken\tdest_path\n"
    with report_path.open("w", encoding="utf-8") as f:
        f.write(header)
        for r in rows:
            f.write(
                f"{r.path}\t{r.subdir}\t{r.filename}\t{r.size_mb}\t{r.status}\t{r.action_taken}\t{r.dest_path}\n"
            )

    deleted_label = "Deleted" if execute else "Deleted (dry-run)"
    rescued_label = "Rescued" if execute else "Rescued (dry-run)"
    malformed_label = "Malformed (deleted)" if execute else "Malformed (dry-run)"

    with log_path.open("w", encoding="utf-8") as f:
        f.write(f"{deleted_label}: {len(summary.deleted)} files\n")
        for p in summary.deleted:
            f.write(f"- {p}\n")
        f.write(f"\n{rescued_label}: {len(summary.rescued)} files\n")
        for src, dst in summary.rescued:
            f.write(f"- {src} -> {dst}\n")
        f.write(f"\nSkipped: {summary.skipped} files\n")
        f.write(f"\n{malformed_label}: {len(summary.malformed_deleted)} files\n")
        for p in summary.malformed_deleted:
            f.write(f"- {p}\n")
        if summary.errors:
            f.write(f"\nErrors: {len(summary.errors)}\n")
            for e in summary.errors:
                f.write(f"- {e}\n")


def triage(
    *,
    scan_roots: list[pathlib.Path],
    rules_path: pathlib.Path,
    db_path: pathlib.Path,
    master_library_root: pathlib.Path,
    execute: bool,
    out: IO[str],
) -> list[ReportRow]:
    rules = load_rules(rules_path)
    master_index = build_master_index(master_library_root)

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        stamp = _dt.datetime.now().strftime("%Y%m%d")
        out.write("path\tsubdir\tfilename\tsize_mb\tstatus\taction_taken\tdest_path\n")
        all_rows: list[ReportRow] = []
        for scan_root in scan_roots:
            rows, summary = triage_root(
                scan_root=scan_root,
                rules=rules,
                conn=conn,
                master_index=master_index,
                execute=execute,
            )
            for r in rows:
                out.write(
                    f"{r.path}\t{r.subdir}\t{r.filename}\t{r.size_mb}\t{r.status}\t{r.action_taken}\t{r.dest_path}\n"
                )
            write_root_outputs(
                scan_root=scan_root,
                stamp=stamp,
                rows=rows,
                summary=summary,
                execute=execute,
            )
            all_rows.extend(rows)
        return all_rows
    finally:
        conn.close()


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generalized loose-audio triage tool")
    parser.add_argument("--scan-root", action="append", required=True, help="Scan root (can be passed multiple times)")
    parser.add_argument("--rules", required=True, help="Path to rules JSON")
    parser.add_argument("--db", required=True, help="Path to sqlite DB (read-only)")
    parser.add_argument("--master-library", required=True, help="Path to MASTER_LIBRARY root")
    parser.add_argument("--execute", action="store_true", help="Apply moves and deletes (dry-run by default)")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    scan_roots = [pathlib.Path(p) for p in args.scan_root]
    triage(
        scan_roots=scan_roots,
        rules_path=pathlib.Path(args.rules),
        db_path=pathlib.Path(args.db),
        master_library_root=pathlib.Path(args.master_library),
        execute=bool(args.execute),
        out=sys.stdout,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
