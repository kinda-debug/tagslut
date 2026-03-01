from __future__ import annotations

import json
from pathlib import Path

from tagslut.metadata.genre_normalization import GenreNormalizer


class _FakeAudio:
    def __init__(self, tags: dict | None = None) -> None:
        self.tags = tags if tags is not None else {}
        self.saved = False

    def save(self) -> None:
        self.saved = True


def _write_rules(tmp_path: Path) -> Path:
    rules_path = tmp_path / "genre_rules.json"
    rules_path.write_text(
        json.dumps(
            {
                "genre_map": {"Tech House": "House", "D&B": "Drum & Bass"},
                "style_map": {"Peak Time": "Peak-Time", "Neurofunk": "Neuro"},
            }
        ),
        encoding="utf-8",
    )
    return rules_path


def test_normalize_value_uses_known_mappings(tmp_path: Path) -> None:
    normalizer = GenreNormalizer(_write_rules(tmp_path))

    assert normalizer.normalize_value("Tech House", "genre") == "House"
    assert normalizer.normalize_value("Peak Time", "style") == "Peak-Time"


def test_choose_normalized_picks_highest_priority_tag(tmp_path: Path) -> None:
    normalizer = GenreNormalizer(_write_rules(tmp_path))
    tags = {
        "GENRE": "Trance",
        "SUBGENRE": "Tech House",
        "GENRE_PREFERRED": "D&B",
        "STYLE": "Neurofunk",
    }

    genre, style, dropped = normalizer.choose_normalized(tags)

    assert genre == "Drum & Bass"
    assert style == "Neuro"
    assert "GENRE" in dropped


def test_protected_compound_genre_is_not_split() -> None:
    normalizer = GenreNormalizer()

    genre, style, _ = normalizer.choose_normalized({"GENRE": "minimal / deep tech"})

    assert genre == "minimal / deep tech"
    assert style is None


def test_choose_normalized_handles_empty_and_none_values() -> None:
    normalizer = GenreNormalizer()

    genre, style, dropped = normalizer.choose_normalized({"GENRE": "", "STYLE": "", "GENRE_FULL": "   "})

    assert genre is None
    assert style is None
    assert dropped == []


def test_choose_normalized_splits_parenthetical_into_style() -> None:
    normalizer = GenreNormalizer()

    genre, style, _ = normalizer.choose_normalized({"GENRE": "Techno (Peak Time)"})

    assert genre == "Techno"
    assert style == "Peak Time"


def test_choose_normalized_splits_compound_genre_when_unprotected() -> None:
    normalizer = GenreNormalizer()

    genre, style, _ = normalizer.choose_normalized({"GENRE": "House / Deep House"})

    assert genre == "House"
    assert style == "Deep House"


def test_apply_tags_to_file_sets_expected_fields() -> None:
    audio = _FakeAudio(tags={"EXISTING": "1"})
    normalizer = GenreNormalizer()

    normalizer.apply_tags_to_file(audio, genre="House", style="Deep House")

    assert audio.tags["GENRE"] == "House"
    assert audio.tags["SUBGENRE"] == "Deep House"
    assert audio.tags["GENRE_PREFERRED"] == "Deep House"
    assert audio.tags["GENRE_FULL"] == "House | Deep House"
    assert audio.saved is True


def test_apply_tags_to_file_removes_subgenre_when_style_missing() -> None:
    audio = _FakeAudio(tags={"SUBGENRE": "Old"})
    normalizer = GenreNormalizer()

    normalizer.apply_tags_to_file(audio, genre="Techno", style=None)

    assert "SUBGENRE" not in audio.tags
    assert audio.tags["GENRE_PREFERRED"] == "Techno"
    assert audio.tags["GENRE_FULL"] == "Techno"


def test_apply_tags_to_file_noop_when_audio_tags_missing() -> None:
    audio = _FakeAudio(tags=None)
    normalizer = GenreNormalizer()

    normalizer.apply_tags_to_file(audio, genre="House", style="Classic")

    assert audio.saved is False
