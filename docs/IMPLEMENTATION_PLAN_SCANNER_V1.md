# Implementation Plan: Scanner v1 (Phases 1–7)

> **For AI coding agents (Codex, Copilot, Claude Code):**
> This document is the single source of truth for the scanner implementation.
> Read `docs/SCANNER_V1.md`, `REPORT.md`, and `.claude/AGENTS.md` before starting.
> Implement one phase at a time. Run `poetry run pytest` after each phase.
> Append a progress entry to `docs/SCANNER_V1_PROGRESS.md` after each phase using the template there.
> Do not proceed to the next phase until the evaluator approves.

---

## Constraints (Non-Negotiable)

1. Scanner is **read-only** — never modify, move, delete, or retag source files.
2. All DB changes are **additive** — no drops, renames, or destructive migrations.
3. Every new module must have a corresponding test file.
4. Tests must **not** require `ffmpeg` or `ffprobe` installed — mock `shutil.which` and `subprocess.run`.
5. All paths use `pathlib.Path` — never string concatenation.
6. No new third-party dependencies beyond what is already in `pyproject.toml`.
7. First-run scan accepts **no user input** — instrumentation only.

---

## Existing Code to Read First

| File | Why |
|---|---|
| `tagslut/storage/schema.py` | Understand `_add_missing_columns`, `init_db` pattern |
| `tagslut/storage/models.py` | Existing dataclass style to follow |
| `tagslut/core/quality.py` | `compute_quality_rank` — reuse in Phase 3 |
| `tests/conftest.py` | Available fixtures |
| `pyproject.toml` | Existing deps |

---

## Phase 1 — Schema & Models

**Goal:** Add all scan-related tables, indices, and model dataclasses. No logic yet.
**Branch:** `feature/scanner-schema`
**Estimated LOC:** ~180

### 1.1 — Add `_ensure_scan_tables(conn)` to `tagslut/storage/schema.py`

Call it from `init_db()` just before `connection.commit()`.

```python
def _ensure_scan_tables(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scan_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            library_root TEXT NOT NULL,
            mode TEXT NOT NULL DEFAULT 'initial',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT,
            tool_versions_json TEXT
        );
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scan_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            path TEXT NOT NULL,
            size_bytes INTEGER,
            mtime_ns INTEGER,
            stage INTEGER DEFAULT 0,
            state TEXT DEFAULT 'PENDING',
            last_error TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(run_id) REFERENCES scan_runs(id)
        );
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scan_issues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            path TEXT NOT NULL,
            checksum TEXT,
            issue_code TEXT NOT NULL,
            severity TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(run_id) REFERENCES scan_runs(id)
        );
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS file_metadata_archive (
            checksum TEXT PRIMARY KEY,
            first_seen_at TEXT NOT NULL,
            first_seen_path TEXT NOT NULL,
            raw_tags_json TEXT NOT NULL,
            technical_json TEXT NOT NULL,
            durations_json TEXT NOT NULL,
            isrc_candidates_json TEXT NOT NULL,
            fingerprint_json TEXT,
            identity_confidence INTEGER NOT NULL,
            quality_rank INTEGER
        );
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS file_path_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            checksum TEXT NOT NULL,
            path TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL
        );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_queue_run_state ON scan_queue(run_id, state);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_queue_stage ON scan_queue(stage);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_issues_code ON scan_issues(issue_code);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_archive_confidence ON file_metadata_archive(identity_confidence);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_path_history_checksum ON file_path_history(checksum);")

    _add_missing_columns(conn, "files", {
        "scan_status": "TEXT",
        "scan_flags_json": "TEXT",
        "actual_duration": "REAL",
        "duration_delta": "REAL",
        "identity_confidence": "INTEGER",
        "isrc_candidates_json": "TEXT",
        "duplicate_of_checksum": "TEXT",
        "last_scanned_at": "TEXT",
        "scan_stage_reached": "INTEGER",
    })
```

### 1.2 — Append dataclasses to `tagslut/storage/models.py`

```python
@dataclass
class ScanRun:
    library_root: Path
    mode: str = "initial"
    id: Optional[int] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    tool_versions_json: Optional[str] = None

    def __post_init__(self) -> None:
        if isinstance(self.library_root, str):
            self.library_root = Path(self.library_root)


@dataclass
class ScanQueueItem:
    run_id: int
    path: Path
    id: Optional[int] = None
    size_bytes: Optional[int] = None
    mtime_ns: Optional[int] = None
    stage: int = 0
    state: str = "PENDING"
    last_error: Optional[str] = None
    updated_at: Optional[str] = None

    def __post_init__(self) -> None:
        if isinstance(self.path, str):
            self.path = Path(self.path)


@dataclass
class ScanIssue:
    run_id: int
    path: Path
    issue_code: str
    severity: str
    evidence_json: str
    id: Optional[int] = None
    checksum: Optional[str] = None
    created_at: Optional[str] = None

    def __post_init__(self) -> None:
        if isinstance(self.path, str):
            self.path = Path(self.path)


@dataclass
class FileMetadataArchive:
    checksum: str
    first_seen_at: str
    first_seen_path: Path
    raw_tags_json: str
    technical_json: str
    durations_json: str
    isrc_candidates_json: str
    identity_confidence: int
    fingerprint_json: Optional[str] = None
    quality_rank: Optional[int] = None

    def __post_init__(self) -> None:
        if isinstance(self.first_seen_path, str):
            self.first_seen_path = Path(self.first_seen_path)
```

### 1.3 — Create `tests/storage/test_scan_schema.py`

