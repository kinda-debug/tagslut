#!/usr/bin/env python3
"""End-to-end processing for a single root folder.

Supported operator entrypoint:
  tagslut intake process-root --root <folder> [--db <db>] [options]

This script remains a thin backend implementation invoked by the canonical CLI.

Pipeline:
  1) scan_with_trust
  2) check_integrity_update_db
  3) hoard_tags (db-add)
  4) normalize_genres (db-add + execute)
  5) tag_normalized_genres (execute)
  6) tagslut index enrich (hoarding + execute) scoped to path
  7) embed_cover_art (from DB) scoped to move log or paths list
  8) promote_replace_merge (execute)

This script runs the pipeline in-order for a provided root folder.
"""
from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tagslut.utils import AUDIO_EXTENSIONS  # noqa: E402
from tagslut.utils.console_ui import ConsoleUI  # noqa: E402
from tagslut.utils.db import DbResolutionError, resolve_cli_env_db_path  # noqa: E402
from tagslut.utils.paths import list_files  # noqa: E402
from tagslut.utils.config import get_config  # noqa: E402
from tagslut.exec.transcoder import transcode_to_mp3_from_snapshot  # noqa: E402
from tagslut.storage.v3 import record_provenance_event, resolve_asset_id_by_path  # noqa: E402
from tagslut.storage.v3.analysis_service import resolve_dj_tag_snapshot_for_path  # noqa: E402

ALLOWED_PHASES = (
    "register",
    "integrity",
    "hash",
    "identify",
    "enrich",
    "art",
    "promote",
    "dj",
)
DEFAULT_PHASES = ("register", "integrity", "identify", "enrich", "art", "promote", "dj")
SCAN_ONLY_PHASES = ("register", "integrity", "hash")
IDENTITY_TABLES = {"track_identity", "asset_link", "library_track_sources"}
ASSET_SCAN_TABLES = {"asset_file", "scan_runs", "scan_queue", "scan_issues", "scan_sessions", "file_scan_runs"}
PHASE_TABLE_TOUCHES: dict[str, set[str]] = {
    "register": set(ASSET_SCAN_TABLES),
    "integrity": {"asset_file"},
    "hash": {"asset_file"},
    "identify": set(IDENTITY_TABLES),
    "enrich": set(IDENTITY_TABLES),
    "art": set(),
    "promote": {"move_plan", "move_execution", "provenance_event"},
    "dj": set(),
}


@dataclass(frozen=True)
class PipelineStep:
    phase: str
    label: str
    command: list[str]


logger = logging.getLogger(__name__)
_UI = ConsoleUI()


def run(cmd: list[str]) -> None:
    detail = " ".join(cmd) if _UI.verbose else " ".join(cmd[:8]) + (" ..." if len(cmd) > 8 else "")
    _UI.stage("Run step", "running", detail=detail)
    subprocess.check_call(cmd)


def parse_phases(*, phases_arg: str | None, scan_only: bool) -> tuple[str, ...]:
    if scan_only:
        return SCAN_ONLY_PHASES
    if not phases_arg:
        return DEFAULT_PHASES

    out: list[str] = []
    seen: set[str] = set()
    for raw in phases_arg.split(","):
        phase = raw.strip().lower()
        if not phase:
            continue
        if phase not in ALLOWED_PHASES:
            allowed = ", ".join(ALLOWED_PHASES)
            raise SystemExit(f"Invalid phase '{phase}'. Allowed phases: {allowed}")
        if phase not in seen:
            out.append(phase)
            seen.add(phase)
    if not out:
        allowed = ", ".join(ALLOWED_PHASES)
        raise SystemExit(f"No valid phases provided. Allowed phases: {allowed}")
    return tuple(out)


def planned_table_touches(phases: tuple[str, ...]) -> set[str]:
    tables: set[str] = set()
    for phase in phases:
        tables.update(PHASE_TABLE_TOUCHES.get(phase, set()))
    return tables


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ? LIMIT 1",
        (table_name,),
    ).fetchone()
    return row is not None


