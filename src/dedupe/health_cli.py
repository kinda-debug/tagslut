"""Command-line helpers for running audio health checks.

This module merges the historical stand-alone scripts that lived at the
repository root into a reusable utility that integrates with the unified CLI.
The helpers exposed here stay dependency free so that health checks only rely
on the standard library plus the ``flac`` and ``ffmpeg`` binaries that already
power the rest of the project.
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import os
import threading
import zipfile
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple
from xml.etree import ElementTree

from .health import CommandHealthChecker, HealthChecker, HealthStatus

SUPPORTED_EXTENSIONS: Tuple[str, ...] = (".flac", ".wav", ".aiff", ".aif", ".m4a")
"""Audio file extensions that should be probed for integrity."""

DEFAULT_LOG_PATH = Path.home() / "audio_health_check.log"
"""Default location for health-check logs."""

_XML_NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


@dataclass
class HealthRunSummary:
    """Summary of a health-check run."""

    total: int
    healthy: int
    unhealthy: int
    missing: int
    unknown: int
    log_path: Path

    def formatted_counts(self) -> str:
        """Return a human-readable summary of the run statistics."""

        parts = [
            f"healthy={self.healthy}",
            f"unhealthy={self.unhealthy}",
            f"unknown={self.unknown}",
            f"missing={self.missing}",
        ]
        return f"Checked {self.total} files (" + ", ".join(parts) + ")"


def build_health_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the ``health`` command and its subcommands on *subparsers*."""

    health_parser = subparsers.add_parser(
        "health", help="Run integrity probes on audio files"
    )
    health_sub = health_parser.add_subparsers(dest="health_command", required=True)

    scan_parser = health_sub.add_parser(
        "scan", help="Recursively check supported files under a directory"
    )
    scan_parser.add_argument(
        "root",
        type=Path,
        help="Root directory to scan for supported audio files",
    )
    scan_parser.add_argument(
        "--log",
        type=Path,
        default=DEFAULT_LOG_PATH,
        help=f"Path to the log file (defaults to {DEFAULT_LOG_PATH})",
    )
    scan_parser.add_argument(
        "--workers",
        type=int,
        default=os.cpu_count() or 4,
        help="Number of worker threads to use",
    )

    sheet_parser = health_sub.add_parser(
        "from-spreadsheet",
        help="Check files listed in a spreadsheet (XLSX) or CSV file",
    )
    sheet_parser.add_argument(
        "spreadsheet",
        type=Path,
        help="Spreadsheet containing file paths in the first column",
    )
    sheet_parser.add_argument(
        "--log",
        type=Path,
        default=Path.home() / "audio_health_check_from_spreadsheet.log",
        help="Path to the log file for spreadsheet runs",
    )
    sheet_parser.add_argument(
        "--workers",
        type=int,
        default=os.cpu_count() or 4,
        help="Number of worker threads to use",
    )


def scan_directory(
    root: Path,
    *,
    log_path: Path,
    workers: int,
    checker: Optional[HealthChecker] = None,
) -> HealthRunSummary:
    """Check every supported file under *root* using *checker*.

    ``checker`` defaults to :class:`CommandHealthChecker` to preserve the
    behaviour of the previous scripts.  The function returns a
    :class:`HealthRunSummary` describing the run and writes detailed log output
    to ``log_path``.
    """

    if not root.is_dir():
        raise ValueError(f"{root} is not a directory")
    files = [path for path in root.rglob("*") if path.is_file() and _is_supported(path)]
    intro = [f"Root directory: {root}", f"Files discovered: {len(files)}"]
    return _run_health_checks(
        files,
        log_path=log_path,
        workers=workers,
        checker=checker,
        intro_messages=intro,
    )


def check_spreadsheet(
    spreadsheet: Path,
    *,
    log_path: Path,
    workers: int,
    checker: Optional[HealthChecker] = None,
) -> HealthRunSummary:
    """Check files listed in the first column of *spreadsheet*.

    Supported formats are ``.xlsx`` and ``.csv``.  Any missing files are
    reported in the summary and the detailed log.
    """

    paths = list(_iter_paths_from_sheet(spreadsheet))
    intro = [f"Spreadsheet: {spreadsheet}", f"Paths loaded: {len(paths)}"]
    return _run_health_checks(
        paths,
        log_path=log_path,
        workers=workers,
        checker=checker,
        intro_messages=intro,
    )


