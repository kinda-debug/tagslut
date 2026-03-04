"""Tests for phase controls in tools/review/process_root.py."""

from __future__ import annotations

import importlib.util as _ilu
import sys
from pathlib import Path

from tagslut.db.v3.schema import create_schema_v3


_SCRIPT = Path(__file__).resolve().parent.parent / "tools" / "review" / "process_root.py"
_SPEC = _ilu.spec_from_file_location("process_root", _SCRIPT)
_MOD = _ilu.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MOD
_SPEC.loader.exec_module(_MOD)

parse_phases = _MOD.parse_phases
planned_table_touches = _MOD.planned_table_touches
build_pipeline_steps = _MOD.build_pipeline_steps
IDENTITY_TABLES = _MOD.IDENTITY_TABLES
validate_phase_compatibility = _MOD.validate_phase_compatibility
is_v3_db = _MOD.is_v3_db


def _build_steps(phases: tuple[str, ...]) -> list[object]:
    return build_pipeline_steps(
        db_path=Path("/tmp/music.db"),
        root_path=Path("/tmp/root"),
        library_path=Path("/tmp/library"),
        providers="beatport,deezer,apple_music,itunes",
        force=False,
        no_art=False,
        art_force=False,
        trust=3,
        trust_post=3,
        allow_duplicate_hash=False,
        use_preferred_asset=None,
        require_preferred_asset=False,
        allow_multiple_per_identity=False,
        phases=phases,
    )


def test_default_phases_preserve_full_pipeline_order() -> None:
    phases = parse_phases(phases_arg=None, scan_only=False)
    steps = _build_steps(phases)
    labels = [step.label for step in steps]
    assert labels == [
        "scan_with_trust",
        "check_integrity_update_db",
        "hoard_tags",
        "normalize_genres",
        "tag_normalized_genres",
        "index_enrich",
        "embed_cover_art",
        "promote_replace_merge",
    ]
    assert "--check-hash" not in steps[0].command


def test_scan_only_is_asset_only_and_skips_identity_enrich_promote() -> None:
    phases = parse_phases(phases_arg=None, scan_only=True)
    assert phases == ("register", "integrity", "hash")

    touched = planned_table_touches(phases)
    assert "asset_file" in touched
    assert "scan_runs" in touched
    assert not (touched & IDENTITY_TABLES)

    steps = _build_steps(phases)
    labels = [step.label for step in steps]
    assert labels == ["scan_with_trust", "check_integrity_update_db"]
    assert "--check-hash" in steps[0].command


def test_register_only_runs_registration_without_hash() -> None:
    phases = parse_phases(phases_arg="register", scan_only=False)
    steps = _build_steps(phases)
    assert len(steps) == 1
    assert steps[0].label == "scan_with_trust"
    assert "--check-hash" not in steps[0].command


def test_detects_v3_db_shape(tmp_path: Path) -> None:
    db_path = tmp_path / "music_v3.db"
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    try:
        create_schema_v3(conn)
    finally:
        conn.close()

    assert is_v3_db(db_path) is True


def test_blocks_legacy_scan_phases_on_v3_db(tmp_path: Path) -> None:
    db_path = tmp_path / "music_v3.db"
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    try:
        create_schema_v3(conn)
    finally:
        conn.close()

    err = validate_phase_compatibility(
        db_path=db_path,
        phases=("register", "integrity", "hash"),
    )
    assert err is not None
    assert "v3 DB guard" in err
