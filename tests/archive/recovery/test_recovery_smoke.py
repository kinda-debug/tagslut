import pytest
pytest.skip("recovery module archived", allow_module_level=True)

"""Smoke tests for the tagslut.recovery submodule."""

import sqlite3
from pathlib import Path

import tagslut.recovery as recovery_mod
from tagslut.recovery import Repairer, Reporter, Verifier
from tagslut.storage.schema import init_db


def test_recovery_module_importable() -> None:
    assert hasattr(recovery_mod, "RecoveryScanner")
    assert hasattr(recovery_mod, "Repairer")
    assert hasattr(recovery_mod, "Verifier")
    assert hasattr(recovery_mod, "Reporter")


def test_repairer_instantiates_in_dry_run(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    repairer = Repairer(db_path=db, dry_run=True)
    assert repairer.dry_run is True
    assert repairer.db_path == db


def test_repairer_repair_all_empty_db_returns_zero_total(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    conn = sqlite3.connect(db)
    init_db(conn)
    conn.close()
    repairer = Repairer(db_path=db, dry_run=True)
    stats = repairer.repair_all()
    assert stats["total"] == 0
    assert stats["salvaged"] == 0


def test_reporter_instantiates(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    conn = sqlite3.connect(db)
    init_db(conn)
    conn.close()
    reporter = Reporter(db_path=db)
    assert reporter.db_path == db


def test_verifier_instantiates(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    conn = sqlite3.connect(db)
    init_db(conn)
    conn.close()
    verifier = Verifier(db_path=db)
    assert verifier.db_path == db