```python
import sqlite3
import pytest
from pathlib import Path
from tagslut.storage.schema import init_db
from tagslut.storage.models import ScanRun, ScanQueueItem, ScanIssue, FileMetadataArchive


@pytest.fixture
def mem_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()


def _table_columns(conn, table: str) -> set:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def test_scan_runs_table_exists(mem_db):
    cols = _table_columns(mem_db, "scan_runs")
    assert "library_root" in cols
    assert "mode" in cols
    assert "completed_at" in cols


def test_scan_queue_table_exists(mem_db):
    cols = _table_columns(mem_db, "scan_queue")
    assert "run_id" in cols
    assert "state" in cols
    assert "stage" in cols
    assert "last_error" in cols


def test_scan_issues_table_exists(mem_db):
    cols = _table_columns(mem_db, "scan_issues")
    assert "issue_code" in cols
    assert "severity" in cols
    assert "evidence_json" in cols


def test_file_metadata_archive_table_exists(mem_db):
    cols = _table_columns(mem_db, "file_metadata_archive")
    assert "checksum" in cols
    assert "raw_tags_json" in cols
    assert "isrc_candidates_json" in cols
    assert "identity_confidence" in cols


def test_file_path_history_table_exists(mem_db):
    cols = _table_columns(mem_db, "file_path_history")
    assert "checksum" in cols
    assert "path" in cols
    assert "first_seen_at" in cols


def test_files_table_has_scan_columns(mem_db):
    cols = _table_columns(mem_db, "files")
    for col in [
        "scan_status", "scan_flags_json", "actual_duration",
        "duration_delta", "identity_confidence", "isrc_candidates_json",
        "duplicate_of_checksum", "last_scanned_at", "scan_stage_reached",
    ]:
        assert col in cols, f"Missing column: {col}"


def test_init_db_is_idempotent(mem_db):
    init_db(mem_db)
    init_db(mem_db)


def test_scan_queue_item_path_coercion():
    item = ScanQueueItem(run_id=1, path="/music/track.flac")
    assert isinstance(item.path, Path)


def test_file_metadata_archive_path_coercion():
    a = FileMetadataArchive(
        checksum="abc123",
        first_seen_at="2026-01-01",
        first_seen_path="/music/track.flac",
        raw_tags_json="{}",
        technical_json="{}",
        durations_json="{}",
        isrc_candidates_json="[]",
        identity_confidence=80,
    )
    assert isinstance(a.first_seen_path, Path)
```

### Phase 1 Acceptance Checklist
- [ ] `poetry run pytest tests/storage/test_scan_schema.py -v` — green
- [ ] `poetry run pytest -v` (full suite) — green
- [ ] Progress entry appended to `docs/SCANNER_V1_PROGRESS.md`
- [ ] Phase 1 checkbox in status dashboard flipped to ☑

---

## Phase 2 — ISRC Candidate Extraction

**Goal:** Robust normalization of 0-to-N ISRC values from arbitrary tag inputs.
**Branch:** `feature/scanner-isrc`
**Depends on:** nothing
**Estimated LOC:** ~50

### 2.1 — Create `tagslut/scan/isrc.py`

```python
"""
ISRC candidate extraction and normalization.

Design decisions:
- Multiple ISRCs in one tag value are all extracted.
- Invalid/garbage values are silently dropped.
- Results are deduplicated preserving first-seen order.
- This module does NOT set a canonical ISRC — that requires confidence gating.
"""
import re
from typing import Iterable, List

# 12-char compact form: 2-letter country + 3-char registrant + 7 digits
_ISRC_RE = re.compile(r"\b([A-Z]{2}[A-Z0-9]{3}[0-9]{7})\b")


def normalize_isrc(value: str) -> str:
    """Strip dashes, spaces, uppercase. Does not validate format."""
    return value.upper().replace("-", "").replace(" ", "")


def extract_isrc_candidates(values: Iterable[str]) -> List[str]:
    """
    Extract all valid ISRC candidates from an iterable of strings.

    Handles:
    - Multi-valued tag lists (each value is a separate string)
    - Single string containing multiple ISRCs
    - Strings with dashes or spaces in the ISRC
    - Garbage (ignored silently)

    Returns unique candidates in first-seen order.
    """
    out: List[str] = []
    seen: set = set()
    for v in values:
        if not v:
            continue
        # Normalize before matching
        norm = v.upper().replace("-", " ").replace("/", " ")
        for m in _ISRC_RE.finditer(norm):
            cand = m.group(1)
            if cand not in seen:
                seen.add(cand)
                out.append(cand)
    return out
```

### 2.2 — Create `tests/scan/test_isrc.py`

```python
import pytest
from tagslut.scan.isrc import extract_isrc_candidates


def test_single_isrc():
    assert extract_isrc_candidates(["USABC1234567"]) == ["USABC1234567"]


def test_isrc_with_dashes():
    assert extract_isrc_candidates(["US-ABC-12-34567"]) == ["USABC1234567"]


def test_multiple_values():
    result = extract_isrc_candidates(["USABC1234567", "GBXYZ9876543"])
    assert result == ["USABC1234567", "GBXYZ9876543"]


def test_multiple_isrc_in_one_string():
    result = extract_isrc_candidates(["USABC1234567 GBXYZ9876543"])
    assert len(result) == 2
    assert "USABC1234567" in result
    assert "GBXYZ9876543" in result


def test_garbage_ignored():
    result = extract_isrc_candidates(["not an isrc", "", "12345", None])
    assert result == []


def test_deduplication():
    result = extract_isrc_candidates(["USABC1234567", "USABC1234567"])
    assert result == ["USABC1234567"]


def test_preserves_first_seen_order():
    result = extract_isrc_candidates(["GBXYZ9876543", "USABC1234567"])
    assert result[0] == "GBXYZ9876543"


def test_empty_input():
    assert extract_isrc_candidates([]) == []
```

### Phase 2 Acceptance Checklist
- [ ] `poetry run pytest tests/scan/test_isrc.py -v` — green
- [ ] `poetry run pytest -v` — green
- [ ] Progress entry appended to `docs/SCANNER_V1_PROGRESS.md`

---

## Phase 3 — Discovery + Tags + Checksum + Archive

**Goal:** Enumerate files, extract raw tags and technical metadata, compute checksum, write archive.
**Branch:** `feature/scanner-stage01`
**Depends on:** Phase 1, Phase 2
**Estimated LOC:** ~200

### 3.1 — Create `tagslut/scan/constants.py`

```python
SUPPORTED_EXTENSIONS = {".flac", ".mp3", ".aif", ".aiff", ".wav", ".m4a"}
DURATION_WARN_DELTA_S = 3.0
DURATION_ERROR_DELTA_S = 15.0
IDENTITY_CONFIDENCE_ISRC_SINGLE = 30
IDENTITY_CONFIDENCE_FINGERPRINT = 25
IDENTITY_CONFIDENCE_ARTIST_TITLE = 15
IDENTITY_CONFIDENCE_ALBUM_YEAR = 10
IDENTITY_CONFIDENCE_BPM_VALID = 5
IDENTITY_CONFIDENCE_KEY_VALID = 5
IDENTITY_CONFIDENCE_DURATION_OK = 10
DEDUPE_ISRC_MIN_CONFIDENCE = 70
```

