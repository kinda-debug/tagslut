#!/usr/bin/env python3
"""
manage-blocklist.py

CLI helper to analyze and update DJ artist blocklists.

Commands:
  analyze <artist>   -> Count matches in DB (canonical_artist), optional impact summary
  add <artist>       -> Append artist to blocklist (non-dj or borderline)
  bulk --from-m3u    -> Extract artists from M3U and append to blocklist
"""

from __future__ import annotations

import csv
import os
import re
import sqlite3
import sys
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import click
from mutagen import File as MutagenFile


BLOCKLISTS = {
    "non-dj": Path("config/blocklists/non_dj_artists.txt"),
    "borderline": Path("config/blocklists/borderline_artists.txt"),
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = text.replace("&", " and ")
    text = re.sub(r"\b(feat|featuring|ft)\b.*", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _extract_artist_from_tags(path: Path) -> str | None:
    try:
        audio = MutagenFile(path, easy=False)
    except Exception:
        audio = None
    if audio is None:
        return None
    tags = getattr(audio, "tags", None) or {}
    for key in ("ARTIST", "artist", "TPE1", "ALBUMARTIST", "albumartist", "TPE2"):
        raw = tags.get(key)
        if raw is None:
            continue
        if isinstance(raw, (list, tuple)):
            if not raw:
                continue
            raw = raw[0]
        value = str(raw).strip()
        if value:
            return value
    return None


def _extract_artist_from_filename(path: Path) -> str | None:
    name = path.stem
    if " - " in name:
        return name.split(" - ", 1)[0].strip() or None
    return None


def _iter_m3u_lines(m3u_path: Path) -> Iterable[str]:
    for line in m3u_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        yield line


def _load_blocklist(path: Path) -> set[str]:
    if not path.exists():
        return set()
    items: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        if line.lstrip().startswith("#"):
            continue
        items.add(_normalize_text(line))
    return items


def _append_blocklist(path: Path, artists: list[str], reason: str | None, dry_run: bool) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = _load_blocklist(path)
    to_add = []
    for artist in artists:
        if not artist:
            continue
        key = _normalize_text(artist)
        if key in existing:
            continue
        to_add.append(artist)
        existing.add(key)
    if not to_add:
        return 0
    if dry_run:
        return len(to_add)
    with path.open("a", encoding="utf-8", newline="") as handle:
        if reason:
            handle.write(f"# added { _now_iso() } reason: {reason}\n")
        for artist in to_add:
            handle.write(f"{artist}\n")
    return len(to_add)


def _remove_blocklist(path: Path, artists: Iterable[str], dry_run: bool) -> int:
    if not path.exists():
        raise click.ClickException(f"Blocklist not found: {path}")
    raw_input = " ".join(artists).strip()
    if not raw_input:
        return 0
    targets = {
        _normalize_text(part)
        for part in re.split(r"[,\n]+", raw_input)
        if part.strip()
    }
    haystack = _normalize_text(raw_input)
    removed = 0
    kept_lines: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            kept_lines.append(line)
            continue
        key = _normalize_text(line)
        if key in targets or (haystack and key in haystack):
            removed += 1
            continue
        kept_lines.append(line)
    if removed and not dry_run:
        path.write_text("\n".join(kept_lines).rstrip() + "\n", encoding="utf-8")
    return removed


def _resolve_db_path(db: str | None) -> Path:
    candidate = db or os.environ.get("TAGSLUT_DB", "")
    if not candidate:
        raise click.ClickException(
            "No database path provided. Use --db or set TAGSLUT_DB."
        )
    path = Path(candidate).expanduser().resolve()
    if not path.exists():
        raise click.ClickException(f"DB not found: {path}")
    return path


@dataclass
class MatchRow:
    path: str
    artist: str
    title: str | None
    m3u_path: str | None


def _fetch_matches(
    conn: sqlite3.Connection,
    artist_query: str,
    fuzzy: bool,
) -> list[MatchRow]:
    conn.row_factory = sqlite3.Row
    query_norm = _normalize_text(artist_query)
    like = f"%{artist_query.lower()}%"
    cols = [row[1] for row in conn.execute("PRAGMA table_info(files)")]
    has_m3u = "m3u_path" in cols
    has_title = "canonical_title" in cols

    select_cols = ["path", "canonical_artist"]
    if has_title:
        select_cols.append("canonical_title")
    if has_m3u:
        select_cols.append("m3u_path")

    base = f"SELECT {', '.join(select_cols)} FROM files WHERE canonical_artist IS NOT NULL AND canonical_artist != ''"
    if fuzzy:
        rows = conn.execute(base + " AND lower(canonical_artist) LIKE ?", (like,)).fetchall()
    else:
        rows = conn.execute(base + " AND lower(canonical_artist) = ?", (artist_query.lower(),)).fetchall()

    matches: list[MatchRow] = []
    for row in rows:
        artist = row["canonical_artist"]
        if fuzzy:
            artist_norm = _normalize_text(artist)
            if query_norm not in artist_norm and artist_norm not in query_norm:
                continue
        matches.append(
            MatchRow(
                path=row["path"],
                artist=artist,
                title=row["canonical_title"] if has_title else None,
                m3u_path=row["m3u_path"] if has_m3u else None,
            )
        )
    return matches


@click.group()
def cli() -> None:
    """Manage DJ blocklists (non-dj, borderline)."""


@cli.command("analyze")
@click.argument("artist")
@click.option("--db", type=click.Path(), help="SQLite DB path (default: $TAGSLUT_DB)")
@click.option("--impact", is_flag=True, help="Show impact summary (paths, playlists)")
@click.option("--fuzzy/--exact", default=True, help="Fuzzy match artist names")
@click.option("--show", type=int, default=10, show_default=True, help="Show up to N sample paths")
def analyze(artist: str, db: str | None, impact: bool, fuzzy: bool, show: int) -> None:
    """Analyze how many tracks would be affected by blocking an artist."""
    db_path = _resolve_db_path(db)
    conn = sqlite3.connect(str(db_path))
    try:
        matches = _fetch_matches(conn, artist, fuzzy=fuzzy)
    finally:
        conn.close()

    unique_artists = sorted({m.artist for m in matches})
    playlists = sorted({m.m3u_path for m in matches if m.m3u_path})

    click.echo(f"Matches: {len(matches)}")
    click.echo(f"Artists: {len(unique_artists)}")
    if impact:
        click.echo(f"Playlists: {len(playlists)}")
    if unique_artists:
        click.echo("Artist names:")
        for name in unique_artists[: min(10, len(unique_artists))]:
            click.echo(f"  - {name}")
        if len(unique_artists) > 10:
            click.echo(f"  ... and {len(unique_artists) - 10} more")

    if show and matches:
        click.echo("Sample paths:")
        for row in matches[:show]:
            title = f" — {row.title}" if row.title else ""
            click.echo(f"  {row.path}{title}")


@cli.command("add")
@click.argument("artist")
@click.option("--cat", "category", type=click.Choice(["non-dj", "borderline"]), default="non-dj", show_default=True)
@click.option("--reason", type=str, help="Optional reason comment")
@click.option("--dry-run", is_flag=True, help="Preview without writing")
def add_artist(artist: str, category: str, reason: str | None, dry_run: bool) -> None:
    """Add a single artist to a blocklist."""
    path = BLOCKLISTS[category]
    added = _append_blocklist(path, [artist], reason, dry_run=dry_run)
    mode = "DRY-RUN" if dry_run else "UPDATED"
    click.echo(f"{mode}: {added} artist(s) added to {path}")


@cli.command("bulk")
@click.option("--from-m3u", "m3u_path", type=click.Path(exists=True), required=True, help="M3U file to scan")
@click.option("--cat", "category", type=click.Choice(["non-dj", "borderline"]), default="non-dj", show_default=True)
@click.option("--reason", type=str, help="Optional reason comment")
@click.option("--dry-run", is_flag=True, help="Preview without writing")
def bulk(m3u_path: str, category: str, reason: str | None, dry_run: bool) -> None:
    """Add artists from an M3U playlist to a blocklist."""
    m3u = Path(m3u_path)
    artists: list[str] = []
    missing = 0
    for raw in _iter_m3u_lines(m3u):
        path = Path(raw)
        if path.exists():
            artist = _extract_artist_from_tags(path) or _extract_artist_from_filename(path)
            if artist:
                artists.append(artist)
            continue
        # If the line doesn't look like a path, treat it as a raw artist name.
        if "/" not in raw and "\\" not in raw:
            artists.append(raw)
            continue
        missing += 1

    unique = sorted({a.strip() for a in artists if a.strip()})
    added = _append_blocklist(BLOCKLISTS[category], unique, reason, dry_run=dry_run)
    mode = "DRY-RUN" if dry_run else "UPDATED"
    click.echo(f"{mode}: {added} artist(s) added from {m3u}")
    click.echo(f"Unique artists scanned: {len(unique)}")
    if missing:
        click.echo(f"Missing files: {missing}")


@cli.command("export")
@click.option("--from-crate", "crate_path", type=click.Path(exists=True), required=True, help="Block crate M3U file")
@click.option("--top", type=int, default=20, show_default=True, help="Top N artists")
def export(crate_path: str, top: int) -> None:
    """Export top artists from a block crate."""
    crate = Path(crate_path)
    counts: dict[str, int] = {}
    for raw in _iter_m3u_lines(crate):
        path = Path(raw)
        artist = None
        if path.exists():
            artist = _extract_artist_from_tags(path) or _extract_artist_from_filename(path)
        if not artist:
            continue
        key = artist.strip()
        counts[key] = counts.get(key, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    for artist, count in ranked[:top]:
        click.echo(f"{count}\t{artist}")


@cli.command("remove")
@click.argument("artists", nargs=-1, required=True)
@click.option("--cat", "category", type=click.Choice(BLOCKLISTS.keys()), default="non-dj", show_default=True)
@click.option("--dry-run", is_flag=True, help="Preview removals without editing files.")
def remove(artists: tuple[str, ...], category: str, dry_run: bool) -> None:
    """Remove one or more artists from a blocklist."""
    removed = _remove_blocklist(BLOCKLISTS[category], artists, dry_run=dry_run)
    mode = "DRY-RUN" if dry_run else "UPDATED"
    click.echo(f"{mode}: {removed} artist(s) removed from {BLOCKLISTS[category]}")


if __name__ == "__main__":
    sys.exit(cli())