def _run_health_checks(
    paths: Sequence[Path],
    *,
    log_path: Path,
    workers: int,
    checker: Optional[HealthChecker],
    intro_messages: Optional[Iterable[str]] = None,
) -> HealthRunSummary:
    if checker is None:
        checker = CommandHealthChecker()

    log_path.parent.mkdir(parents=True, exist_ok=True)
    if log_path.exists():
        log_path.unlink()

    lock = threading.Lock()

    def log(message: str) -> None:
        with lock:
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(message + "\n")
            print(message)

    total = len(paths)
    healthy = 0
    unhealthy = 0
    missing = 0
    unknown = 0

    start = _dt.datetime.now()
    log(
        f"--- Audio Health Check started {start.strftime('%Y-%m-%d %H:%M:%S')} ---"
    )
    if intro_messages:
        for message in intro_messages:
            log(message)

    def process(path: Path) -> Tuple[Path, HealthStatus]:
        status = checker.check(path)
        return path, status

    if workers <= 1:
        results: List[Tuple[Path, HealthStatus]] = [process(path) for path in paths]
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_map: Dict[Future[Tuple[Path, HealthStatus]], Path] = {
                executor.submit(process, path): path for path in paths
            }
            results = [future.result() for future in as_completed(future_map)]

    for path, (healthy_flag, note) in results:
        if not path.exists():
            missing += 1
            log(f"[MISSING] {path}")
            continue

        if healthy_flag is True:
            healthy += 1
            log(f"[OK] {path}")
            continue

        detail = note or "health status unknown"
        if healthy_flag is False:
            unhealthy += 1
            log(f"[ERROR] {path} -> {detail}")
        else:
            unknown += 1
            log(f"[UNKNOWN] {path} -> {detail}")

    end = _dt.datetime.now()
    log(f"Checked {total} files: {healthy} OK, {unhealthy} errors, {missing} missing, {unknown} unknown")
    log(f"--- Completed {end.strftime('%Y-%m-%d %H:%M:%S')} ---")

    return HealthRunSummary(
        total=total,
        healthy=healthy,
        unhealthy=unhealthy,
        missing=missing,
        unknown=unknown,
        log_path=log_path,
    )


def _iter_paths_from_sheet(spreadsheet: Path) -> Iterator[Path]:
    if not spreadsheet.exists():
        raise FileNotFoundError(spreadsheet)
    suffix = spreadsheet.suffix.lower()
    if suffix == ".xlsx":
        yield from _iter_xlsx_paths(spreadsheet)
    elif suffix == ".csv":
        yield from _iter_csv_paths(spreadsheet)
    else:
        raise ValueError(f"Unsupported spreadsheet format: {spreadsheet.suffix}")


def _iter_xlsx_paths(spreadsheet: Path) -> Iterator[Path]:
    with zipfile.ZipFile(spreadsheet) as archive:
        shared_strings = _read_shared_strings(archive)
        sheet_name = _first_worksheet_name(archive)
        raw = archive.read(sheet_name)
    root = ElementTree.fromstring(raw)
    for row in root.findall("main:sheetData/main:row", _XML_NS):
        cell = row.find("main:c", _XML_NS)
        if cell is None:
            continue
        value = _read_cell_value(cell, shared_strings)
        text = value.strip()
        if text:
            yield Path(text)


def _iter_csv_paths(spreadsheet: Path) -> Iterator[Path]:
    with spreadsheet.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        for row in reader:
            if not row:
                continue
            text = row[0].strip()
            if text:
                yield Path(text)


def _read_shared_strings(archive: zipfile.ZipFile) -> List[str]:
    try:
        data = archive.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ElementTree.fromstring(data)
    strings: List[str] = []
    for entry in root.findall("main:si", _XML_NS):
        parts = [node.text or "" for node in entry.findall(".//main:t", _XML_NS)]
        strings.append("".join(parts))
    return strings


def _first_worksheet_name(archive: zipfile.ZipFile) -> str:
    sheet_names = sorted(
        name
        for name in archive.namelist()
        if name.startswith("xl/worksheets/") and name.endswith(".xml")
    )
    if not sheet_names:
        raise ValueError("No worksheets found in spreadsheet")
    return sheet_names[0]


def _read_cell_value(cell: ElementTree.Element, shared_strings: Sequence[str]) -> str:
    cell_type = cell.get("t")
    if cell_type == "s":
        raw = cell.findtext("main:v", namespaces=_XML_NS)
        if raw is None:
            return ""
        index = int(raw)
        if 0 <= index < len(shared_strings):
            return shared_strings[index]
        return ""
    if cell_type == "inlineStr":
        parts = cell.findall("main:is/main:t", _XML_NS)
        return "".join(part.text or "" for part in parts)
    if cell_type == "str":
        return cell.findtext("main:v", default="", namespaces=_XML_NS) or ""
    return cell.findtext("main:v", default="", namespaces=_XML_NS) or ""


def _is_supported(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


__all__ = [
    "HealthRunSummary",
    "SUPPORTED_EXTENSIONS",
    "build_health_parser",
    "check_spreadsheet",
    "scan_directory",
]

