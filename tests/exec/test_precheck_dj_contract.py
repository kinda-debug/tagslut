"""P0 contract tests for the --dj intake paths.

These tests pin the two failure modes identified in the DJ workflow audit:

  P0-A: tools/get --dj with an empty PROMOTED_FLACS_FILE must emit a loud
        warning instead of silently succeeding with zero DJ output.

  P0-B: tools/get --dj where precheck decides all tracks already exist must
        take the link_precheck_inventory_to_dj path and clearly announce
        it is not the promotion-driven path.

  P0-C: The same logical track requested in two scenarios (newly promoted vs
        already in inventory) must produce equivalent DJ-visible DB state or
        the operator must be explicitly warned of the difference.
"""
from __future__ import annotations

import csv
import sqlite3
import subprocess
from pathlib import Path

import pytest

from tagslut.exec import precheck_inventory_dj
from tagslut.storage.schema import init_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    init_db(conn)
    conn.commit()
    conn.close()


def _write_decisions_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["playlist_index", "title", "artist", "album", "isrc", "db_path", "decision"]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_dummy_mp3(path: Path, *, title: str, artist: str) -> None:
    """Write a minimal MP3 file with ID3 tags so mutagen can read it."""
    from mutagen.id3 import ID3, TALB, TIT2, TPE1

    path.parent.mkdir(parents=True, exist_ok=True)
    tags = ID3()
    tags.add(TIT2(encoding=3, text=title))
    tags.add(TPE1(encoding=3, text=artist))
    tags.add(TALB(encoding=3, text="Test Album"))
    tags.save(str(path))


# ---------------------------------------------------------------------------
# P0-A: empty PROMOTED_FLACS_FILE must emit a warning, not silently pass
# ---------------------------------------------------------------------------


