import json
import sqlite3
from pathlib import Path

import pytest

from tagslut.core.download_manifest import DownloadManifest, ManifestEntry, build_manifest
from tagslut.filters.identity_resolver import TrackIntent
from tagslut.storage.schema import init_db


@pytest.fixture
def mem_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()


def _insert_file(
    conn: sqlite3.Connection,
    *,
    path: str,
    checksum: str,
    quality_rank: int,
    canonical_isrc: str | None = None,
    isrc: str | None = None,
    beatport_id: str | None = None,
    canonical_artist: str | None = None,
    canonical_title: str | None = None,
    duration: float | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO files (
            path, checksum, metadata_json, quality_rank,
            canonical_isrc, isrc, beatport_id, canonical_artist, canonical_title, duration
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            path,
            checksum,
            "{}",
            quality_rank,
            canonical_isrc,
            isrc or canonical_isrc,
            beatport_id,
            canonical_artist,
            canonical_title,
            duration,
        ),
    )
    conn.commit()


def test_build_manifest_marks_new_when_no_match(mem_db: sqlite3.Connection) -> None:
    manifest = build_manifest([TrackIntent(isrc="NOPE")], mem_db)
    assert len(manifest.new) == 1
    assert len(manifest.upgrades) == 0
    assert len(manifest.skipped) == 0
    assert manifest.new[0].reason == "no inventory match"


def test_build_manifest_marks_skip_when_existing_is_equal_or_better(mem_db: sqlite3.Connection) -> None:
    _insert_file(mem_db, path="/music/a.flac", checksum="a", quality_rank=3, isrc="ISRC1")
    intent = TrackIntent(isrc="ISRC1", bit_depth=24, sample_rate=44100, bitrate=0)  # rank 3
    manifest = build_manifest([intent], mem_db)
    assert len(manifest.skipped) == 1
    assert manifest.skipped[0].existing_path == "/music/a.flac"
    assert manifest.skipped[0].candidate_quality_rank == 3


def test_build_manifest_marks_upgrade_when_candidate_is_better(mem_db: sqlite3.Connection) -> None:
    _insert_file(mem_db, path="/music/a.flac", checksum="a", quality_rank=4, isrc="ISRC1")
    intent = TrackIntent(isrc="ISRC1", bit_depth=24, sample_rate=96000, bitrate=0)  # rank 2
    manifest = build_manifest([intent], mem_db)
    assert len(manifest.upgrades) == 1
    assert "improves existing rank" in manifest.upgrades[0].reason


def test_build_manifest_uses_identity_chain_method_in_reason(mem_db: sqlite3.Connection) -> None:
    _insert_file(mem_db, path="/music/b.flac", checksum="b", quality_rank=5, beatport_id="BP-1")
    intent = TrackIntent(beatport_id="BP-1", bit_depth=24, sample_rate=96000, bitrate=0)
    manifest = build_manifest([intent], mem_db)
    assert len(manifest.upgrades) == 1
    assert manifest.upgrades[0].match_method == "beatport_id"
    assert "matched by beatport_id" in manifest.upgrades[0].reason


def test_build_manifest_honors_explicit_candidate_quality_rank(mem_db: sqlite3.Connection) -> None:
    _insert_file(mem_db, path="/music/c.flac", checksum="c", quality_rank=4, isrc="ISRC2")
    intent = TrackIntent(isrc="ISRC2")
    setattr(intent, "candidate_quality_rank", 2)
    manifest = build_manifest([intent], mem_db)
    assert len(manifest.upgrades) == 1
    assert manifest.upgrades[0].candidate_quality_rank == 2


def test_download_manifest_summary_counts() -> None:
    manifest = DownloadManifest(
        new=[ManifestEntry(track_intent=TrackIntent(title="A"), action="new", reason="new")],
        upgrades=[ManifestEntry(track_intent=TrackIntent(title="B"), action="upgrade", reason="up")],
        skipped=[ManifestEntry(track_intent=TrackIntent(title="C"), action="skip", reason="skip")],
    )
    summary = manifest.summary()
    assert "1 new" in summary
    assert "1 upgrades" in summary
    assert "1 skipped" in summary


def test_download_manifest_to_json_writes_serializable_deterministic_payload(tmp_path: Path) -> None:
    manifest = DownloadManifest(
        new=[ManifestEntry(track_intent=TrackIntent(title="A", artist="X"), action="new", reason="r1")],
        upgrades=[],
        skipped=[ManifestEntry(track_intent=TrackIntent(title="B", artist="Y"), action="skip", reason="r2")],
    )
    out = tmp_path / "manifest.json"
    manifest.to_json(out)

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["counts"] == {"new": 1, "upgrades": 0, "skipped": 1, "download": 1}
    assert payload["new"][0]["track_intent"]["title"] == "A"
    assert payload["skipped"][0]["track_intent"]["artist"] == "Y"


def test_build_manifest_preserves_input_order_within_buckets(mem_db: sqlite3.Connection) -> None:
    intents = [
        TrackIntent(title="new-a", artist="nobody"),
        TrackIntent(title="new-b", artist="nobody"),
    ]
    manifest = build_manifest(intents, mem_db)
    titles = [entry.track_intent.title for entry in manifest.new]
    assert titles == ["new-a", "new-b"]


def test_build_manifest_text_only_match_stays_new(mem_db: sqlite3.Connection) -> None:
    _insert_file(
        mem_db,
        path="/music/fuzzy.flac",
        checksum="f",
        quality_rank=4,
        canonical_artist="Test Artist",
        canonical_title="Great Track",
        duration=240.0,
    )
    manifest = build_manifest(
        [
            TrackIntent(
                artist="Test Artist",
                title="Great Track",
                duration_s=241.0,
                bit_depth=16,
                sample_rate=44100,
                bitrate=0,
            )
        ],
        mem_db,
    )
    assert len(manifest.new) == 1
    assert manifest.new[0].track_intent.title == "Great Track"
