#!/usr/bin/env python3
from __future__ import annotations

import csv
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


STAGING_ROOT = Path("/Volumes/MUSIC/staging")
LOGS_ROOT = Path("/Volumes/MUSIC/logs")

# Ensure we never write/copy anything into MP3_LIBRARY (the prompt forbids touching it).
DISABLE_MP3_LIBRARY_PATH = "/__tagslut_intake_sweep_disable_mp3_library__"


@dataclass(frozen=True)
class BatchResult:
    batch_name: str
    source: str
    total_tracks: int
    ingested: int
    already_in_db: int
    failed: int
    notes: str


def _find_latest_inventory_tsv(logs_root: Path) -> Path:
    candidates = sorted(
        logs_root.glob("inventory_*.tsv"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(f"No inventory TSV found at {logs_root}/inventory_*.tsv (P1 prerequisite missing)")
    return candidates[0]


def _load_inventory_in_asset_file(inventory_tsv: Path) -> dict[str, int]:
    with inventory_tsv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if not reader.fieldnames:
            raise ValueError(f"Inventory TSV missing header: {inventory_tsv}")
        if "path" not in reader.fieldnames or "in_asset_file" not in reader.fieldnames:
            raise ValueError(
                f"Inventory TSV missing required columns (need path, in_asset_file): {inventory_tsv}"
            )

        out: dict[str, int] = {}
        for row in reader:
            p = (row.get("path") or "").strip()
            v = (row.get("in_asset_file") or "").strip()
            if not p:
                continue
            try:
                out[p] = int(v) if v else 0
            except ValueError:
                out[p] = 0
        return out


def _read_m3u8_paths(m3u8_path: Path, base_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for raw in m3u8_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        p = Path(line)
        if not p.is_absolute():
            p = (base_dir / p).resolve()
        else:
            p = p.resolve()
        paths.append(p)
    return paths


_SUMMARY_RE = re.compile(
    r"(?P<ingested>\d+)\s+ingested,\s+(?P<skipped_missing>\d+)\s+skipped\s+\\(file not found\\),\s+(?P<failed>\d+)\s+failed",
    re.IGNORECASE,
)


def _run_spotiflac_intake(log_path: Path, base_dir: Path) -> tuple[int, int, int, str]:
    """
    Returns: (ingested, already_in_db, failed, notes)
    failed includes:
    - tracks marked failed by the parser
    - missing-file skips (file not found)
    """
    cmd = [
        sys.executable,
        "-m",
        "tagslut",
        "intake",
        "spotiflac",
        str(log_path),
        "--base-dir",
        str(base_dir),
    ]
    env = os.environ.copy()
    env["MP3_LIBRARY"] = DISABLE_MP3_LIBRARY_PATH
    env["DJ_POOL_M3U"] = os.path.join(DISABLE_MP3_LIBRARY_PATH, "dj_pool.m3u")

    proc = subprocess.run(cmd, text=True, capture_output=True, env=env)

    already_in_db = len(
        re.findall(r"^\[warning\]\s+already indexed;\s+skipping:", proc.stderr, flags=re.IGNORECASE | re.MULTILINE)
    )
    notes_bits: list[str] = []
    if proc.returncode != 0:
        notes_bits.append(f"exit={proc.returncode}")

    ingested = 0
    skipped_missing = 0
    failed_parser = 0
    for line in proc.stdout.splitlines():
        m = _SUMMARY_RE.search(line)
        if m:
            ingested = int(m.group("ingested"))
            skipped_missing = int(m.group("skipped_missing"))
            failed_parser = int(m.group("failed"))
            break
    else:
        notes_bits.append("summary_unparsed")

    failed = failed_parser + skipped_missing
    if skipped_missing:
        notes_bits.append(f"missing_files={skipped_missing}")

    return ingested, already_in_db, failed, "; ".join(notes_bits)


def _batch_key_for_child_dir(root: Path, path_str: str) -> str | None:
    try:
        p = Path(path_str)
    except Exception:
        return None
    if not str(p).startswith(str(root)):
        return None
    rel = p.relative_to(root)
    if not rel.parts:
        return None
    return rel.parts[0]


def main() -> int:
    inventory_tsv = _find_latest_inventory_tsv(LOGS_ROOT)
    inv_in_asset = _load_inventory_in_asset_file(inventory_tsv)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = LOGS_ROOT / f"intake_sweep_{stamp}.tsv"

    results: list[BatchResult] = []

    # 1) staging/SpotiFLACnext — per *.txt download report at root, using adjacent *.m3u8 (prefer non-_converted).
    spotiflacnext_root = STAGING_ROOT / "SpotiFLACnext"
    if spotiflacnext_root.exists():
        for log_path in sorted(spotiflacnext_root.glob("*.txt")):
            batch_name = log_path.stem
            source = "spotiflacnext"

            notes_bits: list[str] = []
            m3u8_path = spotiflacnext_root / f"{batch_name}.m3u8"
            if not m3u8_path.exists():
                alt = spotiflacnext_root / f"{batch_name}_converted.m3u8"
                if alt.exists():
                    m3u8_path = alt
                    notes_bits.append("used_converted_m3u8")
                else:
                    notes_bits.append("missing_m3u8")

            m3u8_tracks: list[Path] = []
            if m3u8_path.exists():
                try:
                    m3u8_tracks = _read_m3u8_paths(m3u8_path, base_dir=spotiflacnext_root)
                except Exception as exc:
                    notes_bits.append(f"m3u8_read_error={type(exc).__name__}")

            # Skip fully-processed batches when we can resolve concrete track paths.
            if m3u8_tracks:
                missing_from_inventory = [p for p in m3u8_tracks if str(p) not in inv_in_asset]
                if missing_from_inventory:
                    notes_bits.append(f"inventory_missing={len(missing_from_inventory)}")

                unprocessed = 0
                processed = 0
                for p in m3u8_tracks:
                    v = inv_in_asset.get(str(p))
                    if v is None:
                        continue
                    if v == 0:
                        unprocessed += 1
                    else:
                        processed += 1

                if unprocessed == 0 and not missing_from_inventory:
                    results.append(
                        BatchResult(
                            batch_name=batch_name,
                            source=source,
                            total_tracks=len(m3u8_tracks),
                            ingested=0,
                            already_in_db=len(m3u8_tracks),
                            failed=0,
                            notes="skipped_already_in_db",
                        )
                    )
                    continue

            ingested, already_in_db, failed, run_notes = _run_spotiflac_intake(
                log_path=log_path,
                base_dir=spotiflacnext_root,
            )
            if run_notes:
                notes_bits.append(run_notes)

            total_tracks = len(m3u8_tracks) if m3u8_tracks else max(ingested + already_in_db + failed, 0)
            results.append(
                BatchResult(
                    batch_name=batch_name,
                    source=source,
                    total_tracks=total_tracks,
                    ingested=ingested,
                    already_in_db=already_in_db,
                    failed=failed,
                    notes="; ".join([b for b in notes_bits if b]),
                )
            )

    # 2) staging/SpotiFLAC — per *.txt at root (ignore *_Failed.txt helper files).
    spotiflac_root = STAGING_ROOT / "SpotiFLAC"
    if spotiflac_root.exists():
        for log_path in sorted(spotiflac_root.glob("*.txt")):
            if re.search(r"(^|[_-])failed($|[_-])", log_path.stem, flags=re.IGNORECASE):
                continue
            batch_name = log_path.stem
            source = "spotiflac"

            ingested, already_in_db, failed, run_notes = _run_spotiflac_intake(
                log_path=log_path,
                base_dir=spotiflac_root,
            )
            total_tracks = max(ingested + already_in_db + failed, 0)
            results.append(
                BatchResult(
                    batch_name=batch_name,
                    source=source,
                    total_tracks=total_tracks,
                    ingested=ingested,
                    already_in_db=already_in_db,
                    failed=failed,
                    notes=run_notes,
                )
            )

    # 3-6) Manual-required / unrecognized: derive from inventory TSV (in_asset_file=0).
    known_top_dirs = {
        "SpotiFLACnext": "spotiflacnext",
        "SpotiFLAC": "spotiflac",
        "bpdl": "bpdl",
        "StreamripDownloads": "streamrip",
        "tidal": "tidal",
    }
    manual_by_top: dict[str, int] = {}
    for path_str, in_asset in inv_in_asset.items():
        if in_asset != 0:
            continue
        if not path_str.startswith(str(STAGING_ROOT) + "/"):
            continue
        if any(
            token in path_str
            for token in (
                "/_UNRESOLVED/",
                "/_UNRESOLVED_FROM_LIBRARY/",
                "/MASTER_LIBRARY/",
                "/MP3_LIBRARY/",
                "/_work/",
            )
        ):
            continue
        top = _batch_key_for_child_dir(STAGING_ROOT, path_str)
        if not top:
            continue
        if top in ("SpotiFLACnext", "SpotiFLAC"):
            # Spotiflac batches are reported via the per-log sweep above.
            continue
        manual_by_top[top] = manual_by_top.get(top, 0) + 1

    for top_dir, count in sorted(manual_by_top.items()):
        source = known_top_dirs.get(top_dir, "unknown")
        note = "manual required" if source != "unknown" else "unrecognised source, manual required"
        results.append(
            BatchResult(
                batch_name=top_dir,
                source=source,
                total_tracks=count,
                ingested=0,
                already_in_db=0,
                failed=count,
                notes=note,
            )
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(["batch_name", "source", "total_tracks", "ingested", "already_in_db", "failed", "notes"])
        for r in results:
            writer.writerow(
                [
                    r.batch_name,
                    r.source,
                    str(r.total_tracks),
                    str(r.ingested),
                    str(r.already_in_db),
                    str(r.failed),
                    r.notes,
                ]
            )

    batches_processed = len(results)
    tracks_ingested = sum(r.ingested for r in results)
    tracks_already = sum(r.already_in_db for r in results)
    tracks_failed = sum(r.failed for r in results)
    manual_required = sum(1 for r in results if "manual required" in (r.notes or ""))

    print(f"Batches processed: {batches_processed}")
    print(f"Tracks ingested: {tracks_ingested}  |  Already in DB: {tracks_already}  |  Failed: {tracks_failed}  |  Manual required: {manual_required}")
    print(f"Output: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