### 3.2 — Create `tagslut/scan/discovery.py`

```python
"""Stage 0: filesystem discovery."""
from pathlib import Path
from typing import List
from tagslut.scan.constants import SUPPORTED_EXTENSIONS


def discover_paths(root: Path) -> List[Path]:
    """
    Recursively find all supported audio files under root.
    Skips 0-byte files. Returns sorted list for stable ordering.
    """
    found = [
        p for p in root.rglob("*")
        if p.is_file()
        and p.suffix.lower() in SUPPORTED_EXTENSIONS
        and p.stat().st_size > 0
    ]
    return sorted(found)
```

### 3.3 — Create `tagslut/scan/tags.py`

```python
"""Stage 1: raw tag extraction, technical metadata, checksum."""
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from mutagen import File as MutagenFile

from tagslut.scan.isrc import extract_isrc_candidates
from tagslut.core.quality import compute_quality_rank


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
    f = MutagenFile(path, easy=False)
    if f is None:
        raise TagReadError(f"mutagen returned None for {path}")
    result: Dict[str, List[str]] = {}
    for key, val in f.tags.items() if f.tags else []:
        if isinstance(val, list):
            result[str(key)] = [str(v) for v in val]
        else:
            result[str(key)] = [str(val)]
    return result


def read_technical(path: Path) -> Dict[str, Any]:
    """
    Return technical audio parameters from mutagen container info.
    """
    f = MutagenFile(path, easy=False)
    if f is None:
        return {}
    info = f.info
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
```

### 3.4 — Create `tagslut/scan/archive.py`

```python
"""Append-only metadata archive writer."""
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def upsert_archive(
    conn: sqlite3.Connection,
    *,
    checksum: str,
    path: Path,
    raw_tags: Dict,
    technical: Dict,
    durations: Dict,
    isrc_candidates: List[str],
    identity_confidence: int,
    quality_rank: Optional[int],
) -> None:
    """
    Insert into file_metadata_archive if checksum is new (append-only).
    Always upsert file_path_history.
    """
    import json
    now = datetime.now().isoformat()

    existing = conn.execute(
        "SELECT checksum FROM file_metadata_archive WHERE checksum = ?",
        (checksum,)
    ).fetchone()

    if existing is None:
        conn.execute("""
            INSERT INTO file_metadata_archive (
                checksum, first_seen_at, first_seen_path,
                raw_tags_json, technical_json, durations_json,
                isrc_candidates_json, identity_confidence, quality_rank
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            checksum, now, str(path),
            json.dumps(raw_tags), json.dumps(technical), json.dumps(durations),
            json.dumps(isrc_candidates), identity_confidence, quality_rank,
        ))

    # Always track path history
    history = conn.execute(
        "SELECT id FROM file_path_history WHERE checksum = ? AND path = ?",
        (checksum, str(path))
    ).fetchone()

    if history is None:
        conn.execute(
            "INSERT INTO file_path_history (checksum, path, first_seen_at, last_seen_at) VALUES (?, ?, ?, ?)",
            (checksum, str(path), now, now)
        )
    else:
        conn.execute(
            "UPDATE file_path_history SET last_seen_at = ? WHERE checksum = ? AND path = ?",
            (now, checksum, str(path))
        )
```

### 3.5 — Create `tests/scan/test_tags_and_archive.py`

```python
import sqlite3
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from tagslut.storage.schema import init_db
from tagslut.scan.tags import (
    compute_sha256, extract_isrc_from_tags, compute_quality_rank_from_technical
)
from tagslut.scan.archive import upsert_archive


@pytest.fixture
def mem_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()


def test_compute_sha256(tmp_path):
    f = tmp_path / "test.flac"
    f.write_bytes(b"hello")
    checksum = compute_sha256(f)
    assert len(checksum) == 64
    assert checksum == compute_sha256(f)  # deterministic


def test_extract_isrc_from_tags_single():
    raw = {"ISRC": ["USABC1234567"]}
    assert extract_isrc_from_tags(raw) == ["USABC1234567"]


def test_extract_isrc_from_tags_multi_value():
    raw = {"TSRC": ["USABC1234567", "GBXYZ9876543"]}
    result = extract_isrc_from_tags(raw)
    assert len(result) == 2


def test_extract_isrc_from_tags_empty():
    raw = {"TITLE": ["Some Track"], "ARTIST": ["Someone"]}
    assert extract_isrc_from_tags(raw) == []


def test_quality_rank_from_technical():
    tech = {"bit_depth": 24, "sample_rate": 96000, "bitrate": 0}
    assert compute_quality_rank_from_technical(tech) == 2


def test_archive_is_append_only(mem_db, tmp_path):
    path = tmp_path / "track.flac"
    path.write_bytes(b"data")
    original_tags = {"TITLE": ["Original"]}

    upsert_archive(
        mem_db, checksum="abc123", path=path,
        raw_tags=original_tags, technical={}, durations={},
        isrc_candidates=[], identity_confidence=70, quality_rank=4,
    )
    # Second call with different tags — must NOT overwrite
    upsert_archive(
        mem_db, checksum="abc123", path=path,
        raw_tags={"TITLE": ["Modified"]}, technical={}, durations={},
        isrc_candidates=[], identity_confidence=70, quality_rank=4,
    )
    row = mem_db.execute(
        "SELECT raw_tags_json FROM file_metadata_archive WHERE checksum = 'abc123'"
    ).fetchone()
    stored = json.loads(row["raw_tags_json"])
    assert stored["TITLE"] == ["Original"]


def test_path_history_updated_on_second_scan(mem_db, tmp_path):
    path = tmp_path / "track.flac"
    path.write_bytes(b"data")
    for _ in range(2):
        upsert_archive(
            mem_db, checksum="abc123", path=path,
            raw_tags={}, technical={}, durations={},
            isrc_candidates=[], identity_confidence=50, quality_rank=None,
        )
    rows = mem_db.execute(
        "SELECT * FROM file_path_history WHERE checksum = 'abc123'"
    ).fetchall()
    assert len(rows) == 1  # one path record, updated not duplicated
```

