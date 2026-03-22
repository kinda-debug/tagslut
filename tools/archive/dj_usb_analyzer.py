#!/usr/bin/env python3
from __future__ import annotations

import csv
import html
import logging
import os
import re
import shutil
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Iterator

import click
import matplotlib
from pydantic import BaseModel, Field
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from tagslut.dj.transcode import TrackRow, build_output_path, parse_track_number
from tagslut.utils.env_paths import PathNotConfiguredError, get_library_volume
from tagslut.utils.logging import setup_logger

matplotlib.use("Agg")
import matplotlib.pyplot as plt

try:
    from mutagen import File as MutagenFile  # type: ignore
except Exception:  # pragma: no cover - optional dependency handling
    MutagenFile = None


logger = setup_logger("tagslut.dj_usb_analyzer", level=logging.INFO)


SYNC_FIELDS = {
    "safe",
    "block",
    "review",
    "overrides_appended",
    "promoted_ok",
    "promoted_skipped",
    "promoted_failed",
}

REASON_ALIASES: dict[str, tuple[str, ...]] = {
    "exists": ("exists", "output_exists", "already_exists", "skipped_existing"),
    "duration_fail": ("duration", "length", "duration_fail"),
    "bpm_fail": ("bpm", "tempo"),
    "blocklist": ("block", "blocklist"),
    "genre_fail": ("genre",),
    "key_fail": ("key",),
    "missing_source": ("missing", "not_found"),
}


class SyncReport(BaseModel):
    safe: int = 0
    block: int = 0
    review: int = 0
    overrides_appended: int = 0
    promoted_ok: int = 0
    promoted_skipped: int = 0
    promoted_failed: int = 0
    warnings: list[str] = Field(default_factory=list)
    extras: dict[str, str] = Field(default_factory=dict)


class SkipRow(BaseModel):
    exists: bool | None = None
    source: str = ""
    target: str = ""
    reason: str = ""


class UsbStats(BaseModel):
    total_bytes: int
    used_bytes: int
    free_bytes: int
    mp3_count: int
    mp3_bytes: int
    avg_mp3_bytes: float
    non_mp3_used_bytes: int


class Projection(BaseModel):
    target_tracks: int
    projected_mp3_bytes: float
    projected_used_bytes: float
    projected_free_bytes: float
    projected_used_pct: float


class WeirdSkip(BaseModel):
    reason: str
    source: str
    target: str
    exists_flag: bool | None
    source_exists: bool
    target_exists: bool
    age_days: float | None
    score: int
    notes: list[str]


class IncrementalPreset(BaseModel):
    days: int
    total_candidates: int
    missing_on_usb: int
    output_path: Path


def _parse_bool(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "t"}:
        return True
    if text in {"0", "false", "no", "n", "f"}:
        return False
    return None


def _format_bytes(value: float) -> str:
    if value <= 0:
        return "0.0 GiB"
    gib = value / (1024**3)
    return f"{gib:.2f} GiB"


def _format_pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _normalize_reason(reason: str) -> str:
    raw = reason.strip().lower()
    if not raw:
        return "unknown"
    base = raw.split(":", 1)[0].split("(", 1)[0].strip()
    for canonical, tokens in REASON_ALIASES.items():
        if any(token in base for token in tokens):
            return canonical
    return base.replace(" ", "_")


def load_sync_report(path: Path) -> SyncReport:
    if not path.exists():
        raise FileNotFoundError(f"sync report not found: {path}")
    values: dict[str, int] = {}
    warnings: list[str] = []
    extras: dict[str, str] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            metric = (row.get("metric") or row.get("Metric") or "").strip()
            value = (row.get("value") or row.get("Value") or "").strip()
            if not metric:
                continue
            metric_l = metric.lower()
            if metric_l.startswith("warning"):
                if value:
                    warnings.append(value)
                continue
            if metric_l in SYNC_FIELDS:
                try:
                    values[metric_l] = int(float(value)) if value else 0
                except ValueError:
                    values[metric_l] = 0
            else:
                extras[metric_l] = value
    return SyncReport(warnings=warnings, extras=extras, **values)


