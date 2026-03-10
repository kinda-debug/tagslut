from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

from mutagen.id3 import ID3

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_module():
    module_path = PROJECT_ROOT / "tools" / "metadata_scripts" / "sync_mp3_tags_from_flac.py"
    spec = importlib.util.spec_from_file_location("sync_mp3_tags_from_flac_under_test", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _FakeFlac:
    def __init__(self, tags: dict[str, list[str]]) -> None:
        self.tags = tags


def _write_minimal_mp3(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\xff\xe3\x18\x00" + b"\x00" * 417)


def test_sync_script_repairs_core_tags_from_exact_db_match(tmp_path, monkeypatch) -> None:
    module = _load_module()
    mp3_root = tmp_path / "dj"
    mp3_path = mp3_root / "Unknown Artist - Unknown Title [101].mp3"
    flac_path = tmp_path / "master" / "managed.flac"
    _write_minimal_mp3(mp3_path)
    flac_path.parent.mkdir(parents=True, exist_ok=True)
    flac_path.write_bytes(b"flac")

    monkeypatch.setattr(module, "resolve_cli_env_db_path", lambda *args, **kwargs: SimpleNamespace(path=tmp_path / "music.db"))
    monkeypatch.setattr(
        module,
        "load_db_dj_pool_lookup",
        lambda conn, root: {mp3_path.resolve(): SimpleNamespace(source_path=flac_path.resolve())},
    )
    monkeypatch.setattr(
        module,
        "read_audio_metadata",
        lambda path: SimpleNamespace(
            title="",
            artist="",
            album="",
            albumartist="",
            duration_s=200.0,
        )
        if path.resolve() == mp3_path.resolve()
        else None,
    )
    monkeypatch.setattr(
        module,
        "FLAC",
        lambda path: _FakeFlac(
            {
                "title": ["Managed Tune"],
                "artist": ["Managed Artist"],
                "album": ["Managed Album"],
                "albumartist": ["Managed Artist"],
                "tracknumber": ["03"],
                "date": ["2024"],
            }
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "sync_mp3_tags_from_flac.py",
            "--mp3-root",
            str(mp3_root),
            "--match-source",
            "db_dj_pool_path",
            "--copy-core-tags",
            "--no-copy-dj-tags",
            "--execute",
            "--out",
            str(tmp_path / "report.csv"),
            "--backup",
            str(tmp_path / "backup.jsonl"),
        ],
    )

    result = module.main()

    assert result == 0
    tags = ID3(mp3_path)
    assert tags["TIT2"].text[0] == "Managed Tune"
    assert tags["TPE1"].text[0] == "Managed Artist"
    assert tags["TALB"].text[0] == "Managed Album"
    assert tags["TPE2"].text[0] == "Managed Artist"
    assert tags["TRCK"].text[0] == "03"
    assert str(tags["TDRC"].text[0]) == "2024"


def test_sync_script_repairs_core_tags_from_master_match(tmp_path, monkeypatch) -> None:
    module = _load_module()
    mp3_root = tmp_path / "dj"
    mp3_path = mp3_root / "Master Artist - Missing Track.mp3"
    flac_path = tmp_path / "master" / "master.flac"
    _write_minimal_mp3(mp3_path)
    flac_path.parent.mkdir(parents=True, exist_ok=True)
    flac_path.write_bytes(b"flac")

    monkeypatch.setattr(
        module,
        "read_audio_metadata",
        lambda path: SimpleNamespace(
            title="Missing Track",
            artist="Master Artist",
            album="Master Album",
            albumartist="Master Artist",
            duration_s=210.0,
        )
        if path.resolve() == mp3_path.resolve()
        else None,
    )
    monkeypatch.setattr(
        module,
        "load_master_index",
        lambda flac_root, wanted_keys: {
            (module._norm("Missing Track"), module._norm("Master Artist")): [
                SimpleNamespace(path=flac_path.resolve(), album="Master Album", duration_s=210.0)
            ]
        },
    )
    monkeypatch.setattr(
        module,
        "pick_best_master_match",
        lambda metadata, candidates, duration_tol: candidates[0],
    )
    monkeypatch.setattr(
        module,
        "FLAC",
        lambda path: _FakeFlac(
            {
                "title": ["Missing Track"],
                "artist": ["Master Artist"],
                "album": ["Master Album"],
                "albumartist": ["Master Artist"],
                "tracknumber": ["06"],
                "date": ["2024"],
            }
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "sync_mp3_tags_from_flac.py",
            "--mp3-root",
            str(mp3_root),
            "--match-source",
            "master",
            "--copy-core-tags",
            "--no-copy-dj-tags",
            "--execute",
            "--out",
            str(tmp_path / "report.csv"),
            "--backup",
            str(tmp_path / "backup.jsonl"),
        ],
    )

    result = module.main()

    assert result == 0
    tags = ID3(mp3_path)
    assert tags["TRCK"].text[0] == "06"
    assert str(tags["TDRC"].text[0]) == "2024"
