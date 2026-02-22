from __future__ import annotations

import json
from pathlib import Path

import click

from tagslut.dj.curation import load_dj_curation_config
from tagslut.dj.export import plan_export, run_export
from tagslut.dj.transcode import load_tracks, dedupe_tracks, assign_output_paths

DEFAULT_POLICY = "config/dj/dj_curation.yaml"
DEFAULT_OUTPUT = "/Volumes/MUSIC/DJ_YES"
DEFAULT_INPUT = "/Users/georgeskhawam/Desktop/DJ_YES.xlsx"


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
@click.option("--dry-run", is_flag=True, help="Plan only, no transcoding")
def export(
    input_xlsx: str,
    sheet: str | None,
    policy_path: str,
    output_root: str,
    jobs: int,
    overwrite: bool,
    detect_keys: bool,
    dry_run: bool,
) -> None:
    """Curate and transcode DJ library to USB output root."""
    config = load_dj_curation_config(policy_path)
    tracks, dropped_missing, _ = load_tracks(Path(input_xlsx), sheet)
    deduped, dropped_dupes = dedupe_tracks(tracks)
    assign_output_paths(deduped, Path(output_root))

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
        Path(output_root),
        jobs=jobs,
        overwrite=overwrite,
        detect_keys=detect_keys,
        dry_run=dry_run,
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
        click.echo(f"Failed:            {stats.transcoded_failed}")
    else:
        click.echo("(Dry run — transcoding skipped)")