### Phase 3 Acceptance Checklist
- [ ] `poetry run pytest tests/scan/test_tags_and_archive.py -v` — green
- [ ] `poetry run pytest -v` — green
- [ ] Progress entry appended

---

## Phase 4 — Validation (ffprobe + edge decode)

**Goal:** Detect truncation, extension, corruption via fast probes. Store evidence.
**Branch:** `feature/scanner-validation`
**Depends on:** Phase 1
**Estimated LOC:** ~150

### 4.1 — Create `tagslut/scan/issues.py`

```python
"""Issue codes, severities, and DB writer."""
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional


class IssueCodes:
    TAGS_UNREADABLE = "TAGS_UNREADABLE"
    CORRUPT_DECODE = "CORRUPT_DECODE"
    DURATION_MISMATCH = "DURATION_MISMATCH"
    MULTI_ISRC = "MULTI_ISRC"
    ISRC_MISSING = "ISRC_MISSING"
    DURATION_UNVERIFIED = "DURATION_UNVERIFIED"
    DECODE_UNVERIFIED = "DECODE_UNVERIFIED"


class Severity:
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


def record_issue(
    conn: sqlite3.Connection,
    run_id: int,
    path: Path,
    code: str,
    severity: str,
    evidence: dict,
    checksum: Optional[str] = None,
) -> None:
    conn.execute("""
        INSERT INTO scan_issues (run_id, path, checksum, issue_code, severity, evidence_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (run_id, str(path), checksum, code, severity, json.dumps(evidence), datetime.now().isoformat()))
```

### 4.2 — Create `tagslut/scan/validate.py`

```python
"""
Stage 2: fast audio probes via ffprobe and ffmpeg.
Never modifies source files.
"""
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional
import logging

logger = logging.getLogger("tagslut.scan.validate")

EDGE_PROBE_SECONDS = 10.0


def probe_duration_ffprobe(path: Path) -> Optional[float]:
    """
    Measure actual audio duration via ffprobe.
    Returns None if ffprobe is unavailable or fails.
    """
    if shutil.which("ffprobe") is None:
        return None
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def decode_probe_edges(path: Path, duration: Optional[float] = None) -> List[str]:
    """
    Run ffmpeg error-only decode probe on first and last EDGE_PROBE_SECONDS.
    Returns list of error lines (empty = no errors detected).
    Returns [] without running if ffmpeg is not installed.
    """
    if shutil.which("ffmpeg") is None:
        return []

    errors: List[str] = []

    # Probe start
    cmd_start = [
        "ffmpeg", "-v", "error",
        "-ss", "0", "-t", str(EDGE_PROBE_SECONDS),
        "-i", str(path),
        "-f", "null", "-",
    ]
    r = subprocess.run(cmd_start, capture_output=True, text=True)
    if r.stderr.strip():
        errors.extend(r.stderr.strip().splitlines())

    # Probe end (if we know duration)
    if duration and duration > EDGE_PROBE_SECONDS * 2:
        start_offset = duration - EDGE_PROBE_SECONDS
        cmd_end = [
            "ffmpeg", "-v", "error",
            "-ss", str(start_offset), "-t", str(EDGE_PROBE_SECONDS),
            "-i", str(path),
            "-f", "null", "-",
        ]
        r2 = subprocess.run(cmd_end, capture_output=True, text=True)
        if r2.stderr.strip():
            errors.extend(r2.stderr.strip().splitlines())

    return errors
```

### 4.3 — Create `tests/scan/test_validate.py`

```python
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from tagslut.scan.validate import probe_duration_ffprobe, decode_probe_edges


def test_probe_duration_returns_none_when_ffprobe_missing(tmp_path):
    f = tmp_path / "track.flac"
    f.write_bytes(b"fake")
    with patch("shutil.which", return_value=None):
        assert probe_duration_ffprobe(f) is None


def test_probe_duration_returns_float(tmp_path):
    f = tmp_path / "track.flac"
    f.write_bytes(b"fake")
    mock = MagicMock(returncode=0, stdout="245.3\n", stderr="")
    with patch("shutil.which", return_value="/usr/bin/ffprobe"), \
         patch("subprocess.run", return_value=mock):
        result = probe_duration_ffprobe(f)
    assert result == pytest.approx(245.3)


def test_probe_duration_returns_none_on_error(tmp_path):
    f = tmp_path / "track.flac"
    f.write_bytes(b"fake")
    mock = MagicMock(returncode=1, stdout="", stderr="error")
    with patch("shutil.which", return_value="/usr/bin/ffprobe"), \
         patch("subprocess.run", return_value=mock):
        assert probe_duration_ffprobe(f) is None


def test_decode_probe_returns_empty_when_ffmpeg_missing(tmp_path):
    f = tmp_path / "track.flac"
    f.write_bytes(b"fake")
    with patch("shutil.which", return_value=None):
        assert decode_probe_edges(f) == []


def test_decode_probe_returns_errors(tmp_path):
    f = tmp_path / "track.flac"
    f.write_bytes(b"fake")
    mock_ok = MagicMock(returncode=0, stderr="")
    mock_err = MagicMock(returncode=0, stderr="Invalid data found")
    with patch("shutil.which", return_value="/usr/bin/ffmpeg"), \
         patch("subprocess.run", side_effect=[mock_err, mock_ok]):
        errors = decode_probe_edges(f, duration=300.0)
    assert len(errors) >= 1
    assert "Invalid data found" in errors[0]


def test_decode_probe_empty_on_clean_file(tmp_path):
    f = tmp_path / "track.flac"
    f.write_bytes(b"fake")
    mock_clean = MagicMock(returncode=0, stderr="")
    with patch("shutil.which", return_value="/usr/bin/ffmpeg"), \
         patch("subprocess.run", return_value=mock_clean):
        assert decode_probe_edges(f, duration=300.0) == []
```

### Phase 4 Acceptance Checklist
- [ ] `poetry run pytest tests/scan/test_validate.py -v` — green
- [ ] `poetry run pytest -v` — green
- [ ] Progress entry appended

---

## Phase 5 — Classification + Dedupe Election

**Goal:** Derive identity confidence, primary status, and elect canonical copies. No deletion.
**Branch:** `feature/scanner-classify`
**Depends on:** Phase 1, Phase 2, Phase 3, Phase 4
**Estimated LOC:** ~150

