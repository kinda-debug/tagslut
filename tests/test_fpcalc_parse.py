"""Unit tests for :func:`dd_flac_dedupe_db.parse_fpcalc_output`."""

from __future__ import annotations

import base64
import struct
import sys
from pathlib import Path
from typing import List

import pytest

sys.path.append(str(Path(__file__).resolve().parent.parent))

from dd_flac_dedupe_db import parse_fpcalc_output


def _encode_fingerprint(values: List[int]) -> str:
    """Return a base64 representation of ``values`` matching Chromaprint."""

    packed = struct.pack(f"<{len(values)}i", *values)
    return base64.b64encode(packed).decode("ascii")


def _compute_expected_hash(values: List[int]) -> str:
    from dd_flac_dedupe_db import sha1_hex

    return sha1_hex(",".join(str(v) for v in values).encode("utf-8"))


def test_parse_json_list() -> None:
    fingerprint = [1, -2, 3, -4]
    output = '{"fingerprint": [1, -2, 3, -4]}'
    parsed, digest = parse_fpcalc_output(output)
    assert parsed == fingerprint
    assert digest == _compute_expected_hash(fingerprint)


def test_parse_json_base64_with_whitespace() -> None:
    fingerprint = [5, 6, 7]
    encoded = _encode_fingerprint(fingerprint)
    # Insert whitespace/newlines inside the payload to verify normalization.
    noisy = f"{encoded[:4]} \n {encoded[4:]}"
    payload = noisy.replace("\n", "\\n")
    output = '{"fingerprint": "' + payload + '"}'
    parsed, digest = parse_fpcalc_output(output)
    assert parsed == fingerprint
    assert digest == _compute_expected_hash(fingerprint)


def test_parse_legacy_line_base64_urlsafe() -> None:
    fingerprint = [8, 9, 10]
    encoded = base64.urlsafe_b64encode(
        struct.pack(f"<{len(fingerprint)}i", *fingerprint)
    ).decode("ascii")
    output = f"FILE=/tmp/example.flac\nFINGERPRINT={encoded}\n"
    parsed, digest = parse_fpcalc_output(output)
    assert parsed == fingerprint
    assert digest == _compute_expected_hash(fingerprint)


def test_parse_legacy_line_comma_numbers() -> None:
    fingerprint = [11, 12, 13]
    output = (
        "INFO=something\n"
        "FINGERPRINT=" + ",".join(str(v) for v in fingerprint) + "\n"
    )
    parsed, digest = parse_fpcalc_output(output)
    assert parsed == fingerprint
    assert digest == _compute_expected_hash(fingerprint)


@pytest.mark.parametrize(
    "payload",
    [
        "abcde",  # length modulo 4 equals 1 -> impossible
        "not-base64!!",  # illegal characters
    ],
)
def test_parse_rejects_malformed_base64(payload: str) -> None:
    output = f"FINGERPRINT={payload}"
    parsed, digest = parse_fpcalc_output(output)
    assert parsed is None
    assert digest is None


def test_parse_base64_missing_padding_succeeds() -> None:
    fingerprint = [1, 2]
    encoded = _encode_fingerprint(fingerprint)
    truncated = encoded.rstrip("=")
    output = f"FINGERPRINT={truncated}"
    parsed, digest = parse_fpcalc_output(output)
    assert parsed == fingerprint
    assert digest == _compute_expected_hash(fingerprint)
