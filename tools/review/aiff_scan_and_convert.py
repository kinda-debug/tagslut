#!/usr/bin/env python3
"""
Scan AIFF files for likely lossy transcodes and optionally convert selected files to FLAC.

Defaults are conservative:
- Scan-only unless --convert and --execute are both provided.
- Conversion keeps source AIFF files by default.
- Existing destination FLAC files are never overwritten unless --overwrite is set.

This is a heuristic tool. "confirmed_suspect_transcode" indicates strong evidence of
lossy source material inside a lossless container, not formal proof.
"""

from __future__ import annotations

import argparse
import csv
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

from _progress import ProgressTracker


@dataclass(frozen=True)
class ScanRow:
    path: str
    status: str
    sample_rate: str
    duration_s: str
    bw99_hz: str
    bw995_hz: str
    hi16_ratio: str
    hi18_ratio: str
    hi20_ratio: str


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _iter_aiff_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix.lower() in {".aiff", ".aif"} else []
    return sorted([p for p in root.rglob("*") if p.suffix.lower() in {".aiff", ".aif"}])


def _ffprobe_sr_dur(path: Path) -> tuple[int | None, float | None]:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=sample_rate:format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        return None, None
    lines = [x.strip() for x in res.stdout.splitlines() if x.strip()]
    if len(lines) < 2:
        return None, None
    try:
        return int(float(lines[0])), float(lines[1])
    except (TypeError, ValueError):
        return None, None


def _load_pcm_mono(path: Path, seconds: float, target_sr: int = 44100) -> np.ndarray | None:
    cmd = [
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-i",
        str(path),
        "-ac",
        "1",
        "-ar",
        str(target_sr),
        "-t",
        f"{seconds:.2f}",
        "-f",
        "f32le",
        "-",
    ]
    res = subprocess.run(cmd, capture_output=True, check=False)
    if res.returncode != 0 or not res.stdout:
        return None
    arr = np.frombuffer(res.stdout, dtype=np.float32)
    if arr.size < target_sr * 5:
        return None
    return arr


def _spectral_features(samples: np.ndarray, sr: int = 44100) -> dict[str, float] | None:
    n_fft = 16384
    hop = 4096
    if samples.size < n_fft:
        return None
    win = np.hanning(n_fft).astype(np.float32)
    specs: list[np.ndarray] = []
    for start in range(0, samples.size - n_fft + 1, hop):
        segment = samples[start : start + n_fft] * win
        specs.append(np.abs(np.fft.rfft(segment)))
    if not specs:
        return None

    mean_spec = np.mean(np.vstack(specs), axis=0)
    freqs = np.fft.rfftfreq(n_fft, d=1.0 / sr)
    power = mean_spec**2
    total = float(np.sum(power)) + 1e-20

    def band_ratio(f0: float) -> float:
        return float(np.sum(power[freqs >= f0]) / total)

    csum = np.cumsum(power)
    csum /= csum[-1]
    bw99 = float(freqs[min(int(np.searchsorted(csum, 0.99)), len(freqs) - 1)])
    bw995 = float(freqs[min(int(np.searchsorted(csum, 0.995)), len(freqs) - 1)])
    return {
        "bw99_hz": bw99,
        "bw995_hz": bw995,
        "hi16_ratio": band_ratio(16000.0),
        "hi18_ratio": band_ratio(18000.0),
        "hi20_ratio": band_ratio(20000.0),
    }


def _classify(features: dict[str, float]) -> str:
    cond1 = features["bw995_hz"] < 16500 and features["hi18_ratio"] < 0.0007
    cond2 = features["bw99_hz"] < 15500 and features["hi16_ratio"] < 0.0010
    if cond1 and cond2:
        return "confirmed_suspect_transcode"
    if features["bw995_hz"] < 17500 and features["hi18_ratio"] < 0.0008:
        return "suspect_transcode"
    return "likely_lossless"


