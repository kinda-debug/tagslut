from __future__ import annotations

from pathlib import Path

import pytest

from dedupe.utils.final_library_layout import FinalLibraryLayoutError, build_final_library_destination


def test_final_layout_single_disc() -> None:
    dest_root = Path("/tmp/FINAL_LIBRARY")
    tags = {
        "albumartist": "The Cure",
        "album": "Disintegration",
        "date": "1989-05-02",
        "tracknumber": "1",
        "title": "Plainsong",
    }
    result = build_final_library_destination(tags, dest_root)
    assert result.dest_path == dest_root / "The Cure" / "(1989) Disintegration" / "The Cure – (1989) Disintegration – 01 Plainsong.flac"


def test_final_layout_multi_disc_disc_track_format() -> None:
    dest_root = Path("/tmp/FINAL_LIBRARY")
    tags = {
        "albumartist": "Pink Floyd",
        "album": "The Wall",
        "date": "1979",
        "totaldiscs": "2",
        "discnumber": "2",
        "tracknumber": "2",
        "title": "Comfortably Numb",
    }
    result = build_final_library_destination(tags, dest_root)
    assert result.disc_track == "202"
    assert result.dest_path.name == "Pink Floyd – (1979) The Wall – 202 Comfortably Numb.flac"


def test_final_layout_various_artists_uses_track_artist_for_filename() -> None:
    dest_root = Path("/tmp/FINAL_LIBRARY")
    tags = {
        "albumartist": "Various Artists",
        "artist": "Ben Klock",
        "album": "Ostgut Ton – A Decade",
        "date": "2023",
        "tracknumber": "1",
        "title": "Subzero",
    }
    result = build_final_library_destination(tags, dest_root)
    assert result.dest_path.parts[-3] == "Various Artists"
    assert result.dest_path.name.startswith("Ben Klock – (2023) Ostgut Ton – A Decade – 01 ")


def test_final_layout_requires_albumartist_for_non_various() -> None:
    dest_root = Path("/tmp/FINAL_LIBRARY")
    tags = {"artist": "The Cure", "album": "Disintegration", "date": "1989", "tracknumber": "1", "title": "Plainsong"}
    with pytest.raises(FinalLibraryLayoutError):
        build_final_library_destination(tags, dest_root)


def test_final_layout_albumartist_list_is_treated_as_various_artists() -> None:
    dest_root = Path("/tmp/FINAL_LIBRARY")
    tags = {
        "albumartist": "Andrew K, Kevin Swain, Trafik, Richard Dinsdale",
        "artist": "Trafik",
        "album": "Twin Of The Sun",
        "date": "2009",
        "tracknumber": "3",
        "title": "Dirty Word",
    }
    result = build_final_library_destination(tags, dest_root)
    assert result.dest_path.parts[-3] == "Various Artists"
    assert result.dest_path.name.startswith("Trafik – (2009) Twin Of The Sun – 03 ")


def test_final_layout_single_comma_albumartist_is_not_various_artists() -> None:
    dest_root = Path("/tmp/FINAL_LIBRARY")
    tags = {
        "albumartist": "Bach, Johann Sebastian",
        "album": "Goldberg Variations",
        "date": "1955",
        "tracknumber": "1",
        "title": "Aria",
    }
    result = build_final_library_destination(tags, dest_root)
    assert result.dest_path.parts[-3] == "Bach, Johann Sebastian"
