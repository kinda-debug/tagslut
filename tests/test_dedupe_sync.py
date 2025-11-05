from __future__ import annotations

"""Unit tests for :mod:`dedupe_sync`."""

import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.dedupe_sync import (
    NullHealthChecker,
    audit_library_playback,
    discover_dedupe_root,
    gather_track_info,
    pick_preferred_track,
    run_cli,
    synchronize_track,
)


class StubHealthChecker(NullHealthChecker):
    """Return predetermined health states for specific paths."""

    def __init__(self, results: Dict[Path, Tuple[Optional[bool], Optional[str]]]):
        self._results = results

    def check(self, path: Path) -> Tuple[Optional[bool], Optional[str]]:
        return self._results.get(path, (None, "health check disabled"))


def test_discover_dedupe_root(tmp_path: Path) -> None:
    listing = tmp_path / "DEDUPE_DIR.txt"
    listing.write_text(
        """Last login: now
/Volumes/dotad/MUSIC/DEDUPE > tree -L 10
.""",
        encoding="utf-8",
    )
    assert discover_dedupe_root(listing) == Path("/Volumes/dotad/MUSIC/DEDUPE")


def test_pick_preferred_track_health_priority(tmp_path: Path) -> None:
    checker = StubHealthChecker({})
    library = gather_track_info(tmp_path / "lib.flac", checker)
    dedupe = gather_track_info(tmp_path / "stage.flac", checker)
    assert pick_preferred_track(library, dedupe) == "library"


def test_synchronize_moves_when_library_missing(tmp_path: Path) -> None:
    library_root = tmp_path / "library"
    dedupe_root = tmp_path / "dedupe"
    dedupe_file = dedupe_root / "Artist" / "Album" / "song.flac"
    dedupe_file.parent.mkdir(parents=True)
    dedupe_file.write_text("dedupe", encoding="utf-8")

    checker = StubHealthChecker({dedupe_file: (True, "ok")})

    outcome = synchronize_track(
        Path("Artist/Album/song.flac"),
        library_root,
        dedupe_root,
        checker,
    )

    assert outcome.action == "moved"
    assert (library_root / "Artist" / "Album" / "song.flac").read_text(
        encoding="utf-8"
    ) == "dedupe"
    assert not dedupe_file.exists()


def test_synchronize_deletes_when_library_healthier(tmp_path: Path) -> None:
    library_root = tmp_path / "library"
    dedupe_root = tmp_path / "dedupe"
    library_file = library_root / "Artist" / "Album" / "song.flac"
    dedupe_file = dedupe_root / "Artist" / "Album" / "song.flac"

    library_file.parent.mkdir(parents=True)
    dedupe_file.parent.mkdir(parents=True)
    library_file.write_text("library", encoding="utf-8")
    dedupe_file.write_text("dedupe", encoding="utf-8")

    checker = StubHealthChecker(
        {library_file: (True, "lib"), dedupe_file: (False, "dup")}
    )

    outcome = synchronize_track(
        Path("Artist/Album/song.flac"),
        library_root,
        dedupe_root,
        checker,
    )

    assert outcome.action == "deleted"
    assert library_file.read_text(encoding="utf-8") == "library"
    assert not dedupe_file.exists()


def test_synchronize_swaps_when_dedupe_healthier(tmp_path: Path) -> None:
    library_root = tmp_path / "library"
    dedupe_root = tmp_path / "dedupe"
    library_file = library_root / "Artist" / "Album" / "song.flac"
    dedupe_file = dedupe_root / "Artist" / "Album" / "song.flac"

    library_file.parent.mkdir(parents=True)
    dedupe_file.parent.mkdir(parents=True)
    library_file.write_text("library", encoding="utf-8")
    dedupe_file.write_text("dedupe", encoding="utf-8")

    checker = StubHealthChecker(
        {library_file: (False, "lib"), dedupe_file: (True, "dup")}
    )

    outcome = synchronize_track(
        Path("Artist/Album/song.flac"),
        library_root,
        dedupe_root,
        checker,
    )

    assert outcome.action == "swapped"
    assert library_file.read_text(encoding="utf-8") == "dedupe"
    assert not dedupe_file.exists()


