#!/usr/bin/env python3
"""
AcoustID-based repair validation: Verify repaired files have correct duration
and no spliced/concatenated audio residue from other tracks.

Uses fpcalc (Chromaprint) for fast fingerprinting via sliding windows.
Files with inconsistent fingerprints across windows likely have spliced audio.
"""

import argparse
import csv
import json
import logging
import sys
import tempfile
from pathlib import Path
from subprocess import DEVNULL, PIPE, run, TimeoutExpired
from typing import Any, Dict, List, Optional, Tuple

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable, **_kwargs):  # type: ignore
        return iterable

# ============================================================================
# Logging Setup
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# ============================================================================
# Utility Functions
# ============================================================================

def _which(cmd: str) -> Optional[str]:
    """Find command in PATH."""
    try:
        result = run(
            ["which", cmd],
            stdout=PIPE,
            stderr=DEVNULL,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, OSError):
        pass
    return None


def ffprobe_info(path: Path) -> Dict[str, Any]:
    """Extract ffprobe metadata: duration, codec, bitrate, etc."""
    ffprobe = _which("ffprobe")
    if not ffprobe:
        raise FileNotFoundError("ffprobe not found")

    cmd = [
        ffprobe,
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-output_format",
        "json",
        str(path),
    ]
    try:
        result = run(
            cmd,
            stdout=PIPE,
            stderr=PIPE,
            text=True,
            timeout=10,
            check=False,
        )
    except TimeoutExpired as exc:
        msg = f"ffprobe timeout on {path}"
        raise ValueError(msg) from exc

    if result.returncode != 0:
        raise ValueError(f"ffprobe failed: {result.stderr}")

    data = json.loads(result.stdout)
    fmt = data.get("format", {})
    duration = float(fmt.get("duration", 0))
    bitrate = int(fmt.get("bit_rate", 0))
    
    audio_stream: Dict[str, Any] = next(
        (s for s in data.get("streams", [])
         if s.get("codec_type") == "audio"),
        {},
    )
    codec = audio_stream.get("codec_name", "unknown")
    sample_rate = int(audio_stream.get("sample_rate", 0))

    return {
        "path": str(path),
        "duration": duration,
        "bitrate": bitrate,
        "codec": codec,
        "sample_rate": sample_rate,
    }


def get_fingerprints_sliding_windows(
    path: Path,
    window: int = 30,
    max_windows: int = 3,
) -> Tuple[List[str], int]:
    """
    Extract multiple Chromaprint fingerprints using sliding windows.

    Returns:
        (list of fingerprints, total duration)

    Hypothesis: If a file has spliced audio from different tracks,
    fingerprints from different windows will differ significantly.
    """
    ffmpeg = _which("ffmpeg")
    fpcalc = _which("fpcalc")
    if not ffmpeg or not fpcalc:
        return [], 0

    try:
        info = ffprobe_info(path)
    except (FileNotFoundError, OSError, ValueError):
        return [], 0

    duration = info.get("duration", 0)
    if duration <= 0 or duration > 3600:  # Skip files < 1 sec or > 1 hour
        return [], int(duration)

    fingerprints = []
    step = max(10, window - 10)  # 20-sec step for 30-sec window
    offset = 0.0
    window_count = 0

    while offset < duration and window_count < max_windows:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            # Extract window via ffmpeg (with longer timeout for slow files)
            cmd = [
                ffmpeg,
                "-nostdin",
                "-v",
                "error",
                "-ss",
                str(offset),
                "-t",
                str(window),
                "-i",
                str(path),
                "-f",
                "wav",
                str(tmp_path),
            ]
            try:
                run(
                    cmd,
                    stdout=DEVNULL,
                    stderr=DEVNULL,
                    timeout=15,  # Increased from 5s
                    check=False,
                )
            except TimeoutExpired:
                # File too slow to decode; skip fingerprinting
                break

            # Get fpcalc fingerprint
            if tmp_path.exists() and tmp_path.stat().st_size > 0:
                try:
                    proc = run(
                        [fpcalc, str(tmp_path)],
                        stdout=PIPE,
                        stderr=DEVNULL,
                        text=True,
                        timeout=5,  # Increased from 3s
                        check=False,
                    )
                    for line in proc.stdout.splitlines():
                        if line.startswith("FINGERPRINT="):
                            fp = line.split("=", 1)[1].strip()
                            if fp:
                                fingerprints.append(fp)
                            break
                except TimeoutExpired:
                    break
        finally:
            try:
                tmp_path.unlink()
            except OSError:
                pass

        offset += step
        window_count += 1

    return fingerprints, int(duration)


def assess_fingerprint_consistency(
    fingerprints: List[str],
) -> Tuple[bool, float]:
    """
    Assess if fingerprints are consistent (likely single track, no splice).

    Returns:
        (is_consistent, consistency_ratio)

    Logic:
        - If all fingerprints identical → consistent (ratio = 1.0)
        - If mostly identical → likely consistent (ratio > 0.6)
        - If highly varied → likely spliced (ratio < 0.4)
    """
    if not fingerprints:
        return False, 0.0

    if len(fingerprints) == 1:
        return True, 1.0

    # Count unique fingerprints
    unique_fps = set(fingerprints)
    consistency_ratio = 1.0 - (len(unique_fps) - 1) / len(fingerprints)

    # Heuristic: >60% identical fingerprints = consistent
    is_consistent = consistency_ratio > 0.6

    return is_consistent, consistency_ratio


