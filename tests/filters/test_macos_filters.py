from __future__ import annotations

from tagslut.filters.macos_filters import MacOSFilters


def test_is_macos_metadata_ds_store_true() -> None:
    assert MacOSFilters.is_macos_metadata(".DS_Store") is True


def test_is_macos_metadata_regular_audio_false() -> None:
    assert MacOSFilters.is_macos_metadata("track.flac") is False


def test_filter_files_removes_macos_metadata_entries() -> None:
    files = [
        "/music/.DS_Store",
        "/music/._Track.aiff",
        "/music/.Spotlight-V100",
        "/music/set01.flac",
        "/music/set02.mp3",
    ]

    assert MacOSFilters.filter_files(files) == ["/music/set01.flac", "/music/set02.mp3"]


def test_count_filtered_returns_expected_counts() -> None:
    files = ["/m/.DS_Store", "/m/._x", "/m/a.flac"]

    assert MacOSFilters.count_filtered(files) == {"total": 3, "kept": 1, "removed": 2}


def test_is_macos_metadata_by_filename_only() -> None:
    assert MacOSFilters.is_macos_metadata("/nested/path/.Trashes") is True
    assert MacOSFilters.is_macos_metadata("/nested/path/album/.AppleDouble") is True
