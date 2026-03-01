from __future__ import annotations

import pytest

from tagslut.filters.gig_filter import FILTER_COLUMN_MAP, FilterParseError, parse_filter


def test_parse_filter_genre_produces_equality_clause() -> None:
    clause, params = parse_filter("genre:techno")

    assert clause == "canonical_genre = ?"
    assert params == ["techno"]


def test_parse_filter_bpm_range_produces_between() -> None:
    clause, params = parse_filter("bpm:128-145")

    assert clause == "canonical_bpm BETWEEN ? AND ?"
    assert params == [128.0, 145.0]


def test_parse_filter_dj_flag_true_maps_to_integer_one() -> None:
    clause, params = parse_filter("dj_flag:true")

    assert clause == "is_dj_material = ?"
    assert params == [1]


def test_parse_filter_combined_expression_uses_and() -> None:
    clause, params = parse_filter("genre:techno bpm:128-145")

    assert clause == "canonical_genre = ? AND canonical_bpm BETWEEN ? AND ?"
    assert params == ["techno", 128.0, 145.0]


def test_parse_filter_invalid_key_raises_filter_parse_error() -> None:
    with pytest.raises(FilterParseError):
        parse_filter("invalid:")


def test_parse_filter_all_mapped_keys_produce_valid_sql() -> None:
    sample_values = {
        "genre": "house",
        "bpm": "126",
        "key": "8A",
        "dj_flag": "true",
        "label": "Toolroom",
        "source": "beatport",
        "added": ">2025-01-01",
        "quality_rank": "<=3",
    }

    for key, value in sample_values.items():
        clause, params = parse_filter(f"{key}:{value}")
        assert FILTER_COLUMN_MAP[key] in clause
        assert len(params) >= 1


def test_parse_filter_missing_colon_raises() -> None:
    with pytest.raises(FilterParseError):
        parse_filter("genre")
