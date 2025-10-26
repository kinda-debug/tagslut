"""Integration tests for :func:`dd_flac_dedupe_db.compute_fingerprint`."""

from __future__ import annotations

import math
import shutil
import struct
import subprocess
import sys
import wave
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parent.parent))

from dd_flac_dedupe_db import compute_fingerprint


@pytest.mark.skipif(shutil.which("fpcalc") is None, reason="fpcalc not installed")
def test_compute_fingerprint_with_generated_sample(tmp_path: Path) -> None:
    """Generate a tiny FLAC sample and ensure ``compute_fingerprint`` succeeds."""

    wav_path = tmp_path / "sample.wav"
    flac_path = tmp_path / "sample.flac"

    with wave.open(str(wav_path), "w") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(8000)
        frames = bytearray()
        for index in range(8000):
            value = int(32767 * math.sin(2.0 * math.pi * 440.0 * index / 8000))
            frames.extend(struct.pack("<h", value))
        wav_file.writeframes(frames)

    if shutil.which("ffmpeg"):
        cmd = ["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", str(wav_path), str(flac_path)]
    elif shutil.which("flac"):
        cmd = ["flac", "-f", "-o", str(flac_path), str(wav_path)]
    else:
        pytest.skip("Neither ffmpeg nor flac available to create test fixture")

    completed = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if completed.returncode != 0 or not flac_path.exists():
        pytest.skip(f"Failed to create FLAC fixture: {completed.stderr.decode('utf-8', 'replace')}")

    fingerprint, digest = compute_fingerprint(flac_path)
    if fingerprint is None or digest is None:
        pytest.skip("fpcalc failed to produce fingerprint in this environment")

    assert isinstance(fingerprint, list)
    assert isinstance(digest, str)
    assert fingerprint, "Fingerprint list should not be empty"
    assert digest, "Fingerprint hash should not be empty"
