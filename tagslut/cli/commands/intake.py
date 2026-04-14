from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import click
import httpx

from tagslut.cli.runtime import run_python_script, WRAPPER_CONTEXT
from tagslut.core.download_manifest import DownloadManifest, build_manifest
from tagslut.exec.intake_orchestrator import run_intake
from tagslut.exec.dj_pool_m3u import write_dj_pool_m3u
from tagslut.filters.identity_resolver import TrackIntent
from tagslut.storage.schema import get_connection
from tagslut.utils.db import DbResolutionError, resolve_cli_env_db_path
from tagslut.utils.env_paths import get_artifacts_dir


def _looks_like_url(value: str) -> bool:
    lowered = (value or "").strip().lower()
    return lowered.startswith("http://") or lowered.startswith("https://")


class _IntakeGroup(click.Group):
    """Click group that defaults `tagslut intake <URL>` to `tagslut intake url <URL>`."""

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        if args and _looks_like_url(args[0]):
            args.insert(0, "url")
        return super().parse_args(ctx, args)


def _load_jsonl_lines(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise click.ClickException(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
        if not isinstance(payload, dict):
            raise click.ClickException(f"Invalid JSONL object at {path}:{line_no}: expected object")
        records.append(payload)
    return records


def _load_track_records(*, input_path: str | None, url: str | None) -> list[dict[str, Any]]:
    if bool(input_path) == bool(url):
        raise click.ClickException("Provide exactly one of --input or --url")

    if input_path:
        path = Path(input_path).expanduser().resolve()
        if not path.exists():
            raise click.ClickException(f"Input not found: {path}")
        return _load_jsonl_lines(path)

    assert url is not None
    try:
        response = httpx.get(url, timeout=30.0)
        response.raise_for_status()
    except Exception as exc:
        raise click.ClickException(f"Failed to fetch URL: {exc}") from exc

    records: list[dict[str, Any]] = []
    for line_no, raw in enumerate(response.text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise click.ClickException(f"Invalid JSONL from URL at line {line_no}: {exc}") from exc
        if not isinstance(payload, dict):
            raise click.ClickException(f"Invalid JSONL object from URL at line {line_no}: expected object")
        records.append(payload)
    return records


def _record_to_intent(record: dict[str, Any]) -> TrackIntent:
    intent = TrackIntent(
        title=record.get("title"),
        artist=record.get("artist"),
        duration_s=float(record["duration_s"]) if record.get("duration_s") is not None else None,
        isrc=record.get("isrc"),
        beatport_id=(str(record["beatport_id"]) if record.get("beatport_id") is not None else None),
        tidal_id=(str(record["tidal_id"]) if record.get("tidal_id") is not None else None),
        bit_depth=int(record["bit_depth"]) if record.get("bit_depth") is not None else None,
        sample_rate=int(record["sample_rate"]) if record.get("sample_rate") is not None else None,
        bitrate=int(record["bitrate"]) if record.get("bitrate") is not None else None,
    )

    if record.get("quality_rank") is not None:
        setattr(intent, "candidate_quality_rank", int(record["quality_rank"]))

    return intent


def _default_manifest_path() -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return get_artifacts_dir() / f"intake_manifest_{ts}.json"


def _build_and_write_manifest(
    *,
    db_path: str,
    input_path: str | None,
    url: str | None,
    output: str | None,
) -> tuple[DownloadManifest, Path]:
    records = _load_track_records(input_path=input_path, url=url)
    intents = [_record_to_intent(record) for record in records]

    with get_connection(db_path, purpose="read") as conn:
        manifest = build_manifest(intents, conn)

    output_path = Path(output).expanduser().resolve() if output else _default_manifest_path().resolve()
    manifest.to_json(output_path)
    return manifest, output_path


def _intent_reference(intent_dict: dict[str, Any]) -> str:
    for key in ["isrc", "beatport_id", "tidal_id"]:
        value = intent_dict.get(key)
        if value:
            return f"{key}:{value}"

    artist = intent_dict.get("artist")
    title = intent_dict.get("title")
    if artist and title:
        return f"artist:{artist} title:{title}"
    if title:
        return f"title:{title}"
    return "unresolved-intent"


def register_intake_group(cli: click.Group) -> None:
    @cli.group(cls=_IntakeGroup)
    def intake():  # type: ignore  # TODO: mypy-strict
        """Canonical intake commands.

        Shortcut: `tagslut intake <URL>` is an alias for `tagslut intake url <URL>`.
        """

    @intake.command("url")
    @click.argument("url")
    @click.option("--db", "db_path", default=None, help="Path to tagslut DB (or set TAGSLUT_DB)")
    @click.option("--playlist-name", default=None, help="Name for the batch DJ pool M3U file")
    @click.option(
        "--tag",
        is_flag=True,
        default=False,
        help="Fully enrich and write back promoted FLACs in MASTER_LIBRARY before any optional MP3/DJ stages. DJ pool admission requires a separate --dj pass.",
    )
    @click.option(
        "--mp3",
        is_flag=True,
        default=False,
        help=(
            "Convenience shortcut. Build MP3_LIBRARY copies during intake. "
            "(Requires --mp3-root.)"
        ),
    )
    @click.option(
        "--dj",
        is_flag=True,
        default=False,
        help=(
            "Build MP3s into MP3_LIBRARY and add tracks to DJ pool M3U playlists."
        ),
    )
    @click.option(
        "--mp3-root",
        default=None,
        type=click.Path(file_okay=False, writable=True),
        help="MP3 asset output root (required with --mp3).",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        default=False,
        help="Precheck only — no download, no writes.",
    )
    @click.option(
        "--no-precheck",
        is_flag=True,
        default=False,
        help="Explicitly waive precheck gating (downloads may proceed even if duplicates exist).",
    )
    @click.option(
        "--force-download",
        is_flag=True,
        default=False,
        help="Keep matched tracks anyway during precheck (cohort expansion).",
    )
    @click.option(
        "--artifact-dir",
        default=None,
        type=click.Path(),
        help="Directory for JSON artifact output (default: artifacts/intake)",
    )
    @click.option(
        "--verbose",
        "-v",
        is_flag=True,
        default=False,
        help="Show a more detailed per-step summary (still path-free).",
    )
    @click.option(
        "--debug-raw",
        is_flag=True,
        default=False,
        help="Stream raw internal stage output (very noisy; includes paths).",
    )
    def intake_url(
        url: str,
        db_path: str | None,
        playlist_name: str | None,
        tag: bool,
        mp3: bool,
        dj: bool,
        mp3_root: str | None,
        dry_run: bool,
        no_precheck: bool,
        force_download: bool,
        artifact_dir: str | None,
        verbose: bool,
        debug_raw: bool,
    ):  # type: ignore  # TODO: mypy-strict
        """Precheck → download → promote → [tag] → [mp3] → [dj] for a single provider URL."""
        if dj:
            mp3 = True
        if mp3 and not dj:
            click.echo(
                "WARNING: tagslut intake --mp3 is a legacy convenience shortcut. "
                "Use the dedicated MP3 commands when you want to build or reconcile "
                "MP3 derivatives outside intake.",
                err=True,
            )

        # Resolve DB path
        try:
            db_resolution = resolve_cli_env_db_path(db_path, purpose="write", source_label="--db")
        except DbResolutionError as exc:
            raise click.ClickException(str(exc)) from exc

        resolved_db_path = db_resolution.path

        # Convert roots + enforce contract
        mp3_root_path = Path(mp3_root).expanduser().resolve() if mp3_root else None
        if mp3_root_path is None and (mp3 or dj):
            if dj:
                raise click.ClickException(
                    "--dj implies --mp3 and requires --mp3-root.\n"
                    "Example: tagslut intake <URL> --dj --mp3-root /path/to/mp3_assets"
                )
            raise click.ClickException(
                "--mp3 requires --mp3-root.\n"
                "Example: tagslut intake <URL> --mp3 --mp3-root /path/to/mp3_assets"
            )

        artifact_dir_path = Path(artifact_dir).expanduser().resolve() if artifact_dir else None

        # Run orchestration
        result = run_intake(
            url=url,
            db_path=resolved_db_path,
            tag=tag,
            mp3=mp3,
            dj=False,
            dry_run=dry_run,
            mp3_root=mp3_root_path,
            artifact_dir=artifact_dir_path,
            verbose=verbose,
            debug_raw=debug_raw,
            no_precheck=no_precheck,
            force_download=force_download,
        )

        if dj and not dry_run and mp3_root_path is not None:
            mp3_stage = next((stage for stage in result.stages if stage.stage == "mp3"), None)
            if mp3_stage and mp3_stage.status == "ok" and mp3_stage.artifact_path:
                try:
                    cohort = json.loads(mp3_stage.artifact_path.read_text(encoding="utf-8"))
                except Exception as exc:
                    raise click.ClickException(
                        f"Failed to read MP3 cohort artifact: {mp3_stage.artifact_path} ({exc})"
                    ) from exc

                raw_paths = cohort.get("paths") if isinstance(cohort, dict) else None
                if isinstance(raw_paths, list):
                    try:
                        from tagslut.exec.mp3_build import _mp3_asset_dest_for_flac_path
                        from tagslut.utils.env_paths import get_volume
                    except Exception as exc:
                        raise click.ClickException(f"Failed to load MP3 path resolver: {exc}") from exc

                    library_root = get_volume("library", required=False)
                    seen: set[str] = set()
                    mp3_paths: list[Path] = []
                    for raw in raw_paths:
                        if not isinstance(raw, str):
                            continue
                        flac_path = Path(raw).expanduser().resolve()
                        dest = _mp3_asset_dest_for_flac_path(
                            flac_path=flac_path,
                            mp3_root=mp3_root_path,
                            library_root=library_root,
                        ).resolve()
                        if not dest.exists():
                            continue
                        key = str(dest)
                        if key in seen:
                            continue
                        seen.add(key)
                        mp3_paths.append(dest)

                    if mp3_paths:
                        try:
                            write_dj_pool_m3u(
                                mp3_paths=mp3_paths,
                                mp3_root=mp3_root_path,
                                playlist_name=playlist_name,
                            )
                        except Exception as exc:
                            raise click.ClickException(f"Failed to write DJ pool M3U playlists: {exc}") from exc

        # Print summary
        click.echo(result.summary())
        if debug_raw and result.artifact_path:
            click.echo(f"Artifact: {result.artifact_path}")
        if debug_raw and result.precheck_csv:
            click.echo(f"Precheck CSV: {result.precheck_csv}")

        # Exit with mapped code
        _EXIT = {"completed": 0, "blocked": 2, "failed": 1}
        sys.exit(_EXIT[result.disposition])

    @intake.command("spotiflac")
    @click.argument("log_file", type=click.Path(exists=True, dir_okay=False))
    @click.option(
        "--base-dir",
        type=click.Path(exists=True, file_okay=False),
        default=None,
        help="Root where SpotiFLAC wrote files (required when M3U8 is missing).",
    )
    @click.option("--dry-run", is_flag=True, default=False, help="Parse and print; write nothing.")
    @click.option(
        "--failed-only",
        is_flag=True,
        default=False,
        help="Report failed tracks only; do not ingest.",
    )
    def intake_spotiflac(  # type: ignore  # TODO: mypy-strict
        log_file: str,
        base_dir: str | None,
        dry_run: bool,
        failed_only: bool,
    ) -> None:
        """Ingest a SpotiFLAC batch output into the standard tagslut intake pipeline."""
        import json
        import os
        import shutil
        from datetime import datetime, timezone

        from tagslut.core.hashing import calculate_file_hash
        from tagslut.core.metadata import extract_metadata
        from tagslut.intake.spotiflac_parser import (
            build_manifest,
            classify_failure_reason,
        )
        from tagslut.storage.queries import get_file
        from tagslut.storage.schema import init_db
        from tagslut.storage.v3 import dual_write_enabled, dual_write_registered_file
        from tagslut.utils.db import DbResolutionError, open_db, resolve_cli_env_db_path

        log_path = Path(log_file).expanduser().resolve()
        tracks = build_manifest(log_path)

        total = len(tracks)
        with_isrc = sum(1 for t in tracks if t.isrc)
        with_path = sum(1 for t in tracks if t.file_path is not None)
        failed_count = sum(1 for t in tracks if t.failed)
        click.echo(
            f"{total} tracks parsed, {with_isrc} with ISRC, {with_path} with resolved file path, {failed_count} failed"
        )

        if failed_only:
            retryable = 0
            for track in tracks:
                if not track.failed:
                    continue
                classification = classify_failure_reason(track.failure_reason)
                if classification == "retryable":
                    retryable += 1
                reason = (track.failure_reason or "").strip()
                click.echo(f"[failed/{classification}] {track.display_title} — {reason}".rstrip(" —"))
            click.echo(f"0 ingested, 0 skipped (file not found), {failed_count} failed ({retryable} retryable)")
            return

        base_root = Path(base_dir).expanduser().resolve() if base_dir else None
        if base_root is None:
            any_resolved = any(t.file_path is not None for t in tracks if not t.failed)
            if not any_resolved:
                raise click.ClickException(
                    "Cannot resolve FLAC paths (no M3U8 found or no paths matched). Provide --base-dir."
                )
        else:
            unresolved = [t for t in tracks if (not t.failed) and t.file_path is None]
            if unresolved:
                import re
                import string

                _TRACK_PREFIX_RE = re.compile(r"^(?:\d+(?:-\d+)?\.\s+|\d+\s*-\s+)")

                def _norm_key(text: str) -> str:
                    lowered = (text or "").lower()
                    lowered = lowered.translate(str.maketrans({ch: " " for ch in string.punctuation}))
                    lowered = re.sub(r"[^a-z0-9\\s]+", " ", lowered)
                    return re.sub(r"\\s+", " ", lowered).strip()

                def _stem_variants(text: str) -> list[str]:
                    raw = (text or "").strip()
                    if not raw:
                        return []
                    stripped = _TRACK_PREFIX_RE.sub("", raw).strip()
                    variants: list[str] = []
                    for value in (raw, stripped):
                        if value and value not in variants:
                            variants.append(value)
                    return variants

                exact_map = {t.display_title: t for t in unresolved}
                norm_map: dict[str, list] = {}
                for t in unresolved:
                    key = _norm_key(t.display_title)
                    if key:
                        norm_map.setdefault(key, []).append(t)

                for pattern in ("*.flac", "*.m4a", "*.mp3"):
                    for candidate_path in base_root.rglob(pattern):
                        for stem in _stem_variants(candidate_path.stem):
                            hit = exact_map.pop(stem, None)
                            if hit is not None:
                                hit.file_path = candidate_path.resolve()
                                break

                            key = _norm_key(stem)
                            bucket = norm_map.get(key)
                            if bucket:
                                track = bucket.pop(0)
                                track.file_path = candidate_path.resolve()
                                if not bucket:
                                    norm_map.pop(key, None)
                                break
                        if not exact_map and not norm_map:
                            break
                    if not exact_map and not norm_map:
                        break

        if dry_run:
            for track in tracks:
                if track.failed:
                    classification = classify_failure_reason(track.failure_reason)
                    reason = (track.failure_reason or "").strip()
                    click.echo(f"[failed/{classification}] {track.display_title} — {reason}".rstrip(" —"))
                    continue
                click.echo(
                    f"[would-ingest] {track.display_title} ({track.isrc or 'no ISRC'}) via {track.provider} -> {track.file_path or 'no path'}"
                )
            return

        try:
            resolution = resolve_cli_env_db_path(
                None,
                purpose="write",
                allow_repo_db=False,
                source_label="TAGSLUT_DB",
            )
        except DbResolutionError as exc:
            raise click.ClickException(str(exc)) from exc

        conn = open_db(resolution)
        try:
            init_db(conn)
            now_iso = datetime.now(timezone.utc).isoformat()
            ingestion_source_prefix = f"spotiflac_log:{log_path.name}"

            ingest_ok = 0
            skipped_missing = 0
            failed_total = 0
            retryable = 0
            mp3_sources: list[Path] = []

            dual_write_v3 = dual_write_enabled()

            with conn:
                for track in tracks:
                    if track.failed:
                        failed_total += 1
                        classification = classify_failure_reason(track.failure_reason)
                        if classification == "retryable":
                            retryable += 1
                        reason = (track.failure_reason or "").strip()
                        click.echo(
                            f"[failed/{classification}] {track.display_title} — {reason}".rstrip(" —")
                        )
                        continue

                    if track.file_path is None:
                        continue

                    file_path = track.file_path
                    if base_root is not None and not file_path.is_absolute():
                        file_path = (base_root / file_path).resolve()

                    if not file_path.exists():
                        click.secho(
                            f"[warning] missing file; skipping: {file_path}",
                            fg="yellow",
                            err=True,
                        )
                        skipped_missing += 1
                        continue

                    existing = get_file(conn, file_path)
                    if existing is not None:
                        click.secho(
                            f"[warning] already indexed; skipping: {file_path}",
                            fg="yellow",
                            err=True,
                        )
                        continue

                    audio = extract_metadata(
                        file_path,
                        scan_integrity=False,
                        scan_hash=False,
                        library="default",
                        zone_manager=None,
                    )
                    audio.original_path = file_path

                    checksum = audio.checksum
                    sha256 = audio.sha256
                    streaminfo_md5 = audio.streaminfo_md5
                    if (not streaminfo_md5) and (not sha256):
                        sha256 = calculate_file_hash(file_path)
                        checksum = sha256

                    zone_value = audio.zone.value if audio.zone else "staging"
                    metadata_json = json.dumps(audio.metadata or {}, ensure_ascii=False, sort_keys=True)
                    flac_ok_value = None if audio.flac_ok is None else int(bool(audio.flac_ok))

                    download_source = f"spotiflac:{track.provider}"

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
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
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
                            download_source,
                            now_iso,
                            str(file_path),
                            "new",
                            0,
                            None,
                            None,
                            None,
                            None,
                            None,
                            None,
                            None,
                            None,
                            None,
                        ),
                    )

                    if dual_write_v3:
                        provider_hints: dict[str, str] = {}
                        if track.isrc:
                            provider_hints["isrc"] = track.isrc
                        if track.spotify_id:
                            provider_hints["spotify_album_id"] = track.spotify_id
                        if track.qobuz_album_id:
                            provider_hints["qobuz_album_id"] = track.qobuz_album_id
                        if track.tidal_album_id:
                            provider_hints["tidal_album_id"] = track.tidal_album_id
                        provider_hints = provider_hints if provider_hints else None

                        ingestion_method_override = (
                            "provider_api" if track.provider != "unknown" else "spotiflac_fallback"
                        )
                        ingestion_source_override = ingestion_source_prefix
                        if track.album_source_url:
                            ingestion_source_override = (
                                f"{ingestion_source_prefix}|source:{track.album_source_url}"
                            )
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
                            download_source=download_source,
                            download_date=now_iso,
                            mgmt_status="new",
                            metadata=audio.metadata or {},
                            duration_ref_ms=None,
                            duration_ref_source=None,
                            event_time=now_iso,
                            download_source_override=download_source,
                            ingestion_method_override=ingestion_method_override,
                            ingestion_source_override=ingestion_source_override,
                            ingestion_confidence_override="high",
                            provider_id_hints=provider_hints,
                        )

                    ingest_ok += 1
                    if file_path.suffix.lower() == ".mp3":
                        mp3_sources.append(file_path)
                    click.echo(
                        f"[ingested] {track.display_title} ({track.isrc or 'no ISRC'}) via {track.provider}"
                    )

            if mp3_sources:
                mp3_library = Path(os.environ.get("MP3_LIBRARY", "/Volumes/MUSIC/MP3_LIBRARY"))
                if not mp3_library.exists():
                    click.secho(
                        "[warning] MP3_LIBRARY not mounted; skipping MP3 copy and M3U steps",
                        fg="yellow",
                        err=True,
                    )
                else:
                    mp3_destinations: list[Path] = []
                    wrote_any = False
                    for src_path in mp3_sources:
                        dest_path = mp3_library / src_path.name
                        mp3_destinations.append(dest_path)
                        if not dest_path.exists():
                            shutil.copy2(src_path, dest_path)
                            wrote_any = True

                    if wrote_any:
                        ingest_logs_dir = Path("_ingest/spotiflac_logs")
                        ingest_logs_dir.mkdir(parents=True, exist_ok=True)
                        batch_m3u_path = ingest_logs_dir / f"{log_path.stem}__mp3.m3u"
                        batch_m3u_path.write_text(
                            "\n".join(str(path) for path in mp3_destinations) + "\n",
                            encoding="utf-8",
                        )

                        dj_pool_path = Path(
                            os.environ.get("DJ_POOL_M3U", "/Volumes/MUSIC/MP3_LIBRARY/dj_pool.m3u")
                        )
                        existing_entries: set[str] = set()
                        if dj_pool_path.exists():
                            existing_entries = {
                                line.strip()
                                for line in dj_pool_path.read_text(encoding="utf-8").splitlines()
                                if line.strip()
                            }
                        to_append = [str(path) for path in mp3_destinations if str(path) not in existing_entries]
                        if to_append:
                            dj_pool_path.parent.mkdir(parents=True, exist_ok=True)
                            with dj_pool_path.open("a", encoding="utf-8") as handle:
                                for entry in to_append:
                                    handle.write(entry + "\n")

            click.echo(
                f"{ingest_ok} ingested, {skipped_missing} skipped (file not found), {failed_total} failed ({retryable} retryable)"
            )
        finally:
            conn.close()

    @intake.command("resolve")
    @click.option("--db", "db_path", required=True, type=click.Path(), help="Path to tagslut DB")
    @click.option("--input", "input_path", type=click.Path(), help="Input JSONL file with track metadata")
    @click.option("--url", help="URL to JSONL track metadata")
    @click.option(
        "--output",
        type=click.Path(),
        help="Manifest output path (default: artifacts/intake_manifest_*.json)",
    )
    def intake_resolve(db_path, input_path, url, output):  # type: ignore  # TODO: mypy-strict
        """Resolve playlist intents against inventory and build NEW/UPGRADE/SKIP manifest."""
        manifest, output_path = _build_and_write_manifest(
            db_path=db_path,
            input_path=input_path,
            url=url,
            output=output,
        )
        click.echo(manifest.summary())
        click.echo(f"Manifest JSON: {output_path}")

    @intake.command("run")
    @click.option("--db", "db_path", required=True, type=click.Path(), help="Path to tagslut DB")
    @click.option("--manifest", "manifest_path", type=click.Path(), help="Existing manifest JSON path")
    @click.option("--input", "input_path", type=click.Path(), help="Input JSONL file (if manifest not provided)")
    @click.option("--url", help="URL to JSONL track metadata (if manifest not provided)")
    @click.option("--output", type=click.Path(), help="Manifest output path when building")
    @click.option(
        "--verbose",
        "-v",
        is_flag=True,
        default=False,
        help="Print per-item progress to stderr.",
    )
    def intake_run(db_path, manifest_path, input_path, url, output, verbose):  # type: ignore  # TODO: mypy-strict
        """Run intake plan: print downloader commands for NEW + UPGRADE manifest entries."""
        from tagslut.cli._progress import make_progress_cb

        if manifest_path:
            manifest_data = json.loads(Path(manifest_path).expanduser().resolve().read_text(encoding="utf-8"))
            new_entries = list(manifest_data.get("new", []))
            upgrade_entries = list(manifest_data.get("upgrades", []))
            summary = manifest_data.get("summary", "Manifest loaded")
            resolved_path = Path(manifest_path).expanduser().resolve()
        else:
            manifest, resolved_path = _build_and_write_manifest(
                db_path=db_path,
                input_path=input_path,
                url=url,
                output=output,
            )
            manifest_data = manifest.to_dict()
            new_entries = list(manifest_data["new"])
            upgrade_entries = list(manifest_data["upgrades"])
            summary = manifest.summary()

        click.echo(summary)
        click.echo(f"Manifest JSON: {resolved_path}")

        download_entries = [*new_entries, *upgrade_entries]
        if not download_entries:
            click.echo("No downloads needed.")
            return

        click.echo("\nPlanned download commands:")
        cb = make_progress_cb(bool(verbose))
        total = len(download_entries)
        for idx, entry in enumerate(download_entries, start=1):
            intent_dict = entry.get("track_intent", {})
            ref = _intent_reference(intent_dict)
            action = entry.get("action", "new").upper()
            click.echo(f"  # {action}")
            click.echo(f"  tools/get \"{ref}\"")
            if cb is not None:
                artist = (intent_dict.get("artist") or "").strip()
                title = (intent_dict.get("title") or "").strip()
                label = f"{artist} – {title}" if artist and title else ref
                cb(label, idx, total)

    @intake.command("prefilter", context_settings=WRAPPER_CONTEXT)
    @click.argument("args", nargs=-1, type=click.UNPROCESSED)
    def intake_prefilter(args):  # type: ignore  # TODO: mypy-strict
        """Run Beatport prefilter against inventory DB."""
        run_python_script("tools/review/beatport_prefilter.py", args)

    @intake.command("process-root")
    @click.option("--db", "db_path", type=click.Path(), help="DB path (or set TAGSLUT_DB)")
    @click.option(
        "--root",
        required=True,
        type=click.Path(exists=True, file_okay=False),
        help="Root folder to process",
    )
    @click.option("--library", type=click.Path(), help="Library destination")
    @click.option("--providers", default="beatport,tidal")
    @click.option("--force", is_flag=True, help="Force re-enrichment")
    @click.option("--no-art", is_flag=True, help="Skip cover art embedding")
    @click.option("--art-force", is_flag=True, help="Force replace embedded art")
    @click.option("--trust", type=int, default=3, help="Pre-scan trust (0-3). Default: 3")
    @click.option("--trust-post", type=int, default=3, help="Post-scan trust (0-3). Default: 3")
    @click.option(
        "--phases",
        help="Comma-separated phases: register,integrity,hash,identify,enrich,art,promote,dj",
    )
    @click.option(
        "--scan-only",
        is_flag=True,
        help="Shortcut for --phases=register,integrity,hash",
    )
    @click.option(
        "--allow-duplicate-hash",
        is_flag=True,
        help="Allow moving files even if identical hash exists in library",
    )
    @click.option(
        "--use-preferred-asset/--no-use-preferred-asset",
        default=None,
        help="Use preferred_asset during promote phase (auto when omitted).",
    )
    @click.option(
        "--require-preferred-asset",
        is_flag=True,
        help="Skip identities without preferred asset under root during promote phase.",
    )
    @click.option(
        "--allow-multiple-per-identity",
        is_flag=True,
        help="Allow promoting multiple assets per identity during promote phase.",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Preview enrichment and transcode without writing files.",
    )
    def intake_process_root(  # type: ignore[no-untyped-def]  # TODO: mypy-strict
        db_path,
        root: str,
        library: str | None,
        providers,
        force,
        no_art,
        art_force,
        trust,
        trust_post,
        phases,
        scan_only,
        allow_duplicate_hash,
        use_preferred_asset,
        require_preferred_asset,
        allow_multiple_per_identity,
        dry_run,
    ):
        """Run end-to-end root processing pipeline (canonical wrapper for tools/review/process_root.py)."""
        try:
            resolution = resolve_cli_env_db_path(db_path, purpose="write", source_label="--db")
        except DbResolutionError as exc:
            raise click.ClickException(str(exc)) from exc

        root_path = Path(root)
        library_path = Path(library) if library is not None else None

        args: list[str] = [
            "--db",
            str(resolution.path),
            "--root",
            str(root_path),
            "--providers",
            str(providers),
            "--trust",
            str(trust),
            "--trust-post",
            str(trust_post),
        ]
        if library_path is not None:
            args.extend(["--library", str(library_path)])
        if force:
            args.append("--force")
        if no_art:
            args.append("--no-art")
        if art_force:
            args.append("--art-force")
        if phases:
            args.extend(["--phases", str(phases)])
        if scan_only:
            args.append("--scan-only")
        if allow_duplicate_hash:
            args.append("--allow-duplicate-hash")
        if use_preferred_asset is True:
            args.append("--use-preferred-asset")
        elif use_preferred_asset is False:
            args.append("--no-use-preferred-asset")
        if require_preferred_asset:
            args.append("--require-preferred-asset")
        if allow_multiple_per_identity:
            args.append("--allow-multiple-per-identity")
        if dry_run:
            args.append("--dry-run")

        run_python_script("tools/review/process_root.py", tuple(args))
