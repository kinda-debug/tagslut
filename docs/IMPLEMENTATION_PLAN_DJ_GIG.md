# Implementation Plan: DJ Gig Workflow (Phases 1–6)

> **For AI coding agents (Codex, Claude Code, Copilot):**
> This document is the single source of truth for implementing the DJ gig workflow.
> Follow each phase in order. Do not skip ahead. Run `poetry run pytest` after each phase.
> Read `REPORT.md` and `.claude/AGENTS.md` before starting.
>
> **Evaluator:** Each phase output will be reviewed before the next phase begins.

---

## Constraints (Non-Negotiable)

1. Master FLAC files are **read-only**. Never modify, move, or delete them during any DJ/gig operation.
2. All DB changes must be **additive** — no column renames, no table drops, no destructive migrations.
3. Every new module must have a corresponding test file.
4. `poetry run pytest` must exit 0 before and after each phase.
5. Use `ffmpeg` via subprocess — do not add a Python ffmpeg binding library.
6. All file path manipulation must use `pathlib.Path`, never string concatenation.
7. Never import from `tagslut.legacy` or use any retired CLI command names.

---

## Existing Code to Read First

Before writing any code, read these files in full:

| File | Why |
|---|---|
| `tagslut/storage/schema.py` | Full DB schema — know what already exists |
| `tagslut/storage/models.py` | `AudioFile` dataclass — extend, don't replace |
| `tagslut/storage/queries.py` | Existing query patterns — follow same style |
| `tagslut/cli/commands/index.py` | CLI command pattern to replicate |
| `tagslut/cli/commands/execute.py` | Minimal command stub pattern |
| `tagslut/core/duration_validator.py` | Example of a well-structured core module |
| `tests/conftest.py` | Fixtures available — use them |
| `pyproject.toml` | Current deps — add to both `[project]` and `[tool.poetry.dependencies]` |

---

## Phase 1 — Schema & Foundation

**Goal:** Database ready for all DJ operations. No CLI changes yet.
**Branch:** `feature/dj-schema`
**Estimated LOC:** ~200

### 1.1 — Add columns to `files` table in `tagslut/storage/schema.py`

In the `required_columns` dict inside `init_db()`, add the following entries.
Do NOT remove any existing entries. These are purely additive:

```python
# DJ pool output tracking
"dj_pool_path": "TEXT",            # absolute path to derived MP3 in DJ pool
"quality_rank": "INTEGER",         # computed rank 1-7 (see quality.py)
"rekordbox_id": "INTEGER",         # Pioneer/Rekordbox internal track ID (written back post-gig)
"last_exported_usb": "TEXT",       # ISO8601 timestamp of last USB export
```

Also add the following indices after the existing index block:

```python
connection.execute("CREATE INDEX IF NOT EXISTS idx_quality_rank ON files(quality_rank);")
connection.execute("CREATE INDEX IF NOT EXISTS idx_dj_pool_path ON files(dj_pool_path);")
connection.execute("CREATE INDEX IF NOT EXISTS idx_last_exported_usb ON files(last_exported_usb);")
```

### 1.2 — Add `gig_sets` and `gig_set_tracks` tables in `tagslut/storage/schema.py`

Add a new private function `_ensure_gig_tables(conn)` and call it from `init_db()` just before `connection.commit()`:

```python
def _ensure_gig_tables(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS gig_sets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            filter_expr TEXT,
            usb_path TEXT,
            manifest_path TEXT,
            track_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            exported_at TEXT
        );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_gig_sets_name ON gig_sets(name);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_gig_sets_exported_at ON gig_sets(exported_at);")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS gig_set_tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gig_set_id INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            mp3_path TEXT,
            usb_dest_path TEXT,
            transcoded_at TEXT,
            exported_at TEXT,
            rekordbox_id INTEGER,
            FOREIGN KEY(gig_set_id) REFERENCES gig_sets(id)
        );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_gig_set_tracks_set ON gig_set_tracks(gig_set_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_gig_set_tracks_file ON gig_set_tracks(file_path);")
    _add_missing_columns(conn, "gig_sets", {
        "filter_expr": "TEXT",
        "usb_path": "TEXT",
        "manifest_path": "TEXT",
        "track_count": "INTEGER DEFAULT 0",
        "exported_at": "TEXT",
    })
    _add_missing_columns(conn, "gig_set_tracks", {
        "mp3_path": "TEXT",
        "usb_dest_path": "TEXT",
        "transcoded_at": "TEXT",
        "exported_at": "TEXT",
        "rekordbox_id": "INTEGER",
    })
```

### 1.3 — Add `GigSet` and `GigSetTrack` dataclasses to `tagslut/storage/models.py`

Append to the end of `models.py`:

```python
@dataclass
class GigSet:
    """
    A named collection of tracks assembled for a specific gig or set.
    """
    name: str
    id: Optional[int] = None
    filter_expr: Optional[str] = None
    usb_path: Optional[str] = None
    manifest_path: Optional[str] = None
    track_count: int = 0
    created_at: Optional[str] = None
    exported_at: Optional[str] = None


@dataclass
class GigSetTrack:
    """
    A single track within a GigSet, tracking its MP3 and USB export state.
    """
    gig_set_id: int
    file_path: Path
    id: Optional[int] = None
    mp3_path: Optional[Path] = None
    usb_dest_path: Optional[Path] = None
    transcoded_at: Optional[str] = None
    exported_at: Optional[str] = None
    rekordbox_id: Optional[int] = None

    def __post_init__(self) -> None:
        if isinstance(self.file_path, str):
            self.file_path = Path(self.file_path)
        if isinstance(self.mp3_path, str):
            self.mp3_path = Path(self.mp3_path)
        if isinstance(self.usb_dest_path, str):
            self.usb_dest_path = Path(self.usb_dest_path)
```

### 1.4 — Create `tagslut/core/quality.py`

Create this file from scratch:

```python
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
```

### 1.5 — Create `tests/storage/test_dj_schema.py`

```python
import sqlite3
import pytest
from tagslut.storage.schema import init_db
from tagslut.storage.models import GigSet, GigSetTrack
from pathlib import Path


@pytest.fixture
def mem_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()


def test_files_table_has_dj_columns(mem_db):
    cols = {row[1] for row in mem_db.execute("PRAGMA table_info(files)")}
    assert "dj_pool_path" in cols
    assert "quality_rank" in cols
    assert "rekordbox_id" in cols
    assert "last_exported_usb" in cols


def test_gig_sets_table_exists(mem_db):
    cols = {row[1] for row in mem_db.execute("PRAGMA table_info(gig_sets)")}
    assert "name" in cols
    assert "filter_expr" in cols
    assert "exported_at" in cols


def test_gig_set_tracks_table_exists(mem_db):
    cols = {row[1] for row in mem_db.execute("PRAGMA table_info(gig_set_tracks)")}
    assert "gig_set_id" in cols
    assert "mp3_path" in cols
    assert "usb_dest_path" in cols


def test_init_db_is_idempotent(mem_db):
    # Calling init_db twice must not raise
    init_db(mem_db)


def test_gig_set_track_path_coercion():
    t = GigSetTrack(gig_set_id=1, file_path="/music/track.flac", mp3_path="/dj/track.mp3")
    assert isinstance(t.file_path, Path)
    assert isinstance(t.mp3_path, Path)
```

