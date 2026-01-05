"""Tests for tiered hashing helpers."""

from __future__ import annotations

from pathlib import Path

from dedupe.core.hashing import calculate_prehash, calculate_tiered_hashes


def _write_file(path: Path, payload: bytes) -> None:
    """Write payload to the provided path."""

    path.write_bytes(payload)


def test_prehash_ignores_tail_bytes(tmp_path: Path) -> None:
    """Tier-1 prehash should ignore data after the configured prefix."""

    file_a = tmp_path / "a.bin"
    file_b = tmp_path / "b.bin"
    prefix = b"prefix-data"
    _write_file(file_a, prefix + b"tail-a")
    _write_file(file_b, prefix + b"tail-b")

    hash_a = calculate_prehash(file_a, bytes_to_hash=len(prefix))
    hash_b = calculate_prehash(file_b, bytes_to_hash=len(prefix))

    assert hash_a == hash_b


def test_tier2_hash_detects_full_content_changes(tmp_path: Path) -> None:
    """Tier-2 hashes should differ when file contents differ."""

    file_a = tmp_path / "a.bin"
    file_b = tmp_path / "b.bin"
    _write_file(file_a, b"same-prefix-a")
    _write_file(file_b, b"same-prefix-b")

    hashes_a = calculate_tiered_hashes(file_a, prehash_bytes=4)
    hashes_b = calculate_tiered_hashes(file_b, prehash_bytes=4)

    assert hashes_a["tier1"] == hashes_b["tier1"]
    assert hashes_a["tier2"] != hashes_b["tier2"]
