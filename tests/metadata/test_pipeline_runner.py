from __future__ import annotations

from unittest.mock import patch

from tagslut.metadata.models.types import EnrichmentResult, LocalFileInfo, ProviderTrack
from tagslut.metadata.pipeline import runner


def _result_with_match(path: str) -> EnrichmentResult:
    result = EnrichmentResult(path=path)
    result.matches = [ProviderTrack(service="beatport", service_track_id="1", title="T", artist="A")]
    return result


def test_run_enrich_all_counts_stats_with_mocked_io() -> None:
    files = [LocalFileInfo(path="/a.flac"), LocalFileInfo(path="/b.flac"), LocalFileInfo(path="/c.flac")]
    resolved = {
        "/a.flac": _result_with_match("/a.flac"),
        "/b.flac": EnrichmentResult(path="/b.flac"),  # no match
        "/c.flac": _result_with_match("/c.flac"),
    }

    with patch("tagslut.metadata.pipeline.runner.db_reader.get_eligible_files", return_value=iter(files)), patch(
        "tagslut.metadata.pipeline.runner.stages.resolve_file",
        side_effect=lambda file_info, *_args, **_kwargs: resolved[file_info.path],
    ), patch("tagslut.metadata.pipeline.runner.db_writer.update_database", return_value=True), patch(
        "tagslut.metadata.pipeline.runner.db_writer.mark_no_match"
    ):
        stats = runner.run_enrich_all(
            db_path=":memory:",
            provider_names=["beatport"],
            provider_getter=lambda _name: None,
            mode="recovery",
            dry_run=True,
            router=None,
        )

    assert stats.total == 3
    assert stats.enriched == 2
    assert stats.no_match == 1
    assert stats.failed == 0


def test_run_enrich_all_logs_checkpoint_intervals() -> None:
    files = [LocalFileInfo(path="/a.flac"), LocalFileInfo(path="/b.flac")]

    with patch("tagslut.metadata.pipeline.runner.db_reader.get_eligible_files", return_value=iter(files)), patch(
        "tagslut.metadata.pipeline.runner.stages.resolve_file",
        return_value=_result_with_match("/x.flac"),
    ), patch("tagslut.metadata.pipeline.runner.db_writer.update_database", return_value=True):
        with patch("tagslut.metadata.pipeline.runner.logger.debug") as debug_log:
            runner.run_enrich_all(
                db_path=":memory:",
                provider_names=["beatport"],
                provider_getter=lambda _name: None,
                mode="recovery",
                dry_run=True,
                router=None,
                checkpoint_interval=1,
            )

    checkpoint_calls = [str(call.args[0]) for call in debug_log.call_args_list if call.args]
    assert any("Checkpoint %d/%d" in msg for msg in checkpoint_calls)


def test_run_enrich_all_handles_keyboard_interrupt_and_returns_partial() -> None:
    files = [LocalFileInfo(path="/a.flac"), LocalFileInfo(path="/b.flac"), LocalFileInfo(path="/c.flac")]
    side_effects: list[object] = [_result_with_match("/a.flac"), KeyboardInterrupt()]

    with patch("tagslut.metadata.pipeline.runner.db_reader.get_eligible_files", return_value=iter(files)), patch(
        "tagslut.metadata.pipeline.runner.stages.resolve_file",
        side_effect=side_effects,
    ), patch("tagslut.metadata.pipeline.runner.db_writer.update_database", return_value=True):
        stats = runner.run_enrich_all(
            db_path=":memory:",
            provider_names=["beatport"],
            provider_getter=lambda _name: None,
            mode="recovery",
            dry_run=True,
            router=None,
        )

    assert stats.enriched == 1
    assert stats.total == 2


def test_run_enrich_file_statuses_not_found_and_not_eligible() -> None:
    with patch("tagslut.metadata.pipeline.runner.db_reader.get_file_row", return_value=None):
        result, status = runner.run_enrich_file(
            db_path=":memory:",
            provider_names=[],
            provider_getter=lambda _name: None,
            mode="recovery",
            dry_run=True,
            path="/missing.flac",
            router=None,
        )
    assert result is None
    assert status == "not_found"

    row = {"path": "/a.flac", "flac_ok": 1, "enriched_at": "yes", "metadata_health_reason": "ok"}
    with patch("tagslut.metadata.pipeline.runner.db_reader.get_file_row", return_value=row):
        result, status = runner.run_enrich_file(
            db_path=":memory:",
            provider_names=[],
            provider_getter=lambda _name: None,
            mode="recovery",
            dry_run=True,
            path="/a.flac",
            router=None,
        )
    assert result is None
    assert status == "not_eligible"


def test_run_enrich_file_statuses_no_match_and_enriched() -> None:
    file_row = {"path": "/x.flac", "flac_ok": 1, "enriched_at": None, "metadata_health_reason": None}
    file_info = LocalFileInfo(path="/x.flac")
    no_match = EnrichmentResult(path="/x.flac")
    yes_match = _result_with_match("/x.flac")

    with patch("tagslut.metadata.pipeline.runner.db_reader.get_file_row", return_value=file_row), patch(
        "tagslut.metadata.pipeline.runner.db_reader.row_to_local_file_info",
        return_value=file_info,
    ), patch("tagslut.metadata.pipeline.runner.stages.resolve_file", return_value=no_match), patch(
        "tagslut.metadata.pipeline.runner.db_writer.mark_no_match"
    ):
        result, status = runner.run_enrich_file(
            db_path=":memory:",
            provider_names=["beatport"],
            provider_getter=lambda _name: None,
            mode="recovery",
            dry_run=True,
            path="/x.flac",
            router=None,
        )
    assert result is not None
    assert status == "no_match"

    with patch("tagslut.metadata.pipeline.runner.db_reader.get_file_row", return_value=file_row), patch(
        "tagslut.metadata.pipeline.runner.db_reader.row_to_local_file_info",
        return_value=file_info,
    ), patch("tagslut.metadata.pipeline.runner.stages.resolve_file", return_value=yes_match), patch(
        "tagslut.metadata.pipeline.runner.db_writer.update_database",
        return_value=True,
    ):
        result, status = runner.run_enrich_file(
            db_path=":memory:",
            provider_names=["beatport"],
            provider_getter=lambda _name: None,
            mode="recovery",
            dry_run=True,
            path="/x.flac",
            router=None,
        )
    assert result is not None
    assert status == "enriched"