### 1.6 — Create `tests/core/test_quality.py`

```python
import pytest
from tagslut.core.quality import compute_quality_rank, is_upgrade, QualityRank


@pytest.mark.parametrize("bit_depth,sample_rate,bitrate,expected", [
    (32, 192000, 0, QualityRank.STUDIO_MASTER),
    (24, 96000, 0, QualityRank.HIRES_LOSSLESS),
    (24, 44100, 0, QualityRank.HIRES_STANDARD),
    (16, 44100, 0, QualityRank.CD_LOSSLESS),
    (16, 44100, 320000, QualityRank.LOSSY_HIGH),
    (16, 44100, 128000, QualityRank.LOSSY_DEGRADED),
])
def test_compute_quality_rank(bit_depth, sample_rate, bitrate, expected):
    assert compute_quality_rank(bit_depth, sample_rate, bitrate) == expected


def test_is_upgrade_better():
    assert is_upgrade(current_rank=4, candidate_rank=2) is True


def test_is_upgrade_same():
    assert is_upgrade(current_rank=4, candidate_rank=4) is False


def test_is_upgrade_worse():
    assert is_upgrade(current_rank=2, candidate_rank=5) is False
```

### Phase 1 Acceptance Checklist
- [ ] `poetry run pytest tests/storage/test_dj_schema.py` — green
- [ ] `poetry run pytest tests/core/test_quality.py` — green
- [ ] `poetry run pytest` (full suite) — green
- [ ] `poetry run mypy tagslut/core/quality.py tagslut/storage/models.py` — clean

---

## Phase 2 — Pre-Download Resolution

**Goal:** `tagslut intake run <url>` resolves track identity against inventory before downloading.
**Branch:** `feature/pre-flight-resolver`
**Depends on:** Phase 1
**Estimated LOC:** ~300

### 2.1 — Create `tagslut/filters/identity_resolver.py`

This module resolves a track intent (from a playlist URL response) to an existing `files` record.

```python
"""
Track identity resolution chain.

Resolution priority:
  1. ISRC              (canonical_isrc column)
  2. Beatport ID       (beatport_id column)
  3. Tidal ID          (tidal_id column)
  4. Qobuz ID          (qobuz_id column)
  5. Fuzzy match       (artist + title + duration ±2s via rapidfuzz)
"""
import sqlite3
from dataclasses import dataclass
from typing import Optional
from rapidfuzz import fuzz


@dataclass
class TrackIntent:
    """
    Represents a track the user intends to acquire (from a URL/playlist).
    Not yet on disk. All fields optional — populated from provider metadata.
    """
    title: Optional[str] = None
    artist: Optional[str] = None
    duration_s: Optional[float] = None
    isrc: Optional[str] = None
    beatport_id: Optional[str] = None
    tidal_id: Optional[str] = None
    qobuz_id: Optional[str] = None
    # Quality of the candidate (from provider API)
    bit_depth: Optional[int] = None
    sample_rate: Optional[int] = None
    bitrate: Optional[int] = None


@dataclass
class ResolutionResult:
    """
    Result of resolving a TrackIntent against the local inventory.
    """
    intent: TrackIntent
    # One of: "new", "upgrade", "skip"
    action: str
    # Path of existing file if found, else None
    existing_path: Optional[str] = None
    existing_quality_rank: Optional[int] = None
    candidate_quality_rank: Optional[int] = None
    match_method: Optional[str] = None  # "isrc", "beatport_id", "fuzzy", None
    match_score: Optional[float] = None


FUZZY_THRESHOLD = 88          # rapidfuzz score 0-100
DURATION_TOLERANCE_S = 2.0    # seconds


class IdentityResolver:
    """
    Resolves TrackIntent objects against a tagslut SQLite inventory.

    Usage:
        resolver = IdentityResolver(conn)
        result = resolver.resolve(intent, candidate_rank=3)
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def resolve(self, intent: TrackIntent, candidate_rank: int) -> ResolutionResult:
        """
        Attempt to find a matching existing file for the given intent.
        Returns a ResolutionResult with action="new", "upgrade", or "skip".
        """
        existing = self._find_existing(intent)
        if existing is None:
            return ResolutionResult(
                intent=intent,
                action="new",
                candidate_quality_rank=candidate_rank,
            )

        existing_path, existing_rank, method, score = existing
        from tagslut.core.quality import is_upgrade
        if is_upgrade(current_rank=existing_rank, candidate_rank=candidate_rank):
            action = "upgrade"
        else:
            action = "skip"

        return ResolutionResult(
            intent=intent,
            action=action,
            existing_path=existing_path,
            existing_quality_rank=existing_rank,
            candidate_quality_rank=candidate_rank,
            match_method=method,
            match_score=score,
        )

    def _find_existing(
        self, intent: TrackIntent
    ) -> Optional[tuple[str, int, str, Optional[float]]]:
        """
        Returns (path, quality_rank, match_method, score) or None.
        """
        # 1. ISRC
        if intent.isrc:
            row = self._conn.execute(
                "SELECT path, quality_rank FROM files WHERE canonical_isrc = ? LIMIT 1",
                (intent.isrc,),
            ).fetchone()
            if row and row[1] is not None:
                return (row[0], row[1], "isrc", 100.0)

        # 2. Beatport ID
        if intent.beatport_id:
            row = self._conn.execute(
                "SELECT path, quality_rank FROM files WHERE beatport_id = ? LIMIT 1",
                (intent.beatport_id,),
            ).fetchone()
            if row and row[1] is not None:
                return (row[0], row[1], "beatport_id", 100.0)

        # 3. Tidal ID
        if intent.tidal_id:
            row = self._conn.execute(
                "SELECT path, quality_rank FROM files WHERE tidal_id = ? LIMIT 1",
                (intent.tidal_id,),
            ).fetchone()
            if row and row[1] is not None:
                return (row[0], row[1], "tidal_id", 100.0)

        # 4. Qobuz ID
        if intent.qobuz_id:
            row = self._conn.execute(
                "SELECT path, quality_rank FROM files WHERE qobuz_id = ? LIMIT 1",
                (intent.qobuz_id,),
            ).fetchone()
            if row and row[1] is not None:
                return (row[0], row[1], "qobuz_id", 100.0)

        # 5. Fuzzy: artist + title + duration
        if intent.artist and intent.title:
            return self._fuzzy_match(intent)

        return None

    def _fuzzy_match(
        self, intent: TrackIntent
    ) -> Optional[tuple[str, int, str, float]]:
        """
        Fuzzy match by artist + title using rapidfuzz, with optional duration gate.
        Only returns a match if score >= FUZZY_THRESHOLD.
        """
        query = """
            SELECT path, quality_rank,
                   canonical_artist, canonical_title, duration
            FROM files
            WHERE canonical_artist IS NOT NULL
              AND canonical_title IS NOT NULL
              AND quality_rank IS NOT NULL
        """
        rows = self._conn.execute(query).fetchall()
        best_score = 0.0
        best_row = None

        search_str = f"{intent.artist} {intent.title}".lower()
        for row in rows:
            candidate_str = f"{row[2]} {row[3]}".lower()
            score = fuzz.token_sort_ratio(search_str, candidate_str)
            if score > best_score:
                # Duration gate: if both have duration, enforce tolerance
                if intent.duration_s and row[4]:
                    if abs(intent.duration_s - row[4]) > DURATION_TOLERANCE_S:
                        continue
                best_score = score
                best_row = row

        if best_row and best_score >= FUZZY_THRESHOLD:
            return (best_row[0], best_row[1], "fuzzy", best_score)
        return None
```