def _coerce_skip_row(raw: dict[str, str]) -> SkipRow:
    exists_val = raw.get("exists") or raw.get("already_exists") or raw.get("exists_flag")
    source = raw.get("source") or raw.get("src") or raw.get("path") or ""
    target = raw.get("target") or raw.get("dest") or raw.get("destination") or ""
    reason = raw.get("reason") or raw.get("skip_reason") or raw.get("status") or ""
    return SkipRow(
        exists=_parse_bool(exists_val),
        source=source.strip(),
        target=target.strip(),
        reason=reason.strip(),
    )


def load_skip_report(path: Path) -> list[SkipRow]:
    if not path.exists():
        raise FileNotFoundError(f"skip report not found: {path}")
    rows: list[SkipRow] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            rows.append(_coerce_skip_row(raw))
    return rows


def summarize_skip_reasons(rows: Iterable[SkipRow]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for row in rows:
        counts[_normalize_reason(row.reason)] += 1
    return counts


def resolve_report_path(path: Path, usb: Path, artifacts: Path) -> Path:
    if path.exists():
        return path
    if not path.is_absolute():
        candidate = usb / path
        if candidate.exists():
            return candidate
        candidate = artifacts / path
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"report not found: {path}")


def resolve_skip_report(path: Path | None, artifacts: Path) -> Path | None:
    if path:
        if path.exists():
            return path
        if not path.is_absolute():
            candidate = artifacts / path
            if candidate.exists():
                return candidate
        raise FileNotFoundError(f"skip report not found: {path}")
    candidates = sorted(artifacts.glob("skip_report*.csv"), key=lambda p: p.stat().st_mtime)
    return candidates[-1] if candidates else None


def iter_mp3_files(root: Path) -> Iterator[Path]:
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            if name.startswith("._"):
                continue
            if name.lower().endswith(".mp3"):
                yield Path(dirpath) / name


def compute_usb_stats(root: Path) -> UsbStats:
    usage = shutil.disk_usage(root)
    mp3_count = 0
    mp3_bytes = 0
    for path in iter_mp3_files(root):
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        mp3_count += 1
        mp3_bytes += stat.st_size
    avg_mp3 = (mp3_bytes / mp3_count) if mp3_count else 0.0
    non_mp3_used = max(0, usage.used - mp3_bytes)
    return UsbStats(
        total_bytes=usage.total,
        used_bytes=usage.used,
        free_bytes=usage.free,
        mp3_count=mp3_count,
        mp3_bytes=mp3_bytes,
        avg_mp3_bytes=avg_mp3,
        non_mp3_used_bytes=non_mp3_used,
    )


def project_usage(stats: UsbStats, target_tracks: int) -> Projection:
    projected_mp3 = stats.avg_mp3_bytes * target_tracks
    projected_used = stats.non_mp3_used_bytes + projected_mp3
    projected_free = stats.total_bytes - projected_used
    projected_pct = projected_used / stats.total_bytes if stats.total_bytes else 0.0
    return Projection(
        target_tracks=target_tracks,
        projected_mp3_bytes=projected_mp3,
        projected_used_bytes=projected_used,
        projected_free_bytes=projected_free,
        projected_used_pct=projected_pct,
    )


def _tag_first(tags: dict[str, Any], *keys: str) -> str | None:
    lowered = {str(k).lower(): v for k, v in tags.items()}
    for key in keys:
        if key.lower() not in lowered:
            continue
        raw = lowered[key.lower()]
        if isinstance(raw, (list, tuple)):
            raw = raw[0] if raw else None
        if raw is None:
            continue
        value = str(raw).strip()
        if value:
            return value
    return None


def _fallback_meta(path: Path) -> dict[str, Any]:
    stem = path.stem
    track_number = None
    title = stem
    match = re.match(r"^(\d{1,2})[\s._-]+(.+)$", stem)
    if match:
        track_number = parse_track_number(match.group(1))
        title = match.group(2).strip() or stem
    album = path.parent.name if path.parent else "Unknown Album"
    artist = path.parent.parent.name if path.parent and path.parent.parent else "Unknown Artist"
    return {
        "album_artist": artist,
        "track_artist": artist,
        "album": album,
        "title": title,
        "track_number": track_number,
    }


