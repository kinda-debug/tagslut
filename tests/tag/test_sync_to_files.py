from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner
from sqlalchemy import select
from sqlalchemy.orm import Session

from tagslut.adapters.rekordbox.importer import import_rekordbox_xml
from tagslut.cli.commands.tag import run_tag_sync_to_files
from tagslut.cli.main import cli
from tagslut.library import create_library_engine, ensure_library_schema
from tagslut.library.models import (
    ApprovedMetadata,
    MetadataCandidate,
    RawProviderResult,
    SourceProvenance,
    Track,
    TrackFile,
)
from tagslut.storage.schema import init_db

FIXTURE_XML = Path(__file__).resolve().parents[1] / "library" / "fixtures" / "small_rekordbox.xml"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _db_path(tmp_path: Path) -> Path:
    return (tmp_path / "sync-to-files.db").resolve()


def _db_url(tmp_path: Path) -> str:
    return f"sqlite:///{_db_path(tmp_path)}"


def _copy_fixture_xml(tmp_path: Path) -> Path:
    xml_path = tmp_path / "small_rekordbox.xml"
    xml_path.write_text(FIXTURE_XML.read_text(encoding="utf-8"), encoding="utf-8")
    return xml_path


def _prepare_library(tmp_path: Path, *, batch_id: str = "batch-1") -> tuple[str, str, str]:
    db_url = _db_url(tmp_path)
    xml_path = _copy_fixture_xml(tmp_path)
    result = import_rekordbox_xml(xml_path, db_url, dry_run=False)
    assert result.errors == []
    ensure_library_schema(db_url)

    with sqlite3.connect(str(_db_path(tmp_path))) as conn:
        conn.row_factory = sqlite3.Row
        init_db(conn)

    engine = create_library_engine(db_url)
    with Session(engine) as session:
        track = session.scalar(select(Track).where(Track.canonical_title == "First Track"))
        assert track is not None
        track_file = session.scalar(
            select(TrackFile)
            .where(
                TrackFile.track_id == track.id,
                TrackFile.active.is_(True),
            )
            .order_by(TrackFile.path.asc())
        )
        assert track_file is not None
        session.add(
            SourceProvenance(
                track_id=track.id,
                source_type="tag_batch",
                source_key=batch_id,
            )
        )
        session.commit()
        return db_url, str(track.id), str(track_file.path)


def _insert_files_for_track(
    db_path: Path,
    track_path: str,
    *,
    library_track_key: str = "track:first",
    include_sibling: bool = True,
    primary_values: dict[str, object] | None = None,
    sibling_values: dict[str, object] | None = None,
) -> list[str]:
    primary_values = dict(primary_values or {})
    sibling_values = dict(sibling_values or {})
    track_path_obj = Path(track_path)
    sibling_suffix = ".flac" if track_path_obj.suffix.lower() == ".mp3" else ".mp3"
    sibling_path = str(track_path_obj.with_suffix(sibling_suffix))
    seeded_paths = [track_path]
    rows: list[tuple[str, dict[str, object]]] = [(track_path, primary_values)]
    if include_sibling:
        rows.append((sibling_path, sibling_values))
        seeded_paths.append(sibling_path)

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        init_db(conn)
        for path, values in rows:
            columns = ["path", "library_track_key", *values.keys()]
            params = [path, library_track_key, *values.values()]
            placeholders = ",".join("?" for _ in columns)
            conn.execute(
                f"INSERT INTO files ({', '.join(columns)}) VALUES ({placeholders})",
                params,
            )
        conn.commit()

    return seeded_paths


def _seed_approved_metadata(
    db_url: str,
    *,
    track_id: str,
    field_name: str,
    value: object,
    batch_id: str = "batch-1",
    provider: str = "spotify",
) -> None:
    engine = create_library_engine(db_url)
    with Session(engine) as session:
        raw_result = RawProviderResult(
            batch_id=batch_id,
            provider=provider,
            external_id=None,
            query_text="sync-to-files test",
            payload_json={},
            fetched_at=_utcnow(),
        )
        session.add(raw_result)
        session.flush()

        candidate = MetadataCandidate(
            track_id=track_id,
            raw_result_id=raw_result.id,
            field_name=field_name,
            normalized_value_json=value,
            confidence=1.0,
            rationale_json={"source": "test"},
            status="approved",
            is_user_override=False,
        )
        session.add(candidate)
        session.flush()

        session.add(
            ApprovedMetadata(
                track_id=track_id,
                field_name=field_name,
                value_json=value,
                approved_from_candidate_id=candidate.id,
                approved_by="tester",
                approved_at=_utcnow(),
                is_user_override=False,
            )
        )
        session.commit()


def _fetch_file_row(db_path: Path, path: str) -> sqlite3.Row:
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM files WHERE path = ?", (path,)).fetchone()
    assert row is not None
    return row


def _write_config(tmp_path: Path, db_url: str) -> Path:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f"[library]\ndb_url = \"{db_url}\"\n",
        encoding="utf-8",
    )
    return config_path


def test_sync_writes_canonical_key_and_derives_camelot(tmp_path: Path) -> None:
    db_url, track_id, track_path = _prepare_library(tmp_path)
    db_path = _db_path(tmp_path)
    seeded_paths = _insert_files_for_track(db_path, track_path, include_sibling=True)
    _seed_approved_metadata(db_url, track_id=track_id, field_name="canonical_key", value="C minor")

    summary = run_tag_sync_to_files(db_url=db_url)

    assert summary.fields_written == 4
    assert len(summary.files_updated) == 2
    for path in seeded_paths:
        row = _fetch_file_row(db_path, path)
        assert row["canonical_key"] == "C minor"
        assert row["key_camelot"] == "5A"
        assert row["enrichment_providers"] == "spotify"


