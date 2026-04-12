from __future__ import annotations

import datetime
import os
import pathlib
import re
import shutil
from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class IntakeKind(str, Enum):
    UNIQUE = "UNIQUE"
    DUPLICATE = "DUPLICATE"
    SKIPPED = "SKIPPED"


@dataclass(frozen=True)
class PlannedIntakeMove:
    src: pathlib.Path
    dst: pathlib.Path
    kind: IntakeKind
    match: pathlib.Path | None


_TRACK_PREFIX_RE = re.compile(r"^\s*\d+\s*(?:[-_.]\s*\d+)?\s+")


def _norm_basename(name: str) -> str:
    return _TRACK_PREFIX_RE.sub("", name).strip().lower()


def _walk_files(root: pathlib.Path) -> Iterable[pathlib.Path]:
    for dirpath, _, filenames in os.walk(root, followlinks=False):
        current = pathlib.Path(dirpath)
        for filename in filenames:
            p = current / filename
            try:
                if p.is_symlink():
                    continue
            except OSError:
                continue
            yield p


def _safe_move(src: pathlib.Path, dst: pathlib.Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(src, dst)
        return
    except OSError as exc:
        if getattr(exc, "errno", None) != getattr(os, "EXDEV", 18):
            raise

    shutil.copy2(src, dst)
    src_stat = src.stat()
    dst_stat = dst.stat()
    if src_stat.st_size != dst_stat.st_size:
        raise RuntimeError(f"size mismatch after copy: {src} -> {dst}")
    src.unlink()


def plan_intake_mp3_to_sort_staging(
    *,
    src_root: pathlib.Path,
    intake_root: pathlib.Path,
    mp3_library_root: pathlib.Path | None,
    leftovers_root: pathlib.Path | None,
    today: datetime.date | None = None,
) -> tuple[list[PlannedIntakeMove], int]:
    """
    Plan moving MP3s from a drop folder into a staging intake folder, while
    optionally deduping by normalized basename against one or two reference roots.

    Only MP3 files directly under src_root are considered (non-recursive).
    Returns (planned_moves, skipped_count).
    """
    if today is None:
        today = datetime.date.today()

    if not src_root.exists() or not src_root.is_dir():
        raise ValueError(f"source not found or not a directory: {src_root}")

    if mp3_library_root is not None:
        if not mp3_library_root.exists() or not mp3_library_root.is_dir():
            raise ValueError(f"mp3 library root not found or not a directory: {mp3_library_root}")
    if leftovers_root is not None:
        if not leftovers_root.exists() or not leftovers_root.is_dir():
            raise ValueError(f"leftovers root not found or not a directory: {leftovers_root}")

    index: dict[str, pathlib.Path] = {}
    for root in [mp3_library_root, leftovers_root]:
        if root is None:
            continue
        for p in _walk_files(root):
            if not p.name.lower().endswith(".mp3"):
                continue
            key = _norm_basename(p.name)
            if key and key not in index:
                index[key] = p

    planned: list[PlannedIntakeMove] = []
    skipped = 0
    for p in sorted(src_root.iterdir(), key=lambda x: str(x)):
        if not p.is_file():
            skipped += 1
            continue
        if not p.name.lower().endswith(".mp3"):
            skipped += 1
            continue

        key = _norm_basename(p.name)
        match = index.get(key)
        if match is None:
            planned.append(
                PlannedIntakeMove(
                    src=p,
                    dst=intake_root / p.name,
                    kind=IntakeKind.UNIQUE,
                    match=None,
                )
            )
        else:
            dupes_root = src_root / f"_dupes_{today.strftime('%Y%m%d')}"
            planned.append(
                PlannedIntakeMove(
                    src=p,
                    dst=dupes_root / p.name,
                    kind=IntakeKind.DUPLICATE,
                    match=match,
                )
            )

    return planned, skipped


def execute_intake_plan(planned: list[PlannedIntakeMove]) -> None:
    for item in planned:
        _safe_move(item.src, item.dst)
        if not item.dst.exists():
            raise RuntimeError(f"destination missing after move: {item.dst}")

