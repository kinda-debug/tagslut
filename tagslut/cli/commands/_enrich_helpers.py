"""Shared enrichment helpers for metadata commands."""

from __future__ import annotations

from pathlib import Path

import click


def _local_file_info_from_path(file_path: Path):  # type: ignore  # TODO: mypy-strict
    from tagslut.core.metadata import extract_metadata
    from tagslut.metadata.models.types import LocalFileInfo

    audio = extract_metadata(file_path, scan_integrity=False, scan_hash=False)
    tags = audio.metadata or {}

    def get_tag(key: str):  # type: ignore  # TODO: mypy-strict
        val = tags.get(key)
        if isinstance(val, list) and val:
            return str(val[0])
        if val is not None:
            return str(val)
        return None

    def get_int_tag(key: str) -> int | None:
        val = get_tag(key)
        if val:
            try:
                return int(val)
            except ValueError:
                pass
        return None

    return LocalFileInfo(
        path=str(audio.path),
        measured_duration_s=audio.duration or None,
        tag_artist=get_tag("artist") or get_tag("albumartist"),
        tag_title=get_tag("title"),
        tag_album=get_tag("album"),
        tag_isrc=get_tag("isrc"),
        tag_label=get_tag("label") or get_tag("organization"),
        tag_year=get_int_tag("date") or get_int_tag("year"),
    )


def _print_enrichment_result(result) -> None:  # type: ignore  # TODO: mypy-strict
    if not result or not result.matches:
        click.echo("No provider match found")
        return
    best = max(result.matches, key=lambda m: m.match_confidence.value if m.match_confidence else 0)
    click.echo(f"Matched: {best.artist} - {best.title} ({best.service})")
    if result.canonical_isrc:
        click.echo(f"ISRC: {result.canonical_isrc}")
    if result.canonical_bpm:
        click.echo(f"BPM: {result.canonical_bpm}")
    if result.canonical_key:
        click.echo(f"Key: {result.canonical_key}")
    if result.canonical_genre:
        click.echo(f"Genre: {result.canonical_genre}")
