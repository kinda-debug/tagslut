from __future__ import annotations

from types import SimpleNamespace

import click
from click.testing import CliRunner

from tagslut.cli.commands.tag import register_curate_group
from tagslut.library.matcher import TrackQuery
from tagslut.metadata.models.types import MatchConfidence, ProviderTrack
from tagslut.tag.providers import clear_provider_registry, get_provider, list_providers
from tagslut.tag.providers.qobuz import QobuzTagProvider


class _StubTokenManager:
    def get_qobuz_app_credentials(self) -> tuple[str | None, str | None]:
        return ("app", "secret")

    def ensure_qobuz_token(self) -> str | None:
        return "tok"


class _StubQobuzMetadataProvider:
    def __init__(self) -> None:
        self.search_by_isrc_calls: list[str] = []
        self.search_calls: list[tuple[str, int]] = []

    def _ensure_credentials(self) -> bool:
        return True

    def search_by_isrc(self, isrc: str) -> list[ProviderTrack]:
        self.search_by_isrc_calls.append(isrc)
        return [
            ProviderTrack(
                service="qobuz",
                service_track_id="q1",
                title="Track One",
                artist="Artist One",
                album="Album One",
                isrc=isrc,
                release_date="2024-01-02",
                genre="Electronic",
                label="Label One",
                version="Extended Mix",
                explicit=True,
                match_confidence=MatchConfidence.EXACT,
                raw={"id": "q1"},
            )
        ]

    def search(self, query: str, limit: int = 10) -> list[ProviderTrack]:
        self.search_calls.append((query, limit))
        return []


def test_builtin_provider_names_are_available() -> None:
    clear_provider_registry()
    assert list_providers() == ["beatport", "tidal", "qobuz"]


def test_get_provider_loads_builtin_qobuz() -> None:
    clear_provider_registry()
    provider = get_provider("qobuz")
    assert provider.name == "qobuz"


def test_qobuz_tag_provider_search_and_normalize() -> None:
    provider = QobuzTagProvider(
        token_manager=_StubTokenManager(),
        metadata_provider=_StubQobuzMetadataProvider(),
    )

    results = provider.search(
        TrackQuery(
            title="Track One",
            artist="Artist One",
            isrc="USRC17607839",
        )
    )

    assert len(results) == 1
    assert results[0].external_id == "q1"

    fields = {candidate.field_name: candidate.normalized_value for candidate in provider.normalize(results[0])}
    assert fields["canonical_title"] == "Track One"
    assert fields["canonical_artist_credit"] == "Artist One"
    assert fields["canonical_album"] == "Album One"
    assert fields["canonical_mix_name"] == "Extended Mix"
    assert fields["canonical_label"] == "Label One"
    assert fields["canonical_genre"] == "Electronic"
    assert fields["canonical_release_date"] == "2024-01-02"
    assert fields["canonical_explicit"] is True
    assert fields["isrc"] == "USRC17607839"


def test_curate_fetch_runs_all_providers_by_default(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    @click.group()
    def cli() -> None:
        pass

    register_curate_group(cli)

    monkeypatch.setattr("tagslut.cli.commands.tag.list_providers", lambda: ["beatport", "tidal", "qobuz"])
    monkeypatch.setattr(
        "tagslut.cli.commands.tag.run_tag_fetch_many",
        lambda provider_names, batch_id, dry_run=False: [
            (name, SimpleNamespace(id=f"{name}-job", status="completed")) for name in provider_names
        ],
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["curate", "fetch", "--batch", "batch-1"])

    assert result.exit_code == 0
    assert "Provider: beatport" in result.output
    assert "Provider: tidal" in result.output
    assert "Provider: qobuz" in result.output


def test_curate_fetch_honors_explicit_provider(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    @click.group()
    def cli() -> None:
        pass

    register_curate_group(cli)

    seen: dict[str, object] = {}

    def _fake_run(provider_names: list[str], batch_id: str, dry_run: bool = False) -> list[tuple[str, object]]:
        seen["provider_names"] = provider_names
        seen["batch_id"] = batch_id
        seen["dry_run"] = dry_run
        return [("qobuz", SimpleNamespace(id="qobuz-job", status="completed"))]

    monkeypatch.setattr("tagslut.cli.commands.tag.run_tag_fetch_many", _fake_run)

    runner = CliRunner()
    result = runner.invoke(cli, ["curate", "fetch", "--provider", "qobuz", "--batch", "batch-2", "--dry-run"])

    assert result.exit_code == 0
    assert seen == {
        "provider_names": ["qobuz"],
        "batch_id": "batch-2",
        "dry_run": True,
    }
