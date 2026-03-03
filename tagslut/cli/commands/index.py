from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

import click

from tagslut.cli.commands._index_helpers import (
    duration_check_version,
    duration_status,
    duration_thresholds_from_config,
    extract_tag_value,
    lookup_duration_ref_ms,
    measure_duration_ms,
    prompt_duplicate_action,
    run_audit_duration,
)
from tagslut.cli.commands._enrich_helpers import (
    _local_file_info_from_path,
    _print_enrichment_result,
)
from tagslut.storage.schema import init_db


def register_index_group(cli: click.Group) -> None:
    @cli.group()
    def index():  # type: ignore  # TODO: mypy-strict
        """Canonical indexing and metadata registration commands."""

    @index.command("register")
    @click.argument('path', type=click.Path(exists=True))
    @click.option('--source', required=True, help='Download source (bpdl, tidal, qobuz, legacy, etc.)')
    @click.option('--db', type=click.Path(), help='Database path (auto-detect from env if not provided)')
    @click.option('--execute', is_flag=True, help='Actually register files (default: dry-run)')
    @click.option(
        '--full-hash',
        is_flag=True,
        help='Compute full-file SHA256 for every file (slow; default uses FLAC STREAMINFO MD5 when available)',
    )
    @click.option('--limit', type=int, help='Only process first N files (useful for smoke tests)')
    @click.option('--dj-only', is_flag=True, help='Mark all registered files as DJ material')
    @click.option('--check-duration', is_flag=True, help='Measure duration and compute duration status')
    @click.option('--prompt/--no-prompt', default=True, help='Prompt when similar files exist')
    @click.option('-v', '--verbose', is_flag=True, help='Verbose output')
    def index_register(  # type: ignore  # TODO: mypy-strict
        path,
        source,
        db,
        execute,
        full_hash,
        limit,
        dj_only,
        check_duration,
        prompt,
        verbose,
    ):
        """
        Register files in inventory.

        Scans directory for FLAC files, computes checksums, and registers
        them in the database with source tracking. Used after downloading
        from Beatport, Tidal, Qobuz, etc.

        \b
        Examples:
            # Dry-run: see what would be registered
            tagslut index register ~/Downloads/bpdl --source bpdl

            # Actually register
            tagslut index register ~/Downloads/bpdl --source bpdl --execute

            # Verbose output
            tagslut index register ~/Downloads/bpdl --source bpdl --execute -v

            # Register with duration checks for DJ material
            tagslut index register ~/Downloads/bpdl --source bpdl --dj-only --check-duration --execute
        """
        import itertools
        import json
        from datetime import datetime, timezone

        from tagslut.core.hashing import calculate_file_hash
        from tagslut.core.metadata import extract_metadata
        from tagslut.storage.queries import get_file
        from tagslut.storage.schema import get_connection, init_db
        from tagslut.storage.v3 import dual_write_enabled, dual_write_registered_file
        from tagslut.utils.audit_log import append_jsonl, resolve_log_path
        from tagslut.utils.config import get_config
        from tagslut.utils.db import resolve_db_path
        from tagslut.utils.paths import list_files

        resolution = resolve_db_path(
            db,
            purpose="write" if execute else "read",
            allow_create=bool(execute),
        )
        db_path = resolution.path

        path_obj = Path(path).expanduser().resolve()
        if not path_obj.exists():
            raise click.ClickException(f"Path not found: {path}")

        if path_obj.is_file():
            if path_obj.suffix.lower() != ".flac":
                raise click.ClickException(
                    f"File is not FLAC: {path_obj} (expected .flac)"
                )
            flac_iter = [path_obj]
        else:
            flac_iter = list_files(path_obj, {".flac"})
        if limit:
            flac_iter = itertools.islice(flac_iter, int(limit))

        click.echo(f"Scanning: {path_obj}")
        click.echo(f"Source: {source}")
        click.echo(f"Hashing: {'full sha256' if full_hash else 'streaminfo md5 (sha256 fallback)'}")
        if limit:
            click.echo(f"Limit: {limit}")
        if not execute:
            click.echo("[DRY-RUN MODE - use --execute to save]")
        click.echo("")

        config = get_config()
        log_dir = None
        if config:
            configured_dir = config.get("mgmt.audit_log_dir")
            if configured_dir:
                log_dir = Path(configured_dir).expanduser()

        conn = get_connection(str(db_path), purpose="write" if execute else "read", allow_create=bool(execute))
        if execute:
            init_db(conn)
        try:
            dual_write_v3 = bool(execute and dual_write_enabled())
            if dual_write_v3:
                click.echo("V3 dual-write: enabled")
            registered = 0
            skipped = 0
            errors = 0
            now_iso = datetime.now(timezone.utc).isoformat()
            ok_max_ms, warn_max_ms = duration_thresholds_from_config()
            duration_version = duration_check_version(ok_max_ms, warn_max_ms)

            total = 0
            for i, file_path in enumerate(flac_iter, start=1):
                total = i
                try:
                    mgmt_status_override = None

                    existing = get_file(conn, file_path)
                    if existing:
                        if verbose:
                            click.echo(f"  [{i}] SKIP (already registered) {file_path.name}")
                        skipped += 1
                        continue

                    audio = extract_metadata(
                        file_path,
                        scan_integrity=False,
                        scan_hash=bool(full_hash),
                        library="default",
                        zone_manager=None,
                    )

                    checksum = audio.checksum
                    sha256 = audio.sha256
                    streaminfo_md5 = audio.streaminfo_md5
                    if (not streaminfo_md5) and (not sha256):
                        sha256 = calculate_file_hash(file_path)
                        checksum = sha256

                    zone_value = audio.zone.value if audio.zone else "staging"
                    metadata_json = json.dumps(audio.metadata or {}, ensure_ascii=False, sort_keys=True)

                    if sha256:
                        existing_matches = conn.execute(
                            "SELECT path, download_source FROM files WHERE sha256 = ? OR checksum = ?",
                            (sha256, sha256),
                        ).fetchall()
                        content_id_for_log = sha256
                        content_id_type = "sha256"
                    elif streaminfo_md5:
                        stream_checksum = f"streaminfo:{streaminfo_md5}"
                        existing_matches = conn.execute(
                            "SELECT path, download_source FROM files WHERE streaminfo_md5 = ? OR checksum = ?",
                            (streaminfo_md5, stream_checksum),
                        ).fetchall()
                        content_id_for_log = streaminfo_md5
                        content_id_type = "streaminfo_md5"
                    else:
                        existing_matches = []
                        content_id_for_log = None
                        content_id_type = "none"

                    if existing_matches:
                        action = prompt_duplicate_action(
                            file_path=file_path,
                            matches=existing_matches,
                            prompt_enabled=prompt,
                        )
                        append_jsonl(
                            resolve_log_path("mgmt_decisions", default_dir=log_dir),
                            {
                                "event": "duplicate_decision",
                                "timestamp": now_iso,
                                "path": str(file_path),
                                "content_id": content_id_for_log,
                                "content_id_type": content_id_type,
                                "source": source,
                                "action": action,
                                "matches": [
                                    {"path": match[0], "source": match[1]}
                                    for match in existing_matches[:10]
                                ],
                            },
                        )
                        if action == "quit":
                            raise click.ClickException("User aborted")
                        if action == "skip":
                            if verbose:
                                click.echo(f"  [{i}] SKIP (duplicate) {file_path.name}")
                            skipped += 1
                            continue
                        if action == "replace":
                            if verbose:
                                click.echo(f"  [{i}] REPLACE (marked) {file_path.name}")
                            mgmt_status_override = "needs_review"

                    duration_measured_ms = None
                    duration_ref_ms = None
                    duration_ref_source = None
                    duration_ref_track_id = None
                    duration_delta_ms = None
                    duration_status_value = None
                    duration_measured_at = None
                    duration_ref_updated_at = None

                    if check_duration:
                        duration_measured_ms = measure_duration_ms(file_path)
                        duration_measured_at = now_iso

                        beatport_id = extract_tag_value(
                            audio.metadata,
                            ["BEATPORT_TRACK_ID", "BP_TRACK_ID", "beatport_track_id"],
                        )
                        isrc = extract_tag_value(audio.metadata, ["ISRC", "TSRC"])

                        duration_ref_ms, duration_ref_source, duration_ref_track_id = lookup_duration_ref_ms(
                            conn, beatport_id, isrc
                        )
                        if duration_measured_ms is None:
                            # Treat unreadable/unmeasurable files as failed safety gate.
                            duration_status_value = "fail"
                            duration_delta_ms = None
                        elif duration_ref_ms is None:
                            # Global fallback: seed reference from local measured duration
                            # so healthy files do not remain perpetually "unknown".
                            duration_ref_ms = duration_measured_ms
                            duration_ref_source = "measured_fallback"
                            duration_ref_track_id = (
                                beatport_id
                                or isrc
                                or f"path:{file_path}"
                            )
                            duration_ref_updated_at = now_iso
                            duration_delta_ms = 0
                            duration_status_value = "ok"
                        else:
                            duration_ref_updated_at = now_iso
                            duration_delta_ms = duration_measured_ms - duration_ref_ms
                            duration_status_value = duration_status(duration_delta_ms, ok_max_ms, warn_max_ms)

                        log_payload = {
                            "event": "duration_check",
                            "timestamp": now_iso,
                            "path": str(file_path),
                            "source": source,
                            "track_id": (
                                f"beatport:{beatport_id}"
                                if beatport_id
                                else (f"isrc:{isrc}" if isrc else None)
                            ),
                            "is_dj_material": bool(dj_only),
                            "duration_ref_ms": duration_ref_ms,
                            "duration_measured_ms": duration_measured_ms,
                            "duration_delta_ms": duration_delta_ms,
                            "duration_status": duration_status_value,
                            "thresholds_ms": {"ok": ok_max_ms, "warn": warn_max_ms},
                            "check_version": duration_version,
                        }
                        append_jsonl(resolve_log_path("mgmt_duration"), log_payload)

                        if dj_only and duration_status_value in ("warn", "fail", "unknown"):
                            anomaly_payload = {
                                "event": "duration_anomaly",
                                "timestamp": now_iso,
                                "path": str(file_path),
                                "track_id": log_payload["track_id"],
                                "is_dj_material": True,
                                "duration_status": duration_status_value,
                                "duration_ref_ms": duration_ref_ms,
                                "duration_measured_ms": duration_measured_ms,
                                "duration_delta_ms": duration_delta_ms,
                                "action": "blocked_promotion",
                            }
                            append_jsonl(resolve_log_path("mgmt_duration"), anomaly_payload)
                            mgmt_status_override = mgmt_status_override or "needs_review"

                    if execute:
                        flac_ok_value = None if audio.flac_ok is None else int(bool(audio.flac_ok))
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO files (
                                path, checksum, streaminfo_md5, sha256, library, zone, mtime, size,
                                duration, bit_depth, sample_rate, bitrate, metadata_json, flac_ok, integrity_state,
                                download_source, download_date, original_path, mgmt_status,
                                is_dj_material, duration_ref_ms, duration_ref_source, duration_ref_track_id,
                                duration_ref_updated_at, duration_measured_ms, duration_measured_at,
                                duration_delta_ms, duration_status, duration_check_version
                            ) VALUES (
                                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                                ?, ?, ?, ?, ?, ?, ?, ?, ?
                            )
                            """,
                            (
                                str(file_path),
                                checksum,
                                streaminfo_md5,
                                sha256,
                                "default",
                                zone_value,
                                audio.mtime,
                                audio.size,
                                float(audio.duration or 0.0),
                                int(audio.bit_depth or 0),
                                int(audio.sample_rate or 0),
                                int(audio.bitrate or 0),
                                metadata_json,
                                flac_ok_value,
                                audio.integrity_state,
                                source,
                                now_iso,
                                str(file_path),
                                mgmt_status_override
                                or (
                                    "needs_review"
                                    if dj_only and duration_status_value in ("warn", "fail", "unknown")
                                    else "new"
                                ),
                                1 if dj_only else 0,
                                duration_ref_ms,
                                duration_ref_source,
                                duration_ref_track_id,
                                duration_ref_updated_at,
                                duration_measured_ms,
                                duration_measured_at,
                                duration_delta_ms,
                                duration_status_value,
                                duration_version if check_duration else None,
                            ),
                        )
                        if dual_write_v3:
                            dual_write_registered_file(
                                conn,
                                path=str(file_path),
                                content_sha256=sha256,
                                streaminfo_md5=streaminfo_md5,
                                checksum=checksum,
                                size_bytes=audio.size,
                                mtime=audio.mtime,
                                duration_s=float(audio.duration or 0.0),
                                sample_rate=int(audio.sample_rate or 0),
                                bit_depth=int(audio.bit_depth or 0),
                                bitrate=int(audio.bitrate or 0),
                                library="default",
                                zone=zone_value,
                                download_source=source,
                                download_date=now_iso,
                                mgmt_status=mgmt_status_override
                                or (
                                    "needs_review"
                                    if dj_only and duration_status_value in ("warn", "fail", "unknown")
                                    else "new"
                                ),
                                metadata=audio.metadata or {},
                                duration_ref_ms=duration_ref_ms,
                                duration_ref_source=duration_ref_source,
                                event_time=now_iso,
                            )

                    if verbose or i % 50 == 0:
                        click.echo(f"  [{i}] {file_path.name}")

                    registered += 1

                except Exception as e:
                    errors += 1
                    click.echo(f"  ERROR: {file_path.name}: {e}")

            if total == 0:
                click.echo(f"No FLAC files found in {path}")
                return

            if execute:
                conn.commit()

        finally:
            conn.close()

        click.echo("")
        click.echo(f"{'='*50}")
        click.echo("RESULTS")
        click.echo(f"{'='*50}")
        click.echo(f"  Total:       {total:>6}")
        click.echo(f"  Registered:  {registered:>6}  {'✓' if registered > 0 else '(none)'}")
        click.echo(f"  Skipped:     {skipped:>6}  (already registered)")
        click.echo(f"  Errors:      {errors:>6}  {'⚠' if errors > 0 else ''}")

    @index.command("check")
    @click.argument('path', type=click.Path(exists=True), required=False)
    @click.option('--source', help='Filter by download source')
    @click.option('--db', type=click.Path(), help='Database path (auto-detect from env if not provided)')
    @click.option('--strict', is_flag=True, help='Strict mode: any match is a conflict')
    @click.option('--prompt/--no-prompt', default=True, help='Prompt when similar files exist')
    @click.option('-v', '--verbose', is_flag=True, help='Verbose output')
    def index_check(path, source, db, strict, prompt, verbose):  # type: ignore  # TODO: mypy-strict
        """
        Check for duplicate files before downloading.

        Scans a directory (or stdin) and checks if any files already
        exist in the database. Useful to avoid re-downloading known files.

        If no path is provided, reads file paths from stdin (one per line).

        \b
        Examples:
            # Check a directory
            tagslut index check ~/Downloads/bpdl --source bpdl

            # Check with pipe
            find ~/incoming -name "*.flac" | tagslut index check --source tidal

            # Strict mode: reject if SAME file exists anywhere
            tagslut index check ~/Downloads --strict
        """
        import sys
        from datetime import datetime, timezone

        from tagslut.core.hashing import calculate_file_hash
        from tagslut.storage.schema import get_connection
        from tagslut.utils.audit_log import append_jsonl, resolve_log_path
        from tagslut.utils.config import get_config
        from tagslut.utils.db import resolve_db_path

        resolution = resolve_db_path(db, purpose="read")
        db_path = resolution.path

        file_paths = []
        if path:
            path_obj = Path(path).expanduser().resolve()
            if path_obj.is_file():
                file_paths = [path_obj]
            elif path_obj.is_dir():
                file_paths = list(path_obj.rglob("*.flac"))
            else:
                raise click.ClickException(f"Path not found: {path}")
        else:
            for line in sys.stdin:
                file_path = Path(line.strip()).expanduser().resolve()
                if file_path.exists() and file_path.suffix.lower() == ".flac":
                    file_paths.append(file_path)

        if not file_paths:
            click.echo("No FLAC files provided")
            return

        click.echo(f"Checking {len(file_paths)} files against database...")
        if source:
            click.echo(f"Filter: source={source}")
        if strict:
            click.echo("Mode: STRICT (any match is a conflict)")
        click.echo("")

        config = get_config()
        log_dir = None
        if config:
            configured_dir = config.get("mgmt.audit_log_dir")
            if configured_dir:
                log_dir = Path(configured_dir).expanduser()

        conn = get_connection(str(db_path), purpose="read")
        try:
            duplicates = []
            unique = []
            allowed = []
            replacements = []
            errors = 0

            for i, file_path in enumerate(file_paths, start=1):
                try:
                    sha256 = calculate_file_hash(file_path)

                    if strict:
                        cursor = conn.execute(
                            "SELECT path, download_source FROM files WHERE sha256 = ?",
                            (sha256,)
                        )
                    else:
                        if source:
                            cursor = conn.execute(
                                "SELECT path, download_source FROM files WHERE sha256 = ? AND download_source = ?",
                                (sha256, source)
                            )
                        else:
                            cursor = conn.execute(
                                "SELECT path, download_source FROM files WHERE sha256 = ?",
                                (sha256,)
                            )

                    existing = cursor.fetchall()

                    if existing:
                        action = prompt_duplicate_action(
                            file_path=file_path,
                            matches=existing,
                            prompt_enabled=prompt,
                        )
                        append_jsonl(
                            resolve_log_path("mgmt_checks", default_dir=log_dir),
                            {
                                "event": "duplicate_check",
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "path": str(file_path),
                                "sha256": sha256,
                                "source_filter": source,
                                "strict": bool(strict),
                                "action": action,
                                "matches": [
                                    {"path": match[0], "source": match[1]}
                                    for match in existing[:10]
                                ],
                            },
                        )
                        if action == "quit":
                            raise click.ClickException("User aborted")
                        if action == "download":
                            allowed.append(file_path)
                            if verbose:
                                click.echo(f"  ALLOW: {file_path.name}")
                        elif action == "replace":
                            replacements.append((file_path, existing))
                            if verbose:
                                click.echo(f"  REPLACE: {file_path.name}")
                        else:
                            duplicates.append((file_path, existing))
                            if verbose:
                                click.echo(f"  CONFLICT: {file_path.name}")
                                for match in existing:
                                    src = match[1] if match[1] else "unknown"
                                    click.echo(f"    → {src}: {Path(match[0]).name}")
                    else:
                        unique.append(file_path)
                        if verbose:
                            click.echo(f"  OK: {file_path.name}")

                    if i % 50 == 0 or i == len(file_paths):
                        click.echo(f"  [{i}/{len(file_paths)}]...")

                except Exception as e:
                    errors += 1
                    click.echo(f"  ERROR: {file_path.name}: {e}")

        finally:
            conn.close()

        click.echo("")
        click.echo(f"{'='*50}")
        click.echo("RESULTS")
        click.echo(f"{'='*50}")
        click.echo(f"  Total:        {len(file_paths):>6}")
        click.echo(f"  Unique:       {len(unique):>6}  ✓ (safe to download)")
        click.echo(f"  Allowed:      {len(allowed):>6}  ✓ (download anyway)")
        click.echo(f"  Replace:      {len(replacements):>6}  ⚠ (mark for replace)")
        click.echo(f"  Duplicates:   {len(duplicates):>6}  ⚠ (already exists)")
        click.echo(f"  Errors:       {errors:>6}  {'⚠' if errors > 0 else ''}")

        if duplicates:
            click.echo("")
            click.echo("Conflicts (files that already exist):")
            for file_path, matches in duplicates[:10]:
                click.echo(f"  • {file_path.name}")
                for match in matches[:2]:
                    src = match[1] if match[1] else "unknown"
                    click.echo(f"    → {src}: {Path(match[0]).name}")
                if len(matches) > 2:
                    click.echo(f"    ... and {len(matches) - 2} more")
            if len(duplicates) > 10:
                click.echo(f"  ... and {len(duplicates) - 10} more conflicts")

        if replacements:
            click.echo("")
            click.echo("Replace candidates:")
            for file_path, matches in replacements[:10]:
                click.echo(f"  • {file_path.name}")
                for match in matches[:2]:
                    src = match[1] if match[1] else "unknown"
                    click.echo(f"    → {src}: {Path(match[0]).name}")
                if len(matches) > 2:
                    click.echo(f"    ... and {len(matches) - 2} more")
            if len(replacements) > 10:
                click.echo(f"  ... and {len(replacements) - 10} more replacements")

    @index.command("duration-check")
    @click.argument("path", type=click.Path(exists=True))
    @click.option("--db", type=click.Path(), help="Database path (auto-detect from env if not provided)")
    @click.option("--execute", is_flag=True, help="Write duration updates to the database")
    @click.option("--dj-only", is_flag=True, help="Mark checked files as DJ material")
    @click.option("--source", help="Override source label for logging")
    @click.option("-v", "--verbose", is_flag=True, help="Verbose output")
    def index_duration_check(path, db, execute, dj_only, source, verbose):  # type: ignore  # TODO: mypy-strict
        """
        Measure durations and update duration status in the DB.
        """
        from datetime import datetime, timezone

        from mutagen.flac import FLAC

        from tagslut.storage.schema import get_connection, init_db
        from tagslut.utils.audit_log import append_jsonl, resolve_log_path
        from tagslut.utils.db import resolve_db_path

        resolution = resolve_db_path(
            db,
            purpose="write" if execute else "read",
            allow_create=bool(execute),
        )
        db_path = resolution.path

        path_obj = Path(path).expanduser().resolve()
        if not path_obj.exists():
            raise click.ClickException(f"Path not found: {path}")

        if path_obj.is_file():
            file_paths = [path_obj]
        else:
            file_paths = list(path_obj.rglob("*.flac"))

        if not file_paths:
            click.echo("No FLAC files found to check")
            return

        ok_max_ms, warn_max_ms = duration_thresholds_from_config()
        duration_version = duration_check_version(ok_max_ms, warn_max_ms)
        now_iso = datetime.now(timezone.utc).isoformat()

        conn = get_connection(str(db_path), purpose="write" if execute else "read", allow_create=bool(execute))
        if execute:
            init_db(conn)
        try:
            updated = 0
            missing = 0
            errors = 0

            for i, file_path in enumerate(file_paths, start=1):
                try:
                    row = conn.execute(
                        "SELECT beatport_id, canonical_isrc, canonical_duration FROM files WHERE path = ?",
                        (str(file_path),),
                    ).fetchone()
                    if not row:
                        missing += 1
                        if verbose:
                            click.echo(f"  [{i}/{len(file_paths)}] SKIP (not in DB) {file_path.name}")
                        continue
                    db_beatport_id = (row[0] or "").strip() if row[0] is not None else None
                    db_isrc = (row[1] or "").strip() if row[1] is not None else None
                    db_canonical_duration = row[2]

                    audio = None
                    try:
                        audio = FLAC(file_path)
                    except Exception:
                        audio = None

                    tags = audio.tags or {} if audio is not None else {}  # type: ignore  # TODO: mypy-strict
                    beatport_id = extract_tag_value(  # type: ignore  # TODO: mypy-strict
                        tags,
                        ["BEATPORT_TRACK_ID", "BP_TRACK_ID", "beatport_track_id"],
                    )
                    isrc = extract_tag_value(tags, ["ISRC", "TSRC"])  # type: ignore  # TODO: mypy-strict
                    if not beatport_id and db_beatport_id:
                        beatport_id = db_beatport_id
                    if not isrc and db_isrc:
                        isrc = db_isrc

                    duration_ref_ms, duration_ref_source, duration_ref_track_id = lookup_duration_ref_ms(
                        conn, beatport_id, isrc
                    )
                    if duration_ref_ms is None and db_canonical_duration is not None:
                        try:
                            duration_ref_ms = int(round(float(db_canonical_duration) * 1000))
                            duration_ref_source = "canonical_duration:db"
                            if duration_ref_track_id is None:
                                duration_ref_track_id = beatport_id or isrc
                        except Exception:
                            duration_ref_ms = None
                    duration_measured_ms = measure_duration_ms(file_path)
                    if duration_measured_ms is None:
                        duration_delta_ms = None
                        duration_status_value = "fail"
                    elif duration_ref_ms is None:
                        duration_ref_ms = duration_measured_ms
                        duration_ref_source = "measured_fallback"
                        duration_ref_track_id = (
                            beatport_id
                            or isrc
                            or f"path:{file_path}"
                        )
                        duration_delta_ms = 0
                        duration_status_value = "ok"
                    else:
                        duration_delta_ms = duration_measured_ms - duration_ref_ms
                        duration_status_value = duration_status(duration_delta_ms, ok_max_ms, warn_max_ms)

                    log_payload = {
                        "event": "duration_check",
                        "timestamp": now_iso,
                        "path": str(file_path),
                        "source": source,
                        "track_id": f"beatport:{beatport_id}" if beatport_id else (f"isrc:{isrc}" if isrc else None),
                        "is_dj_material": bool(dj_only),
                        "duration_ref_ms": duration_ref_ms,
                        "duration_measured_ms": duration_measured_ms,
                        "duration_delta_ms": duration_delta_ms,
                        "duration_status": duration_status_value,
                        "thresholds_ms": {"ok": ok_max_ms, "warn": warn_max_ms},
                        "check_version": duration_version,
                    }
                    append_jsonl(resolve_log_path("mgmt_duration"), log_payload)

                    if dj_only and duration_status_value in ("warn", "fail", "unknown"):
                        anomaly_payload = {
                            "event": "duration_anomaly",
                            "timestamp": now_iso,
                            "path": str(file_path),
                            "track_id": log_payload["track_id"],
                            "is_dj_material": True,
                            "duration_status": duration_status_value,
                            "duration_ref_ms": duration_ref_ms,
                            "duration_measured_ms": duration_measured_ms,
                            "duration_delta_ms": duration_delta_ms,
                            "action": "blocked_promotion",
                        }
                        append_jsonl(resolve_log_path("mgmt_duration"), anomaly_payload)

                    if execute:
                        conn.execute(
                            """
                            UPDATE files SET
                                is_dj_material = CASE WHEN ? THEN 1 ELSE is_dj_material END,
                                duration_ref_ms = ?,
                                duration_ref_source = ?,
                                duration_ref_track_id = ?,
                                duration_ref_updated_at = ?,
                                duration_measured_ms = ?,
                                duration_measured_at = ?,
                                duration_delta_ms = ?,
                                duration_status = ?,
                                duration_check_version = ?,
                                mgmt_status = CASE
                                    WHEN ? AND ? IN ('warn','fail','unknown') THEN 'needs_review'
                                    ELSE mgmt_status
                                END
                            WHERE path = ?
                            """,
                            (
                                1 if dj_only else 0,
                                duration_ref_ms,
                                duration_ref_source,
                                duration_ref_track_id,
                                now_iso if duration_ref_ms is not None else None,
                                duration_measured_ms,
                                now_iso if duration_measured_ms is not None else None,
                                duration_delta_ms,
                                duration_status_value,
                                duration_version,
                                1 if dj_only else 0,
                                duration_status_value,
                                str(file_path),
                            ),
                        )

                    if verbose or i % 50 == 0 or i == len(file_paths):
                        click.echo(f"  [{i}/{len(file_paths)}] {file_path.name}")
                    updated += 1

                except Exception as e:
                    errors += 1
                    click.echo(f"  ERROR: {file_path.name}: {e}")

            if execute:
                conn.commit()

        finally:
            conn.close()

        click.echo("")
        click.echo(f"{'='*50}")
        click.echo("DURATION CHECK RESULTS")
        click.echo(f"{'='*50}")
        click.echo(f"  Total:        {len(file_paths):>6}")
        click.echo(f"  Updated:      {updated:>6}")
        click.echo(f"  Missing DB:   {missing:>6}")
        click.echo(f"  Errors:       {errors:>6}  {'⚠' if errors > 0 else ''}")

    @index.command("duration-audit")
    @click.option("--db", type=click.Path(), help="Database path (auto-detect from env if not provided)")
    @click.option("--dj-only", is_flag=True, help="Only DJ material")
    @click.option("--status", "status_filter", help="Comma-separated statuses (warn,fail,unknown)")
    @click.option("--source", help="Filter by download source")
    @click.option("--since", help="Filter by download_date >= YYYY-MM-DD")
    @click.option("--inactive-exclude", is_flag=True, help="Exclude mgmt_status=inactive")
    def index_duration_audit(  # type: ignore  # TODO: mypy-strict
        db,
        dj_only,
        status_filter,
        source,
        since,
        inactive_exclude,
    ):
        """
        Report files with duration_status != ok (or filtered statuses).
        """
        run_audit_duration(
            db=db,
            dj_only=dj_only,
            status_filter=status_filter,
            source=source,
            since=since,
            inactive_exclude=inactive_exclude,
        )

    @index.command("set-duration-ref")
    @click.argument("path", type=click.Path(exists=True))
    @click.option("--db", type=click.Path(), help="Database path (auto-detect from env if not provided)")
    @click.option("--dj-only", is_flag=True, help="Mark file as DJ material")
    @click.option("--confirm", is_flag=True, help="Confirm manual duration reference override")
    @click.option("--execute", is_flag=True, help="Write updates to the database")
    def index_set_duration_ref(path, db, dj_only, confirm, execute):  # type: ignore  # TODO: mypy-strict
        """
        Manually set a duration reference from a known-good file.
        """
        from datetime import datetime, timezone

        from tagslut.core.hashing import calculate_file_hash
        from tagslut.storage.schema import get_connection, init_db
        from tagslut.utils.audit_log import append_jsonl, resolve_log_path
        from tagslut.utils.db import resolve_db_path

        if execute and not confirm:
            raise click.ClickException("--confirm is required with --execute")

        resolution = resolve_db_path(
            db,
            purpose="write" if execute else "read",
            allow_create=bool(execute),
        )
        db_path = resolution.path

        file_path = Path(path).expanduser().resolve()
        if not file_path.exists():
            raise click.ClickException(f"Path not found: {path}")

        duration_measured_ms = measure_duration_ms(file_path)
        if duration_measured_ms is None:
            raise click.ClickException("Could not measure duration from file")

        sha256 = calculate_file_hash(file_path)
        manual_id = f"manual:{sha256}"
        now_iso = datetime.now(timezone.utc).isoformat()

        ok_max_ms, warn_max_ms = duration_thresholds_from_config()
        duration_version = duration_check_version(ok_max_ms, warn_max_ms)

        conn = get_connection(str(db_path), purpose="write" if execute else "read", allow_create=bool(execute))
        if execute:
            init_db(conn)
        try:
            if execute:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO track_duration_refs
                        (ref_id, ref_type, duration_ref_ms, ref_source, ref_updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (manual_id, "manual", duration_measured_ms, "manual", now_iso),
                )

                conn.execute(
                    """
                    UPDATE files SET
                        is_dj_material = CASE WHEN ? THEN 1 ELSE is_dj_material END,
                        duration_ref_ms = ?,
                        duration_ref_source = ?,
                        duration_ref_track_id = ?,
                        duration_ref_updated_at = ?,
                        duration_measured_ms = ?,
                        duration_measured_at = ?,
                        duration_delta_ms = 0,
                        duration_status = 'ok',
                        duration_check_version = ?
                    WHERE path = ?
                    """,
                    (
                        1 if dj_only else 0,
                        duration_measured_ms,
                        "manual",
                        manual_id,
                        now_iso,
                        duration_measured_ms,
                        now_iso,
                        duration_version,
                        str(file_path),
                    ),
                )
                conn.commit()

            log_payload = {
                "event": "duration_check",
                "timestamp": now_iso,
                "path": str(file_path),
                "source": "manual",
                "track_id": manual_id,
                "is_dj_material": bool(dj_only),
                "duration_ref_ms": duration_measured_ms,
                "duration_measured_ms": duration_measured_ms,
                "duration_delta_ms": 0,
                "duration_status": "ok",
                "thresholds_ms": {"ok": ok_max_ms, "warn": warn_max_ms},
                "check_version": duration_version,
            }
            append_jsonl(resolve_log_path("mgmt_duration"), log_payload)
        finally:
            conn.close()

        click.echo(f"Duration reference set: {manual_id} ({duration_measured_ms} ms)")

    @index.command("promote-classification")
    @click.option("--db", required=True, type=click.Path(exists=True), help="Path to inventory DB")
    @click.option("--dry-run", is_flag=True, default=False)
    def index_promote_classification(db, dry_run):  # type: ignore  # TODO: mypy-strict
        """Promote classification_v2 to primary classification column."""
        from tagslut.storage.classification_promotion import (
            PromotionError,
            format_promotion_result,
            promote_classification_v2,
        )

        try:
            result = promote_classification_v2(Path(db), dry_run=dry_run)
        except PromotionError as exc:
            raise click.ClickException(str(exc)) from exc

        for line in format_promotion_result(result):
            click.echo(line)
        if result.status == "dry_run":
            click.echo("Dry-run only: no database changes were made.")

    @index.command("enrich")
    @click.option('--db', type=click.Path(), required=False, help='Database path')
    @click.option('--path', type=str, help='Filter files by path pattern (SQL LIKE) or file/dir in --standalone mode')
    @click.option('--zones', type=str, help='Comma-separated zones to include (e.g. accepted,staging)')
    @click.option(
        '--providers',
        default='beatport,tidal,deezer,traxsource,musicbrainz',
        help='Comma-separated list of providers (order = priority)',
    )
    @click.option('--limit', type=int, help='Maximum files to process')
    @click.option('--force', is_flag=True, help='Re-process ALL already-processed files')
    @click.option('--retry-no-match', is_flag=True, help='Retry files that had no provider match')
    @click.option('--execute', is_flag=True, help='Actually update database (default: dry-run)')
    @click.option('--recovery', is_flag=True, help='Recovery mode: focus on duration health validation')
    @click.option('--hoarding', is_flag=True, help='Hoarding mode: collect full metadata (BPM, key, genre, etc.)')
    @click.option('-v', '--verbose', is_flag=True, help='Verbose output')
    @click.option('--standalone', is_flag=True, help='Run without a database (read tags directly)')
    def index_enrich(  # type: ignore[no-untyped-def]  # TODO: mypy-strict
        db,
        path,
        zones,
        providers,
        limit,
        force,
        retry_no_match,
        execute,
        recovery,
        hoarding,
        verbose,
        standalone,
    ):
        """
        Fetch metadata from external providers.

        Two modes available:

        \b
        --recovery  Health validation mode. Compares local file durations against
                    provider durations to detect truncated or stitched files.
                    Accepts lower-confidence matches. Sets metadata_health field.

        \b
        --hoarding  Full metadata mode. Fetches BPM, key, genre, label, artwork.
                    Requires higher-confidence matches (ISRC or strong text match).
                    Stores canonical values and raw provider data.

        If neither flag is specified, defaults to --recovery mode.

        \b
        Examples:
            # Recovery mode: validate health of recovered files
            tagslut index enrich --db music.db --recovery --execute

            # Hoarding mode: collect full metadata for DJ library
            tagslut index enrich --db music.db --hoarding --execute

            # Both modes: health check + full metadata
            tagslut index enrich --db music.db --recovery --hoarding --execute

            # Filter by path pattern
            tagslut index enrich --db music.db --recovery --path "/Volumes/Music/DJ/%" --execute
        """
        import logging
        import shutil
        import sqlite3
        from datetime import datetime

        from tagslut.cli.runtime import collect_flac_paths as _collect_flac_paths
        from tagslut.metadata.auth import TokenManager
        from tagslut.metadata.enricher import Enricher
        from tagslut.storage.schema import init_db

        if not db and not standalone:
            raise click.ClickException("--db is required (or use --standalone)")
        if db and standalone:
            raise click.ClickException("--standalone cannot be used with --db")

        # Silence noisy loggers
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)

        # Determine mode - default to recovery if neither specified
        if not recovery and not hoarding:
            recovery = True

        # Build mode string for enricher
        if recovery and hoarding:
            mode = "both"
        elif recovery:
            mode = "recovery"
        else:
            mode = "hoarding"

        if standalone:
            if not path:
                raise click.ClickException("--path is required in --standalone mode (file or directory)")
            if zones:
                click.echo("Warning: --zones filter is ignored in standalone mode")
            if execute:
                click.echo("Note: --execute is ignored in standalone mode (no DB writes).")
            file_paths = _collect_flac_paths(path)
            if limit:
                file_paths = file_paths[:limit]
            if not file_paths:
                click.echo("No FLAC files found to enrich.")
                return

            # Minimal console logging for standalone runs
            logging.basicConfig(
                level=logging.DEBUG if verbose else logging.INFO,
                format='%(asctime)s - %(levelname)s - %(message)s'
            )

            provider_list = [p.strip() for p in providers.split(',') if p.strip()]
            token_manager = TokenManager()

            click.echo("")
            click.echo("┌" + "─" * 50 + "┐")
            if mode == "recovery":
                click.echo("│  METADATA ENRICHMENT - Recovery Mode              │")
            elif mode == "hoarding":
                click.echo("│  METADATA ENRICHMENT - Hoarding Mode              │")
            else:
                click.echo("│  METADATA ENRICHMENT - Recovery + Hoarding        │")
            click.echo("└" + "─" * 50 + "┘")
            click.echo("")
            click.echo(f"  Files:      {len(file_paths)}")
            click.echo(f"  Providers:  {' → '.join(provider_list)}")
            click.echo("")

            stats = {"total": 0, "enriched": 0, "no_match": 0, "failed": 0}

            with Enricher(
                db_path=Path("__standalone__"),
                token_manager=token_manager,
                providers=provider_list,
                dry_run=True,
                mode=mode,
            ) as enricher:
                for i, file_path in enumerate(file_paths, start=1):
                    click.echo(f"[{i}/{len(file_paths)}] {file_path}")
                    try:
                        file_info = _local_file_info_from_path(file_path)
                        result = enricher.resolve_file(file_info)
                        if result.matches:
                            stats["enriched"] += 1
                        else:
                            stats["no_match"] += 1
                        _print_enrichment_result(result)
                    except Exception as e:
                        stats["failed"] += 1
                        click.echo(f"Error: {e}")
                    stats["total"] += 1
                    click.echo("")

            click.echo(f"{'='*50}")
            click.echo("RESULTS")
            click.echo(f"{'='*50}")
            click.echo(f"  Total:      {stats['total']:>6}")
            click.echo(f"  Enriched:   {stats['enriched']:>6}  ✓")
            click.echo(f"  No match:   {stats['no_match']:>6}")
            click.echo(f"  Failed:     {stats['failed']:>6}")
            return

        # Set up logging to both file and console
        db_path = Path(db)
        log_dir = db_path.parent
        log_file = log_dir / f"enrich_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

        # Clear any existing handlers
        root_logger = logging.getLogger()
        root_logger.handlers = []

        # File handler - detailed logs (but not httpcore noise)
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        root_logger.addHandler(file_handler)

        # Console handler - minimal (only warnings/errors unless verbose)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG if verbose else logging.WARNING)
        console_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
        root_logger.addHandler(console_handler)

        root_logger.setLevel(logging.DEBUG)

        if not db_path.exists():
            raise click.ClickException(f"Database not found: {db_path}")

        # Ensure schema is up to date
        conn = sqlite3.connect(db_path)
        init_db(conn)
        conn.close()

        # Parse providers
        provider_list = [p.strip() for p in providers.split(',')]

        # Initialize token manager
        token_manager = TokenManager()

        # Check token status
        status = token_manager.status()
        for provider in provider_list:
            if provider in status:
                pstatus = status[provider]
                if not pstatus.get('configured'):
                    click.echo(f"Warning: {provider} not configured in tokens.json")
                elif pstatus.get('expired'):
                    click.echo(f"Warning: {provider} token expired, will attempt refresh")

        click.echo("")
        click.echo("┌" + "─" * 50 + "┐")
        if mode == "recovery":
            click.echo("│  METADATA ENRICHMENT - Recovery Mode              │")
        elif mode == "hoarding":
            click.echo("│  METADATA ENRICHMENT - Hoarding Mode              │")
        else:
            click.echo("│  METADATA ENRICHMENT - Recovery + Hoarding        │")
        click.echo("└" + "─" * 50 + "┘")

        if not execute:
            click.echo("")
            click.echo("  ⚠  DRY-RUN MODE - use --execute to update database")

        click.echo("")
        click.echo(f"  Database:   {db_path}")
        click.echo(f"  Providers:  {' → '.join(provider_list)}")
        if path:
            click.echo(f"  Path:       {path}")
        if zones:
            click.echo(f"  Zones:      {zones}")
        if limit:
            click.echo(f"  Limit:      {limit}")
        if force:
            click.echo("  Mode:       Force (re-process ALL)")
        elif retry_no_match:
            click.echo("  Mode:       Retry (files with no previous match)")

        click.echo(f"  Log file:   {log_file}")
        click.echo("")
        click.echo("Resumable: Ctrl+C to pause, run again to continue")
        click.echo("")

        term_width = shutil.get_terminal_size().columns

        def progress(current, total, filepath):  # type: ignore  # TODO: mypy-strict
            remaining = total - current
            pct = (current / total) * 100 if total > 0 else 0

            # Truncate filepath to fit terminal
            max_path_len = term_width - 45
            display_path = filepath
            if len(filepath) > max_path_len:
                display_path = "..." + filepath[-(max_path_len - 3):]

            # Simple progress line that updates in place
            status_line = f"\r[{current:>5}/{total}] {remaining:>5} left ({pct:5.1f}%) | {display_path}"
            click.echo(status_line.ljust(term_width)[:term_width], nl=False)

            # Print newline at end
            if current == total:
                click.echo("")

        with Enricher(
            db_path=db_path,
            token_manager=token_manager,
            providers=provider_list,
            dry_run=not execute,
            mode=mode,
        ) as enricher:
            zone_list = [z.strip() for z in zones.split(",")] if zones else None
            stats = enricher.enrich_all(
                path_pattern=path,
                limit=limit,
                force=force,
                retry_no_match=retry_no_match,
                zones=zone_list,
                progress_callback=progress,
            )

        click.echo("")
        click.echo(f"{'='*50}")
        click.echo("RESULTS")
        click.echo(f"{'='*50}")
        click.echo(f"  Total:      {stats.total:>6}")
        click.echo(f"  Enriched:   {stats.enriched:>6}  ✓")
        click.echo(f"  No match:   {stats.no_match:>6}")
        click.echo(f"  Failed:     {stats.failed:>6}  {'⚠' if stats.failed > 0 else ''}")

        # Show sample of no-match files
        if stats.no_match_files:
            click.echo("")
            click.echo("NO MATCH (sample):")
            for p in stats.no_match_files[:10]:
                # Show just the filename
                click.echo(f"  • {Path(p).name}")
            if len(stats.no_match_files) > 10:
                click.echo(f"  ... and {len(stats.no_match_files) - 10} more")

        click.echo("")
        click.echo(f"Full log: {log_file}")

    # ------------------------------------------------------------------
    # DJ flag commands
    # ------------------------------------------------------------------

    @index.command("dj-flag")
    @click.argument("target")
    @click.option(
        "--set",
        "flag_value",
        default="true",
        show_default=True,
        type=click.Choice(["true", "false"], case_sensitive=False),
        help="Set dj_flag to true or false.",
    )
    @click.option(
        "--db",
        "db_path",
        required=True,
        type=click.Path(exists=True),
        help="Path to the inventory SQLite database.",
    )
    def index_dj_flag(target: str, flag_value: str, db_path: str) -> None:
        """Flag a track (or batch by ISRC) as DJ material.

        TARGET may be a file path or an ISRC string.
        """
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        init_db(conn)
        value = 1 if flag_value.lower() == "true" else 0
        with conn:
            cur = conn.execute(
                "UPDATE files SET dj_flag = ? WHERE path = ? OR isrc = ?",
                (value, target, target),
            )
        click.echo(f"dj_flag set to {value} for {cur.rowcount} row(s) matching '{target}'.")
        conn.close()

    @index.command("dj-autoflag")
    @click.option("--genre", default=None, help="Filter by genre (case-insensitive substring).")
    @click.option("--bpm", "bpm_range", default=None, help="BPM range, e.g. '125-145'.")
    @click.option("--label", default=None, help="Filter by label (case-insensitive substring).")
    @click.option(
        "--set",
        "flag_value",
        default="true",
        show_default=True,
        type=click.Choice(["true", "false"], case_sensitive=False),
        help="Set dj_flag to true or false.",
    )
    @click.option(
        "--db",
        "db_path",
        required=True,
        type=click.Path(exists=True),
        help="Path to the inventory SQLite database.",
    )
    def index_dj_autoflag(
        genre: Optional[str],
        bpm_range: Optional[str],
        label: Optional[str],
        flag_value: str,
        db_path: str,
    ) -> None:
        """Bulk-flag tracks by genre, BPM range, or label.

        Example: tagslut index dj-autoflag --genre techno --bpm 125-145 --db inventory.db
        """
        value = 1 if flag_value.lower() == "true" else 0

        clauses: list[str] = []
        params: list[object] = []

        if genre:
            clauses.append(
                "(LOWER(genre) LIKE ? OR LOWER(canonical_genre) LIKE ?)"
            )
            pattern = f"%{genre.lower()}%"
            params.extend([pattern, pattern])

        if bpm_range:
            try:
                lo_str, hi_str = bpm_range.split("-", 1)
                lo, hi = float(lo_str), float(hi_str)
            except ValueError:
                click.echo(
                    f"Invalid BPM range '{bpm_range}'. Expected format: '125-145'.",
                    err=True,
                )
                return
            clauses.append("(bpm BETWEEN ? AND ? OR canonical_bpm BETWEEN ? AND ?)")
            params.extend([lo, hi, lo, hi])

        if label:
            clauses.append("LOWER(canonical_label) LIKE ?")
            params.append(f"%{label.lower()}%")

        if not clauses:
            click.echo("Provide at least one filter (--genre, --bpm, --label).", err=True)
            return

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        init_db(conn)

        where = " AND ".join(clauses)
        params.insert(0, value)
        with conn:
            cur = conn.execute(f"UPDATE files SET dj_flag = ? WHERE {where}", params)
        click.echo(f"dj_flag set to {value} for {cur.rowcount} row(s).")
        conn.close()

    @index.command("dj-status")
    @click.option(
        "--db",
        "db_path",
        required=True,
        type=click.Path(exists=True),
        help="Path to the inventory SQLite database.",
    )
    def index_dj_status(db_path: str) -> None:
        """Show DJ pool status: flagged tracks, export state, and field coverage."""
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            total = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            flagged = conn.execute(
                "SELECT COUNT(*) FROM files WHERE dj_flag = 1"
            ).fetchone()[0]
            exported = conn.execute(
                "SELECT COUNT(*) FROM files WHERE last_exported_usb IS NOT NULL"
            ).fetchone()[0]
            has_bpm = conn.execute(
                "SELECT COUNT(*) FROM files WHERE bpm IS NOT NULL"
            ).fetchone()[0]
            has_key = conn.execute(
                "SELECT COUNT(*) FROM files WHERE key_camelot IS NOT NULL"
            ).fetchone()[0]
            has_isrc = conn.execute(
                "SELECT COUNT(*) FROM files WHERE isrc IS NOT NULL"
            ).fetchone()[0]
            in_pool = conn.execute(
                "SELECT COUNT(*) FROM files WHERE dj_pool_path IS NOT NULL"
            ).fetchone()[0]
        finally:
            conn.close()

        click.echo(f"Total tracks:         {total}")
        click.echo(f"DJ-flagged:           {flagged}")
        click.echo(f"In DJ pool (MP3):     {in_pool}")
        click.echo(f"Exported to USB:      {exported}")
        click.echo(f"Have BPM:             {has_bpm}")
        click.echo(f"Have Camelot key:     {has_key}")
        click.echo(f"Have ISRC:            {has_isrc}")
