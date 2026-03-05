"""Shared helpers for canonical index/verify/report inventory commands."""

from __future__ import annotations

from pathlib import Path

import click

from tagslut.cli.runtime import collect_flac_paths as _collect_flac_paths


def duration_thresholds_from_config() -> tuple[int, int]:
    from tagslut.utils.config import get_config

    config = get_config()
    ok_max = int(config.get("mgmt.duration.ok_max_delta_ms", 2000) or 2000)
    warn_max = int(config.get("mgmt.duration.warn_max_delta_ms", 8000) or 8000)
    return ok_max, warn_max


def duration_check_version(ok_max_ms: int, warn_max_ms: int) -> str:
    return f"duration_v1_ok{ok_max_ms//1000}_warn{warn_max_ms//1000}"


def duration_status(delta_ms: int | None, ok_max_ms: int, warn_max_ms: int) -> str:
    if delta_ms is None:
        return "unknown"
    abs_delta = abs(delta_ms)
    if abs_delta <= ok_max_ms:
        return "ok"
    if abs_delta <= warn_max_ms:
        return "warn"
    return "fail"


def collect_flac_inputs(paths: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    for input_path in paths:
        files.extend(_collect_flac_paths(input_path))
    return files


def resolve_group_name(file_path: Path, base_paths: list[Path]) -> str:
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


def safe_playlist_name(name: str) -> str:
    cleaned = name.strip().replace("/", "-").replace("\\", "-")
    return cleaned or "playlist"


def extract_tag_value(tags: dict, keys: list[str]) -> str | None:  # type: ignore  # TODO: mypy-strict
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


def format_extinf(file_path: Path) -> tuple[int, str]:
    try:
        from mutagen.flac import FLAC

        audio = FLAC(file_path)
        duration = int(audio.info.length) if audio.info.length else -1
        tags = audio.tags or {}  # type: ignore  # TODO: mypy-strict
        artist = extract_tag_value(tags, ["artist", "albumartist"]) or "Unknown"  # type: ignore  # TODO: mypy-strict
        title = extract_tag_value(tags, ["title"]) or file_path.stem  # type: ignore  # TODO: mypy-strict
        return duration, f"{artist} - {title}"
    except Exception:
        return -1, file_path.stem


def write_m3u(*, playlist_name: str, files: list[Path], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_name = safe_playlist_name(playlist_name)
    output_path = output_dir / f"{safe_name}.m3u"

    lines = ["#EXTM3U", "#EXTENC: UTF-8", f"#PLAYLIST:{playlist_name}"]
    for file_path in files:
        duration, label = format_extinf(file_path)
        lines.append(f"#EXTINF:{duration},{label}")
        lines.append(str(file_path.resolve()))

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def prompt_duplicate_action(
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


def measure_duration_ms(file_path: Path) -> int | None:
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


def lookup_duration_ref_ms(  # type: ignore  # TODO: mypy-strict
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


def run_audit_duration(
    db: str | None,
    dj_only: bool,
    status_filter: str | None,
    source: str | None,
    since: str | None,
    inactive_exclude: bool,
) -> None:
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


def run_report_m3u(
    *,
    paths: tuple[str, ...],
    merge: bool,
    m3u_dir: str | None,
    db: str | None,
    source: str | None,
    verbose: bool,
) -> None:
    from datetime import datetime, timezone

    from tagslut.storage.schema import get_connection, init_db
    from tagslut.utils.config import get_config
    from tagslut.utils.db import resolve_db_path

    if not paths:
        raise click.ClickException("Provide at least one PATH when using --m3u")

    config = get_config()
    default_m3u_dir = config.get("mgmt.m3u_dir") if config else None
    output_dir = Path(m3u_dir) if m3u_dir else (Path(default_m3u_dir).expanduser() if default_m3u_dir else None)

    input_paths = [Path(p).expanduser().resolve() for p in paths]
    flac_files = collect_flac_inputs(tuple(paths))
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
            group = resolve_group_name(file_path, base_paths)
            groups.setdefault(group, []).append(file_path)
        for group_name in list(groups.keys()):
            groups[group_name] = sorted(groups[group_name], key=lambda p: str(p))

    if verbose:
        click.echo(f"Input paths: {len(input_paths)}")
        click.echo(f"FLAC files: {len(flac_files)}")
        click.echo(f"Groups: {len(groups)}")
        for name, files in groups.items():
            click.echo(f"  {name}: {len(files)} tracks")

    resolution = resolve_db_path(db, purpose="write", allow_create=True)
    conn = get_connection(str(resolution.path), purpose="write", allow_create=True)
    init_db(conn)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(files)")}
    has_m3u_path = "m3u_path" in columns

    now_iso = datetime.now(timezone.utc).isoformat()
    playlist_outputs: list[Path] = []
    try:
        for group_name, files in groups.items():
            playlist_name = safe_playlist_name(group_name)
            if merge:
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                label = source or "tagslut"
                playlist_name = f"{label}-{stamp}"

            output_path = write_m3u(
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