def test_synchronize_prunes_empty_directories(tmp_path: Path) -> None:
    library_root = tmp_path / "library"
    dedupe_root = tmp_path / "dedupe"
    dedupe_file = dedupe_root / "Artist" / "Album" / "song.flac"

    dedupe_file.parent.mkdir(parents=True)
    dedupe_file.write_text("dedupe", encoding="utf-8")

    checker = StubHealthChecker({dedupe_file: (True, "ok")})

    outcome = synchronize_track(
        Path("Artist/Album/song.flac"),
        library_root,
        dedupe_root,
        checker,
    )

    assert outcome.action == "moved"
    assert not (dedupe_root / "Artist" / "Album").exists()
    assert not (dedupe_root / "Artist").exists()
    assert dedupe_root.exists()


def test_synchronize_dry_run(tmp_path: Path) -> None:
    library_root = tmp_path / "library"
    dedupe_root = tmp_path / "dedupe"
    library_file = library_root / "Artist" / "Album" / "song.flac"
    dedupe_file = dedupe_root / "Artist" / "Album" / "song.flac"

    library_file.parent.mkdir(parents=True)
    dedupe_file.parent.mkdir(parents=True)
    library_file.write_text("library", encoding="utf-8")
    dedupe_file.write_text("dedupe", encoding="utf-8")

    checker = StubHealthChecker(
        {library_file: (False, "lib"), dedupe_file: (True, "dup")}
    )

    outcome = synchronize_track(
        Path("Artist/Album/song.flac"),
        library_root,
        dedupe_root,
        checker,
        dry_run=True,
    )

    assert outcome.action == "would-swap"
    assert library_file.read_text(encoding="utf-8") == "library"
    assert dedupe_file.read_text(encoding="utf-8") == "dedupe"


def test_audit_library_playback_reports_status(tmp_path: Path) -> None:
    library_root = tmp_path / "library"
    healthy_file = library_root / "Artist" / "Album" / "healthy.flac"
    bad_file = library_root / "Artist" / "Album" / "broken.flac"

    healthy_file.parent.mkdir(parents=True)
    healthy_file.write_text("ok", encoding="utf-8")
    bad_file.write_text("bad", encoding="utf-8")

    checker = StubHealthChecker(
        {
            healthy_file: (True, "decoded"),
            bad_file: (False, "decode failed"),
        }
    )

    results = audit_library_playback(library_root, checker)
    outcome_map = {result.relative_path.name: result for result in results}

    assert len(results) == 2
    assert outcome_map["healthy.flac"].healthy is True
    assert outcome_map["broken.flac"].healthy is False
    assert outcome_map["broken.flac"].note == "decode failed"


def test_run_cli_requires_health_checks_for_library_verify(tmp_path: Path) -> None:
    library_root = tmp_path / "library"
    dedupe_root = tmp_path / "dedupe"
    library_root.mkdir()
    dedupe_root.mkdir()

    with pytest.raises(SystemExit):
        run_cli(
            [
                "--library-root",
                str(library_root),
                "--dedupe-root",
                str(dedupe_root),
                "--health-check",
                "none",
                "--verify-library",
            ]
        )


def test_run_cli_reports_library_audit_summary(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    library_root = tmp_path / "library"
    dedupe_root = tmp_path / "dedupe"
    library_file = library_root / "Artist" / "Album" / "song.flac"
    dedupe_file = dedupe_root / "Artist" / "Album" / "song.flac"

    library_file.parent.mkdir(parents=True)
    dedupe_file.parent.mkdir(parents=True)
    library_file.write_text("library", encoding="utf-8")
    dedupe_file.write_text("dedupe", encoding="utf-8")

    class StubCommandChecker:
        def __init__(self, timeout: int = 45) -> None:
            self.timeout = timeout

        def check(self, path: Path) -> Tuple[Optional[bool], Optional[str]]:
            return True, "ok"

    monkeypatch.setattr("scripts.dedupe_sync.CommandHealthChecker", StubCommandChecker)

    exit_code = run_cli(
        [
            "--library-root",
            str(library_root),
            "--dedupe-root",
            str(dedupe_root),
            "--verify-library",
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Library audit:" in captured.out
