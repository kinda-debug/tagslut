#!/usr/bin/env python3
from __future__ import annotations

import csv
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click

from tagslut.dj.classify import (
    append_overrides,
    classify_tracks,
    promote_safe_tracks,
    write_m3u,
)
from tagslut.dj.curation import load_dj_curation_config


@dataclass
class SyncReport:
    safe: int
    block: int
    review: int
    overrides_appended: int
    promoted_ok: int
    promoted_skipped: int
    promoted_failed: int
    warnings: list[str]

    def to_rows(self) -> list[list[str]]:
        rows = [
            ["safe", str(self.safe)],
            ["block", str(self.block)],
            ["review", str(self.review)],
            ["overrides_appended", str(self.overrides_appended)],
            ["promoted_ok", str(self.promoted_ok)],
            ["promoted_skipped", str(self.promoted_skipped)],
            ["promoted_failed", str(self.promoted_failed)],
        ]
        for idx, warning in enumerate(self.warnings, start=1):
            rows.append([f"warning_{idx}", warning])
        return rows


def _check_fs_type(path: Path) -> str | None:
    if shutil.which("diskutil") is None:
        return None
    try:
        out = subprocess.check_output(
            ["diskutil", "info", str(path)],
            text=True,
            stderr=subprocess.STDOUT,
        )
    except Exception:
        return None
    for line in out.splitlines():
        if "File System Personality" in line:
            return line.split(":", 1)[-1].strip()
    return None


def _check_free_space(path: Path, min_gb: int = 16) -> tuple[bool, str]:
    usage = shutil.disk_usage(path)
    free_gb = usage.free / (1024**3)
    ok = free_gb >= min_gb
    return ok, f"{free_gb:.1f}GB free (min {min_gb}GB)"


def _validate_usb(path: Path) -> list[str]:
    warnings: list[str] = []
    if not path.exists() or not path.is_dir():
        raise click.ClickException(f"USB path not found or not a directory: {path}")

    ok, msg = _check_free_space(path)
    if not ok:
        raise click.ClickException(f"USB free space check failed: {msg}")

    fs_type = _check_fs_type(path)
    if fs_type and fs_type.lower() not in {"ms-dos fat32", "exfat"}:
        warnings.append(f"USB filesystem is {fs_type} (expected FAT32 or exFAT)")
    elif fs_type is None:
        warnings.append("USB filesystem type could not be detected (diskutil missing)")

    return warnings


def _warn_long_paths(root: Path, max_len: int = 255) -> list[str]:
    warnings: list[str] = []
    for p in root.rglob("*.mp3"):
        rel = str(p.relative_to(root))
        if len(rel) > max_len:
            warnings.append(f"path too long ({len(rel)}): {rel}")
            if len(warnings) >= 5:
                break
    return warnings


@click.command()
@click.option("--source", "source_path", required=True, type=click.Path(), help="Source library (folder/XLSX/M3U)")
@click.option("--usb", "usb_path", required=True, type=click.Path(), help="DJUSB mount path")
@click.option("--policy", "policy_path", default="config/dj/dj_curation.yaml", help="DJ curation policy YAML")
@click.option("--jobs", default=4, show_default=True, help="Parallel transcode workers")
@click.option("--overwrite", is_flag=True, help="Overwrite existing MP3s")
@click.option("--no-overrides", is_flag=True, help="Do not append to track_overrides.csv")
@click.option("--no-crates", is_flag=True, help="Do not write crate M3U files")
def main(
    source_path: str,
    usb_path: str,
    policy_path: str,
    jobs: int,
    overwrite: bool,
    no_overrides: bool,
    no_crates: bool,
) -> None:
    usb = Path(usb_path)
    warnings = _validate_usb(usb)

    config = load_dj_curation_config(policy_path)
    safe, block, review = classify_tracks(Path(source_path), config)

    if not no_crates:
        crates_dir = Path("config/dj/crates")
        write_m3u(crates_dir / "safe.m3u8", safe)
        write_m3u(crates_dir / "review.m3u8", review)
        write_m3u(crates_dir / "block.m3u8", block)

    appended = 0
    if not no_overrides:
        overrides_path = Path("config/dj/track_overrides.csv")
        appended += append_overrides(overrides_path, safe)
        appended += append_overrides(overrides_path, block)

    ok, skipped, failed = promote_safe_tracks(
        safe,
        usb,
        jobs=jobs,
        overwrite=overwrite,
    )

    warnings.extend(_warn_long_paths(usb))

    report = SyncReport(
        safe=len(safe),
        block=len(block),
        review=len(review),
        overrides_appended=appended,
        promoted_ok=ok,
        promoted_skipped=skipped,
        promoted_failed=failed,
        warnings=warnings,
    )

    report_path = usb / "sync_report.csv"
    with report_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "value"])
        for row in report.to_rows():
            writer.writerow(row)

    click.echo(f"Safe:   {report.safe}")
    click.echo(f"Block:  {report.block}")
    click.echo(f"Review: {report.review}")
    click.echo(f"Overrides appended: {report.overrides_appended}")
    click.echo(f"Promoted: {report.promoted_ok} ok, {report.promoted_skipped} skipped, {report.promoted_failed} failed")
    if report.warnings:
        click.echo("Warnings:")
        for warning in report.warnings:
            click.echo(f"- {warning}")
    click.echo(f"Wrote report: {report_path}")


if __name__ == "__main__":
    sys.exit(main())
