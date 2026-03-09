from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

flask = pytest.importorskip("flask", reason="flask optional dep not installed")

from tagslut._web import review_app  # noqa: E402


def _make_review_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE files (
            canonical_artist TEXT,
            canonical_album TEXT,
            canonical_title TEXT,
            path TEXT,
            mtime INTEGER
        )
        """
    )
    conn.executemany(
        "INSERT INTO files VALUES (?, ?, ?, ?, ?)",
        [
            ("Artist One", "Album One", "Track One", "/music/artist-one/track-one.flac", 2),
            ("Artist Two", "Album Two", "Track Two", "/music/artist-two/track-two.flac", 1),
        ],
    )
    conn.commit()
    conn.close()


def test_artist_search_query_returns_results(tmp_path: Path) -> None:
    db_path = tmp_path / "review.sqlite3"
    _make_review_db(db_path)

    review_app.APP.config["TESTING"] = True
    review_app.APP.config["DB_PATH"] = str(db_path)
    client = review_app.APP.test_client()

    response = client.get("/api/items?level=artist&q=Artist%20One")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload == {
        "items": [
            {
                "count": 1,
                "key": "artist one",
                "label": "Artist One",
                "status": "unreviewed",
            }
        ]
    }


def test_album_search_query_returns_results(tmp_path: Path) -> None:
    db_path = tmp_path / "review.sqlite3"
    _make_review_db(db_path)

    review_app.APP.config["TESTING"] = True
    review_app.APP.config["DB_PATH"] = str(db_path)
    client = review_app.APP.test_client()

    response = client.get("/api/items?level=album&q=Album%20One")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload == {
        "items": [
            {
                "count": 1,
                "key": "artist one|album one",
                "label": "Artist One — Album One",
                "status": "unreviewed",
            }
        ]
    }


def test_export_usb_validation_uses_repo_artifacts_and_accepts_macos_mount() -> None:
    assert review_app._validate_usb_path("/Volumes/DJUSB") == "/Volumes/DJUSB"
    assert review_app._validate_output_path("dj_review_ok.m3u8") == (
        Path(review_app.__file__).resolve().parents[2] / "artifacts" / "dj_review_ok.m3u8"
    )
