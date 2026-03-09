from __future__ import annotations

from pathlib import Path

import pytest

from tagslut.utils import env_paths


def test_get_volume_prefers_canonical_library_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("LIBRARY_ROOT", str(tmp_path / "library"))
    monkeypatch.setenv("VOLUME_LIBRARY", str(tmp_path / "legacy-library"))

    resolved = env_paths.get_volume("library")

    assert resolved == (tmp_path / "library").resolve()


def test_get_volume_uses_legacy_quarantine_with_warning(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("QUARANTINE_ROOT", raising=False)
    monkeypatch.setenv("VOLUME_QUARANTINE", str(tmp_path / "legacy-quarantine"))

    with pytest.warns(DeprecationWarning, match="VOLUME_QUARANTINE is deprecated"):
        resolved = env_paths.get_volume("quarantine")

    assert resolved == (tmp_path / "legacy-quarantine").resolve()


def test_get_volume_required_mentions_canonical_and_legacy_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("STAGING_ROOT", raising=False)
    monkeypatch.delenv("VOLUME_STAGING", raising=False)

    with pytest.raises(env_paths.PathNotConfiguredError) as exc:
        env_paths.get_volume("staging", required=True)

    message = str(exc.value)
    assert "STAGING_ROOT" in message
    assert "VOLUME_STAGING" in message