### 2.2 — Create `tagslut/core/pre_flight.py`

```python
"""
Pre-download resolution engine.

Builds a filtered download manifest before any files are downloaded,
preventing redundant downloads of tracks already in the master library
at equal or better quality.
"""
import sqlite3
from dataclasses import dataclass, field
from typing import List

from tagslut.filters.identity_resolver import IdentityResolver, TrackIntent, ResolutionResult
from tagslut.core.quality import compute_quality_rank


@dataclass
class DownloadManifest:
    """
    Output of the pre-flight check. Only 'new' and 'upgrade' tracks
    should be passed to the downloader.
    """
    new: List[ResolutionResult] = field(default_factory=list)
    upgrades: List[ResolutionResult] = field(default_factory=list)
    skipped: List[ResolutionResult] = field(default_factory=list)

    @property
    def download_count(self) -> int:
        return len(self.new) + len(self.upgrades)

    @property
    def skip_count(self) -> int:
        return len(self.skipped)

    def summary(self) -> str:
        return (
            f"Pre-flight: {len(self.new)} new, "
            f"{len(self.upgrades)} upgrades, "
            f"{len(self.skipped)} skipped — "
            f"downloading {self.download_count} tracks"
        )


class PreFlightResolver:
    """
    Resolves a list of TrackIntents against the inventory database
    and produces a DownloadManifest.

    Usage:
        with get_connection(db_path) as conn:
            resolver = PreFlightResolver(conn)
            manifest = resolver.resolve(intents)
            print(manifest.summary())
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._resolver = IdentityResolver(conn)

    def resolve(self, intents: List[TrackIntent]) -> DownloadManifest:
        manifest = DownloadManifest()
        for intent in intents:
            candidate_rank = self._candidate_rank(intent)
            result = self._resolver.resolve(intent, candidate_rank)
            if result.action == "new":
                manifest.new.append(result)
            elif result.action == "upgrade":
                manifest.upgrades.append(result)
            else:
                manifest.skipped.append(result)
        return manifest

    @staticmethod
    def _candidate_rank(intent: TrackIntent) -> int:
        """
        Compute quality rank of the candidate. If provider info is unknown,
        assume worst case (rank 7) to avoid skipping a potentially better file.
        """
        if intent.bit_depth and intent.sample_rate:
            return int(compute_quality_rank(
                intent.bit_depth,
                intent.sample_rate,
                intent.bitrate or 0,
            ))
        return 7  # unknown = assume worst, always download
```

### 2.3 — Create `tests/core/test_pre_flight.py`

```python
import sqlite3
import pytest
from tagslut.storage.schema import init_db
from tagslut.filters.identity_resolver import TrackIntent
from tagslut.core.pre_flight import PreFlightResolver


@pytest.fixture
def db_with_track():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    # Insert a known CD-quality track (rank 4)
    conn.execute("""
        INSERT INTO files (
            path, checksum, duration, bit_depth, sample_rate, bitrate,
            metadata_json, quality_rank, canonical_isrc, canonical_artist,
            canonical_title, beatport_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "/music/artist - track.flac", "abc123", 240.0,
        16, 44100, 0,
        "{}", 4, "USABC1234567", "Test Artist", "Test Track", "BP001"
    ))
    conn.commit()
    yield conn
    conn.close()


def test_known_isrc_same_quality_is_skipped(db_with_track):
    resolver = PreFlightResolver(db_with_track)
    intent = TrackIntent(isrc="USABC1234567", bit_depth=16, sample_rate=44100, bitrate=0)
    manifest = resolver.resolve([intent])
    assert manifest.skip_count == 1
    assert manifest.download_count == 0


def test_known_isrc_better_quality_is_upgrade(db_with_track):
    resolver = PreFlightResolver(db_with_track)
    # 24bit offer = rank 3, current is rank 4 → upgrade
    intent = TrackIntent(isrc="USABC1234567", bit_depth=24, sample_rate=44100, bitrate=0)
    manifest = resolver.resolve([intent])
    assert len(manifest.upgrades) == 1
    assert manifest.download_count == 1


def test_unknown_track_is_new(db_with_track):
    resolver = PreFlightResolver(db_with_track)
    intent = TrackIntent(isrc="UNKNOWN9999999", bit_depth=16, sample_rate=44100, bitrate=0)
    manifest = resolver.resolve([intent])
    assert len(manifest.new) == 1


def test_manifest_summary_string(db_with_track):
    resolver = PreFlightResolver(db_with_track)
    intents = [
        TrackIntent(isrc="USABC1234567", bit_depth=16, sample_rate=44100, bitrate=0),  # skip
        TrackIntent(isrc="NEW001", bit_depth=24, sample_rate=96000, bitrate=0),          # new
    ]
    manifest = resolver.resolve(intents)
    summary = manifest.summary()
    assert "1 new" in summary
    assert "1 skipped" in summary
```

### Phase 2 Acceptance Checklist
- [ ] `poetry run pytest tests/core/test_pre_flight.py` — green
- [ ] `poetry run pytest` (full suite) — green
- [ ] `poetry run mypy tagslut/core/pre_flight.py tagslut/filters/identity_resolver.py` — clean

---

## Phase 3 — Transcoder

**Goal:** FLAC master → MP3 DJ pool copy, immutable master, full tag inheritance.
**Branch:** `feature/transcoder`
**Depends on:** Phase 1
**Estimated LOC:** ~120

### 3.1 — Create `tagslut/exec/transcoder.py`

