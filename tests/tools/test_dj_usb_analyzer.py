import os
from pathlib import Path

from tagslut.dj.transcode import build_output_path
from tools.dj_usb_analyzer import (
    SkipRow,
    build_track_row_from_path,
    find_weird_skips,
    generate_incremental_m3u,
    load_skip_report,
    load_sync_report,
    summarize_skip_reasons,
)


def test_load_sync_report_parses(tmp_path: Path) -> None:
    report = tmp_path / "sync_report.csv"
    report.write_text(
        "metric,value\n"
        "safe,10\n"
        "block,2\n"
        "review,3\n"
        "overrides_appended,1\n"
        "promoted_ok,5\n"
        "promoted_skipped,6\n"
        "promoted_failed,0\n"
        "warning_1,USB filesystem is exfat\n",
        encoding="utf-8",
    )
    summary = load_sync_report(report)
    assert summary.safe == 10
    assert summary.block == 2
    assert summary.review == 3
    assert summary.promoted_ok == 5
    assert summary.promoted_skipped == 6
    assert summary.promoted_failed == 0
    assert summary.warnings == ["USB filesystem is exfat"]


def test_skip_report_reason_counts(tmp_path: Path) -> None:
    report = tmp_path / "skip_report.csv"
    report.write_text(
        "exists,source,target,reason\n"
        "1,/src/a.flac,/dst/a.mp3,exists\n"
        "0,/src/b.flac,/dst/b.mp3,duration_fail:short\n"
        "0,/src/c.flac,/dst/c.mp3,bpm_fail\n",
        encoding="utf-8",
    )
    rows = load_skip_report(report)
    counts = summarize_skip_reasons(rows)
    assert counts["exists"] == 1
    assert counts["duration_fail"] == 1
    assert counts["bpm_fail"] == 1


def test_find_weird_skips(tmp_path: Path) -> None:
    existing_source = tmp_path / "source.flac"
    existing_source.write_text("x", encoding="utf-8")
    target = tmp_path / "target.mp3"
    target.write_text("y", encoding="utf-8")

    rows = [
        SkipRow(exists=False, source=str(existing_source), target=str(target), reason="exists"),
        SkipRow(exists=True, source=str(tmp_path / "missing.flac"),
                target=str(target), reason="exists"),
    ]
    weird = find_weird_skips(rows, max_items=10)
    assert len(weird) == 2
    assert weird[0].score >= weird[1].score


def test_generate_incremental_m3u(tmp_path: Path) -> None:
    library = tmp_path / "library"
    usb = tmp_path / "usb"

    existing = library / "Artist" / "Album" / "01 Song.flac"
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_text("x", encoding="utf-8")

    new_track = library / "Artist" / "Album" / "02 New.flac"
    new_track.write_text("y", encoding="utf-8")

    os.utime(existing, None)
    os.utime(new_track, None)

    track_row = build_track_row_from_path(existing)
    target = build_output_path(usb, track_row)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("mp3", encoding="utf-8")

    preset = generate_incremental_m3u(library, usb, days=90, out_dir=tmp_path)
    lines = preset.output_path.read_text(encoding="utf-8").splitlines()

    assert str(new_track) in lines
    assert str(existing) not in lines
