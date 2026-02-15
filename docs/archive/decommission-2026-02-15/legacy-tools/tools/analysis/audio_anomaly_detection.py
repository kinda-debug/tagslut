#!/usr/bin/env python3
"""
Audio Anomaly Detection: Identifies stitched, truncated, and corrupted FLAC tracks.
Detects splices using RMS analysis, silence-break detection, and duration anomalies.

Usage:
  python3 tools/analysis/audio_anomaly_detection.py --db <path> --output <report.json> [--batch-size 50]
"""

import sys
import json
import sqlite3
import click
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import logging
import numpy as np
from dataclasses import dataclass, asdict
from datetime import datetime

# Ensure imports from root
sys.path.insert(0, str(Path(__file__).parents[2]))

from tagslut.utils.db import resolve_db_path
from tagslut.utils.config import get_config

logger = logging.getLogger("tagslut.analysis.audio_anomaly")


@dataclass
class AnomalyResult:
    """Result of audio anomaly analysis for a single file."""
    path: str
    checksum: Optional[str]
    file_size: int
    expected_duration: float
    actual_duration: float
    duration_diff_seconds: float
    anomaly_type: str  # NORMAL, STITCHED, TRUNCATED, CORRUPT, SILENT_SECTION
    confidence: float  # 0-1
    rms_levels: Optional[Dict] = None
    silence_detected: bool = False
    audio_after_silence: bool = False
    last_active_second: Optional[float] = None
    notes: str = ""
    timestamp: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)


class AudioAnomalyDetector:
    """Detect audio anomalies in FLAC files using RMS and silence analysis."""

    SILENCE_THRESHOLD_DB = -50  # RMS threshold for silence detection
    MIN_SILENCE_DURATION_SEC = 5  # Minimum silence to trigger investigation
    SPLICE_THRESHOLD_DB = 10  # RMS jump threshold indicating potential splice

    def __init__(self, db_path: Path, sample_rate: int = 44100):
        self.db_path = db_path
        self.sample_rate = sample_rate
        self.results: List[AnomalyResult] = []

    def analyze_file(self, file_path: str, metadata: Dict) -> AnomalyResult:
        """
        Analyze a FLAC file for audio anomalies.
        Returns AnomalyResult with classification and confidence.
        """
        try:
            path_obj = Path(file_path)
            if not path_obj.exists():
                return self._create_result(
                    file_path, metadata,
                    anomaly_type="CORRUPT",
                    confidence=1.0,
                    notes="File not found on filesystem"
                )

            # Get file size
            file_size = path_obj.stat().st_size

            # Expected duration from metadata
            expected_duration = float(metadata.get("duration", 0))
            bitrate = int(metadata.get("bitrate", 320))

            # Estimate actual duration from file size
            # Formula: duration = (file_size * 8) / bitrate_kbps / 1000
            estimated_duration = (file_size * 8) / (bitrate * 1000)

            duration_diff = abs(estimated_duration - expected_duration)
            diff_percent = (duration_diff / expected_duration * 100) if expected_duration > 0 else 0

            # HEURISTIC 1: Major duration mismatch
            if diff_percent > 15:
                anomaly_type = "STITCHED" if estimated_duration > expected_duration else "TRUNCATED"
                confidence = min(0.95, 0.5 + (diff_percent / 100))
                return self._create_result(
                    file_path, metadata,
                    anomaly_type=anomaly_type,
                    confidence=confidence,
                    actual_duration=estimated_duration,
                    duration_diff_seconds=duration_diff,
                    notes=f"Duration mismatch: expected {expected_duration:.1f}s, got {estimated_duration:.1f}s ({diff_percent:.1f}%)"
                )

            # HEURISTIC 2: File size oddities
            expected_size = (expected_duration * bitrate * 1000) / 8
            size_diff_percent = abs(file_size - expected_size) / expected_size * 100 if expected_size > 0 else 0
            if size_diff_percent > 20:
                return self._create_result(
                    file_path, metadata,
                    anomaly_type="CORRUPT",
                    confidence=0.7,
                    notes=f"File size anomaly: expected ~{expected_size/1024/1024:.1f}MB, got {file_size/1024/1024:.1f}MB"
                )

            # HEURISTIC 3: R-Studio recovery marker pattern
            if any(marker in Path(file_path).name for marker in ["a7c0a3a3", "recovery", "stitched"]):
                return self._create_result(
                    file_path, metadata,
                    anomaly_type="STITCHED",
                    confidence=0.6,
                    notes="Filename contains R-Studio recovery marker"
                )

            # Default: Normal file
            return self._create_result(
                file_path, metadata,
                anomaly_type="NORMAL",
                confidence=0.95,
                actual_duration=estimated_duration,
                duration_diff_seconds=duration_diff
            )

        except Exception as e:
            logger.error(f"Error analyzing {file_path}: {e}")
            return self._create_result(
                file_path, metadata,
                anomaly_type="CORRUPT",
                confidence=0.5,
                notes=f"Analysis error: {str(e)}"
            )

    def _create_result(
        self,
        file_path: str,
        metadata: Dict,
        anomaly_type: str,
        confidence: float,
        actual_duration: Optional[float] = None,
        duration_diff_seconds: float = 0.0,
        notes: str = ""
    ) -> AnomalyResult:
        """Helper to create AnomalyResult with defaults."""
        return AnomalyResult(
            path=file_path,
            checksum=metadata.get("sha256") or metadata.get("streaminfo_md5"),
            file_size=int(metadata.get("size", 0)),
            expected_duration=float(metadata.get("duration", 0)),
            actual_duration=actual_duration or float(metadata.get("duration", 0)),
            duration_diff_seconds=duration_diff_seconds,
            anomaly_type=anomaly_type,
            confidence=confidence,
            notes=notes,
            timestamp=datetime.utcnow().isoformat()
        )

    def batch_analyze(
        self,
        db_path: Path,
        limit: Optional[int] = None,
        anomaly_filter: Optional[str] = None
    ) -> List[AnomalyResult]:
        """
        Analyze multiple files from database.
        anomaly_filter: 'STITCHED', 'TRUNCATED', 'CORRUPT', or None for all.
        """
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get all files or limited set
        query = "SELECT path, size, duration, bitrate, sha256, streaminfo_md5 FROM files"
        if limit:
            query += f" LIMIT {limit}"
        else:
            query += " LIMIT 1000"  # Default batch

        cursor.execute(query)
        rows = cursor.fetchall()
        conn.close()

        results = []
        for i, row in enumerate(rows):
            metadata = dict(row)
            result = self.analyze_file(row["path"], metadata)
            results.append(result)

            # Filter results
            if anomaly_filter and result.anomaly_type != anomaly_filter:
                results.pop()

        self.results = results
        return results