```python
"""
FLAC to MP3 transcoder for DJ pool export.

Master FLAC files are NEVER modified. MP3 is written to dest_dir.
All tags are copied from source FLAC to output MP3 via mutagen.
Requires ffmpeg installed as a system dependency.
"""
import subprocess
import shutil
from pathlib import Path
from typing import Optional
import logging

from mutagen.flac import FLAC
from mutagen.id3 import (
    ID3, TIT2, TPE1, TALB, TRCK, TDRC, TCON, TBPM, TKEY, TSRC,
    TXXX, COMM
)

logger = logging.getLogger("tagslut.transcoder")


class TranscodeError(Exception):
    pass


class FFmpegNotFoundError(TranscodeError):
    pass


def _check_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise FFmpegNotFoundError(
            "ffmpeg not found in PATH. Install it: brew install ffmpeg (macOS) "
            "or apt install ffmpeg (Linux)"
        )


def _build_mp3_filename(source: Path, tags: Optional[FLAC]) -> str:
    """
    Build DJ-friendly MP3 filename: Artist - Title (Key) (BPM).mp3
    Falls back to source stem if tags are missing.
    """
    if tags is None:
        return source.stem + ".mp3"

    artist = (tags.get("artist") or tags.get("albumartist") or [""])[0]
    title = (tags.get("title") or [""])[0]
    key = (tags.get("initialkey") or tags.get("key") or [""])[0]
    bpm = (tags.get("bpm") or [""])[0]

    if not artist or not title:
        return source.stem + ".mp3"

    parts = f"{artist} - {title}"
    if key:
        parts += f" ({key})"
    if bpm:
        parts += f" ({bpm})"

    # Sanitise for filesystem
    safe = "".join(c for c in parts if c not in r'\/:*?"<>|')
    return safe + ".mp3"


def transcode_to_mp3(
    source: Path,
    dest_dir: Path,
    bitrate: int = 320,
    overwrite: bool = False,
) -> Path:
    """
    Transcode a FLAC file to MP3 and copy to dest_dir.

    The source FLAC is never modified.
    Tags are copied from FLAC to MP3 via mutagen.

    Args:
        source:    Absolute path to the source FLAC file.
        dest_dir:  Destination directory for the MP3.
        bitrate:   MP3 bitrate in kbps (default 320).
        overwrite: If False, skip if dest already exists.

    Returns:
        Path to the created MP3 file.

    Raises:
        FFmpegNotFoundError: If ffmpeg is not installed.
        TranscodeError: If ffmpeg returns a non-zero exit code.
        FileNotFoundError: If source does not exist.
    """
    if not source.exists():
        raise FileNotFoundError(f"Source file not found: {source}")
    _check_ffmpeg()

    try:
        flac_tags: Optional[FLAC] = FLAC(source)
    except Exception:
        flac_tags = None
        logger.warning("Could not read FLAC tags from %s", source)

    dest_dir.mkdir(parents=True, exist_ok=True)
    mp3_name = _build_mp3_filename(source, flac_tags)
    dest_path = dest_dir / mp3_name

    if dest_path.exists() and not overwrite:
        logger.info("Skipping transcode, already exists: %s", dest_path)
        return dest_path

    cmd = [
        "ffmpeg", "-y",
        "-i", str(source),
        "-codec:a", "libmp3lame",
        "-b:a", f"{bitrate}k",
        "-id3v2_version", "3",
        "-map_metadata", "0",
        str(dest_path),
    ]
    logger.debug("Transcoding: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise TranscodeError(
            f"ffmpeg failed for {source}:\n{result.stderr[-500:]}"
        )

    # Re-apply tags from mutagen for fields ffmpeg may not copy cleanly
    _apply_id3_tags(dest_path, flac_tags)

    logger.info("Transcoded: %s → %s", source, dest_path)
    return dest_path


def _apply_id3_tags(mp3_path: Path, flac_tags: Optional[FLAC]) -> None:
    """Apply critical DJ tags to the MP3 via mutagen ID3."""
    if flac_tags is None:
        return
    try:
        tags = ID3(mp3_path)
    except Exception:
        tags = ID3()

    def first(key: str) -> Optional[str]:
        vals = flac_tags.get(key)
        return vals[0] if vals else None

    if first("title"):
        tags["TIT2"] = TIT2(encoding=3, text=first("title"))
    if first("artist") or first("albumartist"):
        tags["TPE1"] = TPE1(encoding=3, text=first("artist") or first("albumartist"))
    if first("album"):
        tags["TALB"] = TALB(encoding=3, text=first("album"))
    if first("date") or first("year"):
        tags["TDRC"] = TDRC(encoding=3, text=first("date") or first("year"))
    if first("genre"):
        tags["TCON"] = TCON(encoding=3, text=first("genre"))
    if first("bpm"):
        tags["TBPM"] = TBPM(encoding=3, text=first("bpm"))
    if first("initialkey") or first("key"):
        tags["TKEY"] = TKEY(encoding=3, text=first("initialkey") or first("key"))
    if first("isrc"):
        tags["TSRC"] = TSRC(encoding=3, text=first("isrc"))

    tags.save(mp3_path)
```

### 3.2 — Create `tests/exec/test_transcoder.py`

Use `unittest.mock.patch` to mock the `subprocess.run` and `shutil.which` calls.
Do NOT require ffmpeg to be installed for tests to pass.

```python
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from tagslut.exec.transcoder import transcode_to_mp3, FFmpegNotFoundError, TranscodeError


def test_raises_if_ffmpeg_not_found(tmp_path):
    src = tmp_path / "track.flac"
    src.write_bytes(b"fake")
    with patch("shutil.which", return_value=None):
        with pytest.raises(FFmpegNotFoundError):
            transcode_to_mp3(src, tmp_path / "out")


def test_raises_if_source_not_found(tmp_path):
    with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        with pytest.raises(FileNotFoundError):
            transcode_to_mp3(tmp_path / "nonexistent.flac", tmp_path / "out")


def test_raises_on_ffmpeg_error(tmp_path):
    src = tmp_path / "track.flac"
    src.write_bytes(b"fake")
    mock_result = MagicMock(returncode=1, stderr="error")
    with patch("shutil.which", return_value="/usr/bin/ffmpeg"), \
         patch("subprocess.run", return_value=mock_result), \
         patch("tagslut.exec.transcoder.FLAC", side_effect=Exception("no tags")), \
         patch("tagslut.exec.transcoder._apply_id3_tags"):
        with pytest.raises(TranscodeError):
            transcode_to_mp3(src, tmp_path / "out")


def test_skips_existing_when_no_overwrite(tmp_path):
    src = tmp_path / "track.flac"
    src.write_bytes(b"fake")
    dest_dir = tmp_path / "out"
    dest_dir.mkdir()
    # Pre-create the expected MP3
    existing = dest_dir / "track.mp3"
    existing.write_bytes(b"existing")
    with patch("shutil.which", return_value="/usr/bin/ffmpeg"), \
         patch("tagslut.exec.transcoder.FLAC", side_effect=Exception()), \
         patch("subprocess.run") as mock_run:
        result = transcode_to_mp3(src, dest_dir, overwrite=False)
        mock_run.assert_not_called()
```

### Phase 3 Acceptance Checklist
- [ ] `poetry run pytest tests/exec/test_transcoder.py` — green (no ffmpeg required)
- [ ] `poetry run pytest` — green
- [ ] `poetry run mypy tagslut/exec/transcoder.py` — clean

---

## Phase 4 — USB Export

**Goal:** `tagslut export usb` takes a source folder, copies files to USB, writes Pioneer database.
**Branch:** `feature/usb-export`
**Depends on:** Phase 1, Phase 3
**New dependency:** `pyrekordbox>=0.3`
**Estimated LOC:** ~200

### 4.1 — Add `pyrekordbox` to `pyproject.toml`

Add to BOTH `[project].dependencies` AND `[tool.poetry.dependencies]`:
```toml
pyrekordbox = ">=0.3,<1.0"
```

Run `poetry lock --no-update` after.

### 4.2 — Create `tagslut/exec/usb_export.py`

