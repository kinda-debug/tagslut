"""Pytest configuration and test fixtures for tagslut test suite.

This module provides comprehensive test fixtures for:
- FLAC file variations (healthy, corrupted, truncated, stitched)
- Mutagen metadata type variations (int vs str, bytes vs hex)
- Mock file objects and database fixtures
- Progress tracking and IO monitoring fixtures
- Integration test helpers
"""

from __future__ import annotations

import base64
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, Generator, List
from unittest.mock import MagicMock, Mock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURE_DIR = ROOT / "tests" / "data"

# FLAC Header Fixtures (base64 encoded valid FLAC headers)
HEALTHY_FLAC_B64 = (
    "ZkxhQwAAACIQABAAAAALAAALAfQAcAAAAIBQrUjBixKWAtMFoSiyRdNEhAAAKCAAAAByZWZlcmVu"
    "Y2UgbGliRkxBQyAxLjQuMyAyMDIzMDYyMwAAAAD/+GQCAH8eAQO52w=="
)

# Corrupted FLAC (bad header)
CORRUPT_FLAC_B64 = "Tm90RkxBQ0hlYWRlcg=="

# Truncated FLAC (incomplete)
TRUNCATED_FLAC_B64 = "ZkxhQwAA"


def _ensure_fixture_files() -> None:
    """Create test fixture FLAC files if they don't exist."""
    FIXTURE_DIR.mkdir(exist_ok=True)
    
    # Healthy FLAC
    healthy = FIXTURE_DIR / "healthy.flac"
    if not healthy.exists():
        healthy.write_bytes(base64.b64decode(HEALTHY_FLAC_B64))
    
    # Corrupted FLAC
    corrupt = FIXTURE_DIR / "corrupt.flac"
    if not corrupt.exists():
        corrupt.write_bytes(base64.b64decode(CORRUPT_FLAC_B64))
    
    # Truncated FLAC
    truncated = FIXTURE_DIR / "truncated.flac"
    if not truncated.exists():
        truncated.write_bytes(base64.b64decode(TRUNCATED_FLAC_B64))


def pytest_configure(config: Any) -> None:
    """Initialize pytest configuration and fixtures."""
    _ensure_fixture_files()
    # Register custom markers
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )


@pytest.fixture
def fixture_dir() -> Path:
    """Return path to test fixture directory."""
    return FIXTURE_DIR


@pytest.fixture
def healthy_flac_path(fixture_dir: Path) -> Path:
    """Return path to healthy FLAC test file."""
    return fixture_dir / "healthy.flac"


@pytest.fixture
def corrupt_flac_path(fixture_dir: Path) -> Path:
    """Return path to corrupted FLAC test file."""
    return fixture_dir / "corrupt.flac"


@pytest.fixture
def truncated_flac_path(fixture_dir: Path) -> Path:
    """Return path to truncated FLAC test file."""
    return fixture_dir / "truncated.flac"


@pytest.fixture
def mutagen_metadata_int() -> Dict[str, Any]:
    """Mock mutagen metadata with int values (known issue #71)."""
    return {
        "streaminfo_md5": 123456789,  # int instead of str
        "duration_ms": 180000,  # int milliseconds
        "bitrate_kbps": 320,
    }


@pytest.fixture
def mutagen_metadata_str() -> Dict[str, Any]:
    """Mock mutagen metadata with proper str values."""
    return {
        "streaminfo_md5": "7a1b2c3d4e5f6g7h8i9j0k",  # hex string
        "duration_ms": 180000,
        "bitrate_kbps": 320,
    }


@pytest.fixture
def mutagen_metadata_bytes() -> Dict[str, Any]:
    """Mock mutagen metadata with bytes values."""
    return {
        "streaminfo_md5": b"7a1b2c3d4e5f6g7h8i9j0k",  # bytes instead of str
        "duration_ms": 180000,
    }


@pytest.fixture
def confidence_scores() -> Dict[str, float]:
    """Fixture providing confidence score examples."""
    return {
        "high_confidence": 0.95,
        "medium_confidence": 0.75,
        "low_confidence": 0.55,
        "very_low_confidence": 0.35,
    }


@pytest.fixture
def mock_file_record() -> Dict[str, Any]:
    """Create a mock file record for testing."""
    return {
        "file_id": "file_1",
        "path": "/music/Artist/Album/01_track.flac",
        "size_bytes": 50000000,
        "md5": "abc123def456",
        "sha256": "0a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p",
        "streaminfo_md5": "7a1b2c3d4e5f6g7h8i9j0k",
        "duration_ms": 180000,
        "bitrate_kbps": 320,
        "integrity_state": "ok",
        "flac_ok": True,
        "zone": "primary",
        "decision": "KEEP",
        "confidence": 0.95,
    }


