#!/usr/bin/env python3
from __future__ import annotations

import csv
import os
import re
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path("/Users/georgeskhawam/Projects/tagslut")

SPOTIFLACNEXT_ROOT = Path("/Volumes/MUSIC/staging/SpotiFLACnext")
SPOTIFLAC_ROOT = Path("/Volumes/MUSIC/staging/SpotiFLAC")
LOGS_ROOT = Path("/Volumes/MUSIC/logs")

DISABLE_MP3_LIBRARY_PATH = "/__tagslut_intake_sweep_disable_mp3_library__"

_TRACKS_PARSED_RE = re.compile(r"^(?P<total>\d+)\s+tracks\s+parsed\b", re.IGNORECASE)
_SUMMARY_RE = re.compile(
    r"(?P<ingested>\d+)\s+ingested,\s+"
    r"(?P<skipped_missing>\d+)\s+skipped\s+\\(file not found\\),\s+"
    r"(?P<failed>\d+)\s+failed\b",
    re.IGNORECASE,
)
_ALREADY_INDEXED_RE = re.compile(
    r"^\\[warning\\]\\s+already indexed;\\s+skipping:",
    re.IGNORECASE,
)

_FAILED_FILE_RE = re.compile(r"(^|[_-])failed($|[_-])", re.IGNORECASE)

_AUDIO_EXTS = {".flac", ".m4a", ".mp3"}


@dataclass(frozen=True)
class Batch:
    batch_name: str
    source: str
    anchor_type: str  # txt | m3u8_only
    anchor_path: Path
    base_dir: Path


@dataclass(frozen=True)
class BatchResult:
    batch_name: str
    source: str
    anchor_type: str
    total_tracks: int
    ingested: int
    already_in_db: int
    failed: int
    notes: str


def _iter_spotiflacnext_batches(root: Path) -> list[Batch]:
    if not root.exists():
        return []

    batches: list[Batch] = []
    for m3u8_path in sorted(root.rglob("*.m3u8"), key=lambda p: str(p).lower()):
        if m3u8_path.name.endswith("_converted.m3u8"):
            continue

        txt_path = m3u8_path.with_suffix(".txt")
        anchor_path = txt_path if txt_path.exists() else m3u8_path
        anchor_type = "txt" if txt_path.exists() else "m3u8_only"

        try:
            rel = anchor_path.relative_to(root)
            batch_name = str(rel.with_suffix(""))
        except ValueError:
            batch_name = anchor_path.stem

        batches.append(
            Batch(
                batch_name=batch_name,
                source="spotiflacnext",
                anchor_type=anchor_type,
                anchor_path=anchor_path,
                base_dir=root,
            )
        )
    return batches


def _iter_spotiflac_batches(root: Path) -> list[Batch]:
    if not root.exists():
        return []

    batches: list[Batch] = []
    for txt_path in sorted(root.rglob("*.txt"), key=lambda p: str(p).lower()):
        if _FAILED_FILE_RE.search(txt_path.stem):
            continue

        try:
            rel = txt_path.relative_to(root)
            batch_name = str(rel.with_suffix(""))
        except ValueError:
            batch_name = txt_path.stem

        batches.append(
            Batch(
                batch_name=batch_name,
                source="spotiflac",
                anchor_type="txt",
                anchor_path=txt_path,
                base_dir=root,
            )
        )
    return batches


