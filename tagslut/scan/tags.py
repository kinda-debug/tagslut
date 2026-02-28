"""Stage 1: raw tag extraction, technical metadata, checksum."""

import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional

from mutagen import File as MutagenFile

from tagslut.core.quality import compute_quality_rank
from tagslut.scan.isrc import extract_isrc_candidates


class TagReadError(Exception):
    pass


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def read_raw_tags(path: Path) -> Dict[str, List[str]]:
    """
    Return all tag fields as {field_name: [values...]} with string values.
    Raises TagReadError if mutagen cannot open the file.
    """
    file_obj = MutagenFile(path, easy=False)
    if file_obj is None:
        raise TagReadError(f"mutagen returned None for {path}")

    result: Dict[str, List[str]] = {}
    for key, val in file_obj.tags.items() if file_obj.tags else []:
        if isinstance(val, list):
            result[str(key)] = [str(v) for v in val]
        else:
            result[str(key)] = [str(val)]
    return result


def read_technical(path: Path) -> Dict[str, Any]:
    """
    Return technical audio parameters from mutagen container info.
    """
    file_obj = MutagenFile(path, easy=False)
    if file_obj is None:
        return {}

    info = file_obj.info
    return {
        "duration_tagged": getattr(info, "length", None),
        "bit_depth": getattr(info, "bits_per_sample", None),
        "sample_rate": getattr(info, "sample_rate", None),
        "bitrate": getattr(info, "bitrate", None),
        "channels": getattr(info, "channels", None),
    }


def extract_isrc_from_tags(raw_tags: Dict[str, List[str]]) -> List[str]:
    """
    Collect all ISRC-related tag values and extract candidates.
    Checks ISRC, TSRC, and any field containing 'isrc' (case-insensitive).
    """
    values: List[str] = []
    for key, vals in raw_tags.items():
        if "isrc" in key.lower() or key.upper() in ("ISRC", "TSRC"):
            values.extend(vals)
    return extract_isrc_candidates(values)


def compute_quality_rank_from_technical(technical: Dict[str, Any]) -> Optional[int]:
    bit_depth = technical.get("bit_depth")
    sample_rate = technical.get("sample_rate")
    bitrate = technical.get("bitrate") or 0
    if bit_depth and sample_rate:
        return int(compute_quality_rank(bit_depth, sample_rate, bitrate))
    return None
