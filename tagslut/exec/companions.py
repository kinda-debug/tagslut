"""Helpers for moving per-track companion files alongside audio moves."""

from __future__ import annotations

from pathlib import Path

from tagslut.exec.engine import CollisionPolicy, MoveReceipt, execute_move
from tagslut.utils import AUDIO_EXTENSIONS

_TRACK_SIDECAR_SUFFIXES = (
    ".lrc",
    ".cover.jpg",
    ".cover.jpeg",
    ".cover.png",
    ".jpg",
    ".jpeg",
    ".png",
)


def _is_audio_path(path: Path) -> bool:
    return path.suffix.lower() in AUDIO_EXTENSIONS


def iter_track_companion_pairs(src: Path, dest: Path) -> list[tuple[Path, Path]]:
    """Return existing sidecar src/dest pairs derived from one audio move."""

    src = Path(src)
    dest = Path(dest)
    if not _is_audio_path(src):
        return []

    pairs: list[tuple[Path, Path]] = []
    seen: set[Path] = set()
    for suffix in _TRACK_SIDECAR_SUFFIXES:
        companion_src = src.with_name(f"{src.stem}{suffix}")
        if not companion_src.exists() or companion_src in seen:
            continue
        seen.add(companion_src)
        companion_dest = dest.with_name(f"{dest.stem}{suffix}")
        pairs.append((companion_src, companion_dest))
    return pairs


def execute_track_companion_moves(
    *,
    src: Path,
    dest: Path,
    execute: bool,
    collision_policy: CollisionPolicy = "skip",
) -> list[MoveReceipt]:
    """Move known per-track sidecars derived from one audio move."""

    return [
        execute_move(
            companion_src,
            companion_dest,
            execute=execute,
            collision_policy=collision_policy,
        )
        for companion_src, companion_dest in iter_track_companion_pairs(src, dest)
    ]