def build_track_row_from_path(path: Path) -> TrackRow:
    tags: dict[str, Any] = {}
    if MutagenFile is not None:
        try:
            audio = MutagenFile(path, easy=True)
        except Exception:
            audio = None
        if audio is not None and getattr(audio, "tags", None):
            tags = dict(audio.tags)
    fallback = _fallback_meta(path)
    artist = _tag_first(tags, "artist", "trackartist", "track artist") or fallback["track_artist"]
    album_artist = _tag_first(tags, "albumartist", "album artist") or fallback["album_artist"]
    album = _tag_first(tags, "album") or fallback["album"]
    title = _tag_first(tags, "title") or fallback["title"]
    track_raw = _tag_first(tags, "tracknumber", "track")
    track_number = parse_track_number(track_raw) if track_raw else fallback["track_number"]

    row = TrackRow(
        row_num=0,
        album_artist=album_artist,
        album=album,
        track_number=track_number,
        title=title,
        track_artist=artist,
        external_id="",
        source="local",
        source_path=path,
        dedupe_key=("meta", album_artist.lower(), title.lower()),
    )
    return row


def iter_recent_sources(root: Path, days: int, exts: set[str]) -> Iterator[Path]:
    cutoff = datetime.now().timestamp() - days * 86400
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            if name.startswith("._"):
                continue
            suffix = Path(name).suffix.lower()
            if suffix not in exts:
                continue
            path = Path(dirpath) / name
            try:
                mtime = path.stat().st_mtime
            except FileNotFoundError:
                continue
            if mtime >= cutoff:
                yield path


def generate_incremental_m3u(
    library_root: Path,
    usb_root: Path,
    days: int,
    out_dir: Path,
    exts: set[str] | None = None,
) -> IncrementalPreset:
    if exts is None:
        exts = {".flac"}
    total_candidates = 0
    missing: list[Path] = []
    for path in iter_recent_sources(library_root, days, exts):
        total_candidates += 1
        track = build_track_row_from_path(path)
        target = build_output_path(usb_root, track)
        if target.exists():
            continue
        missing.append(path)

    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"incremental_{days}d_{stamp}.m3u8"
    lines = ["#EXTM3U"] + [str(p) for p in sorted(missing)]
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return IncrementalPreset(
        days=days,
        total_candidates=total_candidates,
        missing_on_usb=len(missing),
        output_path=out_path,
    )


def find_weird_skips(rows: Iterable[SkipRow], max_items: int = 10) -> list[WeirdSkip]:
    now = datetime.now().timestamp()
    weird: list[WeirdSkip] = []
    for row in rows:
        reason = row.reason.strip() or "unknown"
        reason_l = reason.lower()
        source_path = Path(row.source) if row.source else None
        target_path = Path(row.target) if row.target else None
        source_exists = source_path.exists() if source_path else False
        target_exists = target_path.exists() if target_path else False
        exists_flag = row.exists
        score = 0
        notes: list[str] = []
        age_days = None

        if exists_flag is False and "exist" in reason_l:
            score += 3
            notes.append("reason says exists but exists flag=false")
        if exists_flag is True and not source_exists:
            score += 4
            notes.append("exists flag=true but source missing")
        if "exist" in reason_l and not target_exists:
            score += 2
            notes.append("reason says exists but target missing")
        if source_path is None or not source_path.exists():
            if "missing" not in reason_l:
                score += 1
                notes.append("source missing on disk")
        if source_exists:
            try:
                age_days = (now - source_path.stat().st_mtime) / 86400
            except FileNotFoundError:
                age_days = None
            if age_days is not None and age_days <= 90 and "exist" in reason_l:
                score += 2
                notes.append(f"recent source ({age_days:.0f}d) skipped as exists")

        if score == 0:
            continue

        weird.append(
            WeirdSkip(
                reason=reason,
                source=row.source,
                target=row.target,
                exists_flag=exists_flag,
                source_exists=source_exists,
                target_exists=target_exists,
                age_days=age_days,
                score=score,
                notes=notes,
            )
        )

    weird.sort(key=lambda w: (-w.score, w.age_days if w.age_days is not None else 9999))
    return weird[:max_items]


