from pathlib import Path

import pytest

from tagslut.metadata.canon import apply_canon, load_canon_rules, write_canon_to_file


RULES_PATH = Path(__file__).resolve().parents[1] / "tools" / "rules" / "library_canon.json"


def test_removes_replaygain_and_tool_fields_but_keeps_critical_fields():
    rules = load_canon_rules(RULES_PATH)
    tags = {
        "replaygain_track_gain": "1.0 dB",
        "acoustid_id": "abc",
        "encoder": "foo",
        "composer": "Alice",
        "comment": ["keep me"],
        "copyright": "© 2020",
    }
    out = apply_canon(tags, rules)
    assert "replaygain_track_gain" not in out
    assert "acoustid_id" not in out
    assert "encoder" not in out
    assert out["composer"] == "Alice"
    assert out["comment"] == ["keep me"]
    assert out["copyright"] == "© 2020"


def test_year_only_date_fields():
    rules = load_canon_rules(RULES_PATH)
    tags = {
        "date": "2020-05-17",
        "originaldate": "1999-11-01",
    }
    out = apply_canon(tags, rules)
    assert out["date"] == "2020"
    assert out["originaldate"] == "1999"


def test_removes_namespaced_performer_and_instrument():
    rules = load_canon_rules(RULES_PATH)
    tags = {
        "performer:violin": "Alice",
        "instrument:guitar": "Bob",
        "title": "Keep",
    }
    out = apply_canon(tags, rules)
    assert "performer:violin" not in out
    assert "instrument:guitar" not in out
    assert out["title"] == "Keep"


def test_keeps_service_ids_if_present_and_does_not_create():
    rules = load_canon_rules(RULES_PATH)
    tags = {
        "itunestrackid": "123",
    }
    out = apply_canon(tags, rules)
    assert out["itunestrackid"] == "123"
    assert "qobuz_track_id" not in out


def test_removes_underscore_prefixed_keys():
    rules = load_canon_rules(RULES_PATH)
    tags = {
        "_something": "junk",
        "artist": "Daft Punk",
    }
    out = apply_canon(tags, rules)
    assert "_something" not in out
    assert out["artist"] == "Daft Punk"


def test_write_canon_to_file_dry_run_returns_diff_without_saving(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    rules = load_canon_rules(RULES_PATH)
    audio_path = tmp_path / "sample.flac"
    audio_path.write_text("stub", encoding="utf-8")

    class FakeAudio:
        def __init__(self) -> None:
            self.tags = {"date": ["2020-05-17"]}
            self.saved = False

        def items(self):  # type: ignore[no-untyped-def]
            return self.tags.items()

        def clear(self) -> None:
            self.tags = {}

        def __setitem__(self, key: str, value):  # type: ignore[no-untyped-def]
            self.tags[key] = value

        def save(self) -> None:
            self.saved = True

    fake_audio = FakeAudio()
    monkeypatch.setattr("mutagen.File", lambda *_args, **_kwargs: fake_audio)

    diff = write_canon_to_file(audio_path, rules, dry_run=True)

    assert "date" in diff
    assert diff["date"] == (["2020-05-17"], ["2020"])
    assert fake_audio.saved is False


def test_write_canon_to_file_execute_with_mock_mutagen_object(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    rules = load_canon_rules(RULES_PATH)
    audio_path = tmp_path / "sample.mp3"
    audio_path.write_text("stub", encoding="utf-8")

    class FakeAudio:
        def __init__(self) -> None:
            self.tags = {"date": ["2020-05-17"], "artist": ["Alice"]}
            self.saved = False

        def items(self):  # type: ignore[no-untyped-def]
            return self.tags.items()

        def clear(self) -> None:
            self.tags = {}

        def __setitem__(self, key: str, value):  # type: ignore[no-untyped-def]
            self.tags[key] = value

        def save(self) -> None:
            self.saved = True

    fake_audio = FakeAudio()
    monkeypatch.setattr("mutagen.File", lambda *_args, **_kwargs: fake_audio)

    diff = write_canon_to_file(audio_path, rules, dry_run=False)

    assert "date" in diff
    assert fake_audio.saved is True
    assert fake_audio.tags["date"] == ["2020"]


def test_write_canon_to_file_unsupported_format_raises(tmp_path: Path) -> None:
    rules = load_canon_rules(RULES_PATH)
    unsupported = tmp_path / "sample.wav"
    unsupported.write_text("stub", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported file format"):
        write_canon_to_file(unsupported, rules, dry_run=True)
