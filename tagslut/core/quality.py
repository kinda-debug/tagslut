"""
Quality rank computation for audio files.

Rank 1 = best (studio master), Rank 7 = worst (degraded lossy).
Used for upgrade decisions during pre-download resolution.
"""
from enum import IntEnum


class QualityRank(IntEnum):
    STUDIO_MASTER = 1       # FLAC 32bit+ or DSD
    HIRES_LOSSLESS = 2      # FLAC 24bit / 96kHz+
    HIRES_STANDARD = 3      # FLAC 24bit / 44.1kHz
    CD_LOSSLESS = 4         # FLAC 16bit / 44.1kHz
    UNCOMPRESSED = 5        # AIFF or WAV 16bit (bitrate=0)
    LOSSY_HIGH = 6          # MP3/AAC 320kbps
    LOSSY_DEGRADED = 7      # MP3/AAC < 320kbps


def compute_quality_rank(bit_depth: int, sample_rate: int, bitrate: int) -> QualityRank:
    """
    Compute quality rank from audio technical parameters.

    Args:
        bit_depth:   Bits per sample (e.g. 16, 24, 32)
        sample_rate: Samples per second in Hz (e.g. 44100, 96000)
        bitrate:     Bits per second (e.g. 320000). Use 0 for lossless/uncompressed.

    Returns:
        QualityRank enum value.
    """
    if bit_depth >= 32:
        return QualityRank.STUDIO_MASTER
    if bit_depth >= 24 and sample_rate >= 96000:
        return QualityRank.HIRES_LOSSLESS
    if bit_depth >= 24:
        return QualityRank.HIRES_STANDARD
    if bit_depth >= 16 and sample_rate >= 44100 and bitrate == 0:
        return QualityRank.CD_LOSSLESS
    if bitrate == 0:
        return QualityRank.UNCOMPRESSED
    if bitrate >= 320000:
        return QualityRank.LOSSY_HIGH
    return QualityRank.LOSSY_DEGRADED


def is_upgrade(current_rank: int, candidate_rank: int) -> bool:
    """
    Return True if candidate is a quality improvement over current.
    Lower rank number = better quality.
    """
    return candidate_rank < current_rank