### 5.1 — Create `tagslut/scan/classify.py`

```python
"""
Identity confidence scoring and primary status classification.
Instrumentation-only — no user input.
"""
from typing import Any, Dict, List, Optional, Tuple

from tagslut.scan.constants import (
    DURATION_ERROR_DELTA_S, DURATION_WARN_DELTA_S,
    IDENTITY_CONFIDENCE_ISRC_SINGLE, IDENTITY_CONFIDENCE_FINGERPRINT,
    IDENTITY_CONFIDENCE_ARTIST_TITLE, IDENTITY_CONFIDENCE_ALBUM_YEAR,
    IDENTITY_CONFIDENCE_BPM_VALID, IDENTITY_CONFIDENCE_KEY_VALID,
    IDENTITY_CONFIDENCE_DURATION_OK,
)


def compute_identity_confidence(
    raw_tags: Dict[str, List[str]],
    isrc_candidates: List[str],
    duration_delta: Optional[float],
    has_fingerprint: bool = False,
) -> int:
    """
    Score 0-100. Purely from measured signals — no user input.
    """
    score = 0

    # ISRC signal
    if len(isrc_candidates) == 1:
        score += IDENTITY_CONFIDENCE_ISRC_SINGLE
    # Multi-ISRC: no bonus (ambiguous)

    # Fingerprint
    if has_fingerprint:
        score += IDENTITY_CONFIDENCE_FINGERPRINT

    # Artist + title
    def _has(keys):
        return any(
            any(v.strip() for v in raw_tags.get(k, []))
            for k in keys
        )

    if _has(["ARTIST", "TPE1", "artist", "albumartist"]) and \
       _has(["TITLE", "TIT2", "title"]):
        score += IDENTITY_CONFIDENCE_ARTIST_TITLE

    if _has(["ALBUM", "TALB", "album"]) and _has(["DATE", "TDRC", "year", "date"]):
        score += IDENTITY_CONFIDENCE_ALBUM_YEAR

    # BPM valid range
    for key in ["BPM", "TBPM", "bpm"]:
        vals = raw_tags.get(key, [])
        for v in vals:
            try:
                bpm = float(v)
                if 60 <= bpm <= 220:
                    score += IDENTITY_CONFIDENCE_BPM_VALID
                    break
            except (ValueError, TypeError):
                pass

    # Key present
    if _has(["INITIALKEY", "TKEY", "initialkey", "key"]):
        score += IDENTITY_CONFIDENCE_KEY_VALID

    # Duration coherent
    if duration_delta is not None and abs(duration_delta) < DURATION_WARN_DELTA_S:
        score += IDENTITY_CONFIDENCE_DURATION_OK

    return min(score, 100)


def classify_primary_status(
    has_tags_error: bool,
    decode_errors: List[str],
    duration_delta: Optional[float],
) -> Tuple[str, List[str]]:
    """
    Return (scan_status, flags[]).
    """
    flags: List[str] = []

    if has_tags_error or decode_errors:
        return "CORRUPT", flags

    if duration_delta is not None:
        if duration_delta < -DURATION_ERROR_DELTA_S:
            return "TRUNCATED", flags
        if duration_delta > DURATION_ERROR_DELTA_S:
            return "EXTENDED", flags
        if abs(duration_delta) > DURATION_WARN_DELTA_S:
            flags.append("DURATION_MISMATCH_WARN")

    return "CLEAN", flags
```

### 5.2 — Create `tagslut/scan/dedupe.py`

```python
"""
Canonical copy election. No deletion.
Election criteria (in order): quality_rank ASC, identity_confidence DESC, size_bytes DESC.
"""
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from tagslut.scan.constants import DEDUPE_ISRC_MIN_CONFIDENCE


@dataclass
class FileCandidate:
    path: Path
    checksum: str
    quality_rank: Optional[int]
    identity_confidence: int
    size_bytes: int


def elect_canonical(candidates: List[FileCandidate]) -> str:
    """Return the checksum of the elected canonical copy."""
    def sort_key(c: FileCandidate):
        rank = c.quality_rank if c.quality_rank is not None else 999
        return (rank, -c.identity_confidence, -c.size_bytes)
    return sorted(candidates, key=sort_key)[0].checksum


def find_exact_duplicates(conn: sqlite3.Connection, checksum: str) -> List[str]:
    """Return paths of all other files with the same checksum."""
    rows = conn.execute(
        "SELECT path FROM files WHERE checksum = ?", (checksum,)
    ).fetchall()
    return [row[0] for row in rows]


def mark_format_duplicates(conn: sqlite3.Connection) -> int:
    """
    For each group of files sharing a single canonical_isrc (with confidence >= threshold),
    elect a canonical and mark the rest as FORMAT_DUPLICATE.
    Returns count of files marked.
    """
    marked = 0
    rows = conn.execute("""
        SELECT canonical_isrc, COUNT(*) as cnt
        FROM files
        WHERE canonical_isrc IS NOT NULL
          AND identity_confidence >= ?
          AND scan_status != 'CORRUPT'
        GROUP BY canonical_isrc
        HAVING cnt > 1
    """, (DEDUPE_ISRC_MIN_CONFIDENCE,)).fetchall()

    for row in rows:
        isrc = row[0]
        group = conn.execute("""
            SELECT path, checksum, quality_rank, identity_confidence, size_bytes
            FROM files
            WHERE canonical_isrc = ? AND identity_confidence >= ?
        """, (isrc, DEDUPE_ISRC_MIN_CONFIDENCE)).fetchall()

        candidates = [
            FileCandidate(
                path=Path(r[0]), checksum=r[1],
                quality_rank=r[2], identity_confidence=r[3], size_bytes=r[4] or 0,
            )
            for r in group
        ]
        canonical_checksum = elect_canonical(candidates)

        for c in candidates:
            if c.checksum != canonical_checksum:
                conn.execute("""
                    UPDATE files
                    SET scan_status = 'FORMAT_DUPLICATE', duplicate_of_checksum = ?
                    WHERE checksum = ?
                """, (canonical_checksum, c.checksum))
                marked += 1

    return marked
```

### 5.3 — Create `tests/scan/test_classify_and_dedupe.py`

