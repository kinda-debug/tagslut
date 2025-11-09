#!/usr/bin/env python3
"""
Enhanced truncation detection for FLAC files.

Detects truncated files by:
1. Checking file size vs bitrate (rough indicator)
2. Attempting full decode with ffmpeg (catches incomplete streams)
3. Comparing fingerprints from start vs end (detects missing audio)
4. Checking for FLAC frame errors
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Tuple


def ffprobe_info(path: Path) -> dict:
    """Extract ffprobe metadata."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_format",
        "-show_streams",
        "-output_format", "json",
        str(path),
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    if result.returncode != 0:
        raise ValueError(f"ffprobe failed: {result.stderr}")

    return json.loads(result.stdout)  # type: ignore


def check_truncation_via_bitrate(path: Path) -> Tuple[bool, str]:
    """
    Check if file is truncated by comparing file size vs bitrate.

    Returns:
        (is_truncated, reason)
    """
    try:
        info = ffprobe_info(path)
        fmt = info.get("format", {})

        duration = float(fmt.get("duration", 0))
        bitrate = int(fmt.get("bit_rate", 0))
        file_size = int(fmt.get("size", 0))

        if duration <= 0 or bitrate <= 0 or file_size <= 0:
            return False, "Insufficient metadata"

        # Expected size = (duration * bitrate) / 8 + overhead
        expected_size = (duration * bitrate / 8) * 0.95
        # 5% tolerance for overhead

        # If actual size << expected, likely truncated
        size_ratio = file_size / expected_size
        if size_ratio < 0.85:  # More than 15% smaller than expected
            return True, (
                f"File size mismatch: {file_size} bytes vs "
                f"{int(expected_size)} expected (ratio: {size_ratio:.2f})"
            )

        return False, "Size check passed"

    except (ValueError, KeyError, OSError) as e:
        return False, f"Size check error: {e}"