@pytest.fixture
def mock_duplicate_pair() -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Create a pair of duplicate file records for testing."""
    file1 = {
        "file_id": "file_1",
        "path": "/music/Artist/Album/01_track.flac",
        "size_bytes": 50000000,
        "md5": "abc123def456",
        "sha256": "0a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p",
        "streaminfo_md5": "7a1b2c3d4e5f6g7h8i9j0k",
        "zone": "primary",
        "integrity_state": "ok",
        "flac_ok": True,
    }
    
    file2 = {
        "file_id": "file_2",
        "path": "/backup/Artist/Album/01_track.flac",
        "size_bytes": 50000000,
        "md5": "abc123def456",  # Same hash
        "sha256": "0a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p",  # Same hash
        "streaminfo_md5": "7a1b2c3d4e5f6g7h8i9j0k",
        "zone": "backup",
        "integrity_state": "ok",
        "flac_ok": True,
    }
    
    return (file1, file2)


@pytest.fixture
def mock_anomalous_file() -> Dict[str, Any]:
    """Create a mock anomalous file record for testing audio anomaly detection."""
    return {
        "file_id": "anomaly_1",
        "path": "/music/recovered/stitched_track.flac",
        "size_bytes": 100000000,  # Larger than expected
        "duration_ms": 180000,  # Normal duration
        "streaminfo_md5": "corrupted_hash_value",
        "integrity_state": "anomaly",
        "flac_ok": False,
        "anomaly_type": "stitched_audio",  # Multiple tracks appended
    }


@pytest.fixture
def mock_progress_tracker() -> Mock:
    """Create a mock progress tracker for testing."""
    tracker = Mock()
    tracker.start = Mock()
    tracker.update = Mock()
    tracker.stop = Mock()
    tracker.get_eta = Mock(return_value="0:05:30")
    tracker.get_throughput = Mock(return_value=100.5)  # MB/s
    return tracker


@pytest.fixture
def mock_io_monitor() -> Mock:
    """Create a mock IO monitor for testing."""
    monitor = Mock()
    monitor.check_mount_state = Mock(return_value=True)
    monitor.detect_io_stall = Mock(return_value=False)
    monitor.get_volume_info = Mock(return_value={
        "mount_path": "/Volumes/Music",
        "free_space": 500000000000,
        "total_space": 1000000000000,
    })
    return monitor


@pytest.fixture
def mock_schema_validator() -> Mock:
    """Create a mock schema validator for testing."""
    validator = Mock()
    validator.validate_metadata = Mock(return_value=True)
    validator.coerce_types = Mock(side_effect=lambda x: x)
    return validator


@pytest.fixture
def mock_confidence_scorer() -> Mock:
    """Create a mock confidence scorer for testing."""
    scorer = Mock()
    scorer.score_decision = Mock(return_value=0.85)
    scorer.identify_low_confidence = Mock(return_value=[])
    return scorer


@pytest.fixture
def mock_validation_sampler() -> Mock:
    """Create a mock validation sampler for testing."""
    sampler = Mock()
    sampler.stratified_sample = Mock(return_value=[])
    sampler.get_sample_size = Mock(return_value=10)
    return sampler


@pytest.fixture
def mock_database() -> sqlite3.Connection:
    """Create an in-memory SQLite database for testing."""
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    
    # Create minimal schema for testing
    cursor = db.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS files (
            file_id TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            size_bytes INTEGER,
            md5 TEXT,
            sha256 TEXT,
            streaminfo_md5 TEXT,
            duration_ms INTEGER,
            integrity_state TEXT,
            zone TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS decisions (
            file_id TEXT PRIMARY KEY,
            decision TEXT,
            confidence REAL,
            FOREIGN KEY(file_id) REFERENCES files(file_id)
        )
    """)
    db.commit()
    return db


@pytest.fixture
def populated_database(mock_database: sqlite3.Connection) -> sqlite3.Connection:
    """Create a database pre-populated with test data."""
    cursor = mock_database.cursor()
    cursor.execute("""
        INSERT INTO files VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "file_1", "/music/track1.flac", 50000000, "hash1", "sha1",
        "stream1", 180000, "ok", "primary"
    ))
    cursor.execute("""
        INSERT INTO files VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "file_2", "/backup/track1.flac", 50000000, "hash1", "sha1",
        "stream1", 180000, "ok", "backup"
    ))
    mock_database.commit()
    return mock_database


@pytest.fixture
def interrupt_event() -> Generator[Any, None, None]:
    """Fixture to simulate interrupt events during long operations."""
    class InterruptSimulator:
        def __init__(self) -> None:
            self.interrupt_count = 0
            self.max_interrupts = 1
        
        def should_interrupt(self) -> bool:
            self.interrupt_count += 1
            return self.interrupt_count > self.max_interrupts
    
    yield InterruptSimulator()