```python
"""
USB export engine for Pioneer CDJ compatibility.

Copies MP3/FLAC files to a USB drive and writes a Rekordbox-compatible
PIONEER/ database using pyrekordbox.

Master FLAC files in the source library are never modified.
"""
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional
import logging

logger = logging.getLogger("tagslut.usb_export")

SUPPORTED_EXTENSIONS = {".mp3", ".flac", ".aif", ".aiff", ".wav", ".m4a"}


def scan_source(source_dir: Path) -> List[Path]:
    """
    Recursively scan source_dir and return all supported audio files.
    """
    return sorted(
        p for p in source_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def copy_to_usb(
    tracks: List[Path],
    usb_path: Path,
    crate_name: str,
    dry_run: bool = False,
) -> List[Path]:
    """
    Copy track files to USB under /MUSIC/<crate_name>/.

    Returns list of destination paths (for database registration).
    Does not modify source files.
    """
    dest_dir = usb_path / "MUSIC" / crate_name
    copied: List[Path] = []

    for track in tracks:
        dest = dest_dir / track.name
        if dry_run:
            logger.info("[DRY RUN] Would copy: %s → %s", track, dest)
            copied.append(dest)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(track, dest)
        logger.info("Copied: %s → %s", track, dest)
        copied.append(dest)

    return copied


def write_rekordbox_db(
    tracks: List[Path],
    usb_path: Path,
    crate_name: str,
    dry_run: bool = False,
) -> None:
    """
    Write the PIONEER/ database to the USB using pyrekordbox.

    Creates a crate named `crate_name` containing all tracks.
    BPM and key are read from file tags if available.

    Raises ImportError if pyrekordbox is not installed.
    """
    if dry_run:
        logger.info("[DRY RUN] Would write Rekordbox DB for %d tracks", len(tracks))
        return

    try:
        import pyrekordbox  # type: ignore
    except ImportError as e:
        raise ImportError(
            "pyrekordbox is required for USB export. "
            "Run: poetry add pyrekordbox"
        ) from e

    # NOTE: pyrekordbox API may vary by version.
    # The following is a reference implementation — adjust to actual API.
    # See: https://pyrekordbox.readthedocs.io/
    pioneer_dir = usb_path / "PIONEER"
    pioneer_dir.mkdir(parents=True, exist_ok=True)

    try:
        db = pyrekordbox.Rb6Database(pioneer_dir / "rekordbox.db")
    except Exception:
        db = pyrekordbox.Rb6Database.create(pioneer_dir / "rekordbox.db")

    track_ids = []
    for track_path in tracks:
        try:
            bpm, key = _read_bpm_key(track_path)
            track_id = db.add_track(
                path=str(track_path),
                bpm=bpm,
                key=key,
            )
            track_ids.append(track_id)
        except Exception as exc:
            logger.warning("Failed to add track %s to DB: %s", track_path, exc)

    if track_ids:
        db.create_playlist(name=crate_name, track_ids=track_ids)

    db.save()
    logger.info("Rekordbox DB written: %s (%d tracks)", pioneer_dir, len(track_ids))


def write_manifest(
    tracks: List[Path],
    usb_path: Path,
    crate_name: str,
) -> Path:
    """
    Write a human-readable manifest file to the USB root.
    Returns the manifest path.
    """
    manifest_path = usb_path / f"gig_manifest_{datetime.now().strftime('%Y-%m-%d')}.txt"
    lines = [
        f"# tagslut gig manifest",
        f"# Crate: {crate_name}",
        f"# Exported: {datetime.now().isoformat()}",
        f"# Tracks: {len(tracks)}",
        "",
    ]
    for i, track in enumerate(tracks, 1):
        lines.append(f"{i:04d}  {track.name}")

    manifest_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Manifest written: %s", manifest_path)
    return manifest_path


def _read_bpm_key(path: Path) -> tuple[Optional[float], Optional[str]]:
    """Read BPM and key from file tags. Returns (None, None) on failure."""
    try:
        from mutagen import File as MutagenFile
        f = MutagenFile(path, easy=True)
        if f is None:
            return None, None
        bpm_raw = f.get("bpm") or f.get("TBPM")
        key_raw = f.get("initialkey") or f.get("TKEY")
        bpm = float(bpm_raw[0]) if bpm_raw else None
        key = str(key_raw[0]) if key_raw else None
        return bpm, key
    except Exception:
        return None, None
```

### 4.3 — Create `tagslut/cli/commands/export.py`

```python
"""tagslut export — USB and DJ pool export commands."""
import click
from pathlib import Path


@click.group("export")
def export_group() -> None:
    """Export tracks to USB or DJ pool."""


@export_group.command("usb")
@click.option("--source", required=True, type=click.Path(exists=True, path_type=Path),
              help="Source directory containing audio files")
@click.option("--usb", required=True, type=click.Path(exists=True, path_type=Path),
              help="USB mount point (e.g. /Volumes/PIONEER_USB)")
@click.option("--crate", default="tagslut export", show_default=True,
              help="Crate/playlist name in Rekordbox")
@click.option("--dry-run", is_flag=True, help="Print what would happen without writing anything")
def export_usb(source: Path, usb: Path, crate: str, dry_run: bool) -> None:
    """Export a folder of tracks to a Pioneer CDJ-ready USB."""
    from tagslut.exec.usb_export import scan_source, copy_to_usb, write_rekordbox_db, write_manifest

    tracks = scan_source(source)
    if not tracks:
        click.echo(f"No supported audio files found in {source}")
        raise SystemExit(1)

    click.echo(f"Found {len(tracks)} tracks in {source}")

    dest_tracks = copy_to_usb(tracks, usb, crate, dry_run=dry_run)
    write_rekordbox_db(dest_tracks, usb, crate, dry_run=dry_run)

    if not dry_run:
        manifest = write_manifest(dest_tracks, usb, crate)
        click.echo(f"Manifest: {manifest}")

    click.echo(f"{'[DRY RUN] ' if dry_run else ''}Export complete: {len(dest_tracks)} tracks → {usb}")
```

### 4.4 — Register `export` group in `tagslut/cli/main.py`

Find the section in `main.py` where command groups are registered (look for `cli.add_command` calls)
and add:

```python
from tagslut.cli.commands.export import export_group
cli.add_command(export_group, name="export")
```

### 4.5 — Create `tests/exec/test_usb_export.py`

```python
from pathlib import Path
import pytest
from tagslut.exec.usb_export import scan_source, copy_to_usb, write_manifest


@pytest.fixture
def source_dir(tmp_path):
    d = tmp_path / "source"
    d.mkdir()
    (d / "track1.mp3").write_bytes(b"mp3data")
    (d / "track2.flac").write_bytes(b"flacdata")
    (d / "cover.jpg").write_bytes(b"imgdata")  # should be ignored
    return d


def test_scan_source_finds_audio_only(source_dir):
    tracks = scan_source(source_dir)
    names = [t.name for t in tracks]
    assert "track1.mp3" in names
    assert "track2.flac" in names
    assert "cover.jpg" not in names


def test_copy_to_usb_dry_run_no_write(tmp_path, source_dir):
    tracks = scan_source(source_dir)
    usb = tmp_path / "usb"
    usb.mkdir()
    copied = copy_to_usb(tracks, usb, "Test Crate", dry_run=True)
    # Dry run: no files actually written
    assert not (usb / "MUSIC" / "Test Crate").exists()
    assert len(copied) == 2


def test_copy_to_usb_writes_files(tmp_path, source_dir):
    tracks = scan_source(source_dir)
    usb = tmp_path / "usb"
    usb.mkdir()
    copied = copy_to_usb(tracks, usb, "Test Crate", dry_run=False)
    assert len(copied) == 2
    for dest in copied:
        assert dest.exists()


def test_write_manifest(tmp_path, source_dir):
    tracks = scan_source(source_dir)
    usb = tmp_path / "usb"
    usb.mkdir()
    manifest = write_manifest(tracks, usb, "Test Crate")
    assert manifest.exists()
    content = manifest.read_text()
    assert "Test Crate" in content
    assert "track1.mp3" in content
```

