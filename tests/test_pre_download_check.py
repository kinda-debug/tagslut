from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

from tagslut.storage.schema import init_db


def _load_pre_download_check_module():
    module_path = Path(__file__).resolve().parents[1] / "tools" / "review" / "pre_download_check.py"
    spec = importlib.util.spec_from_file_location("pre_download_check_module", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_decide_match_action_skips_equal_or_better_existing() -> None:
    module = _load_pre_download_check_module()
    matched = module.DbRow(
        path="/library/existing.flac",
        isrc="AAA",
        beatport_id="123",
        tidal_id="",
        spotify_id="",
        title="Track",
        artist="Artist",
        album="Album",
        download_source="bpdl",
        quality_rank=2,
    )

    decision, reason = module.decide_match_action(
        matched,
        match_method="beatport_id",
        candidate_quality_rank=3,
        force_keep_matched=False,
    )

    assert decision == "skip"
    assert "equal or better" in reason


def test_decide_match_action_keeps_upgrade_or_unknown_quality() -> None:
    module = _load_pre_download_check_module()
    upgrade_row = module.DbRow(
        path="/library/existing.flac",
        isrc="AAA",
        beatport_id="123",
        tidal_id="",
        spotify_id="",
        title="Track",
        artist="Artist",
        album="Album",
        download_source="bpdl",
        quality_rank=6,
    )
    unknown_row = module.DbRow(
        path="/library/existing-unknown.flac",
        isrc="BBB",
        beatport_id="456",
        tidal_id="",
        spotify_id="",
        title="Track",
        artist="Artist",
        album="Album",
        download_source="legacy",
        quality_rank=None,
    )

    upgrade_decision, upgrade_reason = module.decide_match_action(
        upgrade_row,
        match_method="isrc",
        candidate_quality_rank=3,
        force_keep_matched=False,
    )
    unknown_decision, unknown_reason = module.decide_match_action(
        unknown_row,
        match_method="exact_title_artist",
        candidate_quality_rank=3,
        force_keep_matched=False,
    )

    assert upgrade_decision == "keep"
    assert "improves existing rank 6" in upgrade_reason
    assert unknown_decision == "keep"
    assert "quality rank missing" in unknown_reason


def test_infer_quality_rank_uses_file_format_when_column_missing() -> None:
    module = _load_pre_download_check_module()

    flac_rank = module.infer_quality_rank(
        path="/library/existing.flac",
        quality_rank=None,
        bit_depth=16,
        sample_rate=44100,
        bitrate=943752,
    )
    mp3_rank = module.infer_quality_rank(
        path="/library/existing.mp3",
        quality_rank=None,
        bit_depth=None,
        sample_rate=None,
        bitrate=320000,
    )

    assert flac_rank == 4
    assert mp3_rank == 6


def test_load_db_rows_indexes_tidal_id_and_derives_quality_rank(tmp_path: Path) -> None:
    module = _load_pre_download_check_module()
    db_path = tmp_path / "music.db"

    conn = sqlite3.connect(db_path)
    init_db(conn)
    conn.execute(
        """
        INSERT INTO files (
            path,
            metadata_json,
            canonical_isrc,
            tidal_id,
            canonical_title,
            canonical_artist,
            canonical_album,
            bit_depth,
            sample_rate,
            bitrate,
            quality_rank
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "/library/example.flac",
            "{}",
            "USABC1234567",
            "TI1",
            "Track",
            "Artist",
            "Album",
            16,
            44100,
            943752,
            None,
        ),
    )
    conn.commit()
    conn.close()

    _, _, by_tidal, _, _, _ = module.load_db_rows(db_path)

    assert "TI1" in by_tidal
    assert by_tidal["TI1"][0].quality_rank == 4


def test_build_keep_track_url_supports_spotify() -> None:
    module = _load_pre_download_check_module()

    assert module.build_keep_track_url("spotify", "abc123") == "https://open.spotify.com/track/abc123"