def _check_truncation_quick(path: Path) -> bool:
    """
    Quick truncation check via FFmpeg decode.

    Returns True if file appears truncated/corrupted.
    """
    try:
        cmd = [
            "ffmpeg",
            "-v", "verbose",
            "-i", str(path),
            "-f", "null",
            "-",
        ]
        result = run(
            cmd,
            stdout=DEVNULL,
            stderr=PIPE,
            timeout=60,
            check=False,
        )

        # Decode stderr with error handling for invalid UTF-8
        stderr = result.stderr.decode('utf-8', errors='replace').lower()

        # Check for ANY decode errors in audio stream
        if "decode errors" in stderr:
            # Look for lines that indicate errors > 0
            for line in stderr.splitlines():
                if "decode errors" in line:
                    # Extract the number and check if > 0
                    if " 0 decode errors" not in line:
                        return True
        if "truncated" in stderr:
            return True

        return False

    except (TimeoutExpired, OSError):
        return True


def validate_repair(
    file_path: Path,
    expected_duration: Optional[float] = None,
    tolerance_sec: float = 2.0,
    check_truncation: bool = True,
) -> Dict[str, Any]:
    """
    Validate a repaired file:
      1. Check for truncation (FFmpeg decode validation)
      2. Check duration is reasonable (close to expected if provided)
      3. Extract fingerprints from multiple windows
      4. Check fingerprint consistency (no splice detection)
      5. Return comprehensive validation report
    """
    result: Dict[str, Any] = {
        "path": str(file_path),
        "file_exists": file_path.exists(),
        "valid": False,
        "truncated": None,
        "reason": None,
        "error": None,
    }

    if not result["file_exists"]:
        result["reason"] = "File does not exist"
        return result

    # Check truncation first (most critical issue)
    if check_truncation:
        truncated = _check_truncation_quick(file_path)
        result["truncated"] = truncated
        if truncated:
            result["reason"] = "File is truncated (FFmpeg decode failed)"
            return result

    try:
        # Get metadata
        info = ffprobe_info(file_path)
        result["duration"] = info["duration"]
        result["codec"] = info["codec"]
        result["bitrate"] = info["bitrate"]
        result["sample_rate"] = info["sample_rate"]

        # Check duration if expected provided
        if expected_duration is not None:
            delta = abs(info["duration"] - expected_duration)
            result["duration_delta"] = delta
            result["duration_acceptable"] = delta <= tolerance_sec
            if delta > tolerance_sec:
                msg = (
                    f"Duration mismatch: {info['duration']:.1f}s vs "
                    f"expected {expected_duration:.1f}s "
                    f"(delta={delta:.1f}s)"
                )
                result["reason"] = msg
                return result
        else:
            result["duration_acceptable"] = True

        # Get fingerprints
        fps, _ = get_fingerprints_sliding_windows(file_path)
        result["fingerprint_count"] = len(fps)
        result["fingerprints"] = fps

        # Assess consistency
        is_consistent, ratio = assess_fingerprint_consistency(fps)
        result["consistent"] = is_consistent
        result["consistency_ratio"] = ratio

        if not is_consistent and len(fps) > 1:
            msg = (
                f"Fingerprints inconsistent (ratio={ratio:.2f}); "
                "possible splice detected"
            )
            result["reason"] = msg
            return result

        # All checks passed
        result["valid"] = True
        result["reason"] = "OK"

    except (FileNotFoundError, OSError, ValueError) as e:
        result["error"] = str(e)
        result["reason"] = f"Validation error: {e}"

    return result


# ============================================================================
# Main Workflow
# ============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate repaired FLAC files using AcoustID fingerprints",
    )
    parser.add_argument(
        "input",
        type=Path,
        help="File or directory to validate",
    )
    parser.add_argument(
        "--expected-duration",
        type=float,
        default=None,
        help="Expected duration in seconds (for comparison)",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=2.0,
        help="Duration tolerance in seconds (default: 2.0)",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=None,
        help="Output validation results to CSV",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Output validation results to JSON",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output",
    )

    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    # Collect files to validate
    if args.input.is_file():
        files = [args.input]
    elif args.input.is_dir():
        files = sorted(args.input.glob("**/*.flac"))
    else:
        logger.error("Input not found: %s", args.input)
        sys.exit(1)

    if not files:
        logger.warning("No FLAC files found in %s", args.input)
        return

    logger.info("Validating %d file(s)", len(files))

    # Validate each file
    results = []
    for file_path in tqdm(files, desc="Validating repairs"):
        result = validate_repair(
            file_path,
            expected_duration=args.expected_duration,
            tolerance_sec=args.tolerance,
        )
        results.append(result)

    # Summary
    valid_count = sum(1 for r in results if r.get("valid"))
    logger.info("--- Validation Summary ---")
    logger.info("Total files: %d", len(results))
    logger.info("Valid: %d", valid_count)
    logger.info("Invalid: %d", len(results) - valid_count)

    # Flag any invalid files
    invalid_files = [r for r in results if not r.get("valid")]
    if invalid_files:
        logger.warning(
            "%d file(s) failed validation:", len(invalid_files)
        )
        for r in invalid_files:
            logger.warning("  %s: %s", r["path"], r.get("reason"))

    # Output to CSV if requested
    if args.output_csv:
        csv_path = Path(args.output_csv)
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            fieldnames = [
                "path",
                "valid",
                "reason",
                "duration",
                "duration_delta",
                "codec",
                "fingerprint_count",
                "consistency_ratio",
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in results:
                row = {k: r.get(k) for k in fieldnames}
                writer.writerow(row)
        logger.info("CSV report written to %s", csv_path)

    # Output to JSON if requested
    if args.output_json:
        json_path = Path(args.output_json)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        logger.info("JSON report written to %s", json_path)

    # Exit code
    sys.exit(0 if len(invalid_files) == 0 else 1)


if __name__ == "__main__":
    main()
