#!/usr/bin/env python3
"""Step-0 ingestion pipeline for canonical FLAC libraries."""

from __future__ import annotations

import argparse
import csv
import importlib
import importlib.util
import json
import logging
import shutil
import sqlite3
import subprocess
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator, Optional

from dedupe import metadata, utils
from dedupe.core.hashing import DEFAULT_PREHASH_BYTES, calculate_tiered_hashes
from dedupe.step0 import (
    IntegrityResult,
    ScannedFile,
    build_canonical_path,
    choose_canonical,
    classify_integrity,
    confidence_score,
    extract_identity_hints,
)
from dedupe.storage import initialise_step0_schema
from dedupe.storage import queries as storage_queries

logger = logging.getLogger(__name__)

HASH_STRATEGY = "tiered-sha256-v1"
KNOWN_COMMANDS = {"scan", "status", "decide", "apply", "artifacts"}


def _normalise_prefix(path: Path) -> str:
    """Return a normalised prefix string for SQLite LIKE filters."""

    normalised = utils.normalise_path(str(path))
    return normalised.rstrip("/") + "/"


def _infer_volume(path: Path) -> Optional[str]:
    """Infer a source volume name from the absolute path."""

    try:
        parts = path.resolve(strict=False).parts
    except Exception:
        parts = path.parts
    if len(parts) >= 3 and parts[0] == "/" and parts[1] == "Volumes":
        return parts[2]
    if len(parts) >= 2 and parts[0] == "/":
        return parts[1]
    return None


def _stat_file(path: Path) -> tuple[Optional[int], Optional[float]]:
    """Return (size, mtime) for a path, handling errors safely."""

    try:
        stat = path.stat()
        return int(stat.st_size), float(stat.st_mtime)
    except OSError:
        return None, None


def _tiered_hashes(path: Path, prehash_bytes: int) -> dict[str, str]:
    """Return Tier-1 and Tier-2 hashes for *path*."""

    return calculate_tiered_hashes(path, prehash_bytes=prehash_bytes)


def _load_resume_records(
    connection: sqlite3.Connection,
    inputs: list[Path],
) -> list[ScannedFile]:
    """Load previously scanned Step-0 records for the input roots.

    This allows the Step-0 pipeline to resume a prior run without re-hashing and
    re-testing files already recorded in the Step-0 tables.
    """

    prefixes = [_normalise_prefix(path) for path in inputs]
    if not prefixes:
        return []

    where = " OR ".join(["ir.path LIKE ?"] * len(prefixes))
    params = [f"{prefix}%" for prefix in prefixes]

    query = f"""
    WITH latest AS (
        SELECT path, MAX(id) AS max_id
        FROM integrity_results
        GROUP BY path
    )
    SELECT
        ir.path,
        ir.content_hash,
        ir.status,
        ir.stderr_excerpt,
        ir.return_code,
        ac.streaminfo_md5,
        ac.duration,
        ac.sample_rate,
        ac.bit_depth,
        ac.channels,
        ih.tags_json
    FROM integrity_results ir
    JOIN latest ON latest.path = ir.path AND latest.max_id = ir.id
    LEFT JOIN audio_content ac ON ac.content_hash = ir.content_hash
    LEFT JOIN identity_hints ih ON ih.content_hash = ir.content_hash
    WHERE {where}
    """

    cursor = connection.execute(query, params)
    records: list[ScannedFile] = []
    for row in cursor.fetchall():
        tags_json = row[10] if len(row) > 10 else None
        tags: dict[str, object]
        if tags_json:
            try:
                tags = json.loads(tags_json)
            except json.JSONDecodeError:
                tags = {}
        else:
            tags = {}
        records.append(
            ScannedFile(
                path=row[0],
                content_hash=row[1],
                streaminfo_md5=row[5],
                duration=row[6],
                sample_rate=row[7],
                bit_depth=row[8],
                channels=row[9],
                tags=tags,
                integrity=IntegrityResult(
                    status=row[2],
                    stderr_excerpt=row[3] or "",
                    return_code=row[4],
                ),
            )
        )
    return records


