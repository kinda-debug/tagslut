import pathlib
import sqlite3

import pytest

from tools.triage_loose_audio import triage


def _write_db(db_path: pathlib.Path, *, asset_paths=None, isrcs=None) -> None:
    asset_paths = asset_paths or []
    isrcs = isrcs or []
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("create table asset_file (path text)")
        conn.execute("create table track_identity (isrc text)")
        for p in asset_paths:
            conn.execute("insert into asset_file (path) values (?)", (str(p),))
        for isrc in isrcs:
            conn.execute("insert into track_identity (isrc) values (?)", (isrc,))
        conn.commit()
    finally:
        conn.close()


def _write_rules(rules_path: pathlib.Path, rules: list[dict]) -> None:
    import json

    rules_path.write_text(json.dumps(rules), encoding="utf-8")


def _run_triage(tmp_path: pathlib.Path, *, scan_roots, rules, db_path, master_root, execute: bool):
    from io import StringIO

    out = StringIO()
    triage(
        scan_roots=[pathlib.Path(p) for p in scan_roots],
        rules_path=pathlib.Path(rules),
        db_path=pathlib.Path(db_path),
        master_library_root=pathlib.Path(master_root),
        execute=execute,
        out=out,
    )
    return out.getvalue()


def test_in_db_path_status(tmp_path: pathlib.Path):
    scan_root = tmp_path / "scan"
    scan_root.mkdir()
    f = scan_root / "a.flac"
    f.write_bytes(b"x")

    db_path = tmp_path / "db.sqlite"
    _write_db(db_path, asset_paths=[f])

    master_root = tmp_path / "master"
    master_root.mkdir()

    rules_path = tmp_path / "rules.json"
    _write_rules(
        rules_path,
        [
            {
                "match_prefix": str(scan_root),
                "action": "skip",
                "only_if_status": None,
                "rescue_dest": None,
                "note": "noop",
            }
        ],
    )

    out = _run_triage(
        tmp_path,
        scan_roots=[scan_root],
        rules=rules_path,
        db_path=db_path,
        master_root=master_root,
        execute=False,
    )
    assert "\tin_db_path\t" in out


def test_in_db_isrc_status(tmp_path: pathlib.Path):
    scan_root = tmp_path / "scan"
    scan_root.mkdir()
    f = scan_root / "track [USRC17607839].flac"
    f.write_bytes(b"x")

    db_path = tmp_path / "db.sqlite"
    _write_db(db_path, isrcs=["USRC17607839"])

    master_root = tmp_path / "master"
    master_root.mkdir()

    rules_path = tmp_path / "rules.json"
    _write_rules(
        rules_path,
        [
            {
                "match_prefix": str(scan_root),
                "action": "skip",
                "only_if_status": None,
                "rescue_dest": None,
                "note": "noop",
            }
        ],
    )

    out = _run_triage(
        tmp_path,
        scan_roots=[scan_root],
        rules=rules_path,
        db_path=db_path,
        master_root=master_root,
        execute=False,
    )
    assert "\tin_db_isrc\t" in out


def test_in_master_library_status(tmp_path: pathlib.Path):
    master_root = tmp_path / "master"
    master_root.mkdir()
    (master_root / "01 - Hello.flac").write_bytes(b"x")

    scan_root = tmp_path / "scan"
    scan_root.mkdir()
    f = scan_root / "Hello.wav"
    f.write_bytes(b"x")

    db_path = tmp_path / "db.sqlite"
    _write_db(db_path)

    rules_path = tmp_path / "rules.json"
    _write_rules(
        rules_path,
        [
            {
                "match_prefix": str(scan_root),
                "action": "skip",
                "only_if_status": None,
                "rescue_dest": None,
                "note": "noop",
            }
        ],
    )

    out = _run_triage(
        tmp_path,
        scan_roots=[scan_root],
        rules=rules_path,
        db_path=db_path,
        master_root=master_root,
        execute=False,
    )
    assert "\tin_master_library\t" in out


