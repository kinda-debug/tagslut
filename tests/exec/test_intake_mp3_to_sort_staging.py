from __future__ import annotations

import datetime
from pathlib import Path

from tagslut.exec.intake_mp3_to_sort_staging import (
    IntakeKind,
    execute_intake_plan,
    plan_intake_mp3_to_sort_staging,
)


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def test_plan_and_execute_intake_moves_unique_and_dupes(tmp_path: Path) -> None:
    src_root = tmp_path / "src"
    intake_root = tmp_path / "intake"
    lib_root = tmp_path / "lib"
    leftovers_root = tmp_path / "leftovers"

    src_root.mkdir()
    lib_root.mkdir()
    leftovers_root.mkdir()

    # Existing in library: matches normalized "01 Foo.mp3"
    _write_bytes(lib_root / "Foo.mp3", b"lib")

    # Incoming
    incoming_dupe = src_root / "01 Foo.mp3"
    incoming_unique = src_root / "Bar.mp3"
    _write_bytes(incoming_dupe, b"a")
    _write_bytes(incoming_unique, b"b")

    # Non-mp3 + subdir are skipped
    _write_bytes(src_root / "notes.txt", b"nope")
    (src_root / "subdir").mkdir()

    today = datetime.date(2026, 4, 12)
    planned, skipped = plan_intake_mp3_to_sort_staging(
        src_root=src_root,
        intake_root=intake_root,
        mp3_library_root=lib_root,
        leftovers_root=leftovers_root,
        today=today,
    )

    assert skipped == 2
    assert {p.kind for p in planned} == {IntakeKind.UNIQUE, IntakeKind.DUPLICATE}

    unique = next(p for p in planned if p.kind == IntakeKind.UNIQUE)
    dupe = next(p for p in planned if p.kind == IntakeKind.DUPLICATE)

    assert unique.src == incoming_unique
    assert unique.dst == intake_root / "Bar.mp3"
    assert unique.match is None

    assert dupe.src == incoming_dupe
    assert dupe.dst == src_root / "_dupes_20260412" / "01 Foo.mp3"
    assert dupe.match == lib_root / "Foo.mp3"

    execute_intake_plan(planned)

    assert not incoming_unique.exists()
    assert (intake_root / "Bar.mp3").exists()

    assert not incoming_dupe.exists()
    assert (src_root / "_dupes_20260412" / "01 Foo.mp3").exists()