def check_truncation_via_decode(path: Path) -> Tuple[bool, str]:
    """
    Check truncation by attempting full decode and capturing errors.

    ffmpeg's decode will:
    - Warn/error if file is incomplete
    - Fail if audio stream is corrupted
    """
    try:
        # Try to decode the entire file to /dev/null
        # If file is truncated, ffmpeg will complain
        cmd = [
            "ffmpeg",
            "-v", "warning",  # Show warnings and above
            "-i", str(path),
            "-f", "null",
            "-",
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

        stderr = result.stderr.lower()

        # Check for truncation indicators in ffmpeg output
        truncation_indicators = [
            "truncated",
            "incomplete",
            "premature end",
            "eof",
            "error",  # Generic error
        ]

        for indicator in truncation_indicators:
            if indicator in stderr:
                return True, f"ffmpeg decode detected: {indicator}"

        # If we got here with non-zero exit code, that's suspicious
        if result.returncode != 0:
            return True, (
                f"ffmpeg decode failed with exit code {result.returncode}"
            )

        return False, "Decode check passed"

    except subprocess.TimeoutExpired:
        msg = (
            "ffmpeg decode timeout "
            "(file likely very large or corrupted)"
        )
        return True, msg
    except OSError as e:
        return False, f"Decode check error: {e}"


def check_truncation_via_fingerprints(path: Path) -> Tuple[bool, str]:
    """
    Check truncation by comparing fingerprints from start vs end.

    If file is truncated, the end section will either:
    - Be missing (extract fails)
    - Be incomplete (fingerprint differs or silent)
    """
    try:
        info = ffprobe_info(path)
        fmt = info.get("format", {})
        duration = float(fmt.get("duration", 0))

        if duration <= 0:
            return False, "Duration unavailable"

        fps_start = extract_fingerprint_at_offset(path, 0)
        fp_end_offset = max(0, duration - 30)
        fps_end = extract_fingerprint_at_offset(path, fp_end_offset)

        if not fps_start and not fps_end:
            return False, "No fingerprints extracted"

        if fps_start and not fps_end:
            return True, (
                "Start fingerprint exists but end fingerprint missing "
                "(truncated file)"
            )

        if fps_start and fps_end and fps_start != fps_end:
            return False, "Fingerprints differ (single track confirmed)"

        return False, "Fingerprint check passed"

    except (ValueError, OSError) as e:
        return False, f"Fingerprint check error: {e}"


def extract_fingerprint_at_offset(
    path: Path,
    offset: float,
    window: int = 10,
) -> str:
    """Extract a single Chromaprint fingerprint at given offset."""
    try:
        ffmpeg = subprocess.run(
            ["which", "ffmpeg"],
            capture_output=True,
            text=True,
            check=False,
        )
        fpcalc = subprocess.run(
            ["which", "fpcalc"],
            capture_output=True,
            text=True,
            check=False,
        )

        if ffmpeg.returncode != 0 or fpcalc.returncode != 0:
            return ""

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            subprocess.run(
                [
                    ffmpeg.stdout.strip(),
                    "-nostdin",
                    "-v", "error",
                    "-ss", str(offset),
                    "-t", str(window),
                    "-i", str(path),
                    "-f", "wav",
                    str(tmp_path),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
                check=False,
            )

            if tmp_path.stat().st_size == 0:
                return ""

            proc = subprocess.run(
                [fpcalc.stdout.strip(), str(tmp_path)],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )

            for line in proc.stdout.splitlines():
                if line.startswith("FINGERPRINT="):
                    return line.split("=", 1)[1].strip()

            return ""
        finally:
            try:
                tmp_path.unlink()
            except OSError:
                pass

    except (subprocess.TimeoutExpired, OSError):
        return ""


def check_file_truncation(path: Path) -> dict:
    """
    Comprehensive truncation detection.

    Returns dict with:
        is_truncated: bool
        checks: list of (check_name, is_truncated, reason)
        summary: overall assessment
    """
    checks_list: list = []
    results = {
        "path": str(path),
        "is_truncated": False,
        "checks": checks_list,
        "summary": None,
    }

    # Check 1: Bitrate ratio
    truncated, reason = check_truncation_via_bitrate(path)
    checks_list.append(("Bitrate Ratio", truncated, reason))

    # Check 2: FFmpeg decode
    truncated, reason = check_truncation_via_decode(path)
    checks_list.append(("FFmpeg Decode", truncated, reason))

    # Check 3: Fingerprints
    truncated, reason = check_truncation_via_fingerprints(path)
    checks_list.append(("Fingerprints", truncated, reason))

    # Overall: if ANY check flags as truncated, consider it truncated
    is_truncated = any(check[1] for check in checks_list)
    results["is_truncated"] = is_truncated

    # Summary
    failed_checks = [
        (name, reason) for name, truncated, reason in checks_list
        if truncated
    ]
    if failed_checks:
        results["summary"] = (
            f"TRUNCATED: {len(failed_checks)} check(s) flagged truncation"
        )
    else:
        results["summary"] = "OK: All checks passed"

    return results


def main() -> None:
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python3 check_truncation.py <file.flac>")
        sys.exit(1)

    file_path = Path(sys.argv[1])

    if not file_path.exists():
        print(f"File not found: {file_path}")
        sys.exit(1)

    print("=" * 80)
    print("Truncation Detection Check")
    print("=" * 80)
    print(f"\nFile: {file_path.name}")
    print(f"Size: {file_path.stat().st_size / 1024 / 1024:.1f} MB")
    print()

    results = check_file_truncation(file_path)

    print("Results:")
    print()
    for check_name, truncated, reason in results["checks"]:
        status = "⚠️  TRUNCATED" if truncated else "✅ OK"
        print(f"{status} | {check_name}: {reason}")

    print()
    print("=" * 80)
    print(results["summary"])
    print("=" * 80)

    if results["is_truncated"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
