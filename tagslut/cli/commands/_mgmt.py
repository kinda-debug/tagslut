"""Internal management group: inventory tracking, duplicate checking, and duration management."""

from __future__ import annotations

import logging
from pathlib import Path

import click

from tagslut.cli.runtime import collect_flac_paths as _collect_flac_paths

logger = logging.getLogger("tagslut")


def _duration_thresholds_from_config() -> tuple[int, int]:
    from tagslut.utils.config import get_config

    config = get_config()
    ok_max = int(config.get("mgmt.duration.ok_max_delta_ms", 2000) or 2000)
    warn_max = int(config.get("mgmt.duration.warn_max_delta_ms", 8000) or 8000)
    return ok_max, warn_max


def _duration_check_version(ok_max_ms: int, warn_max_ms: int) -> str:
    return f"duration_v1_ok{ok_max_ms//1000}_warn{warn_max_ms//1000}"


def _duration_status(delta_ms: int | None, ok_max_ms: int, warn_max_ms: int) -> str:
    if delta_ms is None:
        return "unknown"
    abs_delta = abs(delta_ms)
    if abs_delta <= ok_max_ms:
        return "ok"
    if abs_delta <= warn_max_ms:
        return "warn"
    return "fail"


def _collect_flac_inputs(paths: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    for input_path in paths:
        files.extend(_collect_flac_paths(input_path))
    return files


def _resolve_group_name(file_path: Path, base_paths: list[Path]) -> str:
    best_base: Path | None = None
    best_parts = -1
    for base in base_paths:
        try:
            rel = file_path.relative_to(base)
        except ValueError:
            continue
        if len(rel.parts) > best_parts:
            best_parts = len(rel.parts)
            best_base = base

    if best_base is None:
        return file_path.parent.name or "playlist"

    rel = file_path.relative_to(best_base)
    if len(rel.parts) > 1:
        return rel.parts[0]
    return best_base.name or file_path.parent.name or "playlist"


def _safe_playlist_name(name: str) -> str:
    cleaned = name.strip().replace("/", "-").replace("\\", "-")
    return cleaned or "playlist"


def _format_extinf(file_path: Path) -> tuple[int, str]:
    try:
        from mutagen.flac import FLAC
        audio = FLAC(file_path)
        duration = int(audio.info.length) if audio.info.length else -1
        tags = audio.tags or {}  # type: ignore  # TODO: mypy-strict
        artist = _extract_tag_value(tags, ["artist", "albumartist"]) or "Unknown"  # type: ignore  # TODO: mypy-strict
        title = _extract_tag_value(tags, ["title"]) or file_path.stem  # type: ignore  # TODO: mypy-strict
        return duration, f"{artist} - {title}"
    except Exception:
        return -1, file_path.stem


def _write_m3u(
    *,
    playlist_name: str,
    files: list[Path],
    output_dir: Path,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _safe_playlist_name(playlist_name)
    output_path = output_dir / f"{safe_name}.m3u"

    lines = ["#EXTM3U", "#EXTENC: UTF-8", f"#PLAYLIST:{playlist_name}"]
    for file_path in files:
        duration, label = _format_extinf(file_path)
        lines.append(f"#EXTINF:{duration},{label}")
        lines.append(str(file_path.resolve()))

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def _prompt_duplicate_action(
    *,
    file_path: Path,
    matches: list[tuple[str, str | None]],
    prompt_enabled: bool,
) -> str:
    import sys

    if not prompt_enabled or not sys.stdin.isatty():
        return "skip"

    click.echo("\n⚠️  Similar track found in inventory:")
    click.echo(f"\nEXISTING for {file_path.name}:")
    for match_path, match_source in matches[:5]:
        src = match_source or "unknown"
        click.echo(f"  → {src}: {match_path}")
    if len(matches) > 5:
        click.echo(f"  ... and {len(matches) - 5} more")

    click.echo("\nActions: [S]kip  [D]ownload anyway  [R]eplace  [Q]uit")
    choice = click.prompt("Choose action", default="S", show_default=True)
    choice = choice.strip().lower()
    if choice in {"s", "skip"}:
        return "skip"
    if choice in {"d", "download", "download anyway", "download_anyway"}:
        return "download"
    if choice in {"r", "replace"}:
        return "replace"
    if choice in {"q", "quit"}:
        return "quit"
    return "skip"


def _measure_duration_ms(file_path: Path) -> int | None:
    try:
        from mutagen import File as MutagenFile  # type: ignore  # TODO: mypy-strict
        audio = MutagenFile(str(file_path), easy=False)
        if audio is None or not hasattr(audio, "info") or audio.info is None:
            return None
        length = getattr(audio.info, "length", None)
        if length is None:
            return None
        return int(round(float(length) * 1000))
    except Exception:
        return None


def _extract_tag_value(tags: dict, keys: list[str]) -> str | None:  # type: ignore  # TODO: mypy-strict
    if not tags:
        return None
    lowered = {str(k).lower(): v for k, v in tags.items()}
    for key in keys:
        raw = lowered.get(key.lower())
        if raw is None:
            continue
        if isinstance(raw, (list, tuple)):
            if not raw:
                continue
            return str(raw[0]).strip() or None
        return str(raw).strip() or None
    return None


def _lookup_duration_ref_ms(  # type: ignore  # TODO: mypy-strict
    conn,
    beatport_id: str | None,
    isrc: str | None,
) -> tuple[int | None, str | None, str | None]:
    if beatport_id:
        row = conn.execute(
            "SELECT duration_ref_ms, ref_source FROM track_duration_refs WHERE ref_id = ?",
            (beatport_id,),
        ).fetchone()
        if row:
            return int(row[0]), row[1], beatport_id
        row = conn.execute(
            """
            SELECT canonical_duration, canonical_duration_source
            FROM files
            WHERE beatport_id = ? AND canonical_duration IS NOT NULL
            LIMIT 1
            """,
            (beatport_id,),
        ).fetchone()
        if row and row[0] is not None:
            return int(round(float(row[0]) * 1000)), row[1], beatport_id
    if isrc:
        row = conn.execute(
            "SELECT duration_ref_ms, ref_source FROM track_duration_refs WHERE ref_id = ?",
            (isrc,),
        ).fetchone()
        if row:
            return int(row[0]), row[1], isrc
        row = conn.execute(
            """
            SELECT canonical_duration, canonical_duration_source
            FROM files
            WHERE canonical_isrc = ? AND canonical_duration IS NOT NULL
            LIMIT 1
            """,
            (isrc,),
        ).fetchone()
        if row and row[0] is not None:
            return int(round(float(row[0]) * 1000)), row[1], isrc
    return None, None, None


def register_mgmt_group(cli: click.Group) -> None:
    @cli.group(name="_mgmt", invoke_without_command=True, hidden=True)
    @click.option("--m3u", "m3u_mode", is_flag=True, help="Generate Roon-compatible M3U playlist(s)")
    @click.option("--merge", is_flag=True, help="Merge all items into a single M3U")
    @click.option("--m3u-dir", type=click.Path(), help="Output directory for M3U files")
    @click.option("--db", type=click.Path(), help="Database path (auto-detect from env if not provided)")
    @click.option("--source", help="Source label for playlist naming (bpdl, tidal, etc.)")
    @click.option("--path", "paths", multiple=True, type=click.Path(), help="Input path(s) for --m3u")
    @click.pass_context
    def mgmt(ctx, m3u_mode, merge, m3u_dir, db, source, paths):  # type: ignore  # TODO: mypy-strict
        """Internal management mode: inventory tracking and duplicate checking."""
        if ctx.invoked_subcommand is None:
            if not m3u_mode:
                click.echo(ctx.get_help())
                return
            if not paths:
                raise click.ClickException("Provide at least one PATH when using --m3u")

            from tagslut.storage.schema import get_connection, init_db
            from tagslut.utils.db import resolve_db_path
            from tagslut.utils.config import get_config
            from datetime import datetime, timezone

            config = get_config()
            default_m3u_dir = config.get("mgmt.m3u_dir") if config else None
            output_dir = Path(m3u_dir) if m3u_dir else (Path(default_m3u_dir).expanduser() if default_m3u_dir else None)

            input_paths = [Path(p).expanduser().resolve() for p in paths]
            flac_files = _collect_flac_inputs(tuple(paths))
            if not flac_files:
                raise click.ClickException("No FLAC files found in provided PATHS")

            if output_dir is None:
                if len(input_paths) == 1 and input_paths[0].is_dir():
                    output_dir = input_paths[0]
                else:
                    output_dir = Path.cwd()

            groups: dict[str, list[Path]] = {}
            if merge:
                groups["merged"] = sorted(flac_files, key=lambda p: str(p))
            else:
                base_paths = [p for p in input_paths if p.exists()]
                for file_path in flac_files:
                    group = _resolve_group_name(file_path, base_paths)
                    groups.setdefault(group, []).append(file_path)
                for group_name in list(groups.keys()):
                    groups[group_name] = sorted(groups[group_name], key=lambda p: str(p))

            resolution = resolve_db_path(db, purpose="write", allow_create=True)
            conn = get_connection(str(resolution.path), purpose="write", allow_create=True)
            init_db(conn)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(files)")}
            has_m3u_path = "m3u_path" in columns

            now_iso = datetime.now(timezone.utc).isoformat()
            playlist_outputs: list[Path] = []
            try:
                for group_name, files in groups.items():
                    playlist_name = _safe_playlist_name(group_name)
                    if merge:
                        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                        label = source or "tagslut"
                        playlist_name = f"{label}-{stamp}"

                    output_path = _write_m3u(
                        playlist_name=playlist_name,
                        files=files,
                        output_dir=output_dir,
                    )
                    playlist_outputs.append(output_path)

                    for file_path in files:
                        if has_m3u_path:
                            conn.execute(
                                "UPDATE files SET m3u_exported = ?, m3u_path = ? WHERE path = ?",
                                (now_iso, str(output_path), str(file_path)),
                            )
                        else:
                            conn.execute(
                                "UPDATE files SET m3u_exported = ? WHERE path = ?",
                                (now_iso, str(file_path)),
                            )
                conn.commit()
            finally:
                conn.close()

            click.echo(f"Generated {len(playlist_outputs)} M3U file(s):")
            for item in playlist_outputs:
                click.echo(f"  {item}")

    @mgmt.command()
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
    def register(path, source, db, execute, full_hash, limit, dj_only, check_duration, prompt, verbose):  # type: ignore  # TODO: mypy-strict
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
        from tagslut.storage.schema import get_connection, init_db
        from tagslut.storage.queries import get_file
        from tagslut.storage.v3 import dual_write_enabled, dual_write_registered_file
        from tagslut.core.hashing import calculate_file_hash
        from tagslut.core.metadata import extract_metadata
        from tagslut.utils.db import resolve_db_path
        from datetime import datetime, timezone
        from tagslut.utils.audit_log import append_jsonl, resolve_log_path
        from tagslut.utils.config import get_config
        from tagslut.utils.paths import list_files
        import json
        import itertools

        resolution = resolve_db_path(
            db,
            purpose="write" if execute else "read",
            allow_create=bool(execute),
        )
        db_path = resolution.path

        path_obj = Path(path).expanduser().resolve()
        if not path_obj.exists():
            raise click.ClickException(f"Path not found: {path}")

        # Collect FLAC files (streaming; avoids huge in-memory lists for big libraries).
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
            ok_max_ms, warn_max_ms = _duration_thresholds_from_config()
            duration_version = _duration_check_version(ok_max_ms, warn_max_ms)

            total = 0
            for i, file_path in enumerate(flac_iter, start=1):
                total = i
                try:
                    mgmt_status_override = None

                    # Check if already registered
                    existing = get_file(conn, file_path)
                    if existing:
                        if verbose:
                            click.echo(f"  [{i}] SKIP (already registered) {file_path.name}")
                        skipped += 1
                        continue

                    # Extract STREAMINFO MD5 + tags/tech. Full hash is optional for speed.
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

                    # Check for existing file with same content fingerprint
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
                        action = _prompt_duplicate_action(
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
                    duration_status = None
                    duration_measured_at = None
                    duration_ref_updated_at = None

                    if check_duration:
                        duration_measured_ms = _measure_duration_ms(file_path)
                        duration_measured_at = now_iso

                        beatport_id = _extract_tag_value(
                            audio.metadata,
                            ["BEATPORT_TRACK_ID", "BP_TRACK_ID", "beatport_track_id"],
                        )
                        isrc = _extract_tag_value(audio.metadata, ["ISRC", "TSRC"])

                        duration_ref_ms, duration_ref_source, duration_ref_track_id = _lookup_duration_ref_ms(
                            conn, beatport_id, isrc
                        )
                        if duration_ref_ms is not None:
                            duration_ref_updated_at = now_iso
                        if duration_measured_ms is not None and duration_ref_ms is not None:
                            duration_delta_ms = duration_measured_ms - duration_ref_ms
                        duration_status = _duration_status(duration_delta_ms, ok_max_ms, warn_max_ms)

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
                            "duration_status": duration_status,
                            "thresholds_ms": {"ok": ok_max_ms, "warn": warn_max_ms},
                            "check_version": duration_version,
                        }
                        append_jsonl(resolve_log_path("mgmt_duration"), log_payload)

                        if dj_only and duration_status in ("warn", "fail", "unknown"):
                            anomaly_payload = {
                                "event": "duration_anomaly",
                                "timestamp": now_iso,
                                "path": str(file_path),
                                "track_id": log_payload["track_id"],
                                "is_dj_material": True,
                                "duration_status": duration_status,
                                "duration_ref_ms": duration_ref_ms,
                                "duration_measured_ms": duration_measured_ms,
                                "duration_delta_ms": duration_delta_ms,
                                "action": "blocked_promotion",
                            }
                            append_jsonl(resolve_log_path("mgmt_duration"), anomaly_payload)
                            mgmt_status_override = mgmt_status_override or "needs_review"

                    # Register in database
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
                            )
                            VALUES (
                                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
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
                                str(file_path),  # original_path = current path (no move yet)
                                mgmt_status_override
                                or (
                                    "needs_review"
                                    if dj_only and duration_status in ("warn", "fail", "unknown")
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
                                duration_status,
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
                                    if dj_only and duration_status in ("warn", "fail", "unknown")
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

    @mgmt.command()
    @click.argument('path', type=click.Path(exists=True), required=False)
    @click.option('--source', help='Filter by download source')
    @click.option('--db', type=click.Path(), help='Database path (auto-detect from env if not provided)')
    @click.option('--strict', is_flag=True, help='Strict mode: any match is a conflict')
    @click.option('--prompt/--no-prompt', default=True, help='Prompt when similar files exist')
    @click.option('-v', '--verbose', is_flag=True, help='Verbose output')
    def check(path, source, db, strict, prompt, verbose):  # type: ignore  # TODO: mypy-strict
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
        from tagslut.storage.schema import get_connection
        from tagslut.core.hashing import calculate_file_hash
        from tagslut.utils.db import resolve_db_path
        from tagslut.utils.audit_log import append_jsonl, resolve_log_path
        from tagslut.utils.config import get_config
        from datetime import datetime, timezone
        import sys

        # Resolve database path (auto-detect from CLI/env/config)
        resolution = resolve_db_path(db, purpose="read")
        db_path = resolution.path

        # Collect file paths from argument or stdin
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
            # Read from stdin
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
                    # Compute checksum
                    sha256 = calculate_file_hash(file_path)

                    # Query database directly to check for existing file with same sha256
                    if strict:
                        # Any match is a conflict
                        cursor = conn.execute(
                            "SELECT path, download_source FROM files WHERE sha256 = ?",
                            (sha256,)
                        )
                    else:
                        # Only match if same source
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
                        action = _prompt_duplicate_action(
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

    @mgmt.command("check-duration")
    @click.argument("path", type=click.Path(exists=True))
    @click.option("--db", type=click.Path(), help="Database path (auto-detect from env if not provided)")
    @click.option("--execute", is_flag=True, help="Write duration updates to the database")
    @click.option("--dj-only", is_flag=True, help="Mark checked files as DJ material")
    @click.option("--source", help="Override source label for logging")
    @click.option("-v", "--verbose", is_flag=True, help="Verbose output")
    def check_duration(path, db, execute, dj_only, source, verbose):  # type: ignore  # TODO: mypy-strict
        """
        Measure durations and update duration status in the DB.
        """
        from tagslut.storage.schema import get_connection, init_db
        from tagslut.utils.db import resolve_db_path
        from tagslut.utils.audit_log import append_jsonl, resolve_log_path
        from mutagen.flac import FLAC
        from datetime import datetime, timezone

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

        ok_max_ms, warn_max_ms = _duration_thresholds_from_config()
        duration_version = _duration_check_version(ok_max_ms, warn_max_ms)
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
                    beatport_id = _extract_tag_value(tags, ["BEATPORT_TRACK_ID", "BP_TRACK_ID", "beatport_track_id"])  # type: ignore  # TODO: mypy-strict
                    isrc = _extract_tag_value(tags, ["ISRC", "TSRC"])  # type: ignore  # TODO: mypy-strict
                    if not beatport_id and db_beatport_id:
                        beatport_id = db_beatport_id
                    if not isrc and db_isrc:
                        isrc = db_isrc

                    duration_ref_ms, duration_ref_source, duration_ref_track_id = _lookup_duration_ref_ms(
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
                    duration_measured_ms = _measure_duration_ms(file_path)
                    duration_delta_ms = None
                    if duration_measured_ms is not None and duration_ref_ms is not None:
                        duration_delta_ms = duration_measured_ms - duration_ref_ms
                    duration_status = _duration_status(duration_delta_ms, ok_max_ms, warn_max_ms)

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
                        "duration_status": duration_status,
                        "thresholds_ms": {"ok": ok_max_ms, "warn": warn_max_ms},
                        "check_version": duration_version,
                    }
                    append_jsonl(resolve_log_path("mgmt_duration"), log_payload)

                    if dj_only and duration_status in ("warn", "fail", "unknown"):
                        anomaly_payload = {
                            "event": "duration_anomaly",
                            "timestamp": now_iso,
                            "path": str(file_path),
                            "track_id": log_payload["track_id"],
                            "is_dj_material": True,
                            "duration_status": duration_status,
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
                                duration_status,
                                duration_version,
                                1 if dj_only else 0,
                                duration_status,
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

    @mgmt.command("audit-duration")
    @click.option("--db", type=click.Path(), help="Database path (auto-detect from env if not provided)")
    @click.option("--dj-only", is_flag=True, help="Only DJ material")
    @click.option("--status", "status_filter", help="Comma-separated statuses (warn,fail,unknown)")
    @click.option("--source", help="Filter by download source")
    @click.option("--since", help="Filter by download_date >= YYYY-MM-DD")
    @click.option("--inactive-exclude", is_flag=True, help="Exclude mgmt_status=inactive")
    def audit_duration(db, dj_only, status_filter, source, since, inactive_exclude):  # type: ignore  # TODO: mypy-strict
        """
        Report files with duration_status != ok (or filtered statuses).
        """
        from tagslut.storage.schema import get_connection
        from tagslut.utils.db import resolve_db_path

        resolution = resolve_db_path(db, purpose="read")
        db_path = resolution.path

        statuses = None
        if status_filter:
            statuses = [s.strip() for s in status_filter.split(",") if s.strip()]

        conn = get_connection(str(db_path), purpose="read")
        try:
            where = ["1=1"]
            params = []
            if dj_only:
                where.append("is_dj_material = 1")
            if source:
                where.append("download_source = ?")
                params.append(source)
            if since:
                where.append("download_date >= ?")
                params.append(since)
            if statuses:
                where.append(f"duration_status IN ({','.join(['?'] * len(statuses))})")
                params.extend(statuses)
            else:
                where.append("(duration_status IS NULL OR duration_status != 'ok')")
            if inactive_exclude:
                where.append("(mgmt_status IS NULL OR mgmt_status != 'inactive')")

            query = (
                "SELECT path, duration_status, duration_ref_ms, duration_measured_ms, "
                "duration_delta_ms, download_source FROM files WHERE "
                + " AND ".join(where)
                + " ORDER BY download_source, path"
            )

            rows = conn.execute(query, tuple(params)).fetchall()
            click.echo(f"Found {len(rows)} file(s) with duration issues.")
            for row in rows:
                click.echo(
                    f"  {row[0]} | status={row[1]} | delta_ms={row[4]} | source={row[5]}"
                )
        finally:
            conn.close()

    @mgmt.command("set-duration-ref")
    @click.argument("path", type=click.Path(exists=True))
    @click.option("--db", type=click.Path(), help="Database path (auto-detect from env if not provided)")
    @click.option("--dj-only", is_flag=True, help="Mark file as DJ material")
    @click.option("--confirm", is_flag=True, help="Confirm manual duration reference override")
    @click.option("--execute", is_flag=True, help="Write updates to the database")
    def set_duration_ref(path, db, dj_only, confirm, execute):  # type: ignore  # TODO: mypy-strict
        """
        Manually set a duration reference from a known-good file.
        """
        from tagslut.storage.schema import get_connection, init_db
        from tagslut.utils.db import resolve_db_path
        from tagslut.core.hashing import calculate_file_hash
        from tagslut.utils.audit_log import append_jsonl, resolve_log_path
        from datetime import datetime, timezone

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

        duration_measured_ms = _measure_duration_ms(file_path)
        if duration_measured_ms is None:
            raise click.ClickException("Could not measure duration from file")

        sha256 = calculate_file_hash(file_path)
        manual_id = f"manual:{sha256}"
        now_iso = datetime.now(timezone.utc).isoformat()

        ok_max_ms, warn_max_ms = _duration_thresholds_from_config()
        duration_version = _duration_check_version(ok_max_ms, warn_max_ms)

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
