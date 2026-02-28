import pytest

from tagslut.core.quality import QualityRank, compute_quality_rank, is_upgrade


@pytest.mark.parametrize("bit_depth,sample_rate,bitrate,expected", [
    (32, 192000, 0, QualityRank.STUDIO_MASTER),
    (24, 96000, 0, QualityRank.HIRES_LOSSLESS),
    (24, 44100, 0, QualityRank.HIRES_STANDARD),
    (16, 44100, 0, QualityRank.CD_LOSSLESS),
    (16, 44100, 320000, QualityRank.LOSSY_HIGH),
    (16, 44100, 128000, QualityRank.LOSSY_DEGRADED),
])
def test_compute_quality_rank(bit_depth, sample_rate, bitrate, expected):
    assert compute_quality_rank(bit_depth, sample_rate, bitrate) == expected


def test_is_upgrade_better():
    assert is_upgrade(current_rank=4, candidate_rank=2) is True


def test_is_upgrade_same():
    assert is_upgrade(current_rank=4, candidate_rank=4) is False


def test_is_upgrade_worse():
    assert is_upgrade(current_rank=2, candidate_rank=5) is False