def _scan_file(path: Path, max_seconds: float) -> ScanRow:
    sample_rate, duration_s = _ffprobe_sr_dur(path)
    if sample_rate is None:
        return ScanRow(str(path), "error_probe", "", "", "", "", "", "", "")

    sample_window = min(max_seconds, duration_s or max_seconds)
    pcm = _load_pcm_mono(path, seconds=sample_window, target_sr=44100)
    if pcm is None:
        return ScanRow(
            str(path),
            "error_decode",
            str(sample_rate),
            f"{duration_s:.3f}" if duration_s else "",
            "",
            "",
            "",
            "",
            "",
        )

    feats = _spectral_features(pcm, sr=44100)
    if feats is None:
        return ScanRow(
            str(path),
            "error_features",
            str(sample_rate),
            f"{duration_s:.3f}" if duration_s else "",
            "",
            "",
            "",
            "",
            "",
        )

    return ScanRow(
        path=str(path),
        status=_classify(feats),
        sample_rate=str(sample_rate),
        duration_s=f"{duration_s:.3f}" if duration_s else "",
        bw99_hz=f"{feats['bw99_hz']:.1f}",
        bw995_hz=f"{feats['bw995_hz']:.1f}",
        hi16_ratio=f"{feats['hi16_ratio']:.6f}",
        hi18_ratio=f"{feats['hi18_ratio']:.6f}",
        hi20_ratio=f"{feats['hi20_ratio']:.6f}",
    )


def _write_scan_outputs(rows: list[ScanRow], out_csv: Path, out_confirmed: Path, out_suspect: Path) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "path",
                "status",
                "sample_rate",
                "duration_s",
                "bw99_hz",
                "bw995_hz",
                "hi16_ratio",
                "hi18_ratio",
                "hi20_ratio",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)

    confirmed = [r.path for r in rows if r.status == "confirmed_suspect_transcode"]
    suspect = [r.path for r in rows if r.status in {"confirmed_suspect_transcode", "suspect_transcode"}]
    out_confirmed.write_text("\n".join(confirmed) + ("\n" if confirmed else ""), encoding="utf-8")
    out_suspect.write_text("\n".join(suspect) + ("\n" if suspect else ""), encoding="utf-8")