def test_unknown_in_rescue_rule_moves_in_execute(tmp_path: pathlib.Path):
    scan_root = tmp_path / "scan"
    scan_root.mkdir()
    f = scan_root / "x.flac"
    f.write_bytes(b"x")

    rescue_dest = tmp_path / "rescue"
    rescue_dest.mkdir()

    db_path = tmp_path / "db.sqlite"
    _write_db(db_path)

    master_root = tmp_path / "master"
    master_root.mkdir()

    rules_path = tmp_path / "rules.json"
    _write_rules(
        rules_path,
        [
            {
                "match_prefix": str(scan_root),
                "action": "rescue",
                "only_if_status": None,
                "rescue_dest": str(rescue_dest),
                "note": "rescue unknown",
            }
        ],
    )

    _run_triage(
        tmp_path,
        scan_roots=[scan_root],
        rules=rules_path,
        db_path=db_path,
        master_root=master_root,
        execute=True,
    )

    assert not f.exists()
    assert (rescue_dest / "x.flac").exists()


def test_unknown_in_delete_rule_with_rescue_dest_moves(tmp_path: pathlib.Path):
    scan_root = tmp_path / "scan"
    scan_root.mkdir()
    f = scan_root / "x.flac"
    f.write_bytes(b"x")

    rescue_dest = tmp_path / "rescue"
    rescue_dest.mkdir()

    db_path = tmp_path / "db.sqlite"
    _write_db(db_path)

    master_root = tmp_path / "master"
    master_root.mkdir()

    rules_path = tmp_path / "rules.json"
    _write_rules(
        rules_path,
        [
            {
                "match_prefix": str(scan_root),
                "action": "delete",
                "only_if_status": ["in_db_path", "in_db_isrc", "in_master_library"],
                "rescue_dest": str(rescue_dest),
                "note": "delete verified, rescue unknown",
            }
        ],
    )

    _run_triage(
        tmp_path,
        scan_roots=[scan_root],
        rules=rules_path,
        db_path=db_path,
        master_root=master_root,
        execute=True,
    )

    assert not f.exists()
    assert (rescue_dest / "x.flac").exists()


def test_in_db_path_in_delete_rule_deletes_in_execute(tmp_path: pathlib.Path):
    scan_root = tmp_path / "scan"
    scan_root.mkdir()
    f = scan_root / "x.flac"
    f.write_bytes(b"x")

    db_path = tmp_path / "db.sqlite"
    _write_db(db_path, asset_paths=[f])

    master_root = tmp_path / "master"
    master_root.mkdir()

    rules_path = tmp_path / "rules.json"
    _write_rules(
        rules_path,
        [
            {
                "match_prefix": str(scan_root),
                "action": "delete",
                "only_if_status": ["in_db_path"],
                "rescue_dest": None,
                "note": "delete in_db_path",
            }
        ],
    )

    _run_triage(
        tmp_path,
        scan_roots=[scan_root],
        rules=rules_path,
        db_path=db_path,
        master_root=master_root,
        execute=True,
    )
    assert not f.exists()


def test_double_extension_always_deleted(tmp_path: pathlib.Path):
    scan_root = tmp_path / "scan"
    scan_root.mkdir()
    f = scan_root / "x.flac.flac"
    f.write_bytes(b"x")

    rescue_dest = tmp_path / "rescue"
    rescue_dest.mkdir()

    db_path = tmp_path / "db.sqlite"
    _write_db(db_path)

    master_root = tmp_path / "master"
    master_root.mkdir()

    rules_path = tmp_path / "rules.json"
    _write_rules(
        rules_path,
        [
            {
                "match_prefix": str(scan_root),
                "action": "rescue",
                "only_if_status": None,
                "rescue_dest": str(rescue_dest),
                "note": "would rescue, but malformed overrides",
            }
        ],
    )

    _run_triage(
        tmp_path,
        scan_roots=[scan_root],
        rules=rules_path,
        db_path=db_path,
        master_root=master_root,
        execute=True,
    )
    assert not f.exists()