def _run_spotiflac_intake(batch: Batch) -> BatchResult:
    cmd = [
        sys.executable,
        "-m",
        "tagslut.cli.main",
        "intake",
        "spotiflac",
        "--base-dir",
        str(batch.base_dir),
        str(batch.anchor_path),
    ]

    env = os.environ.copy()
    env["MP3_LIBRARY"] = DISABLE_MP3_LIBRARY_PATH
    env["DJ_POOL_M3U"] = os.path.join(DISABLE_MP3_LIBRARY_PATH, "dj_pool.m3u")

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=env,
    )

    total_tracks: int | None = None
    ingested = 0
    skipped_missing = 0
    failed_parser = 0

    would_ingest = 0
    ingested_lines = 0
    failed_lines = 0
    error_lines = 0

    notes_bits: list[str] = []
    if proc.returncode != 0:
        notes_bits.append(f"exit={proc.returncode}")

    for line in proc.stdout.splitlines():
        if total_tracks is None:
            m_total = _TRACKS_PARSED_RE.match(line.strip())
            if m_total:
                total_tracks = int(m_total.group("total"))

        if line.startswith("[would-ingest]"):
            would_ingest += 1
        elif line.startswith("[ingested]"):
            ingested_lines += 1
        elif line.startswith("[failed/"):
            failed_lines += 1

        if "Error:" in line:
            error_lines += 1

        m = _SUMMARY_RE.search(line)
        if m:
            ingested = int(m.group("ingested"))
            skipped_missing = int(m.group("skipped_missing"))
            failed_parser = int(m.group("failed"))

    for line in proc.stderr.splitlines():
        if _ALREADY_INDEXED_RE.match(line.strip()):
            continue
        if "Error:" in line:
            error_lines += 1

    already_in_db = len(_ALREADY_INDEXED_RE.findall(proc.stderr))

    summary_parsed = (ingested != 0) or (skipped_missing != 0) or (failed_parser != 0) or bool(_SUMMARY_RE.search(proc.stdout))
    if not summary_parsed:
        ingested = ingested_lines
        failed_parser = failed_lines
        if would_ingest:
            notes_bits.append(f"would_ingest={would_ingest}")
        notes_bits.append("summary_unparsed")

    failed_total = failed_parser + skipped_missing
    if skipped_missing:
        notes_bits.append(f"missing_files={skipped_missing}")
    if error_lines:
        notes_bits.append(f"errors={error_lines}")

    if total_tracks is None:
        total_tracks = max(ingested + already_in_db + failed_total, would_ingest + ingested_lines + failed_lines, 0)
        notes_bits.append("total_unparsed")

    return BatchResult(
        batch_name=batch.batch_name,
        source=batch.source,
        anchor_type=batch.anchor_type,
        total_tracks=int(total_tracks),
        ingested=int(ingested),
        already_in_db=int(already_in_db),
        failed=int(failed_total),
        notes="; ".join([b for b in notes_bits if b]),
    )


def _resolve_db_path() -> Path | None:
    try:
        from tagslut.utils.db import DbResolutionError, resolve_cli_env_db_path

        resolution = resolve_cli_env_db_path(
            None,
            purpose="read",
            allow_repo_db=False,
            source_label="TAGSLUT_DB",
        )
        return resolution.path
    except Exception:
        return None


def _load_asset_paths(db_path: Path) -> set[str]:
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        rows = conn.execute("SELECT path FROM asset_file").fetchall()
    finally:
        conn.close()
    return {str(raw_path) for (raw_path,) in rows if raw_path}


def _iter_audio_files(root: Path) -> list[str]:
    if not root.exists():
        return []
    out: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in _AUDIO_EXTS:
            continue
        out.append(str(path.resolve()))
    return out


def main() -> int:
    batches = _iter_spotiflacnext_batches(SPOTIFLACNEXT_ROOT) + _iter_spotiflac_batches(SPOTIFLAC_ROOT)

    db_path = _resolve_db_path()
    before_unindexed: list[str] = []
    if db_path is not None:
        try:
            asset_paths_before = _load_asset_paths(db_path)
            for root in (SPOTIFLACNEXT_ROOT, SPOTIFLAC_ROOT):
                for path_str in _iter_audio_files(root):
                    if path_str not in asset_paths_before:
                        before_unindexed.append(path_str)
        except Exception:
            db_path = None

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    LOGS_ROOT.mkdir(parents=True, exist_ok=True)
    out_path = LOGS_ROOT / f"intake_sweep_v2_{stamp}.tsv"

    with out_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "batch_name",
                "source",
                "anchor_type",
                "total_tracks",
                "ingested",
                "already_in_db",
                "failed",
                "notes",
            ]
        )

        total_ingested = 0
        total_already = 0
        total_failed = 0

        for batch in batches:
            result = _run_spotiflac_intake(batch)
            total_ingested += result.ingested
            total_already += result.already_in_db
            total_failed += result.failed
            writer.writerow(
                [
                    result.batch_name,
                    result.source,
                    result.anchor_type,
                    result.total_tracks,
                    result.ingested,
                    result.already_in_db,
                    result.failed,
                    result.notes,
                ]
            )

    moved = None
    if db_path is not None and before_unindexed:
        try:
            asset_paths_after = _load_asset_paths(db_path)
            moved = sum(1 for p in before_unindexed if p in asset_paths_after)
        except Exception:
            moved = None

    print(f"Batches processed: {len(batches)}")
    print(f"Tracks ingested: {total_ingested}  |  Already in DB: {total_already}  |  Failed: {total_failed}")
    if moved is not None:
        print(f"Inventory delta (in_asset_file 0->1): {moved}")
    print(f"Output: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

