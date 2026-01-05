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
from typing import Iterable, Iterator

from dedupe import metadata, utils
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


def _scan_file(path: Path, strict_integrity: bool) -> ScannedFile:
    """Scan a single file and return a structured record."""

    probe = metadata.probe_audio(path)
    tags = probe.tags
    integrity = _evaluate_integrity(path, strict_integrity)
    return ScannedFile(
        path=utils.normalise_path(str(path)),
        content_hash=utils.compute_md5(path),
        streaminfo_md5=_streaminfo_md5(path),
        duration=probe.stream.duration,
        sample_rate=probe.stream.sample_rate,
        bit_depth=probe.stream.bit_depth,
        channels=probe.stream.channels,
        tags=tags,
        integrity=integrity,
    )


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


def build_parser() -> argparse.ArgumentParser:
    """Build the Step-0 ingestion CLI parser."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inputs",
        nargs="+",
        type=Path,
        required=True,
        help="Input directories to scan for FLAC files.",
    )
    parser.add_argument(
        "--canonical-root",
        type=Path,
        required=True,
        help="Canonical library root directory.",
    )
    parser.add_argument(
        "--quarantine-root",
        type=Path,
        required=True,
        help="Root directory for redundant quarantined files.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        required=True,
        help="SQLite database path for Step-0 ingestion.",
    )
    parser.add_argument(
        "--library-tag",
        required=True,
        help="Library tag label applied to this scan.",
    )
    parser.add_argument(
        "--plan",
        type=Path,
        default=Path("plan.json"),
        help="Plan JSON output path (default: plan.json).",
    )
    parser.add_argument(
        "--reacquire-csv",
        type=Path,
        default=Path("reacquire_manifest.csv"),
        help="Reacquire CSV output path (default: reacquire_manifest.csv).",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply the plan to the filesystem (default: dry-run).",
    )
    parser.add_argument(
        "--move",
        action="store_true",
        help="Move files instead of copying when applying the plan.",
    )
    parser.add_argument(
        "--strict-integrity",
        default=True,
        action=argparse.BooleanOptionalAction,
        help="Require flac --test success for canonical selection (default: true).",
    )
    parser.add_argument(
        "--progress",
        action="store_true",
        help="Log progress while scanning inputs.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    return parser


def main() -> None:
    """CLI entry point for the Step-0 ingestion pipeline."""

    parser = build_parser()
    args = parser.parse_args()
    _configure_logging(args.verbose)

    inputs = [Path(utils.normalise_path(str(path))) for path in args.inputs]
    db_path = Path(utils.normalise_path(str(args.db)))
    canonical_root = Path(utils.normalise_path(str(args.canonical_root)))
    quarantine_root = Path(utils.normalise_path(str(args.quarantine_root)))

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
        for index, path in enumerate(_iter_input_files(inputs), start=1):
            if args.progress and index % 25 == 0:
                logger.info("Scanned %s files...", index)
            if not path.is_file():
                continue
            record = _scan_file(path, args.strict_integrity)
            files.append(record)
            hints = extract_identity_hints(record.tags)
            storage_queries.upsert_audio_content(
                connection,
                content_hash=record.content_hash,
                streaminfo_md5=record.streaminfo_md5,
                duration=record.duration,
                sample_rate=record.sample_rate,
                bit_depth=record.bit_depth,
                channels=record.channels,
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
        actions, reacquire_rows = _plan_actions(files, canonical_root, quarantine_root)
        timestamp = datetime.utcnow().isoformat()
        plan_payload = {
            "scan": {
                "inputs": [str(path) for path in inputs],
                "timestamp": timestamp,
                "library_tag": args.library_tag,
                "strict_integrity": args.strict_integrity,
            },
            "actions": actions,
        }
        _write_plan(args.plan, plan_payload)
        _write_reacquire_manifest(args.reacquire_csv, reacquire_rows)

        for action in actions:
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


if __name__ == "__main__":
    main()
