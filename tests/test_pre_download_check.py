from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_pre_download_check_module():
    module_path = Path(__file__).resolve().parents[1] / "tools" / "review" / "pre_download_check.py"
    spec = importlib.util.spec_from_file_location("pre_download_check_module", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_decide_match_action_skips_equal_or_better_existing() -> None:
    module = _load_pre_download_check_module()
    matched = module.DbRow(
        path="/library/existing.flac",
        isrc="AAA",
        beatport_id="123",
        title="Track",
        artist="Artist",
        album="Album",
        download_source="bpdl",
        quality_rank=2,
    )

    decision, reason = module.decide_match_action(
        matched,
        match_method="beatport_id",
        candidate_quality_rank=3,
        force_keep_matched=False,
    )

    assert decision == "skip"
    assert "equal or better" in reason


def test_decide_match_action_keeps_upgrade_or_unknown_quality() -> None:
    module = _load_pre_download_check_module()
    upgrade_row = module.DbRow(
        path="/library/existing.flac",
        isrc="AAA",
        beatport_id="123",
        title="Track",
        artist="Artist",
        album="Album",
        download_source="bpdl",
        quality_rank=6,
    )
    unknown_row = module.DbRow(
        path="/library/existing-unknown.flac",
        isrc="BBB",
        beatport_id="456",
        title="Track",
        artist="Artist",
        album="Album",
        download_source="legacy",
        quality_rank=None,
    )

    upgrade_decision, upgrade_reason = module.decide_match_action(
        upgrade_row,
        match_method="isrc",
        candidate_quality_rank=3,
        force_keep_matched=False,
    )
    unknown_decision, unknown_reason = module.decide_match_action(
        unknown_row,
        match_method="exact_title_artist",
        candidate_quality_rank=3,
        force_keep_matched=False,
    )

    assert upgrade_decision == "keep"
    assert "improves existing rank 6" in upgrade_reason
    assert unknown_decision == "keep"
    assert "quality rank missing" in unknown_reason