```python
import sqlite3
import pytest
from pathlib import Path
from tagslut.storage.schema import init_db
from tagslut.scan.classify import compute_identity_confidence, classify_primary_status
from tagslut.scan.dedupe import elect_canonical, mark_format_duplicates, FileCandidate


def test_confidence_full_score():
    raw = {
        "ARTIST": ["Test Artist"], "TITLE": ["Test Title"],
        "ALBUM": ["Test Album"], "DATE": ["2020"],
        "BPM": ["128"], "INITIALKEY": ["8A"],
    }
    score = compute_identity_confidence(raw, ["USABC1234567"], duration_delta=0.5)
    assert score >= 70


def test_confidence_multi_isrc_no_bonus():
    raw = {"ARTIST": ["A"], "TITLE": ["T"]}
    score_single = compute_identity_confidence(raw, ["USABC1234567"], duration_delta=0.5)
    score_multi = compute_identity_confidence(raw, ["USABC1234567", "GBXYZ9876543"], duration_delta=0.5)
    assert score_single > score_multi


def test_classify_corrupt_on_decode_errors():
    status, _ = classify_primary_status(False, ["Invalid data"], None)
    assert status == "CORRUPT"


def test_classify_truncated():
    status, _ = classify_primary_status(False, [], -30.0)
    assert status == "TRUNCATED"


def test_classify_extended():
    status, _ = classify_primary_status(False, [], 60.0)
    assert status == "EXTENDED"


def test_classify_clean():
    status, flags = classify_primary_status(False, [], 0.5)
    assert status == "CLEAN"


@pytest.fixture
def db_with_duplicates(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    for i, (qr, conf) in enumerate([(4, 70), (2, 85)]):
        conn.execute("""
            INSERT INTO files (path, checksum, duration, bit_depth, sample_rate, bitrate,
                metadata_json, quality_rank, identity_confidence, canonical_isrc, size_bytes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (f"/music/track{i}.flac", f"checksum{i}", 240.0, 16, 44100, 0,
              "{}", qr, conf, "USABC1234567", 10000000 + i))
    conn.commit()
    yield conn
    conn.close()


def test_mark_format_duplicates(db_with_duplicates):
    marked = mark_format_duplicates(db_with_duplicates)
    assert marked == 1
    row = db_with_duplicates.execute(
        "SELECT scan_status, duplicate_of_checksum FROM files WHERE quality_rank = 4"
    ).fetchone()
    assert row["scan_status"] == "FORMAT_DUPLICATE"
    assert row["duplicate_of_checksum"] == "checksum1"


def test_elect_canonical_prefers_better_quality():
    candidates = [
        FileCandidate(Path("/a.flac"), "c1", quality_rank=4, identity_confidence=80, size_bytes=10),
        FileCandidate(Path("/b.flac"), "c2", quality_rank=2, identity_confidence=70, size_bytes=8),
    ]
    assert elect_canonical(candidates) == "c2"
```

### Phase 5 Acceptance Checklist
- [ ] `poetry run pytest tests/scan/test_classify_and_dedupe.py -v` — green
- [ ] `poetry run pytest -v` — green
- [ ] Progress entry appended

---

## Phase 6 — Runner (resumable, single-writer)

**Goal:** End-to-end scan runner: discovery → queue → process → classify → archive → dedupe.
**Branch:** `feature/scanner-runner`
**Depends on:** Phases 1–5
**Estimated LOC:** ~200

### 6.1 — Create `tagslut/scan/runner.py`

