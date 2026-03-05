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


@click.group("dj")
def dj_group() -> None:
    """DJ library curation and USB export commands."""


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
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Curated DJ source folder to scan recursively.",
)
@click.option(
    "--out",
    "out_path",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Output mirror folder (MP3 CBR 320, 44.1kHz, ID3v2.3, embedded cover).",
)
@click.option(
    "--quarantine",
    "quarantine_path",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Quarantine folder for replaced originals.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Plan only; recommended first run for safety.",
)
def prep_rekordbox(
    root_path: Path,
    out_path: Path,
    quarantine_path: Path,
    dry_run: bool,
) -> None:
    """Prepare a curated folder for Rekordbox. Use --dry-run first (recommended)."""
    try:
        result = run_rekordbox_prep(
            root=root_path.expanduser().resolve(),
            out=out_path.expanduser().resolve(),
            quarantine=quarantine_path.expanduser().resolve(),
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
