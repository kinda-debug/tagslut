from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import click
from click.testing import CliRunner

from tagslut.cli.commands.index import register_index_group
from tagslut.metadata.models.types import EnrichmentResult, LocalFileInfo, ProviderTrack
from tagslut.metadata.pipeline import runner


def _result_with_match(path: str, **kwargs) -> EnrichmentResult:
    result = EnrichmentResult(path=path, **kwargs)
    result.matches = [ProviderTrack(service="beatport", service_track_id="1", title="T", artist="A")]
    return result


def test_bpm_filled_increments_when_bpm_present() -> None:
    files = [LocalFileInfo(path="/a.flac")]
    resolved = _result_with_match("/a.flac", canonical_bpm=128.0)

    with patch("tagslut.metadata.pipeline.runner.db_reader.get_eligible_files", return_value=iter(files)), patch(
        "tagslut.metadata.pipeline.runner.stages.resolve_file",
        return_value=resolved,
    ), patch("tagslut.metadata.pipeline.runner.db_writer.update_database", return_value=True):
        stats = runner.run_enrich_all(
            db_path=":memory:",
            provider_names=["beatport"],
            provider_getter=lambda _name: None,
            mode="hoarding",
            dry_run=True,
            router=None,
        )

    assert stats.bpm_filled == 1


def test_none_values_do_not_increment_hoarding_counters() -> None:
    files = [LocalFileInfo(path="/a.flac")]
    resolved = _result_with_match("/a.flac", canonical_bpm=None)

    with patch("tagslut.metadata.pipeline.runner.db_reader.get_eligible_files", return_value=iter(files)), patch(
        "tagslut.metadata.pipeline.runner.stages.resolve_file",
        return_value=resolved,
    ), patch("tagslut.metadata.pipeline.runner.db_writer.update_database", return_value=True):
        stats = runner.run_enrich_all(
            db_path=":memory:",
            provider_names=["beatport"],
            provider_getter=lambda _name: None,
            mode="hoarding",
            dry_run=True,
            router=None,
        )

    assert stats.bpm_filled == 0


def test_undertagged_added_when_enriched_missing_bpm() -> None:
    files = [LocalFileInfo(path="/a.flac")]
    resolved = _result_with_match(
        "/a.flac",
        canonical_artist="Artist",
        canonical_title="Title",
        canonical_bpm=None,
        canonical_key="F# min",
        canonical_genre="Techno",
        canonical_label="Label",
    )

    with patch("tagslut.metadata.pipeline.runner.db_reader.get_eligible_files", return_value=iter(files)), patch(
        "tagslut.metadata.pipeline.runner.stages.resolve_file",
        return_value=resolved,
    ), patch("tagslut.metadata.pipeline.runner.db_writer.update_database", return_value=True):
        stats = runner.run_enrich_all(
            db_path=":memory:",
            provider_names=["beatport"],
            provider_getter=lambda _name: None,
            mode="hoarding",
            dry_run=True,
            router=None,
        )

    assert stats.undertagged == [("Artist - Title", ["BPM"])]


def test_undertagged_not_added_when_all_critical_fields_present() -> None:
    files = [LocalFileInfo(path="/a.flac")]
    resolved = _result_with_match(
        "/a.flac",
        canonical_artist="Artist",
        canonical_title="Title",
        canonical_bpm=128.0,
        canonical_key="F# min",
        canonical_genre="Techno",
        canonical_label="Label",
    )

    with patch("tagslut.metadata.pipeline.runner.db_reader.get_eligible_files", return_value=iter(files)), patch(
        "tagslut.metadata.pipeline.runner.stages.resolve_file",
        return_value=resolved,
    ), patch("tagslut.metadata.pipeline.runner.db_writer.update_database", return_value=True):
        stats = runner.run_enrich_all(
            db_path=":memory:",
            provider_names=["beatport"],
            provider_getter=lambda _name: None,
            mode="hoarding",
            dry_run=True,
            router=None,
        )

    assert stats.undertagged == []


def test_no_undertagged_block_rendered_when_empty() -> None:
    cli = click.Group()
    register_index_group(cli)

    result = _result_with_match(
        "/a.flac",
        canonical_artist="Artist",
        canonical_title="Title",
        canonical_bpm=128.0,
        canonical_key="F# min",
        canonical_genre="Techno",
        canonical_label="Label",
        canonical_album_art_url="https://example.com/art.jpg",
    )

    class DummyEnricher:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN001
            pass

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, exc_type, exc, tb):  # type: ignore[no-untyped-def]
            return None

        def resolve_file(self, _file_info: LocalFileInfo) -> EnrichmentResult:
            return result

    runner_cli = CliRunner()
    with patch("tagslut.cli.runtime.collect_flac_paths", return_value=[Path("/a.flac")]), patch(
        "tagslut.cli.commands.index._local_file_info_from_path",
        return_value=LocalFileInfo(path="/a.flac", tag_artist="Artist", tag_title="Title"),
    ), patch("tagslut.cli.commands.index._print_enrichment_result"), patch(
        "tagslut.metadata.enricher.Enricher",
        DummyEnricher,
    ):
        res = runner_cli.invoke(
            cli,
            ["index", "enrich", "--standalone", "--hoarding", "--path", "ignored"],
        )

    assert res.exit_code == 0
    assert "HOARDING FIELDS" in res.output
    assert "UNDERTAGGED" not in res.output

