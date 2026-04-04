from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = PROJECT_ROOT / "tools" / "centralize_lossy_pool"


def _load_module():
    loader = importlib.machinery.SourceFileLoader("centralize_lossy_pool_under_test", str(MODULE_PATH))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_file(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path.resolve()


def _media(
    module,
    path: Path,
    *,
    ext: str,
    codec: str | None,
    bitrate_kbps: int | None,
    duration_seconds: float | None,
    artist: str,
    title: str,
    album: str = "",
    album_artist: str = "",
    track_number: int | None = None,
    label: str = "",
    isrc: str = "",
    compilation: bool = False,
    sketchy: bool | None = False,
    bitrate_source: str | None = "mock",
    bitrate_mode: str | None = "CBR",
):
    return module.MediaRead(
        path=path.resolve(),
        ext=ext,
        size=path.stat().st_size,
        codec=codec,
        bitrate_kbps=bitrate_kbps,
        bitrate_source=bitrate_source,
        bitrate_mode=bitrate_mode,
        duration_seconds=duration_seconds,
        sketchy=sketchy,
        tags=module.TagData(
            artist=artist,
            title=title,
            album=album,
            album_artist=album_artist,
            track_number=track_number,
            label=label,
            isrc=isrc,
            compilation=compilation,
        ),
    )


def test_classify_media_accepts_exact_320_mp3(tmp_path: Path) -> None:
    module = _load_module()
    path = _write_file(tmp_path / "track.mp3", b"a" * 2048)
    media = _media(
        module,
        path,
        ext=".mp3",
        codec="mp3",
        bitrate_kbps=320,
        duration_seconds=201.0,
        artist="Artist",
        title="Title",
    )

    assert module.classify_media(media, mp3_kbps=320, aac_min_kbps=256) is None


def test_classify_media_rejects_non_320_and_sketchy_mp3(tmp_path: Path) -> None:
    module = _load_module()
    path = _write_file(tmp_path / "track.mp3", b"a" * 2048)
    bitrate_fail = _media(
        module,
        path,
        ext=".mp3",
        codec="mp3",
        bitrate_kbps=256,
        duration_seconds=201.0,
        artist="Artist",
        title="Title",
    )
    sketchy_fail = _media(
        module,
        path,
        ext=".mp3",
        codec="mp3",
        bitrate_kbps=320,
        duration_seconds=201.0,
        artist="Artist",
        title="Title",
        sketchy=True,
    )

    assert module.classify_media(bitrate_fail, mp3_kbps=320, aac_min_kbps=256) == "bitrate_policy_reject"
    assert module.classify_media(sketchy_fail, mp3_kbps=320, aac_min_kbps=256) == "invalid_media"


def test_classify_media_accepts_and_rejects_m4a_policy(tmp_path: Path) -> None:
    module = _load_module()
    path = _write_file(tmp_path / "track.m4a", b"b" * 2048)
    aac_256 = _media(
        module,
        path,
        ext=".m4a",
        codec="aac",
        bitrate_kbps=256,
        duration_seconds=190.0,
        artist="Artist",
        title="Title",
        sketchy=None,
        bitrate_mode=None,
    )
    aac_320 = _media(
        module,
        path,
        ext=".m4a",
        codec="aac",
        bitrate_kbps=320,
        duration_seconds=190.0,
        artist="Artist",
        title="Title",
        sketchy=None,
        bitrate_mode=None,
    )
    low_aac = _media(
        module,
        path,
        ext=".m4a",
        codec="aac",
        bitrate_kbps=192,
        duration_seconds=190.0,
        artist="Artist",
        title="Title",
        sketchy=None,
        bitrate_mode=None,
    )
    alac = _media(
        module,
        path,
        ext=".m4a",
        codec="alac",
        bitrate_kbps=800,
        duration_seconds=190.0,
        artist="Artist",
        title="Title",
        sketchy=None,
        bitrate_mode=None,
    )

    assert module.classify_media(aac_256, mp3_kbps=320, aac_min_kbps=256) is None
    assert module.classify_media(aac_320, mp3_kbps=320, aac_min_kbps=256) is None
    assert module.classify_media(low_aac, mp3_kbps=320, aac_min_kbps=256) == "bitrate_policy_reject"
    assert module.classify_media(alac, mp3_kbps=320, aac_min_kbps=256) == "codec_policy_reject"


def test_build_plan_applies_hash_and_isrc_dedupe_and_conflict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    source_root = tmp_path / "source"
    dest_root = tmp_path / "dest"
    archive_root = tmp_path / "archive"

    hash_rich = _write_file(source_root / "hash_rich.mp3", b"same-hash")
    hash_poor = _write_file(source_root / "hash_poor.mp3", b"same-hash")
    isrc_mp3 = _write_file(source_root / "song.mp3", b"song-mp3")
    isrc_m4a = _write_file(source_root / "song.m4a", b"song-m4a")
    conflict_a = _write_file(source_root / "conflict_a.mp3", b"conflict-a")
    conflict_b = _write_file(source_root / "conflict_b.m4a", b"conflict-b")

    media_map = {
        hash_rich: _media(
            module,
            hash_rich,
            ext=".mp3",
            codec="mp3",
            bitrate_kbps=320,
            duration_seconds=200.0,
            artist="Artist",
            title="Hash Song",
            album="Album",
            album_artist="Artist",
            track_number=1,
            label="Label",
        ),
        hash_poor: _media(
            module,
            hash_poor,
            ext=".mp3",
            codec="mp3",
            bitrate_kbps=320,
            duration_seconds=200.0,
            artist="Artist",
            title="Hash Song",
        ),
        isrc_mp3: _media(
            module,
            isrc_mp3,
            ext=".mp3",
            codec="mp3",
            bitrate_kbps=320,
            duration_seconds=201.0,
            artist="Artist",
            title="Song",
            album="Album",
            track_number=2,
            isrc="USAAA1234567",
        ),
        isrc_m4a: _media(
            module,
            isrc_m4a,
            ext=".m4a",
            codec="aac",
            bitrate_kbps=256,
            duration_seconds=201.5,
            artist="Artist",
            title="Song",
            album="Album",
            track_number=2,
            isrc="USAAA1234567",
            sketchy=None,
            bitrate_mode=None,
        ),
        conflict_a: _media(
            module,
            conflict_a,
            ext=".mp3",
            codec="mp3",
            bitrate_kbps=320,
            duration_seconds=180.0,
            artist="Artist",
            title="Conflict",
            album="Album",
            isrc="USBBB1234567",
        ),
        conflict_b: _media(
            module,
            conflict_b,
            ext=".m4a",
            codec="aac",
            bitrate_kbps=320,
            duration_seconds=186.5,
            artist="Artist",
            title="Conflict",
            album="Album",
            isrc="USBBB1234567",
            sketchy=None,
            bitrate_mode=None,
        ),
    }

    monkeypatch.setattr(module, "inspect_file", lambda path: media_map[path.resolve()])

    records = module.build_plan(
        source_root.resolve(),
        dest_root=dest_root.resolve(),
        archive_root=archive_root.resolve(),
        mp3_kbps=320,
        aac_min_kbps=256,
        duration_tolerance_seconds=2.0,
    )
    by_name = {row.media.path.name: row for row in records}

    assert by_name["hash_rich.mp3"].action == "keep"
    assert by_name["hash_poor.mp3"].action == "archive"
    assert by_name["hash_poor.mp3"].reason == "archive_duplicate_hash"

    assert by_name["song.mp3"].action == "keep"
    assert by_name["song.m4a"].action == "archive"
    assert by_name["song.m4a"].reason == "archive_duplicate_isrc"

    assert by_name["conflict_a.mp3"].action == "keep"
    assert by_name["conflict_b.m4a"].action == "keep"
    assert "conflict_isrc_duration" in by_name["conflict_a.mp3"].flags
    assert "conflict_isrc_duration" in by_name["conflict_b.m4a"].flags


def test_paths_and_collision_suffix_are_deterministic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    source_root = tmp_path / "source"
    dest_root = tmp_path / "dest"
    archive_root = tmp_path / "archive"

    normal_path = _write_file(source_root / "a_source.mp3", b"a" * 4000)
    collision_path = _write_file(source_root / "b_source.mp3", b"b" * 4000)
    compilation_path = _write_file(source_root / "c_source.mp3", b"c" * 4000)

    media_map = {
        normal_path: _media(
            module,
            normal_path,
            ext=".mp3",
            codec="mp3",
            bitrate_kbps=320,
            duration_seconds=201.0,
            artist="Artist A",
            title="Song A",
            album="Album A",
            track_number=1,
        ),
        collision_path: _media(
            module,
            collision_path,
            ext=".mp3",
            codec="mp3",
            bitrate_kbps=320,
            duration_seconds=202.0,
            artist="Artist A",
            title="Song A",
            album="Album A",
            track_number=1,
        ),
        compilation_path: _media(
            module,
            compilation_path,
            ext=".mp3",
            codec="mp3",
            bitrate_kbps=320,
            duration_seconds=203.0,
            artist="Artist C",
            title="Track C",
            album="Compilation 2026",
            track_number=7,
            label="Label X",
            compilation=True,
        ),
    }
    monkeypatch.setattr(module, "inspect_file", lambda path: media_map[path.resolve()])

    records = module.build_plan(
        source_root.resolve(),
        dest_root=dest_root.resolve(),
        archive_root=archive_root.resolve(),
        mp3_kbps=320,
        aac_min_kbps=256,
        duration_tolerance_seconds=2.0,
    )
    by_name = {row.media.path.name: row for row in records}

    assert by_name["a_source.mp3"].dest == dest_root.resolve() / "Artist A" / "Album A" / "01 - Song A.mp3"
    collision_hash = module._hash_file(collision_path)
    assert by_name["b_source.mp3"].reason == "path_collision_renamed"
    assert by_name["b_source.mp3"].dest == dest_root.resolve() / "Artist A" / "Album A" / f"01 - Song A__{collision_hash[:8]}.mp3"
    assert by_name["c_source.mp3"].dest == dest_root.resolve() / "Label X" / "Compilation 2026" / "07 - Artist C - Track C.mp3"


def test_discovery_excludes_hidden_symlink_dest_archive_and_tree_rbx_style_appledouble(tmp_path: Path) -> None:
    module = _load_module()
    source_root = tmp_path / "source"
    dest_root = source_root / "MP3_LIBRARY_CLEAN"
    archive_root = source_root / "_archive_lossy_pool" / "MP3_LIBRARY_CLEAN_20260403_010101"

    real_track = _write_file(source_root / "!!!" / "As If" / "!!! - (2015) As If - 01 All U Writers.mp3", b"track")
    _write_file(source_root / "!!!" / "As If" / "._!!! - (2015) As If - 01 All U Writers.mp3", b"appledouble")
    _write_file(source_root / ".hidden" / "skip.mp3", b"skip")
    _write_file(dest_root / "existing.mp3", b"dest")
    _write_file(archive_root / "archive_duplicate_hash" / "old.mp3", b"archive")
    (source_root / "!!!" / "As If" / "link.mp3").symlink_to(real_track)

    candidates = list(
        module.iter_candidate_files(
            source_root.resolve(),
            excluded_roots=(dest_root.resolve(), archive_root.resolve()),
            limit_root=None,
        )
    )

    assert candidates == [real_track]


def test_run_dry_run_and_execute_with_read_only_audit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()

    source_root = tmp_path / "source"
    dest_root = tmp_path / "dest"
    archive_root = tmp_path / "archive" / "MP3_LIBRARY_CLEAN_20260403_010101"
    valid = _write_file(source_root / "Artist" / "Album" / "valid.mp3", b"valid-track")
    missing_title = _write_file(source_root / "Artist" / "Album" / "missing_title.mp3", b"missing-title")

    def fake_inspect(path: Path):
        path = path.resolve()
        if path == valid:
            return _media(
                module,
                path,
                ext=".mp3",
                codec="mp3",
                bitrate_kbps=320,
                duration_seconds=210.0,
                artist="Artist",
                title="Valid Track",
                album="Album",
                track_number=1,
            )
        return _media(
            module,
            path,
            ext=".mp3",
            codec="mp3",
            bitrate_kbps=320,
            duration_seconds=211.0,
            artist="Artist",
            title="",
            album="Album",
            track_number=2,
        )

    monkeypatch.setattr(module, "inspect_file", fake_inspect)

    dry_result = module.run(
        module.parse_args(
            [
                "--source-root",
                str(source_root),
                "--dest-root",
                str(dest_root),
                "--archive-root",
                str(archive_root),
                "--dry-run",
            ]
        )
    )
    dry_run_root = archive_root.parent / f"{archive_root.name}__dry_run"
    assert valid.exists()
    assert missing_title.exists()
    assert dry_run_root.exists()
    assert Path(str(dry_result["manifest"])).exists()
    assert not (dest_root / "Artist" / "Album" / "01 - Valid Track.mp3").exists()

    source_root_exec = tmp_path / "source_exec"
    dest_root_exec = tmp_path / "dest_exec"
    archive_root_exec = tmp_path / "archive_exec" / "MP3_LIBRARY_CLEAN_20260403_020202"
    valid_exec = _write_file(source_root_exec / "Artist" / "Album" / "valid.mp3", b"valid-track")
    missing_title_exec = _write_file(source_root_exec / "Artist" / "Album" / "missing_title.mp3", b"missing-title")

    def fake_inspect_exec(path: Path):
        path = path.resolve()
        if path.name in {"valid.mp3", "01 - Valid Track.mp3"}:
            return _media(
                module,
                path,
                ext=".mp3",
                codec="mp3",
                bitrate_kbps=320,
                duration_seconds=210.0,
                artist="Artist",
                title="Valid Track",
                album="Album",
                track_number=1,
            )
        return _media(
            module,
            path,
            ext=".mp3",
            codec="mp3",
            bitrate_kbps=320,
            duration_seconds=211.0,
            artist="Artist",
            title="",
            album="Album",
            track_number=2,
        )

    monkeypatch.setattr(module, "inspect_file", fake_inspect_exec)

    execute_result = module.run(
        module.parse_args(
            [
                "--source-root",
                str(source_root_exec),
                "--dest-root",
                str(dest_root_exec),
                "--archive-root",
                str(archive_root_exec),
                "--execute",
            ]
        )
    )

    kept_path = dest_root_exec / "Artist" / "Album" / "01 - Valid Track.mp3"
    archived_path = archive_root_exec / "missing_required_tags" / "Artist" / "Album" / "missing_title.mp3"
    audit_summary_path = archive_root_exec / "audit_summary.json"
    audit_payload = json.loads(audit_summary_path.read_text(encoding="utf-8"))

    assert kept_path.exists()
    assert archived_path.exists()
    assert not valid_exec.exists()
    assert not missing_title_exec.exists()
    assert execute_result["audit"] is not None
    assert audit_payload["invalid_audio_count"] == 0
    assert audit_payload["exact_duplicate_files"] == 0
    assert audit_payload["unresolved_isrc_conflict_files"] == 0


def test_run_resume_allows_non_empty_dest_and_appends_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_module()
    source_root = tmp_path / "source"
    dest_root = tmp_path / "dest"
    archive_root = tmp_path / "archive" / "MP3_LIBRARY_CLEAN_20260403_040404"

    existing_dest = _write_file(dest_root / "Artist" / "Album" / "01 - Song A.mp3", b"existing-dest")
    new_source = _write_file(source_root / "new_source.mp3", b"new-source-track")
    new_hash = module._hash_file(new_source)
    expected_resumed_dest = dest_root / "Artist" / "Album" / f"01 - Song A__{new_hash[:8]}.mp3"

    archive_root.mkdir(parents=True, exist_ok=True)
    manifest_path = archive_root / "manifest.jsonl"
    manifest_path.write_text(json.dumps({"source": "already-moved"}) + "\n", encoding="utf-8")

    def fake_inspect(path: Path):
        path = path.resolve()
        if path == new_source or path == expected_resumed_dest:
            return _media(
                module,
                path,
                ext=".mp3",
                codec="mp3",
                bitrate_kbps=320,
                duration_seconds=210.0,
                artist="Artist",
                title="Song A",
                album="Album",
                track_number=1,
            )
        if path == existing_dest:
            return _media(
                module,
                path,
                ext=".mp3",
                codec="mp3",
                bitrate_kbps=320,
                duration_seconds=209.0,
                artist="Artist",
                title="Song A",
                album="Album",
                track_number=1,
            )
        raise AssertionError(f"unexpected inspect path: {path}")

    monkeypatch.setattr(module, "inspect_file", fake_inspect)

    module.run(
        module.parse_args(
            [
                "--source-root",
                str(source_root),
                "--dest-root",
                str(dest_root),
                "--archive-root",
                str(archive_root),
                "--execute",
                "--resume",
                "--verbose",
            ]
        )
    )

    manifest_lines = manifest_path.read_text(encoding="utf-8").splitlines()
    captured = capsys.readouterr()

    assert existing_dest.exists()
    assert expected_resumed_dest.exists()
    assert not new_source.exists()
    assert len(manifest_lines) == 2
    assert "MOVE keep" in captured.err
    assert str(new_source) in captured.err


def test_run_aborts_when_dest_root_is_non_empty(tmp_path: Path) -> None:
    module = _load_module()
    source_root = tmp_path / "source"
    dest_root = tmp_path / "dest"
    archive_root = tmp_path / "archive" / "MP3_LIBRARY_CLEAN_20260403_030303"
    _write_file(source_root / "track.mp3", b"track")
    _write_file(dest_root / "already_here.mp3", b"existing")

    with pytest.raises(ValueError, match="non-empty"):
        module.run(
            module.parse_args(
                [
                    "--source-root",
                    str(source_root),
                    "--dest-root",
                    str(dest_root),
                    "--archive-root",
                    str(archive_root),
                    "--dry-run",
                ]
            )
        )