def is_v3_db(db_path: Path) -> bool:
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, "asset_file"):
            return False
        if not _table_exists(conn, "track_identity"):
            return False
        if not _table_exists(conn, "asset_link"):
            return False
        return True
    finally:
        conn.close()


def validate_phase_compatibility(*, db_path: Path, phases: tuple[str, ...]) -> str | None:
    legacy_scan_phases = {"register", "integrity", "hash"}
    requested_legacy = sorted(legacy_scan_phases & set(phases))
    if not requested_legacy:
        return None
    if not is_v3_db(db_path):
        return None
    requested = ",".join(requested_legacy)
    return (
        f"v3 DB guard: phases [{requested}] are not allowed in process-root because they invoke "
        "legacy scan scripts that create/modify v2 tables (including files). "
        "Use process-root for identity/enrich/art/promote phases only."
    )


def build_pipeline_steps(
    *,
    db_path: Path,
    root_path: Path,
    library_path: Path,
    providers: str,
    force: bool,
    no_art: bool,
    art_force: bool,
    trust: int,
    trust_post: int,
    allow_duplicate_hash: bool,
    use_preferred_asset: bool | None,
    require_preferred_asset: bool,
    allow_multiple_per_identity: bool,
    phases: tuple[str, ...],
) -> list[PipelineStep]:
    steps: list[PipelineStep] = []

    if "register" in phases or "hash" in phases:
        scan_cmd = [
            sys.executable,
            "tools/review/scan_with_trust.py",
            "--db",
            str(db_path),
            "--trust",
            str(trust),
            "--trust-post",
            str(trust_post),
        ]
        if "hash" in phases:
            scan_cmd.append("--check-hash")
        scan_cmd.append(str(root_path))
        steps.append(PipelineStep(phase="register", label="scan_with_trust", command=scan_cmd))

    if "integrity" in phases:
        steps.append(
            PipelineStep(
                phase="integrity",
                label="check_integrity_update_db",
                command=[
                    sys.executable,
                    "tools/review/check_integrity_update_db.py",
                    "--db",
                    str(db_path),
                    "--execute",
                    str(root_path),
                ],
            )
        )

    if "identify" in phases:
        steps.extend(
            [
                PipelineStep(
                    phase="identify",
                    label="hoard_tags",
                    command=[
                        sys.executable,
                        "tools/review/hoard_tags.py",
                        "--db",
                        str(db_path),
                        "--db-add",
                        str(root_path),
                    ],
                ),
                PipelineStep(
                    phase="identify",
                    label="normalize_genres",
                    command=[
                        sys.executable,
                        "tools/review/normalize_genres.py",
                        "--db",
                        str(db_path),
                        "--execute",
                        str(root_path),
                    ],
                ),
                PipelineStep(
                    phase="identify",
                    label="tag_normalized_genres",
                    command=[
                        sys.executable,
                        "tools/review/tag_normalized_genres.py",
                        "--execute",
                        str(root_path),
                    ],
                ),
            ]
        )

    if "enrich" in phases:
        enrich_cmd = [
            sys.executable,
            "-m",
            "tagslut",
            "index",
            "enrich",
            "--db",
            str(db_path),
            "--hoarding",
            "--providers",
            providers,
            "--execute",
            "--path",
            f"{root_path}%",
        ]
        if force:
            enrich_cmd.append("--force")
        steps.append(PipelineStep(phase="enrich", label="index_enrich", command=enrich_cmd))

    if "art" in phases and not no_art:
        embed_cmd = [
            sys.executable,
            "tools/review/embed_cover_art.py",
            "--db",
            str(db_path),
            "--root",
            str(root_path),
            "--execute",
        ]
        if art_force:
            embed_cmd.append("--force")
        steps.append(PipelineStep(phase="art", label="embed_cover_art", command=embed_cmd))

    if "promote" in phases:
        promote_cmd = [
            sys.executable,
            "tools/review/promote_replace_merge.py",
            "--db",
            str(db_path),
            "--dest",
            str(library_path),
            "--execute",
            str(root_path),
        ]
        if allow_duplicate_hash:
            promote_cmd.append("--allow-duplicate-hash")
        if use_preferred_asset is True:
            promote_cmd.append("--use-preferred-asset")
        elif use_preferred_asset is False:
            promote_cmd.append("--no-use-preferred-asset")
        if require_preferred_asset:
            promote_cmd.append("--require-preferred-asset")
        if allow_multiple_per_identity:
            promote_cmd.append("--allow-multiple-per-identity")
        steps.append(PipelineStep(phase="promote", label="promote_replace_merge", command=promote_cmd))

    # Reserved phase for future DJ pipeline hooks.
    if "dj" in phases:
        pass

    return steps