### Phase 4 Acceptance Checklist
- [ ] `poetry run pytest tests/exec/test_usb_export.py` — green
- [ ] `tagslut export --help` shows `usb` subcommand
- [ ] `tagslut export usb --source <dir> --usb <dir> --crate Test --dry-run` runs without error
- [ ] `poetry run pytest` — green
- [ ] `docs/SCRIPT_SURFACE.md` updated to include `tagslut export usb`
- [ ] `README.md` updated: ffmpeg listed as system dependency

---

## Phase 5 — Gig Builder

**Goal:** Full filter-driven gig set: query inventory → transcode → USB → Rekordbox.
**Branch:** `feature/gig-builder`
**Depends on:** Phase 1, Phase 3, Phase 4
**Estimated LOC:** ~350

### 5.1 — Create `tagslut/filters/gig_filter.py`

Parses simple filter expressions into SQL WHERE clause fragments.

Supported keys: `genre`, `bpm`, `key`, `dj_flag`, `label`, `source`, `added`, `quality_rank`
Range syntax: `bpm:128-145`
Multi-value: `key:8A,9A,10A`
Comparison: `added:>2025-01-01`, `quality_rank:<=3`

```python
"""
Filter expression parser for gig set queries.

Converts a filter expression string into a safe parameterised SQL
WHERE clause for use against the `files` table.

Example:
    expr = "genre:techno bpm:128-145 dj_flag:true quality_rank:<=4"
    clause, params = parse_filter(expr)
    # clause = "canonical_genre = ? AND canonical_bpm BETWEEN ? AND ? AND is_dj_material = ? AND quality_rank <= ?"
    # params = ("techno", 128, 145, 1, 4)
"""
import re
from typing import Optional

FILTER_COLUMN_MAP = {
    "genre": "canonical_genre",
    "bpm": "canonical_bpm",
    "key": "canonical_key",
    "dj_flag": "is_dj_material",
    "label": "canonical_label",
    "source": "download_source",
    "added": "download_date",
    "quality_rank": "quality_rank",
}


class FilterParseError(ValueError):
    pass


def parse_filter(expr: str) -> tuple[str, list]:
    """
    Parse a filter expression string into a (WHERE clause, params) tuple.
    Both can be passed directly to sqlite3 execute().

    Returns ("1=1", []) for an empty expression (match all).
    """
    if not expr or not expr.strip():
        return "1=1", []

    clauses = []
    params: list = []

    for token in expr.strip().split():
        if ":" not in token:
            raise FilterParseError(f"Invalid filter token (missing colon): {token!r}")
        key, value = token.split(":", 1)
        key = key.lower()

        if key not in FILTER_COLUMN_MAP:
            raise FilterParseError(f"Unknown filter key: {key!r}. Valid: {list(FILTER_COLUMN_MAP)}")

        col = FILTER_COLUMN_MAP[key]

        # Range: bpm:128-145
        range_match = re.fullmatch(r"([\d.]+)-([\d.]+)", value)
        if range_match:
            clauses.append(f"{col} BETWEEN ? AND ?")
            params.extend([float(range_match.group(1)), float(range_match.group(2))])
            continue

        # Comparison: quality_rank:<=3
        cmp_match = re.fullmatch(r"(<=|>=|<|>|=)([\d.]+)", value)
        if cmp_match:
            op, val = cmp_match.group(1), cmp_match.group(2)
            clauses.append(f"{col} {op} ?")
            params.append(float(val))
            continue

        # Boolean: dj_flag:true
        if value.lower() in ("true", "1", "yes"):
            clauses.append(f"{col} = ?")
            params.append(1)
            continue
        if value.lower() in ("false", "0", "no"):
            clauses.append(f"{col} = ?")
            params.append(0)
            continue

        # Multi-value: key:8A,9A,10A
        if "," in value:
            placeholders = ",".join(["?"] * len(value.split(",")))
            clauses.append(f"{col} IN ({placeholders})")
            params.extend(value.split(","))
            continue

        # Date comparison: added:>2025-01-01
        date_match = re.fullmatch(r"(<=|>=|<|>)?(.+)", value)
        if date_match and date_match.group(1):
            clauses.append(f"{col} {date_match.group(1)} ?")
            params.append(date_match.group(2))
            continue

        # Plain equality
        clauses.append(f"{col} = ?")
        params.append(value)

    return " AND ".join(clauses) if clauses else "1=1", params
```

### 5.2 — Create `tagslut/exec/gig_builder.py`

```python
"""
Gig set builder: orchestrates filter → transcode → USB export pipeline.
"""
import sqlite3
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional
import logging

logger = logging.getLogger("tagslut.gig_builder")


@dataclass
class GigBuildResult:
    gig_name: str
    tracks_found: int = 0
    tracks_transcoded: int = 0
    tracks_copied: int = 0
    tracks_skipped: int = 0
    errors: List[str] = field(default_factory=list)
    manifest_path: Optional[Path] = None

    def summary(self) -> str:
        return (
            f"Gig '{self.gig_name}': "
            f"{self.tracks_found} found, "
            f"{self.tracks_transcoded} transcoded, "
            f"{self.tracks_copied} exported, "
            f"{self.tracks_skipped} skipped, "
            f"{len(self.errors)} errors"
        )


class GigBuilder:
    """
    Builds a gig set end-to-end:
      1. Query inventory for matching tracks
      2. Ensure MP3 exists for each track (transcode if needed)
      3. Copy to USB
      4. Write Rekordbox database
      5. Write manifest
      6. Register gig set in DB

    Usage:
        builder = GigBuilder(conn, dj_pool_dir=Path("~/Music/DJPool"))
        result = builder.build(
            name="Techno Set",
            filter_expr="genre:techno bpm:128-145 dj_flag:true",
            usb_path=Path("/Volumes/PIONEER_USB"),
            dry_run=True,
        )
        print(result.summary())
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        dj_pool_dir: Path,
        mp3_bitrate: int = 320,
    ) -> None:
        self._conn = conn
        self._dj_pool_dir = dj_pool_dir
        self._mp3_bitrate = mp3_bitrate

    def build(
        self,
        name: str,
        filter_expr: str,
        usb_path: Path,
        dry_run: bool = False,
    ) -> GigBuildResult:
        from tagslut.filters.gig_filter import parse_filter
        from tagslut.exec.transcoder import transcode_to_mp3, TranscodeError
        from tagslut.exec.usb_export import copy_to_usb, write_rekordbox_db, write_manifest

        result = GigBuildResult(gig_name=name)
        where, params = parse_filter(filter_expr)

        # Step 1: Query inventory
        rows = self._conn.execute(
            f"SELECT path, dj_pool_path, canonical_artist, canonical_title "
            f"FROM files WHERE {where} AND path IS NOT NULL",
            params,
        ).fetchall()

        result.tracks_found = len(rows)
        if not rows:
            logger.warning("No tracks matched filter: %s", filter_expr)
            return result

        mp3_tracks: List[Path] = []

        # Step 2: Ensure MP3 exists for each track
        for row in rows:
            flac_path = Path(row[0])
            existing_mp3 = Path(row[1]) if row[1] else None

            if existing_mp3 and existing_mp3.exists():
                mp3_tracks.append(existing_mp3)
                result.tracks_skipped += 1
                continue

            # Transcode from master FLAC
            if not flac_path.exists():
                result.errors.append(f"Master not found: {flac_path}")
                continue

            try:
                if not dry_run:
                    mp3_path = transcode_to_mp3(
                        flac_path, self._dj_pool_dir, bitrate=self._mp3_bitrate
                    )
                    # Update dj_pool_path in DB
                    self._conn.execute(
                        "UPDATE files SET dj_pool_path = ? WHERE path = ?",
                        (str(mp3_path), str(flac_path)),
                    )
                    mp3_tracks.append(mp3_path)
                else:
                    mp3_tracks.append(self._dj_pool_dir / (flac_path.stem + ".mp3"))
                result.tracks_transcoded += 1
            except TranscodeError as e:
                result.errors.append(str(e))

        # Step 3: Copy to USB
        dest_tracks = copy_to_usb(mp3_tracks, usb_path, name, dry_run=dry_run)
        result.tracks_copied = len(dest_tracks)

        # Step 4: Write Rekordbox DB
        write_rekordbox_db(dest_tracks, usb_path, name, dry_run=dry_run)

        # Step 5: Write manifest
        if not dry_run:
            result.manifest_path = write_manifest(dest_tracks, usb_path, name)

        # Step 6: Register gig set in DB
        if not dry_run:
            self._conn.execute(
                """
                INSERT INTO gig_sets (name, filter_expr, usb_path, track_count, exported_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (name, filter_expr, str(usb_path), result.tracks_copied,
                 datetime.now().isoformat()),
            )
            # Update last_exported_usb on all exported files
            for row in rows:
                self._conn.execute(
                    "UPDATE files SET last_exported_usb = ? WHERE path = ?",
                    (datetime.now().isoformat(), row[0]),
                )
            self._conn.commit()

        return result
```

