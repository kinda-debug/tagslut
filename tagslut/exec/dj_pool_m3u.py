from __future__ import annotations

import os
from pathlib import Path


def _first_id3_text(tags: "object", frame_id: str) -> str | None:
    frame = getattr(tags, "get", lambda _k: None)(frame_id)
    if frame is None:
        return None
    text_attr = getattr(frame, "text", None)
    if text_attr and len(text_attr) > 0:
        value = str(text_attr[0]).strip()
        return value or None
    return None


def _fallback_artist_title_from_filename(path: Path) -> tuple[str, str]:
    stem = (path.stem or "").strip()
    for sep in (" - ", " – ", " — "):
        if sep in stem:
            parts = [p.strip() for p in stem.split(sep) if p.strip()]
            if len(parts) >= 2:
                artist = parts[0]
                title = parts[-1]
                if title[:3].isdigit() and title[3:4] == " ":
                    title = title[4:].strip() or title
                return artist, title
    return "Unknown", stem or path.name


def _extinf_for_mp3(path: Path) -> tuple[int, str, str]:
    try:
        from mutagen.id3 import ID3  # type: ignore[import-untyped]
        from mutagen.mp3 import MP3  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError("mutagen is required — pip install mutagen") from exc

    duration = -1
    try:
        audio = MP3(str(path))
        length = getattr(getattr(audio, "info", None), "length", None)
        duration = int(float(length)) if length is not None else -1
    except Exception:
        duration = -1

    artist: str | None = None
    title: str | None = None
    try:
        tags = ID3(str(path))
        artist = _first_id3_text(tags, "TPE1")
        title = _first_id3_text(tags, "TIT2")
    except Exception:
        artist = None
        title = None

    if not artist or not title:
        fallback_artist, fallback_title = _fallback_artist_title_from_filename(path)
        artist = artist or fallback_artist
        title = title or fallback_title

    return duration, artist, title


def _common_parent_dir(paths: list[Path]) -> Path:
    if not paths:
        raise ValueError("mp3_paths must not be empty")
    if len(paths) == 1:
        return paths[0].resolve().parent
    common = Path(os.path.commonpath([str(p.resolve()) for p in paths]))
    if common.suffix.lower() == ".mp3":
        return common.parent
    return common


def _render_m3u_lines(mp3_paths: list[Path]) -> list[str]:
    lines = ["#EXTM3U"]
    for path in mp3_paths:
        duration, artist, title = _extinf_for_mp3(path)
        lines.append(f"#EXTINF:{duration},{artist} - {title}")
        lines.append(str(path.resolve()))
    return lines


def _read_existing_m3u_paths(path: Path) -> set[str]:
    if not path.exists():
        return set()
    out: set[str] = set()
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = (raw or "").strip()
        if not line or line.startswith("#"):
            continue
        out.add(line)
    return out


def write_dj_pool_m3u(mp3_paths: list[Path], mp3_root: Path) -> tuple[Path, Path]:
    """
    Write batch and global dj_pool.m3u files.

    Args:
        mp3_paths: absolute paths to MP3 files built in this batch
        mp3_root: root of MP3_LIBRARY (e.g. /Volumes/MUSIC/MP3_LIBRARY)

    Returns:
        (batch_m3u_path, global_m3u_path)
    """
    if not mp3_paths:
        raise ValueError("mp3_paths must not be empty")

    resolved_mp3_paths = [Path(p).expanduser().resolve() for p in mp3_paths]
    resolved_mp3_paths = sorted(resolved_mp3_paths, key=lambda p: str(p))

    batch_dir = _common_parent_dir(resolved_mp3_paths)
    batch_m3u_path = (batch_dir / "dj_pool.m3u").resolve()
    batch_m3u_path.write_text("\n".join(_render_m3u_lines(resolved_mp3_paths)) + "\n", encoding="utf-8")

    global_m3u_path = (Path(mp3_root).expanduser().resolve() / "dj_pool.m3u").resolve()
    existing_paths = _read_existing_m3u_paths(global_m3u_path)

    base_lines: list[str]
    if global_m3u_path.exists():
        base_lines = global_m3u_path.read_text(encoding="utf-8", errors="replace").splitlines()
        if not base_lines or (base_lines[0] or "").strip() != "#EXTM3U":
            base_lines = ["#EXTM3U"] + base_lines
    else:
        base_lines = ["#EXTM3U"]

    append_lines: list[str] = []
    for path in resolved_mp3_paths:
        path_str = str(path.resolve())
        if path_str in existing_paths:
            continue
        duration, artist, title = _extinf_for_mp3(path)
        append_lines.append(f"#EXTINF:{duration},{artist} - {title}")
        append_lines.append(path_str)
        existing_paths.add(path_str)

    if append_lines:
        base_lines.extend(append_lines)

    global_m3u_path.parent.mkdir(parents=True, exist_ok=True)
    global_m3u_path.write_text("\n".join(base_lines).rstrip("\n") + "\n", encoding="utf-8")

    return batch_m3u_path, global_m3u_path
