from __future__ import annotations

from pathlib import Path

import pytest

from tagslut.dj.curation import DjCurationConfig
from tagslut.dj.export import PoolProfile, _resolve_output_path, plan_export, pool_profile_from_dict, run_export
from tagslut.dj.transcode import TrackRow, assign_output_paths, make_dedupe_key


def _track(
    tmp_path: Path,
    *,
    name: str,
    artist: str = "Artist",
    title: str = "Title",
    dj_set_role: str | None = None,
) -> TrackRow:
    source_path = tmp_path / f"{name}.flac"
    source_path.write_bytes(b"fake")
    track = TrackRow(
        row_num=1,
        album_artist=artist,
        album="Album",
        track_number=None,
        title=title,
        track_artist=artist,
        external_id=name,
        source="test",
        source_path=source_path,
        dedupe_key=("",),
        dj_set_role=dj_set_role,
    )
    track.dedupe_key = make_dedupe_key(track)
    return track


def _ok_transcode(track: TrackRow, overwrite: bool, timeout_s: int | None = None):
    _ = overwrite
    _ = timeout_s
    assert track.output_path is not None
    track.output_path.parent.mkdir(parents=True, exist_ok=True)
    track.output_path.write_bytes(b"mp3")
    return ("ok", track, "", "")


def test_pool_profile_from_dict_ignores_unknown_keys() -> None:
    profile = pool_profile_from_dict(
        {
            "pool_name": "gig_2026_03_13",
            "layout": "by_role",
            "filename_template": "{artist} - {title}.mp3",
            "require_flac_ok": False,
            "require_artist_title": False,
            "only_profiled": False,
            "create_playlist": False,
            "pool_overwrite_policy": "always",
            "bpm_min": 98,
            "bpm_max": 128,
        }
    )

    assert profile == PoolProfile(
        pool_name="gig_2026_03_13",
        layout="by_role",
        filename_template="{artist} - {title}.mp3",
        bpm_min=98,
        bpm_max=128,
        only_roles=None,
        create_playlist=False,
        pool_overwrite_policy="always",
    )


def test_resolve_output_path_routes_unassigned_and_falls_back_to_existing_filename(
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "pool"
    track = _track(tmp_path, name="source", artist="Alpha", title="Beta", dj_set_role=None)
    track.output_path = output_root / "legacy" / "Existing Name.mp3"
    profile = PoolProfile(layout="by_role", filename_template="{artist} - {missing}.mp3")

    with caplog.at_level("WARNING"):
        resolved = _resolve_output_path(track, output_root, profile)

    assert resolved == output_root / "_unassigned" / "Existing Name.mp3"
    assert "routing to _unassigned" in caplog.text


def test_plan_export_applies_profile_role_filter_and_output_paths(
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "pool"
    groove = _track(tmp_path, name="groove", artist="Alpha", title="Groove", dj_set_role="groove")
    club = _track(tmp_path, name="club", artist="Beta", title="Club", dj_set_role="club")
    config = DjCurationConfig()
    profile = PoolProfile(layout="by_role", only_roles=["groove"], create_playlist=True)

    assign_output_paths([groove, club], output_root)
    with caplog.at_level("INFO"):
        plan = plan_export([groove, club], config, output_root, profile=profile)

    assert plan.profile == profile
    assert [track.title for track in plan.tracks] == ["Groove"]
    assert plan.tracks[0].output_path == output_root / "groove" / "Alpha - Groove.mp3"
    assert "Excluded 1 track(s) via profile.only_roles filter" in caplog.text


def test_run_export_without_profile_preserves_existing_output_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "pool"
    track = _track(tmp_path, name="flat", artist="Artist", title="Flat")
    assign_output_paths([track], output_root)
    expected_output_path = track.output_path
    assert expected_output_path is not None

    seen_paths: list[Path] = []

    def fake_transcode(track: TrackRow, overwrite: bool, timeout_s: int | None = None):
        _ = overwrite
        _ = timeout_s
        assert track.output_path is not None
        seen_paths.append(track.output_path)
        track.output_path.parent.mkdir(parents=True, exist_ok=True)
        track.output_path.write_bytes(b"mp3")
        return ("ok", track, "", "")

    monkeypatch.setattr("tagslut.dj.export.transcode_one", fake_transcode)

    stats = run_export(
        [track],
        DjCurationConfig(),
        output_root,
        jobs=1,
    )

    assert stats.transcoded_ok == 1
    assert seen_paths == [expected_output_path]


def test_run_export_by_role_writes_playlists_for_all_roles(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "pool"
    tracks = [
        _track(tmp_path, name="groove", artist="Alpha", title="Groove", dj_set_role="groove"),
        _track(tmp_path, name="bridge", artist="Beta", title="Bridge", dj_set_role="bridge"),
        _track(tmp_path, name="loose", artist="Gamma", title="Loose", dj_set_role=None),
    ]
    for track in tracks:
        track.output_path = output_root / "legacy" / f"{track.title}.mp3"

    monkeypatch.setattr("tagslut.dj.export.transcode_one", _ok_transcode)

    stats = run_export(
        tracks,
        DjCurationConfig(),
        output_root,
        jobs=1,
        profile=PoolProfile(layout="by_role", create_playlist=True),
    )

    assert stats.transcoded_ok == 3
    assert (output_root / "10_GROOVE.m3u").read_text(encoding="utf-8") == "groove/Alpha - Groove.mp3\n"
    assert (output_root / "20_PRIME.m3u").read_text(encoding="utf-8") == ""
    assert (output_root / "30_BRIDGE.m3u").read_text(encoding="utf-8") == "bridge/Beta - Bridge.mp3\n"
    assert (output_root / "40_CLUB.m3u").read_text(encoding="utf-8") == ""
