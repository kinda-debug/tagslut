#!/usr/bin/env python3
from __future__ import annotations

import csv
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote
import xml.etree.ElementTree as ET

import click

from tagslut.dj.classify import (
    append_overrides,
    classify_tracks,
    promote_safe_tracks,
    write_m3u,
)
from tagslut.dj.curation import load_dj_curation_config

try:
    from mutagen.id3 import ID3, ID3NoHeaderError
    from mutagen.mp3 import MP3
except Exception:  # pragma: no cover - optional dependency handling
    ID3 = None  # type: ignore[assignment]
    ID3NoHeaderError = Exception  # type: ignore[assignment]
    MP3 = None  # type: ignore[assignment]

@dataclass
class SyncReport:
    safe: int
    block: int
    review: int
    overrides_appended: int
    promoted_ok: int
    promoted_skipped: int
    promoted_failed: int
    finalize_scanned: int = 0
    finalize_retaged: int = 0
    finalize_artwork_dropped: int = 0
    finalize_errors: int = 0
    rekordbox_xml: str = ""
    warnings: list[str] = None

    def __post_init__(self) -> None:
        if self.warnings is None:
            self.warnings = []

    def to_rows(self) -> list[list[str]]:
        rows = [
            ["safe", str(self.safe)],
            ["block", str(self.block)],
            ["review", str(self.review)],
            ["overrides_appended", str(self.overrides_appended)],
            ["promoted_ok", str(self.promoted_ok)],
            ["promoted_skipped", str(self.promoted_skipped)],
            ["promoted_failed", str(self.promoted_failed)],
            ["finalize_scanned", str(self.finalize_scanned)],
            ["finalize_retaged", str(self.finalize_retaged)],
            ["finalize_artwork_dropped", str(self.finalize_artwork_dropped)],
            ["finalize_errors", str(self.finalize_errors)],
        ]
        if self.rekordbox_xml:
            rows.append(["rekordbox_xml", self.rekordbox_xml])
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


def _iter_mp3_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            if name.startswith("._"):
                continue
            if name.lower().endswith(".mp3"):
                files.append(Path(dirpath) / name)
    return files


def _enforce_id3v23_and_artwork(path: Path, artwork_max_bytes: int) -> tuple[bool, bool]:
    if ID3 is None:
        raise RuntimeError("mutagen is not available")
    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        return (False, False)
    except Exception as exc:
        raise RuntimeError(f"Failed to read ID3 tags: {exc}") from exc

    removed_art = False
    if artwork_max_bytes > 0:
        apics = tags.getall("APIC")
        if apics:
            keep = []
            for apic in apics:
                data = getattr(apic, "data", None)
                if data and len(data) > artwork_max_bytes:
                    removed_art = True
                    continue
                keep.append(apic)
            if removed_art:
                tags.delall("APIC")
                for apic in keep:
                    tags.add(apic)

    # Force ID3v2.3 on disk when possible
    needs_save = True
    try:
        needs_save = tags.version != (2, 3, 0)
    except Exception:
        needs_save = True

    if removed_art or needs_save:
        tags.save(path, v2_version=3)
        return (True, removed_art)
    return (False, removed_art)


def _tag_text(tags: ID3, *keys: str) -> str | None:
    for key in keys:
        frame = tags.get(key)
        if frame is None:
            continue
        text = getattr(frame, "text", None)
        if text:
            value = str(text[0]).strip()
            if value:
                return value
    return None


def _tag_track_number(tags: ID3) -> str | None:
    raw = _tag_text(tags, "TRCK")
    if not raw:
        return None
    return raw.split("/", 1)[0].strip() or None


def _build_rekordbox_xml(root: Path, output_path: Path, mp3_files: list[Path]) -> None:
    if ID3 is None or MP3 is None:
        raise RuntimeError("mutagen is not available")

    dj_playlists = ET.Element("DJ_PLAYLISTS", attrib={"Version": "1.0.0"})
    ET.SubElement(
        dj_playlists,
        "PRODUCT",
        attrib={"Name": "tagslut", "Version": "v8", "Company": "tagslut"},
    )

    collection = ET.SubElement(dj_playlists, "COLLECTION", attrib={"Entries": str(len(mp3_files))})
    playlist_root = ET.SubElement(dj_playlists, "PLAYLISTS")
    root_node = ET.SubElement(playlist_root, "NODE", attrib={"Type": "0", "Name": "ROOT", "Count": "1"})
    usb_node = ET.SubElement(
        root_node,
        "NODE",
        attrib={"Type": "1", "Name": "DJUSB", "Entries": str(len(mp3_files))},
    )

    for track_id, path in enumerate(mp3_files, start=1):
        try:
            audio = MP3(path)
        except Exception:
            audio = None
        try:
            tags = ID3(path)
        except Exception:
            tags = None

        attrs: dict[str, str] = {"TrackID": str(track_id)}
        if tags:
            title = _tag_text(tags, "TIT2")
            artist = _tag_text(tags, "TPE1")
            album = _tag_text(tags, "TALB")
            genre = _tag_text(tags, "TCON")
            bpm = _tag_text(tags, "TBPM")
            key = _tag_text(tags, "TKEY", "TXXX:INITIALKEY")
            year = _tag_text(tags, "TDRC", "TYER")
            track_number = _tag_track_number(tags)
            if title:
                attrs["Name"] = title
            if artist:
                attrs["Artist"] = artist
            if album:
                attrs["Album"] = album
            if genre:
                attrs["Genre"] = genre
            if bpm:
                attrs["BPM"] = bpm
            if key:
                attrs["Key"] = key
            if year:
                attrs["Year"] = year
            if track_number:
                attrs["TrackNumber"] = track_number

        if audio and getattr(audio, "info", None):
            duration = getattr(audio.info, "length", None)
            bitrate = getattr(audio.info, "bitrate", None)
            if duration:
                attrs["TotalTime"] = str(int(duration))
            if bitrate:
                attrs["BitRate"] = str(int(bitrate / 1000))

        try:
            attrs["FileSize"] = str(path.stat().st_size)
        except Exception:
            pass

        location = "file://localhost" + quote(path.resolve().as_posix())
        attrs["Location"] = location

        ET.SubElement(collection, "TRACK", attrib=attrs)
        ET.SubElement(usb_node, "TRACK", attrib={"Key": str(track_id)})

    tree = ET.ElementTree(dj_playlists)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(output_path, encoding="utf-8", xml_declaration=True)