def _convert_one(src: Path, dst: Path, *, execute: bool, overwrite: bool) -> tuple[bool, str]:
    if dst.exists() and not overwrite:
        return False, "skip_exists"

    cmd = [
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-i",
        str(src),
        "-map_metadata",
        "0",
        "-c:a",
        "flac",
        "-compression_level",
        "8",
        str(dst),
    ]
    if execute:
        if overwrite:
            cmd.insert(1, "-y")
        else:
            cmd.insert(1, "-n")
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            return False, f"ffmpeg_error:{(res.stderr or '').strip()[:220]}"
        verify = subprocess.run(["flac", "-t", "--silent", str(dst)], capture_output=True, text=True, check=False)
        if verify.returncode != 0:
            return False, f"verify_error:{(verify.stderr or '').strip()[:220]}"
        return True, "converted"

    return True, "dry_run_convert"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan AIFF quality and optionally convert selected files to FLAC")
    parser.add_argument("path", type=Path, help="AIFF root folder or a single AIFF file")
    parser.add_argument("--limit", type=int, help="Max files to scan")
    parser.add_argument("--sample-seconds", type=float, default=300.0, help="Audio seconds per file for analysis")
    parser.add_argument("--convert", action="store_true", help="Convert selected AIFF files to FLAC")
    parser.add_argument(
        "--convert-status",
        default="confirmed_suspect_transcode",
        help="Comma-separated scan statuses to convert (default: confirmed_suspect_transcode)",
    )
    parser.add_argument("--dest-root", type=Path, help="Write FLAC files under this root (mirrors source structure)")
    parser.add_argument("--overwrite", action="store_true", help="Allow overwriting existing destination FLAC files")
    parser.add_argument("--delete-source", action="store_true", help="Delete AIFF source after successful conversion")
    parser.add_argument("--execute", action="store_true", help="Perform conversion actions (default: dry-run)")
    parser.add_argument("--report-prefix", type=Path, help="Custom output prefix (without extension)")
    parser.add_argument("--progress-interval", type=int, default=25, help="Progress print interval")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.path.expanduser().resolve()
    if not root.exists():
        raise SystemExit(f"Path not found: {root}")

    files = _iter_aiff_files(root)
    if args.limit and args.limit > 0:
        files = files[: args.limit]
    if not files:
        print("No AIFF files found.")
        return 0

    ts = _timestamp()
    if args.report_prefix:
        prefix = args.report_prefix.expanduser().resolve()
        prefix.parent.mkdir(parents=True, exist_ok=True)
    else:
        prefix = Path("artifacts") / f"aiff_scan_{ts}"
        prefix.parent.mkdir(parents=True, exist_ok=True)

    out_csv = Path(str(prefix) + ".csv")
    out_confirmed = Path(str(prefix) + "_confirmed.txt")
    out_suspect = Path(str(prefix) + "_suspect.txt")
    out_convert_log = Path(str(prefix) + "_convert.csv")

    print(f"Scanning {len(files)} AIFF file(s)...")
    rows: list[ScanRow] = []
    scan_progress = ProgressTracker(total=len(files), interval=int(args.progress_interval), label="Scan")
    for index, file_path in enumerate(files, start=1):
        row = _scan_file(file_path, max_seconds=float(args.sample_seconds))
        rows.append(row)
        if scan_progress.should_print(index):
            confirmed = sum(1 for r in rows if r.status == "confirmed_suspect_transcode")
            suspect = sum(1 for r in rows if r.status in {"confirmed_suspect_transcode", "suspect_transcode"})
            print(scan_progress.line(index, extra=f"confirmed={confirmed} suspect={suspect}"))

    _write_scan_outputs(rows, out_csv=out_csv, out_confirmed=out_confirmed, out_suspect=out_suspect)

    confirmed = sum(1 for r in rows if r.status == "confirmed_suspect_transcode")
    suspect = sum(1 for r in rows if r.status in {"confirmed_suspect_transcode", "suspect_transcode"})
    likely = sum(1 for r in rows if r.status == "likely_lossless")
    errors = len(rows) - confirmed - likely - (suspect - confirmed)

    print("--- Scan Summary ---")
    print(f"Total: {len(rows)}")
    print(f"Likely lossless: {likely}")
    print(f"Confirmed suspect transcode: {confirmed}")
    print(f"Suspect transcode (all): {suspect}")
    print(f"Errors: {errors}")
    print(f"Scan CSV: {out_csv}")
    print(f"Confirmed list: {out_confirmed}")
    print(f"Suspect list: {out_suspect}")

    if not args.convert:
        return 0

    statuses = {x.strip() for x in str(args.convert_status).split(",") if x.strip()}
    selected = [Path(r.path) for r in rows if r.status in statuses]

    print("--- Convert Plan ---")
    print(f"Selected by status {sorted(statuses)}: {len(selected)}")
    if not args.execute:
        print("DRY-RUN conversion: use --execute to write FLAC files")

    out_convert_log.parent.mkdir(parents=True, exist_ok=True)
    with out_convert_log.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["source_aiff", "dest_flac", "result"])
        writer.writeheader()

        converted = 0
        skipped = 0
        failed = 0
        convert_progress = ProgressTracker(total=len(selected), interval=int(args.progress_interval), label="Convert")
        for source_path in selected:
            if args.dest_root:
                rel = source_path.relative_to(root if root.is_dir() else source_path.parent)
                target = args.dest_root.expanduser().resolve() / rel
                target = target.with_suffix(".flac")
            else:
                target = source_path.with_suffix(".flac")

            target.parent.mkdir(parents=True, exist_ok=True)
            ok, reason = _convert_one(source_path, target, execute=bool(args.execute), overwrite=bool(args.overwrite))
            writer.writerow({"source_aiff": str(source_path), "dest_flac": str(target), "result": reason})

            if ok and reason in {"converted", "dry_run_convert"}:
                converted += 1
                if args.execute and args.delete_source and reason == "converted" and source_path.exists():
                    source_path.unlink(missing_ok=True)
            elif reason == "skip_exists":
                skipped += 1
            else:
                failed += 1

            completed = converted + skipped + failed
            if convert_progress.should_print(completed):
                print(
                    convert_progress.line(
                        completed,
                        extra=f"converted={converted} skipped={skipped} failed={failed}",
                    )
                )

        print("--- Convert Summary ---")
        print(f"Planned/attempted: {len(selected)}")
        print(f"Converted (or dry-run convertible): {converted}")
        print(f"Skipped existing: {skipped}")
        print(f"Failed: {failed}")
        print(f"Convert log CSV: {out_convert_log}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
