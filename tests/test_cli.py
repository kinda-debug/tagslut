"""Module description placeholder."""

from __future__ import annotations

from pathlib import Path

from dedupe import cli, scanner, utils


def test_scan_library_accepts_resume_safe(monkeypatch, tmp_path) -> None:
    captured: dict[str, scanner.ScanConfig] = {}

    def _fake_scan(config: scanner.ScanConfig) -> int:
        captured["config"] = config
        return 0

    monkeypatch.setattr(scanner, "scan_library", _fake_scan)

    root = tmp_path / "library"
    out = tmp_path / "db.sqlite"
    root.mkdir(parents=True, exist_ok=True)
    cli.main(
        [
            "scan-library",
            "--root",
            str(root),
            "--out",
            str(out),
            "--resume-safe",
            "--progress",
        ]
    )

    config = captured["config"]
    assert config.resume_safe is True
    assert config.show_progress is True
    assert config.root == Path(utils.normalise_path(str(root)))
    assert config.database == Path(utils.normalise_path(str(out)))