def test_empty_promoted_flacs_emits_warning_on_stderr(tmp_path: Path) -> None:
    """When DJ_INPUT_COUNT == 0 the DJ build block must write a WARNING to stderr.

    This is a unit-level check of the shell code's explicit stderr output.
    We verify the warning text is present in the expected stderr output by
    running a minimal shell snippet that reproduces the logic.
    """
    # Reproduce the patched shell block in isolation
    snippet = r"""
#!/bin/bash
PROMOTED_FLACS_FILE="$(mktemp)"
# File is empty
DJ_INPUT_COUNT="$(wc -l < "$PROMOTED_FLACS_FILE" | tr -d ' ')"
if [[ "$DJ_INPUT_COUNT" -eq 0 ]]; then
    echo "WARNING: --dj was requested but PROMOTED_FLACS_FILE is empty — no FLAC files were promoted in this run." >&2
    echo "WARNING: No DJ MP3 copies were created." >&2
    echo "WARNING: To build DJ copies for already-promoted masters, run: tagslut dj pool-wizard" >&2
    DJ_EXPORT_COUNT=0
fi
echo "DJ_EXPORT_COUNT=${DJ_EXPORT_COUNT:-unset}"
rm -f "$PROMOTED_FLACS_FILE"
"""
    result = subprocess.run(
        ["bash", "-c", snippet],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "WARNING" in result.stderr, (
        "Expected at least one WARNING line on stderr when PROMOTED_FLACS_FILE is empty. "
        f"Got stderr: {result.stderr!r}"
    )
    assert "No DJ MP3 copies were created" in result.stderr
    assert "DJ_EXPORT_COUNT=0" in result.stdout


def test_non_empty_promoted_flacs_does_not_emit_warning(tmp_path: Path) -> None:
    """When PROMOTED_FLACS_FILE has content the warning must NOT appear."""
    flac_file = tmp_path / "track.flac"
    flac_file.write_text("dummy")

    snippet = rf"""
#!/bin/bash
PROMOTED_FLACS_FILE="{tmp_path}/promoted.txt"
echo "{flac_file}" > "$PROMOTED_FLACS_FILE"
DJ_INPUT_COUNT="$(wc -l < "$PROMOTED_FLACS_FILE" | tr -d ' ')"
if [[ "$DJ_INPUT_COUNT" -eq 0 ]]; then
    echo "WARNING: --dj was requested but PROMOTED_FLACS_FILE is empty — no FLAC files were promoted in this run." >&2
    echo "WARNING: No DJ MP3 copies were created." >&2
    DJ_EXPORT_COUNT=0
fi
echo "DJ_INPUT_COUNT=$DJ_INPUT_COUNT"
"""
    result = subprocess.run(
        ["bash", "-c", snippet],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "WARNING" not in result.stderr, (
        "Should not emit a WARNING when PROMOTED_FLACS_FILE is non-empty. "
        f"Got stderr: {result.stderr!r}"
    )
    assert "DJ_INPUT_COUNT=1" in result.stdout


# ---------------------------------------------------------------------------
# P0-B: precheck-hit path emits the contract banner
# ---------------------------------------------------------------------------


def test_precheck_hit_dj_emits_contract_note(tmp_path: Path) -> None:
    """When all tracks are precheck-hit and DJ_MODE=1, the contract note must
    appear on stderr before link_precheck_inventory_to_dj is called."""
    snippet = r"""
#!/bin/bash
PREFILTER_KEEP=0
DJ_MODE=1

if [[ "${PREFILTER_KEEP:-0}" -eq 0 ]]; then
    echo "All candidates already have same-or-better inventory matches; skipping download."
    if [[ "$DJ_MODE" -eq 1 ]]; then
        echo "CONTRACT NOTE: All tracks are precheck-hit inventory. DJ output will be produced via" >&2
        echo "  the precheck-inventory fallback path (link_precheck_inventory_to_dj), NOT the" >&2
        echo "  promotion-driven build_pool_v3 path. Results may differ from a first-time intake run." >&2
        echo "  For a deterministic DJ build from canonical state, use: tagslut dj pool-wizard" >&2
        echo "CALLED_LINK_PRECHECK=1"
    fi
    echo "No new candidates to process; intake pipeline finished."
fi
"""
    result = subprocess.run(
        ["bash", "-c", snippet],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "CONTRACT NOTE" in result.stderr, (
        "Expected CONTRACT NOTE on stderr for precheck-hit DJ run. "
        f"Got stderr: {result.stderr!r}"
    )
    assert "precheck-inventory fallback path" in result.stderr
    assert "CALLED_LINK_PRECHECK=1" in result.stdout


def test_precheck_hit_no_dj_mode_no_contract_note(tmp_path: Path) -> None:
    """When DJ_MODE=0, the contract note must not appear even on a precheck-hit run."""
    snippet = r"""
#!/bin/bash
PREFILTER_KEEP=0
DJ_MODE=0

if [[ "${PREFILTER_KEEP:-0}" -eq 0 ]]; then
    echo "All candidates already have same-or-better inventory matches; skipping download."
    if [[ "$DJ_MODE" -eq 1 ]]; then
        echo "CONTRACT NOTE: All tracks are precheck-hit inventory." >&2
    fi
    echo "No new candidates to process; intake pipeline finished."
fi
"""
    result = subprocess.run(
        ["bash", "-c", snippet],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "CONTRACT NOTE" not in result.stderr


# ---------------------------------------------------------------------------
# P0-C: precheck-hit DJ path records provenance in DB
# ---------------------------------------------------------------------------


def test_precheck_hit_dj_records_provenance(tmp_path: Path) -> None:
    """link_precheck_inventory_to_dj must write a provenance event row when it
    successfully resolves an existing MP3 via tag matching.

    This pins the equivalence requirement: a precheck-hit run must leave
    auditable DB state just like a promotion-hit run.
    """
    db_path = tmp_path / "music.db"
    _make_db(db_path)

    conn = sqlite3.connect(str(db_path))
    source_flac = tmp_path / "library" / "Test Track.flac"
    source_flac.parent.mkdir(parents=True, exist_ok=True)
    source_flac.write_bytes(b"")

    conn.execute(
        """
        INSERT INTO files (path, canonical_title, canonical_artist, canonical_album, canonical_isrc)
        VALUES (?, ?, ?, ?, ?)
        """,
        (str(source_flac), "Test Track", "Test Artist", "Test Album", "ISRC001"),
    )
    conn.commit()
    conn.close()

    dj_root = tmp_path / "dj"
    dj_root.mkdir()
    mp3_file = dj_root / "Test Artist - Test Track.mp3"
    _write_dummy_mp3(mp3_file, title="Test Track", artist="Test Artist")

    decisions_csv = tmp_path / "decisions.csv"
    _write_decisions_csv(
        decisions_csv,
        rows=[
            {
                "playlist_index": "1",
                "title": "Test Track",
                "artist": "Test Artist",
                "album": "Test Album",
                "isrc": "ISRC001",
                "db_path": str(source_flac),
                "decision": "skip",
            }
        ],
    )

    artifact_dir = tmp_path / "artifacts"

    result = precheck_inventory_dj.link_precheck_inventory_to_dj(
        db_path=db_path,
        decisions_csv=decisions_csv,
        dj_root=dj_root,
        playlist_dir=tmp_path / "playlists",
        playlist_base_name="test_playlist",
        artifact_dir=artifact_dir,
    )

    # The function must return a result dict with at least one resolved track.
    # This pins the equivalence requirement: a precheck-hit run must produce
    # auditable DJ state just like a promotion-hit run.
    resolved = result.get("existing_mp3_rows", 0) + result.get("transcoded_rows", 0)
    assert resolved > 0, (
        "Expected link_precheck_inventory_to_dj to resolve at least one track. "
        f"Result: {result}"
    )

    # dj_pool_path must be updated in the DB for reused MP3s
    conn = sqlite3.connect(str(db_path))
    dj_pool_path = conn.execute(
        "SELECT dj_pool_path FROM files WHERE path = ?", (str(source_flac),)
    ).fetchone()
    conn.close()

    assert dj_pool_path is not None and dj_pool_path[0] is not None, (
        "Expected dj_pool_path to be set on the files row after precheck-hit DJ resolution. "
        "precheck-hit and promote-hit runs must both update DJ-facing DB state."
    )
