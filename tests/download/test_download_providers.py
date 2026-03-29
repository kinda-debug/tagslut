from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from tagslut.download.providers import BeatportStoreDownloadProvider, QobuzPurchaseDownloadProvider
from tagslut.storage.v3.download_registration import register_downloaded_asset
from tagslut.storage.v3.schema import create_schema_v3


def test_beatport_stub_raises_not_implemented() -> None:
    provider = BeatportStoreDownloadProvider()
    with pytest.raises(NotImplementedError, match="Beatport store download workflow is not implemented"):
        provider.download_track("USRC17607839", Path("/tmp"))


def test_qobuz_download_track_returns_result_with_download_source_qobuz_purchase(tmp_path: Path, monkeypatch) -> None:
    # Avoid real HTTP calls by stubbing the provider internals.
    monkeypatch.setenv("QOBUZ_APP_ID", "app")
    monkeypatch.setenv("QOBUZ_USER_AUTH_TOKEN", "token")

    provider = QobuzPurchaseDownloadProvider(client=None)
    monkeypatch.setattr(provider, "_resolve_track_id_for_isrc", lambda _isrc: "t1")
    monkeypatch.setattr(provider, "_get_download_url", lambda _track_id: ("https://example.invalid/file", "audio/flac"))

    def _fake_download(_url: str, dest_path: Path) -> None:
        dest_path.write_bytes(b"data")

    monkeypatch.setattr(provider, "_download_to_file", _fake_download)

    result = provider.download_track("USRC17607839", tmp_path)
    assert result.download_source == "qobuz_purchase"
    assert result.provider == "qobuz"
    assert result.provider_track_id == "t1"
    assert result.file_path.exists()


def test_download_source_written_to_asset_file_row(tmp_path: Path) -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_schema_v3(conn)

    file_path = tmp_path / "a.flac"
    file_path.write_bytes(b"x")
    result = type(
        "R",
        (),
        {
            "file_path": file_path,
            "download_source": "qobuz_purchase",
        },
    )()
    register_downloaded_asset(conn, result)  # type: ignore[arg-type]

    row = conn.execute("SELECT path, download_source FROM asset_file WHERE path = ?", (str(file_path),)).fetchone()
    assert row is not None
    assert row["download_source"] == "qobuz_purchase"


def test_register_downloaded_asset_accepts_other_sources(tmp_path: Path) -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_schema_v3(conn)

    for source in ("tidal_wrapper", "beatport_store"):
        file_path = tmp_path / f"{source}.flac"
        file_path.write_bytes(b"x")
        result = type("R", (), {"file_path": file_path, "download_source": source})()
        register_downloaded_asset(conn, result)  # type: ignore[arg-type]

        row = conn.execute(
            "SELECT download_source FROM asset_file WHERE path = ?",
            (str(file_path),),
        ).fetchone()
        assert row is not None
        assert row["download_source"] == source