def test_sync_writes_bpm_to_both_columns(tmp_path: Path) -> None:
    db_url, track_id, track_path = _prepare_library(tmp_path)
    db_path = _db_path(tmp_path)
    seeded_paths = _insert_files_for_track(db_path, track_path, include_sibling=True)
    _seed_approved_metadata(db_url, track_id=track_id, field_name="canonical_bpm", value=128.0)

    summary = run_tag_sync_to_files(db_url=db_url)

    assert summary.fields_written == 4
    for path in seeded_paths:
        row = _fetch_file_row(db_path, path)
        assert row["canonical_bpm"] == 128.0
        assert row["bpm"] == 128.0


def test_sync_skips_null_source(tmp_path: Path) -> None:
    db_url, track_id, track_path = _prepare_library(tmp_path)
    db_path = _db_path(tmp_path)
    _insert_files_for_track(db_path, track_path, include_sibling=False)
    _seed_approved_metadata(db_url, track_id=track_id, field_name="canonical_genre", value=None)

    summary = run_tag_sync_to_files(db_url=db_url)

    row = _fetch_file_row(db_path, track_path)
    assert summary.skipped_null_source == 1
    assert row["canonical_genre"] is None
    assert row["genre"] is None
    assert row["enriched_at"] is None


def test_sync_default_no_overwrite(tmp_path: Path) -> None:
    db_url, track_id, track_path = _prepare_library(tmp_path)
    db_path = _db_path(tmp_path)
    _insert_files_for_track(
        db_path,
        track_path,
        include_sibling=False,
        primary_values={"canonical_key": "G major", "key_camelot": "9B"},
    )
    _seed_approved_metadata(db_url, track_id=track_id, field_name="canonical_key", value="C minor")

    summary = run_tag_sync_to_files(db_url=db_url)

    row = _fetch_file_row(db_path, track_path)
    assert summary.skipped_already_set == 2
    assert row["canonical_key"] == "G major"
    assert row["key_camelot"] == "9B"


def test_sync_force_overwrites(tmp_path: Path) -> None:
    db_url, track_id, track_path = _prepare_library(tmp_path)
    db_path = _db_path(tmp_path)
    _insert_files_for_track(
        db_path,
        track_path,
        include_sibling=False,
        primary_values={"canonical_key": "G major", "key_camelot": "9B"},
    )
    _seed_approved_metadata(db_url, track_id=track_id, field_name="canonical_key", value="C minor")

    summary = run_tag_sync_to_files(db_url=db_url, force=True)

    row = _fetch_file_row(db_path, track_path)
    assert summary.fields_written == 2
    assert row["canonical_key"] == "C minor"
    assert row["key_camelot"] == "5A"


def test_sync_dry_run_no_writes(tmp_path: Path) -> None:
    db_url, track_id, track_path = _prepare_library(tmp_path)
    db_path = _db_path(tmp_path)
    _insert_files_for_track(db_path, track_path, include_sibling=False)
    _seed_approved_metadata(db_url, track_id=track_id, field_name="canonical_key", value="C minor")
    config_path = _write_config(tmp_path, db_url)

    result = CliRunner().invoke(
        cli,
        ["tag", "sync-to-files", "--dry-run"],
        env={"TAGSLUT_CONFIG": str(config_path)},
    )

    assert result.exit_code == 0, result.output
    assert "canonical_key: NULL -> C minor" in result.output
    assert "key_camelot: NULL -> 5A" in result.output
    row = _fetch_file_row(db_path, track_path)
    assert row["canonical_key"] is None
    assert row["key_camelot"] is None
    assert row["enriched_at"] is None


def test_sync_unknown_field_logs_warning(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    db_url, track_id, track_path = _prepare_library(tmp_path)
    db_path = _db_path(tmp_path)
    _insert_files_for_track(db_path, track_path, include_sibling=False)
    _seed_approved_metadata(db_url, track_id=track_id, field_name="unsupported_field", value="ignored")
    _seed_approved_metadata(db_url, track_id=track_id, field_name="canonical_title", value="Synced Title")

    with caplog.at_level(logging.WARNING, logger="tagslut.tag"):
        summary = run_tag_sync_to_files(db_url=db_url)

    row = _fetch_file_row(db_path, track_path)
    assert summary.warnings == 1
    assert row["canonical_title"] == "Synced Title"
    assert "Skipping unsupported approved_metadata field: unsupported_field" in caplog.text


def test_sync_updates_enriched_at(tmp_path: Path) -> None:
    db_url, track_id, track_path = _prepare_library(tmp_path)
    db_path = _db_path(tmp_path)
    _insert_files_for_track(db_path, track_path, include_sibling=False)
    _seed_approved_metadata(db_url, track_id=track_id, field_name="canonical_genre", value="Techno")
    before = _utcnow()

    run_tag_sync_to_files(db_url=db_url)

    after = _utcnow()
    row = _fetch_file_row(db_path, track_path)
    enriched_at = row["enriched_at"]
    assert enriched_at is not None
    parsed = datetime.fromisoformat(str(enriched_at))
    assert before <= parsed <= after
    assert row["enrichment_providers"] == "spotify"
