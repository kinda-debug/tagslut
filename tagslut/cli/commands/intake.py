from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import click
import httpx

from tagslut.cli.runtime import run_python_script, WRAPPER_CONTEXT
from tagslut.core.download_manifest import DownloadManifest, build_manifest
from tagslut.filters.identity_resolver import TrackIntent
from tagslut.storage.schema import get_connection
from tagslut.utils.env_paths import get_artifacts_dir


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
        qobuz_id=(str(record["qobuz_id"]) if record.get("qobuz_id") is not None else None),
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
    for key in ["isrc", "beatport_id", "tidal_id", "qobuz_id"]:
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
    @cli.group()
    def intake():  # type: ignore  # TODO: mypy-strict
        """Canonical intake commands."""

    @intake.command("resolve")
    @click.option("--db", "db_path", required=True, type=click.Path(), help="Path to tagslut DB")
    @click.option("--input", "input_path", type=click.Path(), help="Input JSONL file with track metadata")
    @click.option("--url", help="URL to JSONL track metadata")
    @click.option("--output", type=click.Path(), help="Manifest output path (default: artifacts/intake_manifest_*.json)")
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
    def intake_run(db_path, manifest_path, input_path, url, output):  # type: ignore  # TODO: mypy-strict
        """Run intake plan: print downloader commands for NEW + UPGRADE manifest entries."""
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
        for entry in download_entries:
            intent_dict = entry.get("track_intent", {})
            ref = _intent_reference(intent_dict)
            action = entry.get("action", "new").upper()
            click.echo(f"  # {action}")
            click.echo(f"  tools/get \"{ref}\"")

    @intake.command("prefilter", context_settings=WRAPPER_CONTEXT)
    @click.argument("args", nargs=-1, type=click.UNPROCESSED)
    def intake_prefilter(args):  # type: ignore  # TODO: mypy-strict
        """Run Beatport prefilter against inventory DB."""
        run_python_script("tools/review/beatport_prefilter.py", args)