```python
"""
Initial scan runner. Resumable via scan_queue table.
Single DB writer to avoid SQLite lock contention.
"""
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional
import logging

logger = logging.getLogger("tagslut.scan.runner")


@dataclass
class ScanSummary:
    run_id: int
    discovered: int = 0
    processed: int = 0
    clean: int = 0
    corrupt: int = 0
    truncated: int = 0
    extended: int = 0
    format_duplicates: int = 0
    exact_duplicates: int = 0
    warnings: int = 0
    errors: List[str] = field(default_factory=list)

    def print_summary(self) -> None:
        logger.info(
            "Scan run %d: %d discovered, %d processed — "
            "%d clean, %d corrupt, %d truncated, %d extended, "
            "%d duplicates, %d errors",
            self.run_id, self.discovered, self.processed,
            self.clean, self.corrupt, self.truncated, self.extended,
            self.format_duplicates + self.exact_duplicates, len(self.errors)
        )


def run_initial_scan(
    conn: sqlite3.Connection,
    library_root: Path,
    max_files: Optional[int] = None,
) -> ScanSummary:
    """
    Perform (or resume) an initial scan of library_root.

    - Creates a scan_run record (or reuses the last incomplete one).
    - Populates scan_queue for new paths.
    - Processes PENDING items up to max_files.
    - Writes all results to DB before returning.
    """
    from tagslut.scan.discovery import discover_paths
    from tagslut.scan.tags import (
        compute_sha256, read_raw_tags, read_technical,
        extract_isrc_from_tags, compute_quality_rank_from_technical, TagReadError
    )
    from tagslut.scan.validate import probe_duration_ffprobe, decode_probe_edges
    from tagslut.scan.classify import compute_identity_confidence, classify_primary_status
    from tagslut.scan.archive import upsert_archive
    from tagslut.scan.issues import record_issue, IssueCodes, Severity
    from tagslut.scan.dedupe import mark_format_duplicates, find_exact_duplicates
    from tagslut.scan.constants import DURATION_WARN_DELTA_S

    now = datetime.now().isoformat()

    # Create or reuse scan run
    existing_run = conn.execute(
        "SELECT id FROM scan_runs WHERE library_root = ? AND completed_at IS NULL ORDER BY id DESC LIMIT 1",
        (str(library_root),)
    ).fetchone()

    if existing_run:
        run_id = existing_run[0]
        logger.info("Resuming scan run %d", run_id)
    else:
        conn.execute(
            "INSERT INTO scan_runs (library_root, mode, created_at) VALUES (?, 'initial', ?)",
            (str(library_root), now)
        )
        conn.commit()
        run_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        logger.info("Starting scan run %d", run_id)

    summary = ScanSummary(run_id=run_id)

    # Discover and enqueue new paths
    paths = discover_paths(library_root)
    summary.discovered = len(paths)
    for path in paths:
        existing = conn.execute(
            "SELECT id FROM scan_queue WHERE run_id = ? AND path = ?",
            (run_id, str(path))
        ).fetchone()
        if existing is None:
            stat = path.stat()
            conn.execute(
                "INSERT INTO scan_queue (run_id, path, size_bytes, mtime_ns, state) VALUES (?, ?, ?, ?, 'PENDING')",
                (run_id, str(path), stat.st_size, stat.st_mtime_ns)
            )
    conn.commit()

    # Process PENDING items
    pending = conn.execute(
        "SELECT id, path, size_bytes FROM scan_queue WHERE run_id = ? AND state = 'PENDING' ORDER BY id",
        (run_id,)
    ).fetchall()

    if max_files:
        pending = pending[:max_files]

    for item in pending:
        queue_id, path_str, size_bytes = item[0], item[1], item[2]
        path = Path(path_str)

        conn.execute("UPDATE scan_queue SET state = 'RUNNING' WHERE id = ?", (queue_id,))
        conn.commit()

        try:
            checksum = compute_sha256(path)
            raw_tags = read_raw_tags(path)
            technical = read_technical(path)
            isrc_candidates = extract_isrc_from_tags(raw_tags)
            quality_rank = compute_quality_rank_from_technical(technical)
            duration_tagged = technical.get("duration_tagged")
            has_tags_error = False
        except TagReadError as e:
            conn.execute("UPDATE scan_queue SET state = 'FAILED', last_error = ? WHERE id = ?", (str(e), queue_id))
            record_issue(conn, run_id, path, IssueCodes.TAGS_UNREADABLE, Severity.ERROR, {"error": str(e)})
            conn.execute(
                "UPDATE files SET scan_status = 'CORRUPT', last_scanned_at = ?, scan_stage_reached = 0 WHERE path = ?",
                (now, path_str)
            )
            conn.commit()
            summary.corrupt += 1
            continue
        except Exception as e:
            conn.execute("UPDATE scan_queue SET state = 'FAILED', last_error = ? WHERE id = ?", (str(e), queue_id))
            conn.commit()
            summary.errors.append(str(e))
            continue

        actual_duration = probe_duration_ffprobe(path)
        decode_errors = decode_probe_edges(path, actual_duration)

        if actual_duration is None:
            record_issue(conn, run_id, path, IssueCodes.DURATION_UNVERIFIED, Severity.INFO,
                         {"reason": "ffprobe not available"}, checksum)

        duration_delta = None
        if actual_duration is not None and duration_tagged is not None:
            duration_delta = actual_duration - duration_tagged

        confidence = compute_identity_confidence(raw_tags, isrc_candidates, duration_delta)
        scan_status, flags = classify_primary_status(has_tags_error, decode_errors, duration_delta)

        # ISRC issues
        if not isrc_candidates:
            record_issue(conn, run_id, path, IssueCodes.ISRC_MISSING, Severity.INFO,
                         {"isrc_candidates": []}, checksum)
        elif len(isrc_candidates) > 1:
            record_issue(conn, run_id, path, IssueCodes.MULTI_ISRC, Severity.INFO,
                         {"isrc_candidates": isrc_candidates}, checksum)

        if decode_errors:
            record_issue(conn, run_id, path, IssueCodes.CORRUPT_DECODE, Severity.ERROR,
                         {"errors": decode_errors[:5]}, checksum)

        canonical_isrc = isrc_candidates[0] if len(isrc_candidates) == 1 else None

        # Upsert archive
        upsert_archive(
            conn, checksum=checksum, path=path,
            raw_tags=raw_tags, technical=technical,
            durations={"tagged": duration_tagged, "actual": actual_duration, "delta": duration_delta},
            isrc_candidates=isrc_candidates, identity_confidence=confidence, quality_rank=quality_rank,
        )

        # Exact duplicate check
        existing_paths = find_exact_duplicates(conn, checksum)
        if existing_paths:
            scan_status = "EXACT_DUPLICATE"
            conn.execute(
                "UPDATE files SET duplicate_of_checksum = ? WHERE path = ?",
                (checksum, path_str)
            )

        # Update or insert into files
        conn.execute("""
            UPDATE files SET
                scan_status = ?, scan_flags_json = ?, actual_duration = ?, duration_delta = ?,
                identity_confidence = ?, isrc_candidates_json = ?, last_scanned_at = ?,
                scan_stage_reached = 2, quality_rank = ?, canonical_isrc = ?
            WHERE path = ?
        """, (
            scan_status, json.dumps(flags), actual_duration, duration_delta,
            confidence, json.dumps(isrc_candidates), now, quality_rank, canonical_isrc,
            path_str
        ))

        conn.execute("UPDATE scan_queue SET state = 'DONE' WHERE id = ?", (queue_id,))
        conn.commit()

        summary.processed += 1
        if scan_status == "CLEAN": summary.clean += 1
        elif scan_status == "CORRUPT": summary.corrupt += 1
        elif scan_status == "TRUNCATED": summary.truncated += 1
        elif scan_status == "EXTENDED": summary.extended += 1
        elif scan_status == "EXACT_DUPLICATE": summary.exact_duplicates += 1
        if flags: summary.warnings += 1

    # Dedupe pass
    summary.format_duplicates = mark_format_duplicates(conn)
    conn.commit()

    summary.print_summary()
    return summary
```

### 6.2 — Create `tests/scan/test_runner_resume.py`