def test_rescue_rule_verified_file_is_skipped(tmp_path: pathlib.Path):
    scan_root = tmp_path / "scan"
    scan_root.mkdir()
    f = scan_root / "x.flac"
    f.write_bytes(b"x")

    db_path = tmp_path / "db.sqlite"
    _write_db(db_path, asset_paths=[f])

    rescue_dest = tmp_path / "rescue"
    rescue_dest.mkdir()

    master_root = tmp_path / "master"
    master_root.mkdir()

    rules_path = tmp_path / "rules.json"
    _write_rules(
        rules_path,
        [
            {
                "match_prefix": str(scan_root),
                "action": "rescue",
                "only_if_status": None,
                "rescue_dest": str(rescue_dest),
                "note": "verified should not move",
            }
        ],
    )

    _run_triage(
        tmp_path,
        scan_roots=[scan_root],
        rules=rules_path,
        db_path=db_path,
        master_root=master_root,
        execute=True,
    )
    assert f.exists()
    assert not (rescue_dest / "x.flac").exists()


def test_destination_collision_appends_suffix(tmp_path: pathlib.Path):
    scan_root = tmp_path / "scan"
    scan_root.mkdir()
    f1 = scan_root / "x.flac"
    f2 = scan_root / "x.mp3"
    f1.write_bytes(b"x")
    f2.write_bytes(b"x")

    rescue_dest = tmp_path / "rescue"
    rescue_dest.mkdir()
    (rescue_dest / "x.flac").write_bytes(b"already")

    db_path = tmp_path / "db.sqlite"
    _write_db(db_path)

    master_root = tmp_path / "master"
    master_root.mkdir()

    rules_path = tmp_path / "rules.json"
    _write_rules(
        rules_path,
        [
            {
                "match_prefix": str(scan_root),
                "action": "rescue",
                "only_if_status": None,
                "rescue_dest": str(rescue_dest),
                "note": "rescue unknowns",
            }
        ],
    )

    _run_triage(
        tmp_path,
        scan_roots=[scan_root],
        rules=rules_path,
        db_path=db_path,
        master_root=master_root,
        execute=True,
    )
    assert (rescue_dest / "x.flac").exists()
    assert (rescue_dest / "x_1.flac").exists()
    assert (rescue_dest / "x.mp3").exists()


def test_dry_run_makes_no_moves_or_deletes(tmp_path: pathlib.Path):
    scan_root = tmp_path / "scan"
    scan_root.mkdir()
    f = scan_root / "x.flac"
    f.write_bytes(b"x")

    rescue_dest = tmp_path / "rescue"
    rescue_dest.mkdir()

    db_path = tmp_path / "db.sqlite"
    _write_db(db_path)

    master_root = tmp_path / "master"
    master_root.mkdir()

    rules_path = tmp_path / "rules.json"
    _write_rules(
        rules_path,
        [
            {
                "match_prefix": str(scan_root),
                "action": "rescue",
                "only_if_status": None,
                "rescue_dest": str(rescue_dest),
                "note": "rescue unknowns",
            }
        ],
    )

    _run_triage(
        tmp_path,
        scan_roots=[scan_root],
        rules=rules_path,
        db_path=db_path,
        master_root=master_root,
        execute=False,
    )
    assert f.exists()
    assert not (rescue_dest / "x.flac").exists()


def test_scan_root_passed_twice_processes_both(tmp_path: pathlib.Path):
    scan1 = tmp_path / "scan1"
    scan2 = tmp_path / "scan2"
    scan1.mkdir()
    scan2.mkdir()
    (scan1 / "a.flac").write_bytes(b"x")
    (scan2 / "b.flac").write_bytes(b"x")

    rescue_dest = tmp_path / "rescue"
    rescue_dest.mkdir()

    db_path = tmp_path / "db.sqlite"
    _write_db(db_path)

    master_root = tmp_path / "master"
    master_root.mkdir()

    rules_path = tmp_path / "rules.json"
    _write_rules(
        rules_path,
        [
            {
                "match_prefix": str(scan1),
                "action": "rescue",
                "only_if_status": None,
                "rescue_dest": str(rescue_dest),
                "note": "rescue scan1",
            },
            {
                "match_prefix": str(scan2),
                "action": "rescue",
                "only_if_status": None,
                "rescue_dest": str(rescue_dest),
                "note": "rescue scan2",
            },
        ],
    )

    _run_triage(
        tmp_path,
        scan_roots=[scan1, scan2],
        rules=rules_path,
        db_path=db_path,
        master_root=master_root,
        execute=True,
    )
    assert (rescue_dest / "a.flac").exists()
    assert (rescue_dest / "b.flac").exists()