def suggest_policy_tweaks(summary: SyncReport, reason_counts: Counter[str]) -> list[str]:
    suggestions: list[str] = []
    total_classified = summary.safe + summary.block + summary.review
    review_ratio = (summary.review / total_classified) if total_classified else 0
    block_ratio = (summary.block / total_classified) if total_classified else 0

    if review_ratio >= 0.35:
        suggestions.append(
            f"Review bucket is {_format_pct(review_ratio)} of classified tracks; consider loosening review thresholds or widening safe gates."
        )
    if block_ratio >= 0.35:
        suggestions.append(
            f"Block bucket is {_format_pct(block_ratio)} of classified tracks; consider reducing blocklist strictness or routing borderline to review."
        )

    total_skips = sum(reason_counts.values())
    if total_skips:
        ranked = reason_counts.most_common()
        for reason, count in ranked:
            share = count / total_skips
            if share < 0.15:
                continue
            if reason == "bpm_fail":
                suggestions.append(
                    f"BPM fails are {_format_pct(share)} of skips; consider widening BPM window or relaxing BPM confidence gating."
                )
            elif reason == "duration_fail":
                suggestions.append(
                    f"Duration fails are {_format_pct(share)} of skips; consider widening duration tolerance or enabling duration estimation."
                )
            elif reason == "key_fail":
                suggestions.append(
                    f"Key fails are {_format_pct(share)} of skips; consider relaxing key requirements or adding key detection."
                )
            elif reason == "genre_fail":
                suggestions.append(
                    f"Genre fails are {_format_pct(share)} of skips; consider widening the genre allowlist."
                )
            elif reason == "blocklist":
                suggestions.append(
                    f"Blocklist skips are {_format_pct(share)} of skips; audit blocklist entries or move some to review."
                )
            elif reason == "exists" and share >= 0.25:
                suggestions.append(
                    f"Exists skips are {_format_pct(share)} of skips; tighten incremental filters (e.g., last 60d) to reduce duplicate checks."
                )
            if len(suggestions) >= 3:
                break

    while len(suggestions) < 3:
        suggestions.append("Review thresholds look stable; consider minor BPM/duration tweaks only if you want higher recall.")

    return suggestions[:3]


def plot_skip_reasons(counts: Counter[str], out_path: Path) -> Path:
    if not counts:
        return out_path
    labels = list(counts.keys())
    values = list(counts.values())
    if len(labels) > 8:
        top = list(sorted(counts.items(), key=lambda kv: kv[1], reverse=True))
        head = top[:7]
        tail = top[7:]
        labels = [k for k, _ in head] + ["other"]
        values = [v for _, v in head] + [sum(v for _, v in tail)]

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.pie(values, labels=labels, autopct="%1.0f%%", startangle=90)
    ax.axis("equal")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def render_summary_table(console: Console, summary: SyncReport) -> None:
    table = Table(title="Sync Summary", show_header=True, header_style="bold")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Safe", str(summary.safe))
    table.add_row("Block", str(summary.block))
    table.add_row("Review", str(summary.review))
    table.add_row("Promoted OK", str(summary.promoted_ok))
    table.add_row("Promoted Skipped", str(summary.promoted_skipped))
    table.add_row("Promoted Failed", str(summary.promoted_failed))
    console.print(table)


def render_skip_reasons_table(console: Console, counts: Counter[str]) -> None:
    table = Table(title="Skip Reasons", show_header=True, header_style="bold")
    table.add_column("Reason")
    table.add_column("Count", justify="right")
    for reason, count in counts.most_common():
        table.add_row(reason, str(count))
    console.print(table)


def render_usb_stats(console: Console, stats: UsbStats, projections: list[Projection]) -> None:
    table = Table(title="USB Stats", show_header=True, header_style="bold")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("MP3 Count", str(stats.mp3_count))
    table.add_row("MP3 Size", _format_bytes(stats.mp3_bytes))
    table.add_row("Avg MP3 Size", _format_bytes(stats.avg_mp3_bytes))
    table.add_row("Disk Used", _format_bytes(stats.used_bytes))
    table.add_row("Disk Free", _format_bytes(stats.free_bytes))
    used_pct = stats.used_bytes / stats.total_bytes if stats.total_bytes else 0.0
    table.add_row("Disk Used %", _format_pct(used_pct))
    console.print(table)

    proj_table = Table(title="Projected Space", show_header=True, header_style="bold")
    proj_table.add_column("Tracks")
    proj_table.add_column("Projected Used", justify="right")
    proj_table.add_column("Projected Free", justify="right")
    proj_table.add_column("Used %", justify="right")
    for proj in projections:
        proj_table.add_row(
            str(proj.target_tracks),
            _format_bytes(proj.projected_used_bytes),
            _format_bytes(proj.projected_free_bytes),
            _format_pct(proj.projected_used_pct),
        )
    console.print(proj_table)