### 5.3 — Create `tagslut/cli/commands/gig.py`

```python
"""tagslut gig — DJ gig set management commands."""
import click
from pathlib import Path


@click.group("gig")
def gig_group() -> None:
    """Build and manage DJ gig sets."""


@gig_group.command("build")
@click.argument("name")
@click.option("--filter", "filter_expr", default="dj_flag:true", show_default=True,
              help="Filter expression (e.g. 'genre:techno bpm:128-145 dj_flag:true')")
@click.option("--usb", required=True, type=click.Path(exists=True, path_type=Path),
              help="USB mount point")
@click.option("--dj-pool", type=click.Path(path_type=Path), default=None,
              help="DJ pool directory for MP3s (default: from config)")
@click.option("--bitrate", default=320, show_default=True, help="MP3 bitrate in kbps")
@click.option("--db", "db_path", required=True, type=click.Path(), help="Path to tagslut DB")
@click.option("--dry-run", is_flag=True)
def gig_build(name: str, filter_expr: str, usb: Path, dj_pool: Path,
              bitrate: int, db_path: str, dry_run: bool) -> None:
    """Build a gig set and export to USB."""
    from tagslut.storage.schema import get_connection
    from tagslut.exec.gig_builder import GigBuilder
    from tagslut.utils.config import get_config

    if dj_pool is None:
        config = get_config()
        dj_pool = Path(config.get("dj_pool_dir", "~/Music/DJPool")).expanduser()

    click.echo(f"Building gig: {name!r}")
    click.echo(f"Filter: {filter_expr}")
    click.echo(f"USB: {usb}")
    if dry_run:
        click.echo("[DRY RUN] No files will be written.")

    with get_connection(db_path) as conn:
        builder = GigBuilder(conn, dj_pool_dir=dj_pool, mp3_bitrate=bitrate)
        result = builder.build(name, filter_expr, usb, dry_run=dry_run)

    click.echo(result.summary())
    if result.errors:
        click.echo(f"\n{len(result.errors)} errors:")
        for err in result.errors:
            click.echo(f"  • {err}")


@gig_group.command("list")
@click.option("--db", "db_path", required=True, type=click.Path())
def gig_list(db_path: str) -> None:
    """List all saved gig sets."""
    from tagslut.storage.schema import get_connection
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT name, track_count, exported_at, usb_path FROM gig_sets ORDER BY exported_at DESC"
        ).fetchall()
    if not rows:
        click.echo("No gig sets found.")
        return
    for row in rows:
        click.echo(f"  {row[0]:<40} {row[1]:>4} tracks  {row[2] or 'never exported'}")


@gig_group.command("status")
@click.option("--usb", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--db", "db_path", required=True, type=click.Path())
def gig_status(usb: Path, db_path: str) -> None:
    """Show what's on the USB and flag stale tracks vs current inventory."""
    from tagslut.storage.schema import get_connection
    from tagslut.exec.usb_export import scan_source

    usb_tracks = scan_source(usb / "MUSIC") if (usb / "MUSIC").exists() else []
    click.echo(f"USB: {usb}")
    click.echo(f"Tracks on USB: {len(usb_tracks)}")
    # TODO: diff against last_exported_usb in DB and flag stale
    for t in usb_tracks:
        click.echo(f"  {t.name}")
```

### 5.4 — Register `gig` group in `tagslut/cli/main.py`

```python
from tagslut.cli.commands.gig import gig_group
cli.add_command(gig_group, name="gig")
```

### 5.5 — Create `tests/exec/test_gig_builder.py`

```python
import sqlite3
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from tagslut.storage.schema import init_db
from tagslut.exec.gig_builder import GigBuilder


@pytest.fixture
def db_with_dj_tracks(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    # Insert two DJ-flagged techno tracks
    for i in range(2):
        flac = tmp_path / f"track{i}.flac"
        flac.write_bytes(b"fake")
        conn.execute("""
            INSERT INTO files (
                path, checksum, duration, bit_depth, sample_rate, bitrate,
                metadata_json, quality_rank, is_dj_material, canonical_genre, canonical_bpm
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (str(flac), f"abc{i}", 300.0, 16, 44100, 0, "{}", 4, 1, "techno", 132.0))
    conn.commit()
    yield conn, tmp_path
    conn.close()


def test_gig_build_dry_run_finds_tracks(db_with_dj_tracks, tmp_path):
    conn, src = db_with_dj_tracks
    usb = tmp_path / "usb"
    usb.mkdir()
    pool = tmp_path / "pool"
    pool.mkdir()

    with patch("tagslut.exec.gig_builder.transcode_to_mp3") as mock_t, \
         patch("tagslut.exec.gig_builder.copy_to_usb", return_value=[]) as mock_c, \
         patch("tagslut.exec.gig_builder.write_rekordbox_db"), \
         patch("tagslut.exec.gig_builder.write_manifest"):
        builder = GigBuilder(conn, dj_pool_dir=pool)
        result = builder.build("Test Gig", "dj_flag:true", usb, dry_run=True)

    assert result.tracks_found == 2
    assert result.gig_name == "Test Gig"
    mock_t.assert_not_called()  # dry_run=True


def test_gig_build_no_match_returns_zero(db_with_dj_tracks, tmp_path):
    conn, _ = db_with_dj_tracks
    usb = tmp_path / "usb"
    usb.mkdir()
    builder = GigBuilder(conn, dj_pool_dir=tmp_path / "pool")
    result = builder.build("Empty", "genre:jazz", usb, dry_run=True)
    assert result.tracks_found == 0
```