```python
import sqlite3
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from tagslut.storage.schema import init_db
from tagslut.scan.runner import run_initial_scan


@pytest.fixture
def fake_library(tmp_path):
    lib = tmp_path / "library"
    lib.mkdir()
    (lib / "track1.flac").write_bytes(b"flac" * 1000)
    (lib / "track2.flac").write_bytes(b"flac" * 2000)
    (lib / "track3.mp3").write_bytes(b"mp3" * 1000)
    return lib


@pytest.fixture
def mem_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()


def _mock_scan():
    return patch.multiple(
        "tagslut.scan.runner",
        read_raw_tags=MagicMock(return_value={"TITLE": ["Track"], "ARTIST": ["Artist"]}),
        read_technical=MagicMock(return_value={"duration_tagged": 240.0, "bit_depth": 16, "sample_rate": 44100, "bitrate": 0}),
        probe_duration_ffprobe=MagicMock(return_value=240.0),
        decode_probe_edges=MagicMock(return_value=[]),
    )


def test_runner_processes_all_files(fake_library, mem_db):
    with _mock_scan():
        summary = run_initial_scan(mem_db, fake_library)
    assert summary.discovered == 3
    assert summary.processed == 3
    assert len(summary.errors) == 0


def test_runner_resumes_partial_scan(fake_library, mem_db):
    with _mock_scan():
        summary1 = run_initial_scan(mem_db, fake_library, max_files=2)
    assert summary1.processed == 2

    with _mock_scan():
        summary2 = run_initial_scan(mem_db, fake_library)
    assert summary2.processed == 1  # only the remaining file


def test_runner_no_double_processing(fake_library, mem_db):
    with _mock_scan():
        run_initial_scan(mem_db, fake_library)
    done_count = mem_db.execute("SELECT COUNT(*) FROM scan_queue WHERE state = 'DONE'").fetchone()[0]
    assert done_count == 3

    with _mock_scan():
        summary3 = run_initial_scan(mem_db, fake_library)
    assert summary3.processed == 0  # nothing left to process
```

### Phase 6 Acceptance Checklist
- [ ] `poetry run pytest tests/scan/test_runner_resume.py -v` — green
- [ ] `poetry run pytest -v` — green
- [ ] Progress entry appended

---

## Phase 7 — CLI

**Goal:** `tagslut scan init|resume|status|issues` commands.
**Branch:** `feature/scanner-cli`
**Depends on:** Phase 6
**Estimated LOC:** ~120

### 7.1 — Create `tagslut/cli/commands/scan.py`

```python
"""tagslut scan — initial library scan commands."""
import click
from pathlib import Path


@click.group("scan")
def scan_group() -> None:
    """Initial library scan and scan result queries."""


@scan_group.command("init")
@click.option("--library", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--db", "db_path", required=True, type=click.Path())
@click.option("--workers", default=1, show_default=True, type=int)
@click.option("--max-files", default=None, type=int)
def scan_init(library: Path, db_path: str, workers: int, max_files: int) -> None:
    """Scan a library directory and build the inventory DB."""
    from tagslut.storage.schema import get_connection
    from tagslut.scan.runner import run_initial_scan
    with get_connection(db_path) as conn:
        summary = run_initial_scan(conn, library, max_files=max_files)
    click.echo(f"Run {summary.run_id}: {summary.processed} processed, "
               f"{summary.clean} clean, {summary.corrupt} corrupt, "
               f"{summary.format_duplicates + summary.exact_duplicates} duplicates")


@scan_group.command("resume")
@click.option("--db", "db_path", required=True, type=click.Path())
def scan_resume(db_path: str) -> None:
    """Resume the last incomplete scan."""
    from tagslut.storage.schema import get_connection
    from tagslut.scan.runner import run_initial_scan
    with get_connection(db_path) as conn:
        run_row = conn.execute(
            "SELECT library_root FROM scan_runs WHERE completed_at IS NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not run_row:
            click.echo("No incomplete scan found.")
            raise SystemExit(1)
        summary = run_initial_scan(conn, Path(run_row[0]))
    click.echo(f"Resumed run {summary.run_id}: {summary.processed} additional files processed.")


@scan_group.command("status")
@click.option("--db", "db_path", required=True, type=click.Path())
def scan_status(db_path: str) -> None:
    """Show scan status summary."""
    from tagslut.storage.schema import get_connection
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT scan_status, COUNT(*) as n FROM files WHERE scan_status IS NOT NULL GROUP BY scan_status ORDER BY n DESC"
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        issue_counts = conn.execute(
            "SELECT issue_code, COUNT(*) as n FROM scan_issues GROUP BY issue_code ORDER BY n DESC LIMIT 10"
        ).fetchall()
    click.echo(f"Total files: {total}")
    for row in rows:
        click.echo(f"  {row[0]:<20} {row[1]}")
    if issue_counts:
        click.echo("\nTop issues:")
        for row in issue_counts:
            click.echo(f"  {row[0]:<30} {row[1]}")


@scan_group.command("issues")
@click.option("--db", "db_path", required=True, type=click.Path())
@click.option("--code", default=None)
@click.option("--severity", default=None)
@click.option("--limit", default=50, show_default=True)
def scan_issues(db_path: str, code: str, severity: str, limit: int) -> None:
    """List scan issues, optionally filtered by code or severity."""
    from tagslut.storage.schema import get_connection
    with get_connection(db_path) as conn:
        where_parts = []
        params = []
        if code:
            where_parts.append("issue_code = ?")
            params.append(code)
        if severity:
            where_parts.append("severity = ?")
            params.append(severity)
        where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
        rows = conn.execute(
            f"SELECT path, issue_code, severity, evidence_json FROM scan_issues {where} ORDER BY severity DESC LIMIT ?",
            params + [limit]
        ).fetchall()
    if not rows:
        click.echo("No issues found.")
        return
    for row in rows:
        click.echo(f"  [{row[2]}] {row[1]:<25} {Path(row[0]).name}")
```

### 7.2 — Register in `tagslut/cli/main.py`

```python
from tagslut.cli.commands.scan import scan_group
cli.add_command(scan_group, name="scan")
```

### 7.3 — Create `tests/cli/test_scan_cli.py`

```python
from click.testing import CliRunner
from tagslut.cli.main import cli


def test_scan_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["scan", "--help"])
    assert result.exit_code == 0
    assert "init" in result.output
    assert "resume" in result.output
    assert "status" in result.output
    assert "issues" in result.output
```

### Phase 7 Acceptance Checklist
- [ ] `poetry run pytest tests/cli/test_scan_cli.py -v` — green
- [ ] `poetry run pytest -v` — green
- [ ] `poetry run tagslut scan --help` shows all 4 subcommands
- [ ] Progress entry appended to `docs/SCANNER_V1_PROGRESS.md`
- [ ] All 7 phase checkboxes in status dashboard set to ☑

---

## Final Acceptance

```bash
poetry run pytest -v
poetry run tagslut scan --help
poetry run tagslut scan init --library <dir> --db <db>
poetry run tagslut scan status --db <db>
```

*Last updated: 2026-02-28. Implementation authority for scanner workflow.*