def render_weird_skips(console: Console, weird: list[WeirdSkip]) -> None:
    table = Table(title="Weird Skips (Top 10)", show_header=True, header_style="bold")
    table.add_column("Score", justify="right")
    table.add_column("Reason")
    table.add_column("Exists Flag", justify="center")
    table.add_column("Source Exists", justify="center")
    table.add_column("Target Exists", justify="center")
    table.add_column("Age (d)", justify="right")
    table.add_column("Notes")
    for item in weird:
        age = f"{item.age_days:.0f}" if item.age_days is not None else "-"
        table.add_row(
            str(item.score),
            item.reason,
            str(item.exists_flag) if item.exists_flag is not None else "?",
            "yes" if item.source_exists else "no",
            "yes" if item.target_exists else "no",
            age,
            "; ".join(item.notes),
        )
    console.print(table)


def render_policy_tweaks(console: Console, tweaks: list[str]) -> None:
    body = "\n".join(f"- {tweak}" for tweak in tweaks)
    console.print(Panel(body, title="Policy Tuner", border_style="green"))


def _html_table(title: str, rows: list[tuple[str, str]]) -> str:
    lines = [f"<h2>{html.escape(title)}</h2>"]
    lines.append("<table>")
    lines.append("<tr><th>Metric</th><th>Value</th></tr>")
    for key, value in rows:
        lines.append(f"<tr><td>{html.escape(key)}</td><td>{html.escape(value)}</td></tr>")
    lines.append("</table>")
    return "\n".join(lines)


