from __future__ import annotations

import csv
import io
import json
import logging
import os
from collections import Counter
from pathlib import Path
from typing import Iterable

import click

from tagslut.cli.dj_role import role_group
from tagslut.dj.curation import load_dj_curation_config, resolve_track_override
from tagslut.dj.export import get_audio_duration, plan_export, run_export
from tagslut.dj.lexicon import (
    build_location_map,
    estimate_tags,
    load_lexicon_tracks,
    push_to_lexicon_api,
    resolve_location,
    write_lexicon_csv,
)
from tagslut.dj.classify import (
    append_overrides,
    classify_tracks,
    promote_safe_tracks,
    write_m3u,
)
from tagslut.dj.rekordbox_prep import run_rekordbox_prep
from tagslut.dj.transcode import (
    TrackRow,
    assign_output_paths,
    dedupe_tracks,
    load_tracks,
    make_dedupe_key,
    sanitize_component,
)
from tagslut.cli.runtime import run_python_script

logger = logging.getLogger(__name__)

DEFAULT_POLICY = "config/dj/dj_curation_usb_v8.yaml"
DEFAULT_OUTPUT = os.environ.get("DJ_OUTPUT_ROOT", "./output/dj_yes")
DEFAULT_INPUT = os.environ.get("DJ_XLSX", "./input/DJ_YES.xlsx")
DEFAULT_DJUSB = os.environ.get("DJ_USB_ROOT", "./output/dj_usb")
TRACK_OVERRIDES_PATH = Path("config/dj/track_overrides.csv")


def _normalize_crate(value: str) -> str:
    return value.strip().lower()


def _parse_crates(value: str) -> list[str]:
    return [crate.strip() for crate in value.split(",") if crate.strip()]


def _crate_matches(crate_name: str, crate_field: str) -> bool:
    target = _normalize_crate(crate_name)
    return any(_normalize_crate(crate) == target for crate in _parse_crates(crate_field))


def _select_tracks_with_overrides(
    tracks: list,  # type: ignore  # TODO: mypy-strict
    *,
    safe_only: bool,
    crate: str | None,
) -> tuple[list, int]:  # type: ignore  # TODO: mypy-strict
    selected: list = []  # type: ignore  # TODO: mypy-strict
    skipped = 0
    for track in tracks:
        override = resolve_track_override(
            path=str(track.source_path),
            artist=track.track_artist or track.album_artist,
            title=track.title,
        )
        if override is None:
            skipped += 1
            continue
        verdict = str(override.get("verdict") or "").lower()
        if verdict == "block":
            skipped += 1
            continue
        if safe_only and verdict != "safe":
            skipped += 1
            continue
        crate_field = str(override.get("crate") or "")
        if crate and not _crate_matches(crate, crate_field):
            skipped += 1
            continue
        selected.append(track)
    return selected, skipped


def _load_override_items(path: Path) -> list[tuple[str, object]]:
    if not path.exists():
        return []
    items: list[tuple[str, object]] = []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in lines:
        if not line.strip():
            continue
        if line.lstrip().startswith("#"):
            items.append(("comment", line))
            continue
        row = next(csv.reader([line]))
        while len(row) < 6:
            row.append("")
        items.append(("row", row))
    return items