def run_dj_phase(
    *,
    db_path: Path,
    root_path: Path,
    dry_run: bool = False,
    dj_pool_dir: Path | None = None,
) -> None:
    config = get_config()
    pool_dir = (dj_pool_dir or Path(config.get("dj_pool_dir", "~/Music/DJPool"))).expanduser().resolve()
    flac_paths = sorted(
        path for path in list_files(root_path, set(AUDIO_EXTENSIONS))
        if path.is_file() and path.suffix.lower() == ".flac"
    )
    if not flac_paths:
        logger.info("DJ phase: no FLAC files found under %s", root_path)
        return

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    essentia_missing_warned = False
    try:
        for flac_path in flac_paths:
            try:
                snapshot = resolve_dj_tag_snapshot_for_path(
                    conn,
                    flac_path,
                    run_essentia=True,
                    dry_run=dry_run,
                )
            except FileNotFoundError:
                if not essentia_missing_warned:
                    logger.warning(
                        "Essentia not found — DJ tag enrichment skipped. "
                        "Install with: brew install essentia (macOS) or see docs."
                    )
                    essentia_missing_warned = True
                snapshot = resolve_dj_tag_snapshot_for_path(
                    conn,
                    flac_path,
                    run_essentia=False,
                    dry_run=True,
                )

            if snapshot is not None:
                logger.info(
                    "DJ snapshot: %s → bpm=%s key=%s energy=%s",
                    flac_path.name,
                    snapshot.bpm,
                    snapshot.musical_key,
                    snapshot.energy_1_10,
                )

            if dry_run:
                logger.info("DJ dry-run: would transcode %s into %s", flac_path, pool_dir)
                continue

            if snapshot is None:
                logger.warning("DJ snapshot missing for %s; skipping transcode", flac_path)
                continue

            mp3_path = transcode_to_mp3_from_snapshot(flac_path, pool_dir, snapshot)
            resolved_flac_path = str(flac_path.expanduser().resolve())
            resolved_mp3_path = str(mp3_path.expanduser().resolve())
            record_provenance_event(
                conn,
                event_type="dj_export",
                status="success",
                asset_id=resolve_asset_id_by_path(conn, resolved_flac_path),
                identity_id=snapshot.identity_id,
                source_path=resolved_flac_path,
                dest_path=resolved_mp3_path,
                details={
                    "tag_snapshot": snapshot.as_dict(),
                    "bpm_source": snapshot.bpm_source,
                    "key_source": snapshot.key_source,
                    "energy_source": snapshot.energy_source,
                    "format": "mp3",
                    "bitrate": 320,
                    "tool_version": "process_root",
                    "partial_metadata": any(
                        value is None
                        for value in (snapshot.bpm, snapshot.musical_key, snapshot.energy_1_10)
                    ),
                },
            )
            if _table_exists(conn, "files"):
                conn.execute(
                    "UPDATE files SET dj_pool_path = ? WHERE path = ?",
                    (resolved_mp3_path, resolved_flac_path),
                )
        if not dry_run:
            conn.commit()
    finally:
        conn.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="Processing pipeline for a root folder")
    ap.add_argument("--db", help="DB path")
    ap.add_argument("--root", help="Root folder to process")
    ap.add_argument("--library", help="Library destination")
    ap.add_argument("--providers", default="beatport,deezer,apple_music,itunes")
    ap.add_argument("--force", action="store_true", help="Force re-enrichment")
    ap.add_argument("--no-art", action="store_true", help="Skip cover art embedding")
    ap.add_argument("--art-force", action="store_true", help="Force replace embedded art")
    ap.add_argument("--trust", type=int, default=3, help="Pre-scan trust (0-3). Default: 3")
    ap.add_argument("--trust-post", type=int, default=3, help="Post-scan trust (0-3). Default: 3")
    ap.add_argument(
        "--phases",
        help=(
            "Comma-separated phases to run. Allowed: "
            + ", ".join(ALLOWED_PHASES)
            + ". Default is full pipeline."
        ),
    )
    ap.add_argument(
        "--scan-only",
        action="store_true",
        help="Shortcut for --phases=register,integrity,hash",
    )
    ap.add_argument(
        "--allow-duplicate-hash",
        action="store_true",
        help="Allow moving files even if identical hash exists in library",
    )
    ap.add_argument(
        "--use-preferred-asset",
        dest="use_preferred_asset",
        action="store_true",
        default=None,
        help="Use preferred_asset during promote phase",
    )
    ap.add_argument(
        "--no-use-preferred-asset",
        dest="use_preferred_asset",
        action="store_false",
        help="Disable preferred_asset during promote phase",
    )
    ap.add_argument(
        "--require-preferred-asset",
        action="store_true",
        help="Skip identities without preferred asset under root during promote phase",
    )
    ap.add_argument(
        "--allow-multiple-per-identity",
        action="store_true",
        help="Allow promoting multiple assets per identity during promote phase",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Run DJ phase without writing FLAC tags, MP3s, or dj_pool_path updates",
    )
    ap.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose process-root output",
    )
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    default_library = os.environ.get("LIBRARY_ROOT", "./library")

    try:
        db_resolution = resolve_cli_env_db_path(args.db, purpose="write", source_label="--db")
    except DbResolutionError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    db = str(db_resolution.path)
    root = args.root or ""
    library = args.library or default_library

    if not root:
        raise SystemExit("root is required (pass --root)")

    db_path = Path(db)
    root_path = Path(root)
    _UI.verbose = bool(args.verbose)
    if root_path.exists() and not list(list_files(root_path, set(AUDIO_EXTENSIONS))):
        _UI.warn(f"no audio files found under {root_path}")
    library_path = Path(library)

    _UI.begin_command("Process Root", target=str(root_path), mode="dry-run" if args.dry_run else "execute")
    _UI.summary(
        "Context",
        [
            ("Resolved DB path", db),
            ("Library", library_path),
            ("Providers", args.providers),
        ],
    )

    if not root_path.exists():
        raise SystemExit(f"Root not found: {root_path}")
    if not library_path.exists():
        _UI.warn(f"library path does not exist yet: {library_path}")

    phases = parse_phases(phases_arg=args.phases, scan_only=bool(args.scan_only))
    compatibility_error = validate_phase_compatibility(db_path=db_path, phases=phases)
    if compatibility_error:
        raise SystemExit(compatibility_error)
    if args.scan_only:
        forbidden = planned_table_touches(phases) & IDENTITY_TABLES
        if forbidden:
            joined = ", ".join(sorted(forbidden))
            raise SystemExit(f"scan-only safety violation: identity tables would be touched: {joined}")

    steps = build_pipeline_steps(
        db_path=db_path,
        root_path=root_path,
        library_path=library_path,
        providers=args.providers,
        force=bool(args.force),
        no_art=bool(args.no_art),
        art_force=bool(args.art_force),
        trust=int(args.trust),
        trust_post=int(args.trust_post),
        allow_duplicate_hash=bool(args.allow_duplicate_hash),
        use_preferred_asset=args.use_preferred_asset,
        require_preferred_asset=bool(args.require_preferred_asset),
        allow_multiple_per_identity=bool(args.allow_multiple_per_identity),
        phases=phases,
    )

    _UI.note("Phases: " + ",".join(phases))
    if args.scan_only:
        _UI.note("Mode: scan-only")
    for step in steps:
        run(step.command)

    if "dj" in phases:
        run_dj_phase(
            db_path=db_path,
            root_path=root_path,
            dry_run=bool(args.dry_run),
        )


if __name__ == "__main__":
    main()