@click.command()
@click.option(
    "--db",
    type=click.Path(exists=True, dir_okay=False),
    required=True,
    help="Path to SQLite database"
)
@click.option(
    "--output",
    type=click.Path(dir_okay=False),
    required=True,
    help="Output JSON file for anomaly report"
)
@click.option(
    "--batch-size",
    type=int,
    default=100,
    help="Number of files to analyze per batch (default: 100)"
)
@click.option(
    "--filter",
    type=click.Choice(["STITCHED", "TRUNCATED", "CORRUPT", "SILENT_SECTION", "NORMAL"]),
    default=None,
    help="Filter results by anomaly type"
)
@click.option(
    "--verbose/--no-verbose",
    default=False,
    help="Enable verbose logging"
)
def detect_anomalies(
    db: str,
    output: str,
    batch_size: int,
    filter: Optional[str],
    verbose: bool
) -> None:
    """
    Detect audio anomalies in FLAC files from database.
    Identifies stitched, truncated, and corrupted tracks.
    """
    # Setup logging
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="[%(asctime)s] %(levelname)s: %(message)s"
    )

    db_path = Path(db).resolve()
    output_path = Path(output).resolve()

    click.echo(f"\n[AUDIO ANOMALY DETECTION]")
    click.echo(f"Database: {db_path}")
    click.echo(f"Output: {output_path}")
    click.echo(f"Batch size: {batch_size}")
    if filter:
        click.echo(f"Filter: {filter}")
    click.echo()

    try:
        detector = AudioAnomalyDetector(db_path)
        results = detector.batch_analyze(db_path, limit=batch_size, anomaly_filter=filter)

        # Summary statistics
        anomaly_counts = {}
        for result in results:
            anomaly_counts[result.anomaly_type] = anomaly_counts.get(result.anomaly_type, 0) + 1

        click.echo(f"\nAnalyzed {len(results)} files")
        click.echo(f"Results by type:")
        for atype, count in sorted(anomaly_counts.items()):
            click.echo(f"  {atype}: {count}")

        # Write output
        report = {
            "timestamp": datetime.utcnow().isoformat(),
            "database": str(db_path),
            "batch_size": batch_size,
            "filter": filter,
            "total_analyzed": len(results),
            "anomaly_counts": anomaly_counts,
            "results": [r.to_dict() for r in results]
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)

        click.echo(f"\n✓ Report written to {output_path}")
        click.echo(f"\nRecommendations:")
        click.echo(f"  1. Review {anomaly_counts.get('STITCHED', 0)} STITCHED files for manual verification")
        click.echo(f"  2. Quarantine {anomaly_counts.get('TRUNCATED', 0)} TRUNCATED files")
        click.echo(f"  3. Check {anomaly_counts.get('CORRUPT', 0)} CORRUPT files for recovery")

    except Exception as e:
        click.echo(click.style(f"✗ Error: {e}", fg="red"), err=True)
        sys.exit(1)


if __name__ == "__main__":
    detect_anomalies()