def _pioneer_finalize(
    usb_root: Path,
    *,
    artwork_max_kb: int,
    rekordbox_xml: str | None,
) -> tuple[int, int, int, int, str]:
    mp3_files = _iter_mp3_files(usb_root)
    scanned = len(mp3_files)
    retagged = 0
    artwork_dropped = 0
    errors = 0

    if scanned == 0:
        return (0, 0, 0, 0, "")

    max_bytes = max(0, artwork_max_kb) * 1024
    for path in mp3_files:
        try:
            changed, dropped = _enforce_id3v23_and_artwork(path, max_bytes)
        except Exception:
            errors += 1
            continue
        if changed:
            retagged += 1
        if dropped:
            artwork_dropped += 1

    xml_path_str = ""
    if rekordbox_xml:
        xml_path = Path(rekordbox_xml)
        if not xml_path.is_absolute():
            xml_path = usb_root / xml_path
        _build_rekordbox_xml(usb_root, xml_path, mp3_files)
        xml_path_str = str(xml_path)

    return (scanned, retagged, artwork_dropped, errors, xml_path_str)


@click.command()
@click.option("--source", "source_path", required=True, type=click.Path(), help="Source library (folder/XLSX/M3U)")
@click.option("--usb", "usb_path", required=True, type=click.Path(), help="DJUSB mount path")
@click.option(
    "--policy",
    "policy_path",
    default="config/dj/dj_curation_usb_v8.yaml",
    help="DJ curation policy YAML",
)
@click.option("--jobs", default=4, show_default=True, help="Parallel transcode workers")
@click.option("--overwrite", is_flag=True, help="Overwrite existing MP3s")
@click.option("--no-overrides", is_flag=True, help="Do not append to track_overrides.csv")
@click.option("--no-crates", is_flag=True, help="Do not write crate M3U files")
@click.option(
    "--pioneer-finalize/--no-pioneer-finalize",
    default=True,
    show_default=True,
    help="Finalize USB for Pioneer/Rekordbox (ID3v2.3, artwork cap, Rekordbox XML)",
)
@click.option(
    "--artwork-max-kb",
    default=500,
    show_default=True,
    help="Max artwork size (KB) before dropping embedded cover art",
)
@click.option(
    "--rekordbox-xml",
    default="rekordbox.xml",
    show_default=True,
    help="Rekordbox XML output name (relative to USB root)",
)
def main(
    source_path: str,
    usb_path: str,
    policy_path: str,
    jobs: int,
    overwrite: bool,
    no_overrides: bool,
    no_crates: bool,
    pioneer_finalize: bool,
    artwork_max_kb: int,
    rekordbox_xml: str,
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

    finalize_scanned = finalize_retaged = finalize_artwork = finalize_errors = 0
    rekordbox_xml_path = ""
    if pioneer_finalize:
        start = time.time()
        try:
            (
                finalize_scanned,
                finalize_retaged,
                finalize_artwork,
                finalize_errors,
                rekordbox_xml_path,
            ) = _pioneer_finalize(
                usb,
                artwork_max_kb=artwork_max_kb,
                rekordbox_xml=rekordbox_xml,
            )
        except Exception as exc:
            warnings.append(f"pioneer_finalize_failed: {exc}")
        else:
            elapsed = time.time() - start
            warnings.append(
                f"pioneer_finalize: scanned={finalize_scanned} retagged={finalize_retaged} "
                f"artwork_dropped={finalize_artwork} errors={finalize_errors} "
                f"elapsed={elapsed:.1f}s"
            )

    report = SyncReport(
        safe=len(safe),
        block=len(block),
        review=len(review),
        overrides_appended=appended,
        promoted_ok=ok,
        promoted_skipped=skipped,
        promoted_failed=failed,
        finalize_scanned=finalize_scanned,
        finalize_retaged=finalize_retaged,
        finalize_artwork_dropped=finalize_artwork,
        finalize_errors=finalize_errors,
        rekordbox_xml=rekordbox_xml_path,
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