def _configure_logging(verbose: bool) -> None:
    """Configure logging based on verbosity."""

    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _iter_input_files(inputs: Iterable[Path]) -> Iterator[Path]:
    """Yield FLAC files found under the provided input directories."""

    for root in inputs:
        for path in utils.iter_audio_files(root):
            if path.suffix.lower() != ".flac":
                continue
            yield path


def _run_flac_test(path: Path) -> tuple[str, int | None]:
    """Return stderr output and return code from ``flac --test``."""

    try:
        result = subprocess.run(
            ["flac", "--test", str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("FLAC integrity test failed for %s: %s", path, exc)
        return str(exc), None
    return result.stderr or "", result.returncode


def _evaluate_integrity(path: Path, strict: bool) -> IntegrityResult:
    """Evaluate integrity status for a FLAC path."""

    stderr, return_code = _run_flac_test(path)
    result = classify_integrity(stderr, return_code)
    if strict and result.status != "pass":
        return result
    return result


def _streaminfo_md5(path: Path) -> str | None:
    """Return the FLAC streaminfo MD5 signature if available."""

    if importlib.util.find_spec("mutagen.flac") is None:
        return None
    module = importlib.import_module("mutagen.flac")
    flac_type = getattr(module, "FLAC", None)
    if flac_type is None:
        return None
    try:
        audio = flac_type(path)
    except Exception:  # pragma: no cover - defensive logging
        return None
    return getattr(audio.info, "md5_signature", None)


def _scan_file(
    path: Path,
    strict_integrity: bool,
    prehash_bytes: int,
) -> tuple[ScannedFile, dict[str, str]]:
    """Scan a single file and return a structured record plus hashes."""

    probe = metadata.probe_audio(path)
    tags = probe.tags
    integrity = _evaluate_integrity(path, strict_integrity)
    hashes = _tiered_hashes(path, prehash_bytes)
    record = ScannedFile(
        path=utils.normalise_path(str(path)),
        content_hash=hashes["tier2"],
        streaminfo_md5=_streaminfo_md5(path),
        duration=probe.stream.duration,
        sample_rate=probe.stream.sample_rate,
        bit_depth=probe.stream.bit_depth,
        channels=probe.stream.channels,
        tags=tags,
        integrity=integrity,
    )
    return record, hashes


def _identity_recoverable(tags: dict[str, object]) -> bool:
    """Return True when tags provide enough identity to reacquire."""

    hints = extract_identity_hints(tags)
    key_fields = ("artist", "title", "album", "isrc", "musicbrainz_track_id")
    return any(hints.get(key) for key in key_fields)


def _resolve_collision(path: Path, content_hash: str) -> Path:
    """Resolve collisions deterministically using the content hash suffix."""

    if not path.exists():
        return path
    try:
        if utils.compute_md5(path) == content_hash:
            return path
    except OSError:
        logger.warning("Unable to hash existing path for collision check: %s", path)
    stem = path.stem
    suffix = path.suffix
    candidate = path.with_name(f"{stem} [{content_hash[:8]}]{suffix}")
    if candidate.exists():
        candidate = path.with_name(f"{stem} [{content_hash[:8]}-1]{suffix}")
    return candidate


def _plan_actions(
    files: list[ScannedFile],
    canonical_root: Path,
    quarantine_root: Path,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Build plan actions and reacquire manifest rows."""

    grouped: dict[str, list[ScannedFile]] = {}
    for item in files:
        key = item.streaminfo_md5 or item.content_hash
        grouped.setdefault(key, []).append(item)

    actions: list[dict[str, object]] = []
    reacquire_rows: list[dict[str, object]] = []
    for group in grouped.values():
        winner = choose_canonical(group)
        winner_hash = winner.content_hash if winner else None
        winner_tags = winner.tags if winner else {}
        canonical_rel = build_canonical_path(winner_tags) if winner else None
        for item in group:
            hints = extract_identity_hints(item.tags)
            if canonical_rel:
                canonical_path = _resolve_collision(
                    canonical_root / canonical_rel,
                    item.content_hash,
                )
            else:
                canonical_path = canonical_root / build_canonical_path(item.tags)
            decision = "TRASH"
            reason = "Integrity failure with insufficient identity hints."
            quarantine_path = None
            confidence = None
            if item.integrity.status == "pass":
                if winner_hash and item.content_hash == winner_hash:
                    decision = "CANONICAL"
                    reason = "Selected as canonical based on integrity and audio quality."
                else:
                    decision = "REDUNDANT"
                    reason = "Valid duplicate with lower audio priority."
                    if canonical_rel:
                        quarantine_path = _resolve_collision(
                            quarantine_root / canonical_rel,
                            item.content_hash,
                        )
            elif _identity_recoverable(dict(item.tags)):
                decision = "REACQUIRE"
                reason = "Integrity failure but identity hints present."
                confidence = confidence_score(item.tags)
                reacquire_rows.append(
                    {
                        "Artist": hints.get("artist") or "",
                        "Title": hints.get("title") or "",
                        "Album": hints.get("album") or "",
                        "Duration": item.duration or "",
                        "ISRC": hints.get("isrc") or "",
                        "Confidence": f"{confidence:.2f}",
                        "Reason": reason,
                    }
                )

            actions.append(
                {
                    "path": item.path,
                    "content_hash": item.content_hash,
                    "decision": decision,
                    "reason": reason,
                    "canonical_path": str(canonical_path),
                    "quarantine_path": str(quarantine_path) if quarantine_path else None,
                    "integrity": asdict(item.integrity),
                    "confidence": confidence,
                }
            )

    return actions, reacquire_rows


def _write_plan(path: Path, payload: dict[str, object]) -> None:
    """Write the plan JSON file to disk."""

    utils.ensure_parent_directory(path)
    with path.open("w", encoding="utf8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)


def _write_reacquire_manifest(path: Path, rows: list[dict[str, object]]) -> None:
    """Write the reacquire manifest CSV to disk."""

    utils.ensure_parent_directory(path)
    fieldnames = ["Artist", "Title", "Album", "Duration", "ISRC", "Confidence", "Reason"]
    with path.open("w", encoding="utf8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _apply_plan(actions: list[dict[str, object]], *, move_files: bool) -> None:
    """Apply canonical and quarantine actions to the filesystem."""

    for action in actions:
        decision = action["decision"]
        source = Path(action["path"])
        if decision == "CANONICAL":
            destination = Path(action["canonical_path"])
        elif decision == "REDUNDANT" and action["quarantine_path"]:
            destination = Path(action["quarantine_path"])
        else:
            continue
        utils.ensure_parent_directory(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if move_files:
            source.replace(destination)
        else:
            shutil.copy2(source, destination)


def _decision_state(decision: str) -> str:
    """Map pipeline decisions to accepted/rejected/quarantined states."""

    mapping = {
        "CANONICAL": "accepted",
        "REDUNDANT": "quarantined",
        "REACQUIRE": "rejected",
        "TRASH": "rejected",
    }
    return mapping.get(decision, "rejected")


def _load_plan(path: Path) -> list[dict[str, object]]:
    """Load plan actions from JSON."""

    with path.open("r", encoding="utf8") as handle:
        payload = json.load(handle)
    return list(payload.get("actions", []))


def _iter_artifacts(inputs: Iterable[Path]) -> Iterator[Path]:
    """Yield non-audio artifact files under the provided inputs."""

    artifact_extensions = {".csv", ".db", ".sqlite", ".sqlite3", ".log", ".txt", ".json"}
    for root in inputs:
        for entry in root.rglob("*"):
            if entry.is_dir():
                continue
            if entry.suffix.lower() in artifact_extensions:
                yield entry
                continue
            if entry.name.startswith(".DOTAD_"):
                yield entry


def _classify_artifact(path: Path) -> dict[str, object]:
    """Classify an artifact path using simple heuristics."""

    lowered = path.name.lower()
    artifact_type = "artifact"
    orphaned_db = False
    legacy_marker = False
    provenance_notes = None
    if path.name.startswith(".DOTAD_"):
        artifact_type = "dotad_marker"
        legacy_marker = True
        provenance_notes = "Legacy marker file detected."
    elif path.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
        artifact_type = "sqlite_db"
        orphaned_db = True
    elif path.suffix.lower() == ".csv":
        artifact_type = "comparison_csv"
    elif "audit_report" in lowered:
        artifact_type = "audit_report"
    elif "artifacts" in path.parts:
        artifact_type = "artifact_file"
    return {
        "artifact_type": artifact_type,
        "orphaned_db": orphaned_db,
        "legacy_marker": legacy_marker,
        "provenance_notes": provenance_notes,
    }


def _load_decision_records(
    connection: sqlite3.Connection,
    inputs: Optional[list[Path]],
) -> list[ScannedFile]:
    """Load scanned records for decision-making from Step-0 tables."""

    if inputs:
        return _load_resume_records(connection, inputs)

    query = """
    WITH latest AS (
        SELECT path, MAX(id) AS max_id
        FROM integrity_results
        GROUP BY path
    )
    SELECT
        ir.path,
        ir.content_hash,
        ir.status,
        ir.stderr_excerpt,
        ir.return_code,
        ac.streaminfo_md5,
        ac.duration,
        ac.sample_rate,
        ac.bit_depth,
        ac.channels,
        ih.tags_json
    FROM integrity_results ir
    JOIN latest ON latest.path = ir.path AND latest.max_id = ir.id
    LEFT JOIN audio_content ac ON ac.content_hash = ir.content_hash
    LEFT JOIN identity_hints ih ON ih.content_hash = ir.content_hash
    """
    cursor = connection.execute(query)
    records: list[ScannedFile] = []
    for row in cursor.fetchall():
        tags_json = row[10] if len(row) > 10 else None
        tags: dict[str, object]
        if tags_json:
            try:
                tags = json.loads(tags_json)
            except json.JSONDecodeError:
                tags = {}
        else:
            tags = {}
        records.append(
            ScannedFile(
                path=row[0],
                content_hash=row[1],
                streaminfo_md5=row[5],
                duration=row[6],
                sample_rate=row[7],
                bit_depth=row[8],
                channels=row[9],
                tags=tags,
                integrity=IntegrityResult(
                    status=row[2],
                    stderr_excerpt=row[3] or "",
                    return_code=row[4],
                ),
            )
        )
    return records


def build_parser() -> argparse.ArgumentParser:
    """Build the Step-0 ingestion CLI parser."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    subparsers = parser.add_subparsers(dest="command")

    scan_parser = subparsers.add_parser(
        "scan",
        help="Scan inputs, write Step-0 tables, and produce a plan.",
    )
    scan_parser.add_argument(
        "--inputs",
        nargs="+",
        type=Path,
        required=True,
        help="Input directories to scan for FLAC files.",
    )
    scan_parser.add_argument(
        "--canonical-root",
        type=Path,
        required=True,
        help="Canonical library root directory.",
    )
    scan_parser.add_argument(
        "--quarantine-root",
        type=Path,
        required=True,
        help="Root directory for redundant quarantined files.",
    )
    scan_parser.add_argument(
        "--db",
        type=Path,
        required=True,
        help="SQLite database path for Step-0 ingestion.",
    )
    scan_parser.add_argument(
        "--library-tag",
        required=True,
        help="Library tag label applied to this scan.",
    )
    scan_parser.add_argument(
        "--library",
        default=None,
        help="Logical library label to store per file (defaults to --library-tag).",
    )
    scan_parser.add_argument(
        "--zone",
        default=None,
        help="Source zone label (e.g. recovery, bad, vault).",
    )
    scan_parser.add_argument(
        "--plan",
        type=Path,
        default=Path("plan.json"),
        help="Plan JSON output path (default: plan.json).",
    )
    scan_parser.add_argument(
        "--reacquire-csv",
        type=Path,
        default=Path("reacquire_manifest.csv"),
        help="Reacquire CSV output path (default: reacquire_manifest.csv).",
    )
    scan_parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply the plan to the filesystem (default: dry-run).",
    )
    scan_parser.add_argument(
        "--resume",
        default=False,
        action=argparse.BooleanOptionalAction,
        help=(
            "Resume from existing Step-0 scan data in the database. When enabled, "
            "previously scanned files under the --inputs roots are loaded from the "
            "Step-0 tables and only new files are scanned."
        ),
    )
    scan_parser.add_argument(
        "--move",
        action="store_true",
        help="Move files instead of copying when applying the plan.",
    )
    scan_parser.add_argument(
        "--strict-integrity",
        default=True,
        action=argparse.BooleanOptionalAction,
        help="Require flac --test success for canonical selection (default: true).",
    )
    scan_parser.add_argument(
        "--progress",
        action="store_true",
        help="Log progress while scanning inputs.",
    )
    scan_parser.add_argument(
        "--prehash-mb",
        type=int,
        default=DEFAULT_PREHASH_BYTES // (1024 * 1024),
        help="Size in MB for Tier-1 prehashing (default: 4).",
    )

    decide_parser = subparsers.add_parser(
        "decide",
        help="Generate a plan from existing Step-0 scan tables.",
    )
    decide_parser.add_argument(
        "--db",
        type=Path,
        required=True,
        help="SQLite database path for Step-0 ingestion.",
    )
    decide_parser.add_argument(
        "--inputs",
        nargs="*",
        type=Path,
        default=None,
        help="Optional input roots to filter decisions.",
    )
    decide_parser.add_argument(
        "--canonical-root",
        type=Path,
        required=True,
        help="Canonical library root directory.",
    )
    decide_parser.add_argument(
        "--quarantine-root",
        type=Path,
        required=True,
        help="Root directory for redundant quarantined files.",
    )
    decide_parser.add_argument(
        "--library-tag",
        required=True,
        help="Library tag label applied to this plan.",
    )
    decide_parser.add_argument(
        "--plan",
        type=Path,
        default=Path("plan.json"),
        help="Plan JSON output path (default: plan.json).",
    )
    decide_parser.add_argument(
        "--reacquire-csv",
        type=Path,
        default=Path("reacquire_manifest.csv"),
        help="Reacquire CSV output path (default: reacquire_manifest.csv).",
    )
    decide_parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply the plan to the filesystem (default: dry-run).",
    )
    decide_parser.add_argument(
        "--move",
        action="store_true",
        help="Move files instead of copying when applying the plan.",
    )

    apply_parser = subparsers.add_parser(
        "apply",
        help="Apply a saved plan JSON to the filesystem.",
    )
    apply_parser.add_argument(
        "--plan",
        type=Path,
        required=True,
        help="Plan JSON input path.",
    )
    apply_parser.add_argument(
        "--move",
        action="store_true",
        help="Move files instead of copying when applying the plan.",
    )

    status_parser = subparsers.add_parser(
        "status",
        help="Show summary counts for Step-0 tables.",
    )
    status_parser.add_argument(
        "--db",
        type=Path,
        required=True,
        help="SQLite database path for Step-0 ingestion.",
    )

    artifacts_parser = subparsers.add_parser(
        "artifacts",
        help="Scan inputs for artifact files and record them in the database.",
    )
    artifacts_parser.add_argument(
        "--inputs",
        nargs="+",
        type=Path,
        required=True,
        help="Input directories to scan for artifact files.",
    )
    artifacts_parser.add_argument(
        "--db",
        type=Path,
        required=True,
        help="SQLite database path for Step-0 ingestion.",
    )

    return parser


def _run_scan(args: argparse.Namespace) -> None:
    """Execute the scan subcommand."""

    inputs = [Path(utils.normalise_path(str(path))) for path in args.inputs]
    db_path = Path(utils.normalise_path(str(args.db)))
    canonical_root = Path(utils.normalise_path(str(args.canonical_root)))
    quarantine_root = Path(utils.normalise_path(str(args.quarantine_root)))
    prehash_bytes = max(args.prehash_mb, 1) * 1024 * 1024
    library_label = args.library or args.library_tag

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        initialise_step0_schema(connection)
        storage_queries.insert_scan_event(
            connection,
            inputs=[str(path) for path in inputs],
            version="step0",
            library_tag=args.library_tag,
        )
        files: list[ScannedFile] = []
        scanned_paths: set[str] = set()

        if args.resume:
            files = _load_resume_records(connection, inputs)
            scanned_paths = {record.path for record in files}
            logger.info("Resume enabled: loaded %s previously scanned files.", len(files))

        for index, path in enumerate(_iter_input_files(inputs), start=1):
            if args.progress and index % 25 == 0:
                logger.info("Scanned %s files...", index)
            if not path.is_file():
                continue

            normalised_path = utils.normalise_path(str(path))
            if args.resume and normalised_path in scanned_paths:
                continue

            record, hashes = _scan_file(path, args.strict_integrity, prehash_bytes)
            files.append(record)
            scanned_paths.add(record.path)
            hints = extract_identity_hints(record.tags)
            size_bytes, mtime = _stat_file(path)
            volume = _infer_volume(path)
            storage_queries.upsert_audio_content(
                connection,
                content_hash=record.content_hash,
                streaminfo_md5=record.streaminfo_md5,
                duration=record.duration,
                sample_rate=record.sample_rate,
                bit_depth=record.bit_depth,
                channels=record.channels,
                hash_type="sha256",
                coverage="full",
            )
            storage_queries.insert_integrity_result(
                connection,
                content_hash=record.content_hash,
                path=Path(record.path),
                status=record.integrity.status,
                stderr_excerpt=record.integrity.stderr_excerpt,
                return_code=record.integrity.return_code,
            )
            storage_queries.upsert_identity_hints(
                connection,
                content_hash=record.content_hash,
                hints=hints,
                tags=dict(record.tags),
            )
            storage_queries.upsert_step0_file(
                connection,
                absolute_path=record.path,
                content_hash=record.content_hash,
                volume=volume,
                zone=args.zone,
                library=library_label,
                size_bytes=size_bytes,
                mtime=mtime,
                scan_timestamp=datetime.utcnow().isoformat(),
                audio_integrity=record.integrity.status,
                flac_test_passed=record.integrity.status == "pass",
                flac_error=record.integrity.stderr_excerpt,
                duration_seconds=record.duration,
                sample_rate=record.sample_rate,
                bit_depth=record.bit_depth,
                channels=record.channels,
                hash_strategy=HASH_STRATEGY,
                provenance_notes=None,
                orphaned_db=None,
                legacy_marker=None,
            )
            storage_queries.upsert_step0_hash(
                connection,
                absolute_path=record.path,
                hash_type="prehash",
                hash_value=hashes["tier1"],
                coverage="partial",
            )
            storage_queries.upsert_step0_hash(
                connection,
                absolute_path=record.path,
                hash_type="sha256",
                hash_value=hashes["tier2"],
                coverage="full",
            )
        actions, reacquire_rows = _plan_actions(files, canonical_root, quarantine_root)
        timestamp = datetime.utcnow().isoformat()
        plan_payload = {
            "scan": {
                "inputs": [str(path) for path in inputs],
                "timestamp": timestamp,
                "library_tag": args.library_tag,
                "strict_integrity": args.strict_integrity,
                "hash_strategy": HASH_STRATEGY,
            },
            "actions": actions,
        }
        _write_plan(args.plan, plan_payload)
        _write_reacquire_manifest(args.reacquire_csv, reacquire_rows)

        for action in actions:
            decision_state = _decision_state(action["decision"])
            storage_queries.upsert_step0_decision(
                connection,
                absolute_path=action["path"],
                content_hash=action["content_hash"],
                decision=decision_state,
                reason=action["reason"],
                winner_path=action.get("canonical_path"),
            )
            if action["decision"] == "CANONICAL":
                storage_queries.upsert_canonical_map(
                    connection,
                    content_hash=action["content_hash"],
                    canonical_path=action["canonical_path"],
                    reason=action["reason"],
                )
            elif action["decision"] == "REACQUIRE":
                storage_queries.upsert_reacquire_manifest(
                    connection,
                    content_hash=action["content_hash"],
                    reason=action["reason"],
                    confidence=float(action["confidence"] or 0.0),
                )
        connection.commit()

    if args.execute:
        _apply_plan(actions, move_files=args.move)
        logger.info("Applied plan actions for %s files.", len(actions))
    else:
        logger.info("Dry-run complete; plan saved to %s.", args.plan)


def _run_decide(args: argparse.Namespace) -> None:
    """Execute the decide subcommand."""

    db_path = Path(utils.normalise_path(str(args.db)))
    canonical_root = Path(utils.normalise_path(str(args.canonical_root)))
    quarantine_root = Path(utils.normalise_path(str(args.quarantine_root)))
    inputs = [Path(utils.normalise_path(str(path))) for path in args.inputs] if args.inputs else None

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        initialise_step0_schema(connection)
        storage_queries.insert_scan_event(
            connection,
            inputs=[str(path) for path in inputs] if inputs else [],
            version="step0-decide",
            library_tag=args.library_tag,
        )
        files = _load_decision_records(connection, inputs)
        actions, reacquire_rows = _plan_actions(files, canonical_root, quarantine_root)
        timestamp = datetime.utcnow().isoformat()
        plan_payload = {
            "scan": {
                "inputs": [str(path) for path in inputs] if inputs else [],
                "timestamp": timestamp,
                "library_tag": args.library_tag,
                "strict_integrity": True,
                "hash_strategy": HASH_STRATEGY,
            },
            "actions": actions,
        }
        _write_plan(args.plan, plan_payload)
        _write_reacquire_manifest(args.reacquire_csv, reacquire_rows)

        for action in actions:
            decision_state = _decision_state(action["decision"])
            storage_queries.upsert_step0_decision(
                connection,
                absolute_path=action["path"],
                content_hash=action["content_hash"],
                decision=decision_state,
                reason=action["reason"],
                winner_path=action.get("canonical_path"),
            )
            if action["decision"] == "CANONICAL":
                storage_queries.upsert_canonical_map(
                    connection,
                    content_hash=action["content_hash"],
                    canonical_path=action["canonical_path"],
                    reason=action["reason"],
                )
            elif action["decision"] == "REACQUIRE":
                storage_queries.upsert_reacquire_manifest(
                    connection,
                    content_hash=action["content_hash"],
                    reason=action["reason"],
                    confidence=float(action["confidence"] or 0.0),
                )
        connection.commit()

    if args.execute:
        _apply_plan(actions, move_files=args.move)
        logger.info("Applied plan actions for %s files.", len(actions))
    else:
        logger.info("Dry-run complete; plan saved to %s.", args.plan)


def _run_apply(args: argparse.Namespace) -> None:
    """Execute the apply subcommand."""

    plan_actions = _load_plan(args.plan)
    _apply_plan(plan_actions, move_files=args.move)
    logger.info("Applied plan actions for %s files.", len(plan_actions))


def _run_status(args: argparse.Namespace) -> None:
    """Execute the status subcommand."""

    db_path = Path(utils.normalise_path(str(args.db)))
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        initialise_step0_schema(connection)
        file_count = connection.execute("SELECT COUNT(*) FROM step0_files").fetchone()[0]
        decision_count = connection.execute("SELECT COUNT(*) FROM step0_decisions").fetchone()[0]
        canonical_count = connection.execute("SELECT COUNT(*) FROM canonical_map").fetchone()[0]
        artifact_count = connection.execute("SELECT COUNT(*) FROM step0_artifacts").fetchone()[0]
    logger.info("Step-0 files: %s", file_count)
    logger.info("Decisions: %s", decision_count)
    logger.info("Canonical map: %s", canonical_count)
    logger.info("Artifacts: %s", artifact_count)


def _run_artifacts(args: argparse.Namespace) -> None:
    """Execute the artifacts subcommand."""

    inputs = [Path(utils.normalise_path(str(path))) for path in args.inputs]
    db_path = Path(utils.normalise_path(str(args.db)))
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        initialise_step0_schema(connection)
        for path in _iter_artifacts(inputs):
            normalized = utils.normalise_path(str(path))
            volume = _infer_volume(path)
            classification = _classify_artifact(path)
            storage_queries.upsert_step0_artifact(
                connection,
                path=normalized,
                volume=volume,
                artifact_type=classification["artifact_type"],
                related_path=None,
                orphaned_db=classification["orphaned_db"],
                legacy_marker=classification["legacy_marker"],
                provenance_notes=classification["provenance_notes"],
            )
        connection.commit()
    logger.info("Artifact scan complete.")


def main() -> None:
    """CLI entry point for the Step-0 ingestion pipeline."""

    parser = build_parser()
    argv = sys.argv[1:]
    if not argv:
        parser.print_help()
        return
    if argv and argv[0] not in KNOWN_COMMANDS:
        argv = ["scan"] + argv
    args = parser.parse_args(argv)
    _configure_logging(args.verbose)

    if args.command == "scan" or args.command is None:
        _run_scan(args)
    elif args.command == "decide":
        _run_decide(args)
    elif args.command == "apply":
        _run_apply(args)
    elif args.command == "status":
        _run_status(args)
    elif args.command == "artifacts":
        _run_artifacts(args)
    else:
        parser.error("Unknown command.")


if __name__ == "__main__":
    main()
