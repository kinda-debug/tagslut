import pytest
pytest.skip("scan module archived", allow_module_level=True)

from tagslut.scan.isrc import extract_isrc_candidates


def test_single_isrc():
    assert extract_isrc_candidates(["USABC1234567"]) == ["USABC1234567"]


def test_isrc_with_dashes():
    assert extract_isrc_candidates(["US-ABC-12-34567"]) == ["USABC1234567"]


def test_multiple_values():
    result = extract_isrc_candidates(["USABC1234567", "GBXYZ9876543"])
    assert result == ["USABC1234567", "GBXYZ9876543"]


def test_multiple_isrc_in_one_string():
    result = extract_isrc_candidates(["USABC1234567 GBXYZ9876543"])
    assert len(result) == 2
    assert "USABC1234567" in result
    assert "GBXYZ9876543" in result


def test_garbage_ignored():
    result = extract_isrc_candidates(["not an isrc", "", "12345", None])
    assert result == []


def test_deduplication():
    result = extract_isrc_candidates(["USABC1234567", "USABC1234567"])
    assert result == ["USABC1234567"]


def test_preserves_first_seen_order():
    result = extract_isrc_candidates(["GBXYZ9876543", "USABC1234567"])
    assert result[0] == "GBXYZ9876543"


def test_empty_input():
    assert extract_isrc_candidates([]) == []