### Phase 5 Acceptance Checklist
- [ ] `poetry run pytest tests/exec/test_gig_builder.py` — green
- [ ] `tagslut gig --help` shows `build`, `list`, `status`
- [ ] `tagslut gig build "Test" --filter "dj_flag:true" --usb /tmp --db <db> --dry-run` runs
- [ ] `poetry run pytest` — green
- [ ] `docs/SCRIPT_SURFACE.md` updated

---

## Phase 6 — Rekordbox Write-Back

**Goal:** After a gig, sync BPM/key/cue analysis from USB back to master FLAC tags.
**Branch:** `feature/rekordbox-sync`
**Depends on:** Phase 4
**Estimated LOC:** ~150

### 6.1 — Create `tagslut/metadata/rekordbox_sync.py`

```python
"""
Rekordbox write-back: reads Pioneer USB database and syncs
confirmed BPM, key, and play count back to master FLAC tags and inventory DB.

Rekordbox is the ONLY confirmation source for BPM and key.
Master FLAC tags are updated in-place (BPM/key fields only — no other fields touched).
"""
import sqlite3
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger("tagslut.rekordbox_sync")


def sync_from_usb(
    usb_path: Path,
    conn: sqlite3.Connection,
    dry_run: bool = False,
) -> dict:
    """
    Read the Rekordbox database from USB and write confirmed metadata
    back to master FLAC tags and the tagslut inventory.

    Returns a summary dict: {updated: int, not_found: int, errors: list}
    """
    try:
        import pyrekordbox  # type: ignore
    except ImportError as e:
        raise ImportError("pyrekordbox required. Run: poetry add pyrekordbox") from e

    pioneer_db_path = usb_path / "PIONEER" / "rekordbox.db"
    if not pioneer_db_path.exists():
        raise FileNotFoundError(f"No Rekordbox DB found at {pioneer_db_path}")

    summary = {"updated": 0, "not_found": 0, "errors": []}

    try:
        db = pyrekordbox.Rb6Database(pioneer_db_path)
        tracks = db.get_tracks()  # returns list of track objects
    except Exception as e:
        raise RuntimeError(f"Failed to read Rekordbox DB: {e}") from e

    for rb_track in tracks:
        path = getattr(rb_track, "path", None) or getattr(rb_track, "file_path", None)
        bpm = getattr(rb_track, "bpm", None)
        key = getattr(rb_track, "key", None)
        rb_id = getattr(rb_track, "id", None)

        if not path:
            continue

        # Find matching master FLAC in inventory by USB path → gig_set_tracks lookup
        row = conn.execute(
            "SELECT file_path FROM gig_set_tracks WHERE usb_dest_path = ?",
            (str(path),),
        ).fetchone()

        if not row:
            # Fallback: match by filename stem
            stem = Path(path).stem
            row = conn.execute(
                "SELECT path FROM files WHERE path LIKE ?",
                (f"%{stem}%",),
            ).fetchone()

        if not row:
            summary["not_found"] += 1
            continue

        master_path = Path(row[0])
        if not master_path.exists():
            summary["errors"].append(f"Master not found: {master_path}")
            continue

        if not dry_run:
            _write_bpm_key_to_flac(master_path, bpm, key)
            conn.execute(
                """
                UPDATE files
                SET canonical_bpm = COALESCE(?, canonical_bpm),
                    canonical_key = COALESCE(?, canonical_key),
                    rekordbox_id  = COALESCE(?, rekordbox_id)
                WHERE path = ?
                """,
                (float(bpm) if bpm else None, str(key) if key else None,
                 rb_id, str(master_path)),
            )

        summary["updated"] += 1
        logger.info("Synced: %s (BPM=%s key=%s)", master_path.name, bpm, key)

    if not dry_run:
        conn.commit()

    return summary


def _write_bpm_key_to_flac(
    path: Path, bpm: Optional[float], key: Optional[str]
) -> None:
    """Write BPM and key to FLAC tags. Only modifies these two fields."""
    if bpm is None and key is None:
        return
    try:
        from mutagen.flac import FLAC
        f = FLAC(path)
        if bpm is not None:
            f["bpm"] = [str(round(bpm, 2))]
        if key is not None:
            f["initialkey"] = [key]
        f.save()
        logger.debug("Tagged: %s BPM=%s key=%s", path.name, bpm, key)
    except Exception as e:
        logger.error("Failed to write tags to %s: %s", path, e)
```

### 6.2 — Add `rekordbox-sync` to `tagslut/cli/commands/index.py`

Add a new command to the existing `index` group:

```python
@index.command("rekordbox-sync")
@click.option("--usb", required=True, type=click.Path(exists=True, path_type=Path),
              help="USB mount point containing PIONEER/ database")
@click.option("--db", "db_path", required=True, type=click.Path())
@click.option("--dry-run", is_flag=True)
def rekordbox_sync(usb: Path, db_path: str, dry_run: bool) -> None:
    """Sync BPM, key, and Rekordbox IDs from USB back to master library."""
    from tagslut.storage.schema import get_connection
    from tagslut.metadata.rekordbox_sync import sync_from_usb

    with get_connection(db_path) as conn:
        summary = sync_from_usb(usb, conn, dry_run=dry_run)

    prefix = "[DRY RUN] " if dry_run else ""
    click.echo(f"{prefix}Rekordbox sync: {summary['updated']} updated, "
               f"{summary['not_found']} not found, {len(summary['errors'])} errors")
    for err in summary["errors"]:
        click.echo(f"  • {err}")
```

### Phase 6 Acceptance Checklist
- [ ] `tagslut index rekordbox-sync --help` works
- [ ] `poetry run pytest` — green
- [ ] `poetry run mypy tagslut/metadata/rekordbox_sync.py` — clean

---

## Final Acceptance (All Phases)

```bash
# Full test suite green
poetry run pytest -v

# Lint clean
poetry run flake8 tagslut/ tests/

# Type check (existing errors acceptable, no new errors introduced)
poetry run mypy tagslut/core/quality.py \
              tagslut/filters/identity_resolver.py \
              tagslut/core/pre_flight.py \
              tagslut/exec/transcoder.py \
              tagslut/exec/usb_export.py \
              tagslut/exec/gig_builder.py \
              tagslut/filters/gig_filter.py \
              tagslut/metadata/rekordbox_sync.py

# CLI smoke test
tagslut --help           # shows all groups including gig, export
tagslut gig --help       # shows build, list, status
tagslut export --help    # shows usb
```

---

## New Command Surface Summary

```
tagslut export usb     --source <dir> --usb <mount> --crate <name> [--dry-run]
tagslut gig build      <name> --filter <expr> --usb <mount> --db <db> [--dry-run]
tagslut gig list       --db <db>
tagslut gig status     --usb <mount> --db <db>
tagslut index rekordbox-sync  --usb <mount> --db <db> [--dry-run]
```

---

*This plan is the implementation authority for issues #98, #99, #100.*
*Evaluator reviews each phase before the next begins.*
*Last updated: February 2026.*
