"""Tests for :mod:`dedupe.legacy_cli` compatibility entry points."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pytest

from dedupe import legacy_cli


def test_analyse_quarantine_subdir_writes_csv(tmp_path: Path, monkeypatch, capsys) -> None:
    """Ensure the analysis entry point delegates to quarantine helpers."""

    called: dict[str, tuple[Path, int | None, int]] = {}

    def fake_analyse(directory: Path, *, limit: int | None, workers: int) -> list[dict]:
        called["analyse"] = (directory, limit, workers)
        return [{"path": "a.flac"}]

    written: dict[str, tuple[list[dict], Path]] = {}

    def fake_write(rows: list[dict], output: Path) -> None:  # type: ignore[override]
        written["output"] = (rows, output)

    monkeypatch.setattr(legacy_cli.quarantine, "analyse_quarantine", fake_analyse)
    monkeypatch.setattr(legacy_cli.quarantine, "write_analysis_csv", fake_write)

    directory = tmp_path / "quarantine"
    directory.mkdir()
    output = tmp_path / "report.csv"

    result = legacy_cli.analyse_quarantine_subdir_main(
        ["--dir", str(directory), "--out", str(output), "--workers", "8", "--limit", "5"]
    )
    assert result == 0
    assert called["analyse"] == (directory, 5, 8)
    assert written["output"][1] == output
    captured = capsys.readouterr()
    assert "Wrote" in captured.out


def test_simple_quarantine_scan_stdout(tmp_path: Path, monkeypatch, capsys) -> None:
    """The scan entry point should print rows when no output is provided."""

    directory = tmp_path / "quarantine"
    directory.mkdir()

    rows = [{"path": "demo.flac", "size": 123, "duration": 3.14}]

    def fake_scan(path: Path, *, limit: int | None) -> list[dict]:
        assert path == directory
        assert limit == 10
        return rows

    monkeypatch.setattr(legacy_cli.quarantine, "simple_scan", fake_scan)

    result = legacy_cli.simple_quarantine_scan_main(["--dir", str(directory), "--limit", "10"])
    assert result == 0
    captured = capsys.readouterr()
    assert "demo.flac" in captured.out


def test_detect_playback_length_writes_csv(tmp_path: Path, monkeypatch, capsys) -> None:
    """The playback mismatch entry point should write CSV files."""

    directory = tmp_path / "quarantine"
    directory.mkdir()
    output = tmp_path / "length.csv"

    def fake_detect(path: Path, *, limit: int | None) -> list[dict]:
        assert path == directory
        assert limit is None
        return [{"path": "demo.flac", "reported": 1.0, "decoded": 1.1, "ratio": 1.1}]

    def fake_write(fieldnames: Iterable[str], rows: Iterable[dict], output_path: Path) -> None:
        assert list(fieldnames) == ["path", "reported", "decoded", "ratio"]
        assert output_path == output
        data = list(rows)
        assert data[0]["ratio"] == 1.1

    monkeypatch.setattr(legacy_cli.quarantine, "detect_playback_issues", fake_detect)
    monkeypatch.setattr(legacy_cli.quarantine, "write_rows_csv", fake_write)

    result = legacy_cli.detect_playback_length_issues_main(["--dir", str(directory), "--out", str(output)])
    assert result == 0
    captured = capsys.readouterr()
    assert "Wrote" in captured.out