def _write_override_items(path: Path, items: list[tuple[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        for kind, payload in items:
            if kind == "comment":
                handle.write(str(payload).rstrip("\n") + "\n")
                continue
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(payload)  # type: ignore  # TODO: mypy-strict
            handle.write(output.getvalue())


def _iter_override_rows(items: list[tuple[str, object]]) -> Iterable[list[str]]:
    for kind, payload in items:
        if kind == "row":
            yield payload  # type: ignore[misc]


def _read_key_from_file(path: Path) -> str | None:
    try:
        from mutagen import File as MutagenFile  # type: ignore
    except Exception as e:
        logger.debug("mutagen import unavailable while reading key for %s: %s", path, e)
        return None

    try:
        audio = MutagenFile(path, easy=False)
    except Exception as e:
        logger.debug("Failed to read key tags for %s: %s", path, e)
        return None
    if audio is None:
        return None
    for tag in ("TKEY", "KEY", "key", "initialkey", "INITIALKEY"):
        if tag in audio:
            value = audio[tag]
            if isinstance(value, list):
                return str(value[0]) if value else None
            return str(value)
    return None


def _load_tracks_from_overrides(
    *,
    safe_only: bool,
    crate: str | None,
) -> list:  # type: ignore  # TODO: mypy-strict
    items = _load_override_items(TRACK_OVERRIDES_PATH)
    rows = list(_iter_override_rows(items))
    tracks = []
    row_num = 1
    for row in rows:
        if len(row) < 6:
            continue
        path_value = row[0].strip()
        artist = row[1].strip()
        title = row[2].strip()
        verdict = row[3].strip().lower() if len(row) > 3 else ""
        crate_field = row[5].strip() if len(row) > 5 else ""

        if not path_value or not artist or not title:
            continue
        if verdict == "block":
            continue
        if safe_only and verdict != "safe":
            continue
        if crate and not _crate_matches(crate, crate_field):
            continue

        track = TrackRow(
            row_num=row_num,
            album_artist=artist,
            album="",
            track_number=None,
            title=title,
            track_artist=artist,
            external_id="",
            source="override",
            source_path=Path(path_value),
            dedupe_key=("",),
        )
        track.dedupe_key = make_dedupe_key(track)
        tracks.append(track)
        row_num += 1
    return tracks


def _format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "n/a"
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins}:{secs:02d}"


def _prompt_choice() -> str:
    try:
        return click.getchar().upper()
    except Exception as e:
        logger.debug("Failed to read interactive prompt choice: %s", e)
        return ""


def _lexicon_tracks(output_root: Path) -> list[dict]:  # type: ignore  # TODO: mypy-strict
    lexicon_tracks = load_lexicon_tracks(TRACK_OVERRIDES_PATH)
    manifest = build_location_map(output_root)
    output: list[dict] = []  # type: ignore  # TODO: mypy-strict
    for track in lexicon_tracks:
        item = {
            "path": track.path,
            "artist": track.artist,
            "title": track.title,
            "crate": track.crate,
            "bpm": track.bpm,
            "key": track.key,
            "genre": track.genre,
            "duration_sec": track.duration_sec,
        }
        item["location"] = resolve_location(item, output_root, manifest)
        output.append(item)
    return output


@click.group(
    "dj",
    help="""
\b
DJ library operations (Stages 3 and 4 of the 4-stage pipeline).

Stages:
    Stage 1: intake     → Refresh canonical masters via tagslut intake
    Stage 2: mp3        → Build or reconcile MP3 derivatives
    Stage 3: admit      → Select tracks for DJ library
                     backfill   → Auto-admit verified MP3s
                     validate   → Verify DJ library state
  Stage 4: xml emit  → Generate Rekordbox XML
           xml patch → Update prior XML after changes

Common subcommands:
  admit, backfill, validate, xml emit, xml patch

Prerequisite: Stages 1 and 2 (tagslut intake, then tagslut mp3 reconcile or tagslut mp3 build)

See: docs/DJ_PIPELINE.md
""",
    epilog="""
\b
Example workflow:
    1. tagslut intake <provider-url>
    2. tagslut mp3 reconcile --db <path> --mp3-root <path>
    3. tagslut dj backfill --db <path>
    4. tagslut dj validate --db <path>
    5. tagslut dj xml emit --db <path> --out rekordbox.xml

Quick example:
  tagslut dj backfill --db <path>

Docs: docs/DJ_PIPELINE.md
""",
)
def dj_group() -> None:
    """DJ library curation and USB export commands."""


dj_group.add_command(role_group, name="role")


@dj_group.command("curate")
@click.option(
    "--input-xlsx",
    type=click.Path(exists=True),
    default=DEFAULT_INPUT,
    help="Source XLSX manifest",
)
@click.option("--sheet", default=None, help="Worksheet name (default: first sheet)")
@click.option(
    "--policy",
    "policy_path",
    default=DEFAULT_POLICY,
    help="DJ curation policy YAML",
)
@click.option(
    "--output-root",
    type=click.Path(),
    default=DEFAULT_OUTPUT,
    help="Output root for transcoded files",
)
@click.option("--json-output", is_flag=True, help="Output results as JSON")
def curate(
    input_xlsx: str,
    sheet: str | None,
    policy_path: str,
    output_root: str,
    json_output: bool,
) -> None:
    """Preview which tracks pass DJ curation filters (dry run)."""
    config = load_dj_curation_config(policy_path)
    tracks, dropped_missing, _ = load_tracks(Path(input_xlsx), sheet)
    deduped, dropped_dupes = dedupe_tracks(tracks)
    assign_output_paths(deduped, Path(output_root))

    plan = plan_export(deduped, config, Path(output_root))
    stats = plan.stats

    result = {
        "input_tracks": len(tracks),
        "after_dedup": len(deduped),
        "passed_curation": stats.passed_curation,
        "rejected_curation": stats.rejected_curation,
        "flagged_for_review": len(plan.curation_result.flagged_reviewlist)
        if plan.curation_result
        else 0,
        "dropped_missing_on_disk": len(dropped_missing),
        "dropped_duplicates": len(dropped_dupes),
    }

    if json_output:
        click.echo(json.dumps(result, indent=2))
    else:
        click.echo(f"Input tracks:        {result['input_tracks']}")
        click.echo(f"After dedup:         {result['after_dedup']}")
        click.echo(f"Passed curation:     {result['passed_curation']}")
        click.echo(f"Rejected:            {result['rejected_curation']}")
        click.echo(f"Review flagged:      {result['flagged_for_review']}")
        click.echo(f"Missing on disk:     {result['dropped_missing_on_disk']}")


@dj_group.command("export")
@click.option(
    "--input-xlsx",
    type=click.Path(exists=True),
    default=DEFAULT_INPUT,
    help="Source XLSX manifest",
)
@click.option("--sheet", default=None, help="Worksheet name")
@click.option(
    "--policy",
    "policy_path",
    default=DEFAULT_POLICY,
    help="DJ curation policy YAML",
)
@click.option(
    "--output-root",
    type=click.Path(),
    default=DEFAULT_OUTPUT,
    help="Export destination root",
)
@click.option("--jobs", default=4, show_default=True, help="Parallel transcode workers")
@click.option("--overwrite", is_flag=True, help="Overwrite existing files")
@click.option("--detect-keys", is_flag=True, help="Run KeyFinder key detection")
@click.option(
    "--transcode-timeout-s",
    type=int,
    default=None,
    help="Per-track ffmpeg timeout in seconds (overrides DJ_TRANSCODE_TIMEOUT_S)",
)
@click.option("--fail-fast", is_flag=True, help="Stop after the first transcode failure")
@click.option("--dry-run", is_flag=True, help="Plan only, no transcoding")
@click.option("--verbose", is_flag=True, help="Show planned output paths")
@click.option(
    "--safe",
    "safe_only",
    is_flag=True,
    help="Only export tracks marked safe in track_overrides.csv",
)
@click.option("--crate", "crate_name", default=None, help="Filter to a specific crate")
def export(
    input_xlsx: str,
    sheet: str | None,
    policy_path: str,
    output_root: str,
    jobs: int,
    overwrite: bool,
    detect_keys: bool,
    transcode_timeout_s: int | None,
    fail_fast: bool,
    dry_run: bool,
    verbose: bool,
    safe_only: bool,
    crate_name: str | None,
) -> None:
    """Curate and transcode DJ library to USB output root."""
    click.echo("Loading tracks...")
    config = load_dj_curation_config(policy_path)
    if safe_only or crate_name:
        tracks = _load_tracks_from_overrides(safe_only=safe_only, crate=crate_name)
        dropped_missing = []  # type: ignore  # TODO: mypy-strict
        dropped_dupes = []  # type: ignore  # TODO: mypy-strict
        deduped = tracks
    else:
        tracks, dropped_missing, _ = load_tracks(Path(input_xlsx), sheet, check_paths=True)
        deduped, dropped_dupes = dedupe_tracks(tracks)

    export_root = Path(output_root)
    if crate_name:
        export_root = export_root / sanitize_component(crate_name, crate_name)

    assign_output_paths(deduped, export_root)

    if verbose:
        click.echo("Planned output paths (first 5):")
        for track in deduped[:5]:
            click.echo(f"- {track.output_path}")

    skipped = 0
    if safe_only or crate_name:
        if not deduped:
            click.echo("No tracks matched the requested safe/crate filters.")
            return

    if dry_run:
        click.echo("Dry run mode — no transcoding will occur")

    total_ref = [0]

    def progress(completed: int, total: int) -> None:
        if total_ref[0] != total:
            total_ref[0] = total
        if completed % 50 == 0 or completed == total:
            click.echo(f"Progress: {completed}/{total}")

    stats = run_export(
        deduped,
        config,
        export_root,
        jobs=jobs,
        overwrite=overwrite,
        detect_keys=detect_keys,
        dry_run=dry_run,
        safe_mode=safe_only,
        transcode_timeout_s=transcode_timeout_s,
        fail_fast=fail_fast,
        progress_callback=progress,
    )

    click.echo("")
    click.echo(f"Total candidates:  {stats.total_candidates}")
    click.echo(f"Passed curation:   {stats.passed_curation}")
    click.echo(f"Rejected:          {stats.rejected_curation}")
    click.echo(f"Dropped missing:   {len(dropped_missing)}")
    click.echo(f"Dropped dupes:     {len(dropped_dupes)}")
    if not dry_run:
        click.echo(f"Transcoded OK:     {stats.transcoded_ok}")
        click.echo(f"Skipped existing:  {stats.transcoded_skipped}")
        click.echo(f"Missing source:    {stats.missing_source}")
        click.echo(f"Failed:            {stats.transcoded_failed}")
    else:
        click.echo("(Dry run — transcoding skipped)")
        click.echo(f"Missing source:    {stats.missing_source}")

    if safe_only:
        click.echo(f"Exported {len(deduped)} tracks. {skipped} skipped (not yet classified).")


@dj_group.command("prep-rekordbox")
@click.option(
    "--root",
    "root_path",
    required=True,
    type=click.Path(exists=True, file_okay=False),
    help="Curated DJ source folder to scan recursively.",
)
@click.option(
    "--out",
    "out_path",
    required=True,
    type=click.Path(file_okay=False),
    help="Output mirror folder (MP3 CBR 320, 44.1kHz, ID3v2.3, embedded cover).",
)
@click.option(
    "--quarantine",
    "quarantine_path",
    required=True,
    type=click.Path(file_okay=False),
    help="Quarantine folder for replaced originals.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Plan only; recommended first run for safety.",
)
def prep_rekordbox(
    root_path: str,
    out_path: str,
    quarantine_path: str,
    dry_run: bool,
) -> None:
    """Prepare a curated folder for Rekordbox. Use --dry-run first (recommended)."""
    try:
        result = run_rekordbox_prep(
            root=Path(root_path).expanduser().resolve(),
            out=Path(out_path).expanduser().resolve(),
            quarantine=Path(quarantine_path).expanduser().resolve(),
            dry_run=dry_run,
        )
    except (FileNotFoundError, RuntimeError) as exc:
        raise click.ClickException(str(exc)) from exc

    if result.stdout.strip():
        click.echo(result.stdout.rstrip())
    if result.stderr.strip():
        click.echo(result.stderr.rstrip(), err=True)

    summary = result.summary
    click.echo("")
    click.echo("Rekordbox prep summary:")
    click.echo(f"Tracks processed:   {summary.tracks_processed}")
    click.echo(f"SUSPECT_UPSCALE:   {summary.suspect_upscale_count}")
    click.echo(f"Files quarantined: {summary.files_quarantined}")
    click.echo(f"CSV report:        {summary.report_path}")
    if dry_run and not summary.report_path.exists():
        click.echo("Dry run: upstream script does not write the CSV report file.")


@dj_group.group("lexicon")
def lexicon_group() -> None:
    """Estimate and export Lexicon tags for DJ tracks."""


@lexicon_group.command("status")
@click.option(
    "--output-root",
    type=click.Path(),
    default=DEFAULT_DJUSB,
    help="Export root containing export_manifest.jsonl",
)
def lexicon_status(output_root: str) -> None:
    tracks = _lexicon_tracks(Path(output_root))
    counts = {"high": 0, "medium": 0, "low": 0}
    for track in tracks:
        tags = estimate_tags(track)
        counts[tags["confidence"]] = counts.get(tags["confidence"], 0) + 1
    click.echo(f"High confidence:   {counts['high']}")
    click.echo(f"Medium confidence: {counts['medium']}")
    click.echo(f"Low confidence:    {counts['low']}")


@lexicon_group.command("estimate")
@click.option(
    "--output-root",
    type=click.Path(),
    default=DEFAULT_DJUSB,
    help="Export root containing export_manifest.jsonl",
)
def lexicon_estimate(output_root: str) -> None:
    tracks = _lexicon_tracks(Path(output_root))
    if not tracks:
        click.echo("No safe tracks found in track_overrides.csv.")
        return

    click.echo("Artist | Title | BPM | Energy | Danceability | Happiness | Confidence")
    for track in tracks[:20]:
        tags = estimate_tags(track)
        bpm = track.get("bpm")
        bpm_display = f"{int(round(bpm))}" if isinstance(bpm, (int, float)) else "n/a"
        artist = str(track.get("artist") or "")[:24]
        title = str(track.get("title") or "")[:28]
        click.echo(
            f"{artist:24} | {title:28} | {bpm_display:>3} | "
            f"{tags['Energy']:>6} | {tags['Danceability']:>12} | "
            f"{tags['Happiness']:>9} | {tags['confidence']}"
        )


@lexicon_group.command("csv")
@click.option(
    "--output",
    "output_path",
    type=click.Path(),
    default="config/dj/lexicon_import.csv",
    help="Output CSV path for Lexicon import",
)
@click.option(
    "--output-root",
    type=click.Path(),
    default=DEFAULT_DJUSB,
    help="Export root containing export_manifest.jsonl",
)
def lexicon_csv(output_path: str, output_root: str) -> None:
    tracks = _lexicon_tracks(Path(output_root))
    count = write_lexicon_csv(tracks, Path(output_path), Path(output_root))
    click.echo(f"Written {count} tracks to {output_path}")
    click.echo("Import via: Lexicon → Utility → Import Tags From CSV")


@lexicon_group.command("push")
@click.option("--dry-run", is_flag=True, help="Show what would be pushed, no writes")
@click.option(
    "--only-high-confidence",
    is_flag=True,
    help="Only push tracks with high confidence estimates",
)
@click.option(
    "--output-root",
    type=click.Path(),
    default=DEFAULT_DJUSB,
    help="Export root containing export_manifest.jsonl",
)
def lexicon_push(dry_run: bool, only_high_confidence: bool, output_root: str) -> None:
    tracks = _lexicon_tracks(Path(output_root))
    if not tracks:
        click.echo("No safe tracks found in track_overrides.csv.")
        return

    if dry_run:
        preview = tracks[:10]
        click.echo("Dry run — previewing first 10 tracks:")
        for track in preview:
            tags = estimate_tags(track)
            click.echo(
                f"{track.get('artist')} — {track.get('title')} | "
                f"{tags['Energy']}/{tags['Danceability']}/{tags['Happiness']} "
                f"({tags['confidence']})"
            )

    result = push_to_lexicon_api(
        tracks,
        only_high=only_high_confidence,
        dry_run=dry_run,
    )
    click.echo(
        f"Pushed: {result['pushed']} | Skipped: {result['skipped']} | Failed: {result['failed']}")


@dj_group.command("classify")
@click.option("--input", "input_path", required=True, type=click.Path(), help="Input XLSX, folder, or M3U")
@click.option(
    "--policy",
    "policy_path",
    default=DEFAULT_POLICY,
    help="DJ curation policy YAML",
)
@click.option("--output-crates", is_flag=True, help="Write safe/review crates as M3U")
@click.option(
    "--append-overrides/--no-append-overrides",
    "append_overrides_flag",
    default=True,
    help="Append safe/block decisions to track_overrides.csv",
)
@click.option("--promote", is_flag=True, help="Promote safe tracks to DJUSB (transcode to MP3)")
@click.option(
    "--output-root",
    type=click.Path(),
    default=DEFAULT_DJUSB,
    help="DJUSB output root for promotion",
)
@click.option("--jobs", default=4, show_default=True, help="Parallel transcode workers")
@click.option("--overwrite", is_flag=True, help="Overwrite existing MP3s during promote")
def dj_classify(
    input_path: str,
    policy_path: str,
    output_crates: bool,
    append_overrides_flag: bool,
    promote: bool,
    output_root: str,
    jobs: int,
    overwrite: bool,
) -> None:
    """Score tracks and classify into safe/block/review buckets."""
    config = load_dj_curation_config(policy_path)
    safe, block, review = classify_tracks(Path(input_path), config)

    if output_crates:
        crates_dir = Path("config/dj/crates")
        write_m3u(crates_dir / "safe.m3u8", safe)
        write_m3u(crates_dir / "review.m3u8", review)
        write_m3u(crates_dir / "block.m3u8", block)

    appended = 0
    if append_overrides_flag:
        appended += append_overrides(Path("config/dj/track_overrides.csv"), safe)
        appended += append_overrides(Path("config/dj/track_overrides.csv"), block)

    click.echo(f"Safe:   {len(safe)}")
    click.echo(f"Block:  {len(block)}")
    click.echo(f"Review: {len(review)}")
    if append_overrides_flag:
        click.echo(f"Overrides appended: {appended}")
    if promote and safe:
        ok, skipped, failed = promote_safe_tracks(
            safe,
            Path(output_root),
            jobs=jobs,
            overwrite=overwrite,
        )
        click.echo(f"Promoted to DJUSB: {ok} ok, {skipped} skipped, {failed} failed")


@dj_group.command("review-app")
@click.option("--db", "db_path", type=click.Path(), default=None, help="SQLite DB path")
@click.option("--library-prefix", default=None, help="Filter files by path prefix")
@click.option("--host", default=None, help="Host to bind (default: 127.0.0.1)")
@click.option("--port", type=int, default=None, help="Port to bind (default: 5055)")
@click.option("--no-open", is_flag=True, help="Do not open browser on launch")
def review_app(
    db_path: str | None,
    library_prefix: str | None,
    host: str | None,
    port: int | None,
    no_open: bool,
) -> None:
    """Launch the DJ review web app."""
    args: list[str] = []
    if db_path:
        args.extend(["--db", db_path])
    if library_prefix:
        args.extend(["--library-prefix", library_prefix])
    if host:
        args.extend(["--host", host])
    if port:
        args.extend(["--port", str(port)])
    if no_open:
        args.append("--no-open")
    run_python_script("tools/dj_review_app.py", tuple(args))


@dj_group.command("gig-prep")
@click.option(
    "--date",
    "gig_date",
    required=True,
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Gig date in YYYY-MM-DD format",
)
@click.option("--venue", default=None, help="Optional venue name")
@click.option("--bpm-min", type=int, default=98, show_default=True, help="Minimum BPM filter")
@click.option("--bpm-max", type=int, default=130, show_default=True, help="Maximum BPM filter")
@click.option("--roles", default=None, help="Comma-separated DJ set roles to include")
@click.option(
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),  # type: ignore  # TODO: mypy-strict
    default=None,
    help="Optional output file path",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["csv", "json", "text"], case_sensitive=False),
    default="text",
    show_default=True,
    help="Output format",
)
@click.option("--db", "db_path", type=click.Path(), default=None, help="SQLite DB path (or TAGSLUT_DB env)")
def gig_prep(
    gig_date,
    venue: str | None,
    bpm_min: int,
    bpm_max: int,
    roles: str | None,
    output_path: Path | None,
    output_format: str,
    db_path: str | None,
) -> None:
    """Build a gig-ready set plan from DJ-tagged inventory."""
    import sqlite3

    from tagslut.dj.gig_prep import parse_roles_filter, run_gig_prep
    from tagslut.storage.schema import init_db
    from tagslut.utils.db import DbResolutionError, resolve_cli_env_db_path

    if bpm_min > bpm_max:
        raise click.ClickException("--bpm-min cannot be greater than --bpm-max")

    try:
        resolved_db = resolve_cli_env_db_path(db_path, purpose="write", source_label="--db").path
        roles_filter = parse_roles_filter(roles)
    except (DbResolutionError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    output_format = output_format.lower()
    normalized_date = gig_date.date()

    with sqlite3.connect(str(resolved_db)) as conn:
        conn.row_factory = sqlite3.Row
        init_db(conn)
        with conn:
            rendered = run_gig_prep(
                conn,
                gig_date=normalized_date,
                venue=venue,
                bpm_min=bpm_min,
                bpm_max=bpm_max,
                roles_filter=roles_filter,
                output_format=output_format,
                output_path=output_path,
            )

    if output_path is None:
        click.echo(rendered, nl=False)


@dj_group.group("crates")
def crates_group() -> None:
    """Manage DJ crate assignments."""


@crates_group.command("list")
def crates_list() -> None:
    items = _load_override_items(TRACK_OVERRIDES_PATH)
    rows = list(_iter_override_rows(items))
    if not rows:
        click.echo("No track overrides found.")
        return

    counts: Counter[str] = Counter()
    for row in rows:
        crate_field = row[5] if len(row) > 5 else ""
        for crate in _parse_crates(crate_field):
            counts[crate] += 1

    if not counts:
        click.echo("No crates defined.")
        return

    for crate, count in sorted(counts.items(), key=lambda item: item[0].lower()):
        click.echo(f"{crate}: {count}")


@crates_group.command("show")
@click.argument("crate_name")
def crates_show(crate_name: str) -> None:
    items = _load_override_items(TRACK_OVERRIDES_PATH)
    rows = list(_iter_override_rows(items))
    matches = [
        row
        for row in rows
        if len(row) > 5 and _crate_matches(crate_name, row[5])
    ]

    if not matches:
        click.echo(f"No tracks found in crate '{crate_name}'.")
        return

    for row in matches:
        path_value = row[0]
        artist = row[1]
        title = row[2]
        duration = None
        key = None
        if path_value:
            path = Path(path_value)
            if path.exists():
                duration = get_audio_duration(path)
                key = _read_key_from_file(path)
        duration_display = _format_duration(duration)
        key_display = key or "n/a"
        click.echo(f"{artist} — {title} | {duration_display} | {key_display}")


@crates_group.command("move")
@click.argument("from_crate")
@click.argument("to_crate")
def crates_move(from_crate: str, to_crate: str) -> None:
    items = _load_override_items(TRACK_OVERRIDES_PATH)
    if not items:
        click.echo("No track overrides found.")
        return

    moved = 0
    for row in _iter_override_rows(items):
        if len(row) < 6:
            continue
        crates = _parse_crates(row[5])
        if not crates:
            continue
        updated = False
        new_crates: list[str] = []
        for crate in crates:
            if _normalize_crate(crate) == _normalize_crate(from_crate):
                new_crates.append(to_crate)
                updated = True
            else:
                new_crates.append(crate)
        if updated:
            deduped: list[str] = []
            seen = set()
            for crate in new_crates:
                key = _normalize_crate(crate)
                if key in seen:
                    continue
                seen.add(key)
                deduped.append(crate)
            row[5] = ", ".join(deduped)
            moved += 1

    if moved == 0:
        click.echo(f"No tracks found in crate '{from_crate}'.")
        return

    if not click.confirm(f"Move {moved} tracks from '{from_crate}' to '{to_crate}'?"):
        click.echo("Aborted.")
        return

    _write_override_items(TRACK_OVERRIDES_PATH, items)
    click.echo(f"Moved {moved} tracks.")


@crates_group.command("retag")
@click.argument("crate_name")
def crates_retag(crate_name: str) -> None:
    items = _load_override_items(TRACK_OVERRIDES_PATH)
    if not items:
        click.echo("No track overrides found.")
        return

    matches = [
        row
        for row in _iter_override_rows(items)
        if len(row) > 5 and _crate_matches(crate_name, row[5])
    ]
    if not matches:
        click.echo(f"No tracks found in crate '{crate_name}'.")
        return

    updated = 0
    for row in matches:
        artist = row[1]
        title = row[2]
        verdict = row[3] if len(row) > 3 else ""
        crate_field = row[5] if len(row) > 5 else ""

        click.echo("\n" + "-" * 48)
        click.echo(f"ARTIST: {artist}")
        click.echo(f"TITLE:  \"{title}\"")
        click.echo(f"Current verdict: {verdict or 'n/a'} | Current crate: {crate_field or 'n/a'}")
        click.echo("[K] Keep  [B] Block  [R] Review  [S] Skip")
        choice = _prompt_choice()

        if choice == "S" or choice == "":
            continue

        if choice == "B":
            row[3] = "block"
            row[5] = ""
            updated += 1
            continue

        if choice in {"K", "R"}:
            row[3] = "safe" if choice == "K" else "review"
            new_crate = input("Assign crate (Enter to keep current): ").strip()
            if new_crate:
                row[5] = new_crate
            updated += 1

    if updated == 0:
        click.echo("No changes made.")
        return

    _write_override_items(TRACK_OVERRIDES_PATH, items)
    click.echo(f"Updated {updated} tracks.")


@crates_group.command("export")
@click.argument("crate_name")
@click.option(
    "--input-xlsx",
    type=click.Path(exists=True),
    default=DEFAULT_INPUT,
    help="Source XLSX manifest",
)
@click.option("--sheet", default=None, help="Worksheet name")
@click.option(
    "--policy",
    "policy_path",
    default=DEFAULT_POLICY,
    help="DJ curation policy YAML",
)
@click.option(
    "--output-root",
    type=click.Path(),
    default=DEFAULT_OUTPUT,
    help="Export destination root",
)
@click.option("--jobs", default=4, show_default=True, help="Parallel transcode workers")
@click.option("--overwrite", is_flag=True, help="Overwrite existing files")
@click.option("--detect-keys", is_flag=True, help="Run KeyFinder key detection")
@click.option("--dry-run", is_flag=True, help="Plan only, no transcoding")
def crates_export(
    crate_name: str,
    input_xlsx: str,
    sheet: str | None,
    policy_path: str,
    output_root: str,
    jobs: int,
    overwrite: bool,
    detect_keys: bool,
    dry_run: bool,
) -> None:
    """Export only the tracks in a specific crate."""
    config = load_dj_curation_config(policy_path)
    tracks, dropped_missing, _ = load_tracks(Path(input_xlsx), sheet)
    deduped, dropped_dupes = dedupe_tracks(tracks)

    export_root = Path(output_root) / sanitize_component(crate_name, crate_name)
    assign_output_paths(deduped, export_root)

    deduped, skipped = _select_tracks_with_overrides(
        deduped,
        safe_only=True,
        crate=crate_name,
    )
    if not deduped:
        click.echo(f"No tracks matched crate '{crate_name}'.")
        return

    if dry_run:
        click.echo("Dry run mode — no transcoding will occur")

    total_ref = [0]

    def progress(completed: int, total: int) -> None:
        if total_ref[0] != total:
            total_ref[0] = total
        if completed % 50 == 0 or completed == total:
            click.echo(f"Progress: {completed}/{total}")

    stats = run_export(
        deduped,
        config,
        export_root,
        jobs=jobs,
        overwrite=overwrite,
        detect_keys=detect_keys,
        dry_run=dry_run,
        safe_mode=True,
        progress_callback=progress,
    )

    click.echo("")
    click.echo(f"Crate:            {crate_name}")
    click.echo(f"Total candidates: {stats.total_candidates}")
    click.echo(f"Passed curation:  {stats.passed_curation}")
    click.echo(f"Rejected:         {stats.rejected_curation}")
    click.echo(f"Dropped missing:  {len(dropped_missing)}")
    click.echo(f"Dropped dupes:    {len(dropped_dupes)}")
    if not dry_run:
        click.echo(f"Transcoded OK:    {stats.transcoded_ok}")
        click.echo(f"Skipped existing: {stats.transcoded_skipped}")
        click.echo(f"Failed:           {stats.transcoded_failed}")
    else:
        click.echo("(Dry run — transcoding skipped)")
    click.echo(f"Skipped (unclassified): {skipped}")


@dj_group.command("pool-wizard")
@click.option(
    "--db",
    "db_path",
    type=click.Path(),
    default=None,
    help="SQLite DB path (or TAGSLUT_DB env)",
)
@click.option(
    "--master-root",
    required=True,
    type=click.Path(),
    help="MASTER_LIBRARY root path",
)
@click.option(
    "--dj-cache-root",
    required=True,
    type=click.Path(),
    help="DJ_LIBRARY cache root path",
)
@click.option(
    "--out-root",
    type=click.Path(),
    default=None,
    help="Output root for final pool (required in --non-interactive)",
)
@click.option(
    "--plan/--execute",
    "plan_mode",
    default=True,
    help="Plan only (default) or execute",
)
@click.option(
    "--profile",
    "profile_path",
    type=click.Path(),
    default=None,
    help="Read/write JSON profile of wizard answers",
)
@click.option(
    "--non-interactive",
    is_flag=True,
    help="Non-interactive mode (requires --profile and --out-root)",
)
@click.option(
    "--overwrite-run",
    is_flag=True,
    help="Overwrite existing run dir if pool_manifest.json exists",
)
def pool_wizard(
    db_path: str | None,
    master_root: str,
    dj_cache_root: str,
    out_root: str | None,
    plan_mode: bool,
    profile_path: str | None,
    non_interactive: bool,
    overwrite_run: bool,
) -> None:
    """Build a final MP3 DJ pool from MASTER_LIBRARY (plan-first, auditable)."""
    import sys

    from tagslut.exec.dj_pool_wizard import run_pool_wizard
    from tagslut.utils.db import DbResolutionError, resolve_cli_env_db_path

    try:
        resolved_db = resolve_cli_env_db_path(db_path, purpose="read", source_label="--db").path
    except DbResolutionError as exc:
        raise click.ClickException(str(exc)) from exc

    sys.exit(
        run_pool_wizard(
            db_path=resolved_db,
            master_root=master_root,
            dj_cache_root=dj_cache_root,
            out_root=out_root,
            plan_mode=plan_mode,
            profile_path=profile_path,
            non_interactive=non_interactive,
            overwrite_run=overwrite_run,
        )
    )


# ---------------------------------------------------------------------------
# dj admit
# ---------------------------------------------------------------------------


@dj_group.command(
    "admit",
    help="Admit one track into the DJ library. Stage 3a of the 4-stage pipeline.",
)
@click.option("--db", "db_path", default=None, help="Path to tagslut SQLite DB.")
@click.option(
    "--identity-id",
    required=True,
    type=int,
    help="track_identity.id to admit into the DJ library.",
)
@click.option(
    "--mp3-asset-id",
    required=True,
    type=int,
    help="mp3_asset.id to use as the preferred MP3 for this admission.",
)
@click.option("--notes", default=None, help="Optional free-text note (stored as JSON).")
def dj_admit(
    db_path: str | None,
    identity_id: int,
    mp3_asset_id: int,
    notes: str | None,
) -> None:
    """Admit a single track identity into the DJ library.

    Creates a dj_admission row linking the canonical identity to its
    preferred mp3_asset. Raises an error if the identity is already
    actively admitted.
    """
    import sqlite3

    from tagslut.dj.admission import DjAdmissionError, admit_track
    from tagslut.utils.db import DbResolutionError, resolve_cli_env_db_path

    try:
        resolved_db = resolve_cli_env_db_path(
            db_path, purpose="write", source_label="--db"
        ).path
    except DbResolutionError as exc:
        raise click.ClickException(str(exc)) from exc

    notes_dict = {"note": notes} if notes else None
    conn = sqlite3.connect(str(resolved_db))
    try:
        admission_id = admit_track(
            conn,
            identity_id=identity_id,
            mp3_asset_id=mp3_asset_id,
            notes=notes_dict,
        )
        conn.commit()
    except DjAdmissionError as exc:
        conn.close()
        raise click.ClickException(str(exc)) from exc
    finally:
        conn.close()

    click.echo(
        f"Admitted: identity_id={identity_id} mp3_asset_id={mp3_asset_id} "
        f"-> dj_admission.id={admission_id}"
    )


# ---------------------------------------------------------------------------
# dj backfill
# ---------------------------------------------------------------------------


@dj_group.command(
    "backfill",
    help="Auto-admit all verified MP3s to the DJ library. Stage 3b of the 4-stage pipeline.",
)
@click.option("--db", "db_path", default=None, help="Path to tagslut SQLite DB.")
@click.option(
    "--dry-run/--execute",
    default=True,
    show_default=True,
    help="Dry-run reports what would be admitted without writing.",
)
def dj_backfill(
    db_path: str | None,
    dry_run: bool,
) -> None:
    """Auto-admit all mp3_asset rows with status='verified' that have no dj_admission yet.

    Useful for bringing an existing MP3 library under the new DJ admission model
    after running 'tagslut mp3 reconcile'.
    """
    import sqlite3

    from tagslut.dj.admission import backfill_admissions
    from tagslut.utils.db import DbResolutionError, resolve_cli_env_db_path

    try:
        resolved_db = resolve_cli_env_db_path(
            db_path, purpose="write", source_label="--db"
        ).path
    except DbResolutionError as exc:
        raise click.ClickException(str(exc)) from exc

    conn = sqlite3.connect(str(resolved_db))
    try:
        if dry_run:
            # Count without writing
            count = conn.execute(
                """
                SELECT COUNT(*) FROM mp3_asset ma
                WHERE ma.status = 'verified'
                  AND NOT EXISTS (
                    SELECT 1 FROM dj_admission da
                    WHERE da.identity_id = ma.identity_id AND da.status = 'admitted'
                  )
                """
            ).fetchone()[0]
            conn.close()
            click.echo(f"Dry-run: {count} mp3_asset row(s) would be admitted.")
            if count > 0:
                click.secho("Pass --execute to admit them.", fg="yellow")
            return

        admitted, skipped = backfill_admissions(conn)
        conn.commit()
    finally:
        conn.close()

    click.echo(f"Backfill complete: admitted={admitted} skipped_already_active={skipped}")


# ---------------------------------------------------------------------------
# dj validate
# ---------------------------------------------------------------------------


@dj_group.command(
    "validate",
    help="Validate DJ library state. Stage 3c of the 4-stage pipeline.",
)
@click.option("--db", "db_path", default=None, help="Path to tagslut SQLite DB.")
@click.option("--verbose", "-v", is_flag=True, default=False)
def dj_validate(
    db_path: str | None,
    verbose: bool,
) -> None:
    """Validate DJ library consistency.

    Checks performed:
    - Every admitted admission's MP3 file exists on disk with status='verified'.
    - All dj_playlist_track entries reference admitted admissions.
    - Every admitted identity has non-empty title and artist metadata.

    Exits non-zero when issues are found.
    """
    import sqlite3
    import sys

    from tagslut.dj.admission import record_validation_state, validate_dj_library
    from tagslut.dj.xml_emit import _build_export_scope
    from tagslut.utils.db import DbResolutionError, resolve_cli_env_db_path

    try:
        resolved_db = resolve_cli_env_db_path(
            db_path, purpose="write", source_label="--db"
        ).path
    except DbResolutionError as exc:
        raise click.ClickException(str(exc)) from exc

    report = None
    state_hash: str | None = None
    record_warning: str | None = None
    conn = sqlite3.connect(str(resolved_db))
    try:
        report = validate_dj_library(conn)
        try:
            _scope_payload, state_hash = _build_export_scope(conn, playlist_scope=None)
            record_validation_state(
                conn,
                state_hash=state_hash,
                issue_count=len(report.issues),
                passed=report.ok,
                summary=report.summary(),
            )
            conn.commit()
        except sqlite3.OperationalError as exc:
            record_warning = (
                "WARNING: dj validation state was not recorded; "
                f"{exc}"
            )
    finally:
        conn.close()

    if record_warning:
        click.echo(record_warning, err=True)

    if report.ok:
        click.secho(report.summary(), fg="green")
        if state_hash:
            click.echo(f"state_hash: {state_hash}")
        sys.exit(0)

    click.secho(report.summary(), fg="red", err=True)
    if state_hash:
        click.echo(f"state_hash: {state_hash}", err=True)
    if not verbose:
        click.echo(
            f"  ({len(report.issues)} issue(s) — use --verbose for details)",
            err=True,
        )
    sys.exit(1)


# ---------------------------------------------------------------------------
# dj xml group
# ---------------------------------------------------------------------------


@dj_group.group(
    "xml",
    help="Stage 4 Rekordbox XML commands: emit and patch. Requires Stage 3 admissions plus dj validate.",
)
def dj_xml_group() -> None:
    """Rekordbox XML emit and patch commands."""


@dj_xml_group.command(
    "emit",
    help="Emit Rekordbox XML from admitted tracks. Stage 4a of the 4-stage pipeline.",
)
@click.option("--db", "db_path", default=None, help="Path to tagslut SQLite DB.")
@click.option(
    "--out",
    "output_path",
    required=True,
    help="Output path for the Rekordbox XML file.",
    type=click.Path(dir_okay=False, writable=True),
)
@click.option(
    "--playlist-ids",
    default=None,
    help="Comma-separated dj_playlist IDs to include (default: all).",
)
@click.option(
    "--skip-validation",
    is_flag=True,
    default=False,
    help="Skip pre-emit validation (not recommended).",
)
def dj_xml_emit(
    db_path: str | None,
    output_path: str,
    playlist_ids: str | None,
    skip_validation: bool,
) -> None:
    """Emit a full Rekordbox-compatible XML from current dj_* DB state.

    Runs pre-emit validation to ensure all admitted tracks have valid MP3
    files and metadata. Persists stable TrackIDs in dj_track_id_map so
    Rekordbox cue points survive future re-emits.

    Records export manifest in dj_export_state for patch integrity checking.
    """
    import sqlite3
    from pathlib import Path

    from tagslut.dj.xml_emit import emit_rekordbox_xml
    from tagslut.utils.db import DbResolutionError, resolve_cli_env_db_path

    try:
        resolved_db = resolve_cli_env_db_path(
            db_path, purpose="write", source_label="--db"
        ).path
    except DbResolutionError as exc:
        raise click.ClickException(str(exc)) from exc

    scope: list[int] | None = None
    if playlist_ids:
        try:
            scope = [int(x.strip()) for x in playlist_ids.split(",") if x.strip()]
        except ValueError as exc:
            raise click.ClickException(f"Invalid --playlist-ids: {exc}") from exc

    conn = sqlite3.connect(str(resolved_db))
    try:
        manifest_hash = emit_rekordbox_xml(
            conn,
            output_path=Path(output_path),
            playlist_scope=scope,
            skip_validation=skip_validation,
        )
    except ValueError as exc:
        conn.close()
        raise click.ClickException(str(exc)) from exc
    finally:
        conn.close()

    click.echo(f"Emitted: {output_path}")
    click.echo(f"  manifest_hash: {manifest_hash}")


@dj_xml_group.command(
    "patch",
    help="Patch a prior Rekordbox XML export while preserving TrackIDs. Stage 4b of the 4-stage pipeline.",
)
@click.option("--db", "db_path", default=None, help="Path to tagslut SQLite DB.")
@click.option(
    "--out",
    "output_path",
    required=True,
    help="Output path for the patched Rekordbox XML file.",
    type=click.Path(dir_okay=False, writable=True),
)
@click.option(
    "--prior-export-id",
    default=None,
    type=int,
    help="dj_export_state.id of the prior emit to patch against (default: latest).",
)
@click.option(
    "--playlist-ids",
    default=None,
    help="Comma-separated dj_playlist IDs to include (default: all).",
)
@click.option(
    "--skip-validation",
    is_flag=True,
    default=False,
    help="Skip pre-emit validation (not recommended).",
)
def dj_xml_patch(
    db_path: str | None,
    output_path: str,
    prior_export_id: int | None,
    playlist_ids: str | None,
    skip_validation: bool,
) -> None:
    """Patch a previously emitted Rekordbox XML with current dj_* DB state.

    Verifies the prior export manifest before writing. All existing TrackIDs
    are preserved from dj_track_id_map, so Rekordbox retains cue points and
    hot cues from previous imports.

    Use 'tagslut dj xml emit' for a clean initial emit.
    """
    import sqlite3
    from pathlib import Path

    from tagslut.dj.xml_emit import patch_rekordbox_xml
    from tagslut.utils.db import DbResolutionError, resolve_cli_env_db_path

    try:
        resolved_db = resolve_cli_env_db_path(
            db_path, purpose="write", source_label="--db"
        ).path
    except DbResolutionError as exc:
        raise click.ClickException(str(exc)) from exc

    scope: list[int] | None = None
    if playlist_ids:
        try:
            scope = [int(x.strip()) for x in playlist_ids.split(",") if x.strip()]
        except ValueError as exc:
            raise click.ClickException(f"Invalid --playlist-ids: {exc}") from exc

    conn = sqlite3.connect(str(resolved_db))
    try:
        manifest_hash = patch_rekordbox_xml(
            conn,
            output_path=Path(output_path),
            prior_export_id=prior_export_id,
            playlist_scope=scope,
            skip_validation=skip_validation,
        )
    except ValueError as exc:
        conn.close()
        raise click.ClickException(str(exc)) from exc
    finally:
        conn.close()

    click.echo(f"Patched: {output_path}")
    click.echo(f"  manifest_hash: {manifest_hash}")
