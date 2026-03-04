"""Rekordbox prep subprocess wrapper and summary parsing."""

from __future__ import annotations

import csv
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_REKORDBOX_SCRIPT = "rekordbox_prep_dj.py"
DEFAULT_REPORT_FILENAME = "rekordbox_prep_report.csv"
SUSPECT_UPSCALE_STATUS = "SUSPECT_UPSCALE"
PROJECT_ROOT = Path(__file__).resolve().parents[2]

_TRACK_STATUS_PATTERN = re.compile(r"^\[(?P<status>[^\]]+)\]\s+")
_QUARANTINED_PATTERN = re.compile(r"\bquarantined=(?P<count>\d+)\b")


@dataclass(frozen=True)
class RekordboxPrepSummary:
    tracks_processed: int
    suspect_upscale_count: int
    files_quarantined: int
    report_path: Path


@dataclass(frozen=True)
class RekordboxPrepRunResult:
    command: tuple[str, ...]
    stdout: str
    stderr: str
    summary: RekordboxPrepSummary


def resolve_rekordbox_script_path(script_path: Path | None = None) -> Path:
    candidate = script_path or (PROJECT_ROOT / DEFAULT_REKORDBOX_SCRIPT)
    resolved = candidate.expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(
            f"Rekordbox prep script not found: {resolved}. "
            f"Place {DEFAULT_REKORDBOX_SCRIPT} at the repo root."
        )
    if not resolved.is_file():
        raise FileNotFoundError(f"Rekordbox prep script path is not a file: {resolved}")
    return resolved


def build_rekordbox_prep_command(
    *,
    script_path: Path,
    root: Path,
    out: Path,
    quarantine: Path,
    dry_run: bool,
    report_filename: str = DEFAULT_REPORT_FILENAME,
) -> list[str]:
    cmd = [
        sys.executable,
        str(script_path),
        "--root",
        str(root),
        "--out",
        str(out),
        "--quarantine",
        str(quarantine),
        "--report",
        report_filename,
    ]
    if dry_run:
        cmd.append("--dry-run")
    return cmd


def _parse_quarantined_count(note: str) -> int:
    total = 0
    for match in _QUARANTINED_PATTERN.finditer(note):
        total += int(match.group("count"))
    return total


def parse_rekordbox_report_summary(report_path: Path) -> RekordboxPrepSummary:
    with report_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"Report CSV is empty: {report_path}")
        if "status" not in reader.fieldnames:
            raise ValueError(f"Report CSV is missing required 'status' column: {report_path}")

        tracks_processed = 0
        suspect_upscale_count = 0
        files_quarantined = 0

        for row in reader:
            tracks_processed += 1
            status = str(row.get("status") or "").strip().upper()
            if status == SUSPECT_UPSCALE_STATUS:
                suspect_upscale_count += 1
            note = str(row.get("note") or "")
            files_quarantined += _parse_quarantined_count(note)

    return RekordboxPrepSummary(
        tracks_processed=tracks_processed,
        suspect_upscale_count=suspect_upscale_count,
        files_quarantined=files_quarantined,
        report_path=report_path,
    )


def parse_rekordbox_stdout_summary(stdout: str, report_path: Path) -> RekordboxPrepSummary:
    tracks_processed = 0
    suspect_upscale_count = 0
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        match = _TRACK_STATUS_PATTERN.match(line)
        if not match:
            continue
        tracks_processed += 1
        status = match.group("status").strip().upper()
        if status == SUSPECT_UPSCALE_STATUS:
            suspect_upscale_count += 1

    return RekordboxPrepSummary(
        tracks_processed=tracks_processed,
        suspect_upscale_count=suspect_upscale_count,
        files_quarantined=0,
        report_path=report_path,
    )


def run_rekordbox_prep(
    *,
    root: Path,
    out: Path,
    quarantine: Path,
    dry_run: bool,
    script_path: Path | None = None,
    report_filename: str = DEFAULT_REPORT_FILENAME,
) -> RekordboxPrepRunResult:
    resolved_script = resolve_rekordbox_script_path(script_path)
    report_path = out / report_filename
    cmd = build_rekordbox_prep_command(
        script_path=resolved_script,
        root=root,
        out=out,
        quarantine=quarantine,
        dry_run=dry_run,
        report_filename=report_filename,
    )

    proc = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        error_tail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(
            f"rekordbox_prep_dj.py failed with exit code {proc.returncode}: "
            f"{error_tail[-1000:]}"
        )

    if (not dry_run) and report_path.exists():
        summary = parse_rekordbox_report_summary(report_path)
    else:
        summary = parse_rekordbox_stdout_summary(proc.stdout, report_path)

    return RekordboxPrepRunResult(
        command=tuple(cmd),
        stdout=proc.stdout,
        stderr=proc.stderr,
        summary=summary,
    )
