from __future__ import annotations

from pathlib import Path

import pytest

from tagslut.exec import prescan_tag_completion as prescan
from tagslut.metadata.models.types import MatchConfidence, ProviderTrack


class FakeFLAC(dict):
    instances: dict[str, "FakeFLAC"] = {}
    initial_tags: dict[str, dict[str, list[str]]] = {}

    def __init__(self, path: str):
        super().__init__()
        self.path = Path(path)
        self.saved = False
        FakeFLAC.instances[str(self.path)] = self
        for key, value in FakeFLAC.initial_tags.get(str(self.path), {}).items():
            self[key] = list(value)

    def get(self, key: str, default=None):  # type: ignore[override]
        for existing in self.keys():
            if str(existing).lower() == str(key).lower():
                return super().get(existing, default)
        return super().get(key, default)

    def save(self) -> None:
        self.saved = True


class FakeTidalProvider:
    def __init__(self, track: ProviderTrack | None):
        self._track = track

    def search_by_isrc(self, isrc: str, limit: int = 5):
        _ = limit
        if self._track is None:
            return []
        return [self._track]


def test_extract_isrc_from_filename_when_tag_missing(tmp_path: Path) -> None:
    path = tmp_path / "1. Artist - Title [usrc17607839].flac"
    assert prescan.extract_isrc_from_filename(path) == "USRC17607839"


def test_tags_written_when_provider_returns_exact_match(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "1. X - Y [USRC17607839].flac"
    path.write_bytes(b"")

    FakeFLAC.instances.clear()
    FakeFLAC.initial_tags = {str(path): {}}

    monkeypatch.setattr(prescan, "FLAC", FakeFLAC)

    track = ProviderTrack(
        service="tidal",
        service_track_id="123",
        title="Real Title",
        artist="Real Artist",
        isrc="USRC17607839",
        match_confidence=MatchConfidence.EXACT,
    )
    monkeypatch.setattr(prescan, "TidalProvider", lambda token_manager=None: FakeTidalProvider(track))

    stats = prescan.prescan_batch_root(batch_root=tmp_path, db_path=tmp_path / "db.sqlite", execute=True)

    audio = FakeFLAC.instances[str(path)]
    assert audio.saved is True
    assert audio.get("isrc") == ["USRC17607839"]
    assert audio.get("artist") == ["Real Artist"]
    assert audio.get("title") == ["Real Title"]
    assert stats.files_changed == 1


def test_dry_run_does_not_write_tags(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "1. X - Y [USRC17607839].flac"
    path.write_bytes(b"")

    FakeFLAC.instances.clear()
    FakeFLAC.initial_tags = {str(path): {}}
    monkeypatch.setattr(prescan, "FLAC", FakeFLAC)

    track = ProviderTrack(
        service="tidal",
        service_track_id="123",
        title="Real Title",
        artist="Real Artist",
        isrc="USRC17607839",
        match_confidence=MatchConfidence.EXACT,
    )
    monkeypatch.setattr(prescan, "TidalProvider", lambda token_manager=None: FakeTidalProvider(track))

    stats = prescan.prescan_batch_root(batch_root=tmp_path, db_path=tmp_path / "db.sqlite", execute=False)

    audio = FakeFLAC.instances[str(path)]
    assert audio.saved is False
    assert audio.get("isrc") is None
    assert audio.get("artist") is None
    assert audio.get("title") is None
    assert stats.files_changed == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