def write_html_report(
    out_path: Path,
    summary: SyncReport,
    reason_counts: Counter[str],
    stats: UsbStats,
    projections: list[Projection],
    weird: list[WeirdSkip],
    tweaks: list[str],
    pie_path: Path | None,
    incremental: IncrementalPreset | None,
) -> Path:
    rows = [
        ("Safe", str(summary.safe)),
        ("Block", str(summary.block)),
        ("Review", str(summary.review)),
        ("Promoted OK", str(summary.promoted_ok)),
        ("Promoted Skipped", str(summary.promoted_skipped)),
        ("Promoted Failed", str(summary.promoted_failed)),
    ]
    skip_rows = [(reason, str(count)) for reason, count in reason_counts.most_common()]

    usb_rows = [
        ("MP3 Count", str(stats.mp3_count)),
        ("MP3 Size", _format_bytes(stats.mp3_bytes)),
        ("Avg MP3 Size", _format_bytes(stats.avg_mp3_bytes)),
        ("Disk Used", _format_bytes(stats.used_bytes)),
        ("Disk Free", _format_bytes(stats.free_bytes)),
        ("Disk Used %", _format_pct(stats.used_bytes / stats.total_bytes if stats.total_bytes else 0.0)),
    ]

    proj_rows = [
        (
            f"{proj.target_tracks} tracks",
            f"used {_format_bytes(proj.projected_used_bytes)}, free {_format_bytes(proj.projected_free_bytes)} ({_format_pct(proj.projected_used_pct)})",
        )
        for proj in projections
    ]

    weird_rows = [
        (
            f"{item.reason} (score {item.score})",
            "; ".join(item.notes) or "-",
        )
        for item in weird
    ]

    tweaks_rows = [("Suggestion", tweak) for tweak in tweaks]

    html_lines = [
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        "<meta charset='utf-8'/>",
        "<title>DJ USB Analyzer</title>",
        "<style>",
        "body { font-family: Arial, sans-serif; margin: 24px; }",
        "table { border-collapse: collapse; margin-bottom: 24px; }",
        "th, td { border: 1px solid #ddd; padding: 8px 12px; }",
        "th { background: #f5f5f5; text-align: left; }",
        "h1, h2 { margin-top: 24px; }",
        "img { max-width: 600px; display: block; margin-bottom: 24px; }",
        "</style>",
        "</head>",
        "<body>",
        "<h1>DJ USB Analyzer Report</h1>",
        _html_table("Sync Summary", rows),
        _html_table("USB Stats", usb_rows),
        _html_table("Projected Space", proj_rows),
        _html_table("Skip Reasons", skip_rows),
    ]

    if pie_path and pie_path.exists():
        html_lines.append("<h2>Skip Reasons Pie</h2>")
        html_lines.append(f"<img src='{html.escape(pie_path.name)}' alt='Skip reasons pie' />")

    if weird_rows:
        html_lines.append(_html_table("Weird Skips", weird_rows))

    html_lines.append(_html_table("Policy Tweaks", tweaks_rows))

    if incremental:
        html_lines.append("<h2>Next Sync Preset</h2>")
        html_lines.append(
            f"<p>Incremental {incremental.days}d: {incremental.missing_on_usb} missing of {incremental.total_candidates} candidates.</p>"
        )
        html_lines.append(f"<p>M3U8: {html.escape(str(incremental.output_path))}</p>")

    html_lines.extend(["</body>", "</html>"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(html_lines), encoding="utf-8")
    return out_path


@click.command()
@click.option("--usb", "usb_path", required=True, type=click.Path(path_type=Path), help="DJUSB mount path")
@click.option("--report", "report_path", required=True, type=click.Path(path_type=Path), help="sync_report.csv path")
@click.option("--skip-report", "skip_report_path", type=click.Path(path_type=Path), default=None, help="skip_report CSV path")
@click.option("--library", "library_path", type=click.Path(path_type=Path), default=None, help="Library root for incremental preset")
@click.option("--days", default=90, show_default=True, help="Recent days for incremental preset")
@click.option("--artifacts", "artifacts_path", default=Path("artifacts"), show_default=True, type=click.Path(path_type=Path), help="Artifacts output directory")
def main(
    usb_path: Path,
    report_path: Path,
    skip_report_path: Path | None,
    library_path: Path | None,
    days: int,
    artifacts_path: Path,
) -> None:
    console = Console()
    usb = usb_path.expanduser().resolve()
    artifacts = artifacts_path.expanduser().resolve()

    if not usb.exists():
        raise click.ClickException(f"USB path not found: {usb}")

    try:
        report = resolve_report_path(report_path.expanduser(), usb, artifacts)
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc
    summary = load_sync_report(report)
    logger.info("Loaded sync report: %s", report)
    render_summary_table(console, summary)

    try:
        skip_report = resolve_skip_report(skip_report_path, artifacts)
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc
    skip_rows: list[SkipRow] = []
    reason_counts: Counter[str] = Counter()
    pie_path: Path | None = None
    if skip_report:
        skip_rows = load_skip_report(skip_report)
        logger.info("Loaded skip report: %s rows", len(skip_rows))
        reason_counts = summarize_skip_reasons(skip_rows)
        render_skip_reasons_table(console, reason_counts)
        if reason_counts:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            pie_path = artifacts / f"skip_reasons_pie_{stamp}.png"
            plot_skip_reasons(reason_counts, pie_path)
            console.print(f"Skip reasons pie: {pie_path}")
        else:
            console.print("Skip report is empty; skipping skip reason chart.")
    else:
        console.print("Skip report not found; skipping skip reason chart.")

    stats = compute_usb_stats(usb)
    logger.info("USB stats: mp3_count=%d mp3_size=%s", stats.mp3_count, _format_bytes(stats.mp3_bytes))
    projections = [project_usage(stats, target) for target in (10_000, 15_000, 20_000)]
    render_usb_stats(console, stats, projections)

    weird = find_weird_skips(skip_rows, max_items=10) if skip_rows else []
    if weird:
        render_weird_skips(console, weird)

    tweaks = suggest_policy_tweaks(summary, reason_counts)
    render_policy_tweaks(console, tweaks)

    incremental = None
    if library_path is None:
        try:
            library_path = get_library_volume()
        except PathNotConfiguredError:
            library_path = None

    if library_path and library_path.exists():
        incremental = generate_incremental_m3u(
            library_root=library_path,
            usb_root=usb,
            days=days,
            out_dir=artifacts,
        )
        logger.info("Incremental preset written: %s", incremental.output_path)
        console.print(
            f"Incremental preset: {incremental.missing_on_usb}/{incremental.total_candidates} -> {incremental.output_path}"
        )
    else:
        console.print("Library path not configured; skipping incremental preset.")

    report_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    html_path = artifacts / f"analyzer_report_{report_stamp}.html"
    write_html_report(
        html_path,
        summary,
        reason_counts,
        stats,
        projections,
        weird,
        tweaks,
        pie_path,
        incremental,
    )
    console.print(f"HTML report: {html_path}")


if __name__ == "__main__":
    raise SystemExit(main())
