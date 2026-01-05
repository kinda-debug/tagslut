import os
from pathlib import Path

# --- File Contents Definitions ---

MODELS_PY = """
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional, List, Dict, Any

@dataclass
class AudioFile:
    \"\"\"
    Canonical representation of a FLAC file in the system.
    \"\"\"
    path: Path
    checksum: str
    duration: float
    bit_depth: int
    sample_rate: int
    bitrate: int
    metadata: Dict[str, Any]
    flac_ok: bool
    acoustid: Optional[str] = None

    def __post_init__(self):
        # Ensure path is always a Path object
        if isinstance(self.path, str):
            self.path = Path(self.path)

@dataclass
class DuplicateGroup:
    \"\"\"
    Represents a group of potential duplicates identified by a specific strategy.
    \"\"\"
    group_id: str
    files: List[AudioFile]
    similarity: float
    source: Literal["checksum", "acoustid", "dupeguru"]

@dataclass
class Decision:
    \"\"\"
    A concrete action to be taken on a specific file.
    \"\"\"
    file: AudioFile
    action: Literal["KEEP", "DROP", "REVIEW"]
    reason: str
    confidence: Literal["HIGH", "MEDIUM", "LOW"]
    evidence: Dict[str, Any] = field(default_factory=dict)
"""

CONFIG_PY = """
import logging
from pathlib import Path
from typing import Any, Dict

# Prefer standard library tomllib (Python 3.11+)
try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore

# Default locations to check for config
CONFIG_PATHS = [
    Path("config.toml"),
    Path.home() / ".config" / "dedupe" / "config.toml",
]

class Config:
    _instance = None
    _data: Dict[str, Any] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Config, cls).__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self):
        \"\"\"Load configuration from the first found valid source.\"\"\"
        loaded = False
        for path in CONFIG_PATHS:
            if path.exists():
                try:
                    with open(path, "rb") as f:
                        self._data = tomllib.load(f)
                    logging.info(f"Loaded configuration from {path}")
                    loaded = True
                    break
                except Exception as e:
                    logging.error(f"Failed to parse config at {path}: {e}")

        if not loaded:
            logging.warning("No configuration file found. Using defaults.")
            self._data = {}

    def get(self, key: str, default: Any = None) -> Any:
        \"\"\"Retrieve a configuration value by key (dot notation supported).\"\"\"
        keys = key.split(".")
        value = self._data
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default

def get_config() -> Config:
    \"\"\"Public accessor for the singleton configuration.\"\"\"
    return Config()
"""

LOGGING_PY = """
import logging
import sys
from pathlib import Path

def setup_logger(name: str = "dedupe", level: int = logging.INFO, log_file: Path = None) -> logging.Logger:
    \"\"\"
    Configures a structured logger that outputs to stderr and optionally a file.
    \"\"\"
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False  # Prevent double logging if root logger is configured

    # Clear existing handlers
    if logger.hasHandlers():
        logger.handlers.clear()

    # Formatter
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(module)s:%(funcName)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console Handler (Stderr)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File Handler
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger

# Default logger instance
logger = setup_logger()
"""

INTEGRITY_PY = """
import subprocess
import logging
from pathlib import Path
from typing import Tuple

logger = logging.getLogger("dedupe")

def check_flac_integrity(file_path: Path) -> Tuple[bool, str]:
    \"\"\"
    Verifies the integrity of a FLAC file using the official `flac -t` command.

    Args:
        file_path: Path to the FLAC file.

    Returns:
        Tuple[bool, str]: (True if OK, raw stderr output for logging).
    \"\"\"
    if not file_path.exists():
        msg = f"File not found: {file_path}"
        logger.error(msg)
        return False, msg

    try:
        # Run flac -t (test) silently
        # We capture stderr because that's where flac prints errors
        result = subprocess.run(
            ["flac", "-t", "--silent", str(file_path)],
            capture_output=True,
            text=True,
            check=False 
        )

        if result.returncode == 0:
            return True, ""
        
        error_msg = result.stderr.strip() or "Unknown FLAC error"
        logger.warning(f"Integrity check failed for {file_path}: {error_msg}")
        return False, error_msg

    except FileNotFoundError:
        logger.critical("The 'flac' executable is not found in PATH.")
        raise RuntimeError("flac binary missing")
    except Exception as e:
        logger.error(f"Unexpected error checking integrity for {file_path}: {e}")
        return False, str(e)
"""

HASHING_PY = """
import hashlib
import logging
from pathlib import Path

logger = logging.getLogger("dedupe")

def calculate_file_hash(file_path: Path, block_size: int = 65536) -> str:
    \"\"\"
    Calculates the SHA-256 checksum of a file's content.
    Used for strict deduplication (bit-exact matches).
    
    Args:
        file_path: Path to the file.
        block_size: Size of chunks to read into memory (default 64KB).
    
    Returns:
        Hexadecimal string of the hash.
    \"\"\"
    sha256 = hashlib.sha256()
    
    try:
        with open(file_path, "rb") as f:
            while chunk := f.read(block_size):
                sha256.update(chunk)
        
        return sha256.hexdigest()
    
    except OSError as e:
        logger.error(f"Failed to hash {file_path}: {e}")
        raise
"""

METADATA_PY = """
import logging
from pathlib import Path
from typing import Dict, Any

import mutagen
from mutagen.flac import FLAC, FLACNoHeaderError

from dedupe.storage.models import AudioFile
from dedupe.core.integrity import check_flac_integrity
from dedupe.core.hashing import calculate_file_hash

logger = logging.getLogger("dedupe")

def extract_metadata(file_path: Path, scan_integrity: bool = False, scan_hash: bool = False) -> AudioFile:
    \"\"\"
    Extracts technical and tag metadata from a FLAC file and returns a populated AudioFile.

    Args:
        file_path: Path to the FLAC file.
        scan_integrity: If True, runs `flac -t` immediately (expensive).
        scan_hash: If True, calculates SHA-256 immediately (expensive).

    Returns:
        AudioFile object.
    
    Raises:
        ValueError: If file is not a valid FLAC or cannot be read.
    \"\"\"
    path_obj = Path(file_path)
    
    # Defaults
    flac_ok = False
    checksum = "NOT_SCANNED"
    duration = 0.0
    bit_depth = 0
    sample_rate = 0
    bitrate = 0
    tags: Dict[str, Any] = {}

    # Optional expensive checks
    if scan_integrity:
        flac_ok, _ = check_flac_integrity(path_obj)
    
    if scan_hash:
        checksum = calculate_file_hash(path_obj)

    try:
        audio = FLAC(path_obj)
        
        # Technical details
        if audio.info:
            duration = getattr(audio.info, 'length', 0.0)
            bit_depth = getattr(audio.info, 'bits_per_sample', 0)
            sample_rate = getattr(audio.info, 'sample_rate', 0)
            bitrate = getattr(audio.info, 'bitrate', 0)
        
        # Tag extraction
        if audio.tags:
            tags = {k.lower(): v[0] if isinstance(v, list) and len(v) == 1 else v 
                    for k, v in audio.tags.items()}

        # If we didn't run explicit integrity check, standard load implies basic header health
        if not scan_integrity:
            flac_ok = True 

    except FLACNoHeaderError:
        logger.error(f"No FLAC header found: {path_obj}")
        flac_ok = False
    except mutagen.MutagenError as e:
        logger.error(f"Mutagen error reading {path_obj}: {e}")
        flac_ok = False
    except Exception as e:
        logger.error(f"Unexpected error reading metadata for {path_obj}: {e}")
        raise ValueError(f"Failed to read metadata: {e}")

    return AudioFile(
        path=path_obj,
        checksum=checksum,
        duration=duration,
        bit_depth=bit_depth,
        sample_rate=sample_rate,
        bitrate=bitrate,
        metadata=tags,
        flac_ok=flac_ok
    )
"""

CORE_INIT_PY = """
\"\"\"
dedupe.core
-----------
Pure business logic for the FLAC deduplication system.
This module contains no direct user interaction or CLI logic.
\"\"\"

from dedupe.core.metadata import extract_metadata
from dedupe.core.integrity import check_flac_integrity
from dedupe.core.hashing import calculate_file_hash

__all__ = [
    "extract_metadata",
    "check_flac_integrity",
    "calculate_file_hash",
]
"""

SCHEMA_PY = """
import sqlite3
import logging
from pathlib import Path
from typing import List

logger = logging.getLogger("dedupe")

def get_connection(db_path: Path) -> sqlite3.Connection:
    \"\"\"
    Establishes a connection to the SQLite database.
    Sets row_factory to sqlite3.Row for name-based access.
    \"\"\"
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logger.error(f"Failed to connect to database at {db_path}: {e}")
        raise

def init_db(conn: sqlite3.Connection) -> None:
    \"\"\"
    Initializes the database schema.
    Performs additive migrations: creates the table if missing,
    and adds missing columns if the table exists but is outdated.
    \"\"\"
    # Enable Write-Ahead Logging for better concurrency
    conn.execute("PRAGMA journal_mode=WAL;")
    
    # 1. Create table if it doesn't exist
    conn.execute(\"\"\"
    CREATE TABLE IF NOT EXISTS files (
        path TEXT PRIMARY KEY,
        checksum TEXT,
        duration REAL,
        bit_depth INTEGER,
        sample_rate INTEGER,
        bitrate INTEGER,
        metadata_json TEXT,
        flac_ok INTEGER,
        acoustid TEXT
    );
    \"\"\")
    
    # 2. Additive Migrations: Ensure all required columns exist
    existing_columns = _get_existing_columns(conn, "files")
    required_columns = {
        "checksum": "TEXT",
        "duration": "REAL",
        "bit_depth": "INTEGER",
        "sample_rate": "INTEGER",
        "bitrate": "INTEGER",
        "metadata_json": "TEXT",
        "flac_ok": "INTEGER",
        "acoustid": "TEXT"
    }

    for col_name, col_type in required_columns.items():
        if col_name not in existing_columns:
            logger.info(f"Migrating DB: Adding column '{col_name}' to 'files' table.")
            try:
                conn.execute(f"ALTER TABLE files ADD COLUMN {col_name} {col_type}")
            except sqlite3.OperationalError as e:
                logger.error(f"Migration failed for column {col_name}: {e}")
                raise

    # 3. Indices for performance
    conn.execute("CREATE INDEX IF NOT EXISTS idx_checksum ON files(checksum);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_acoustid ON files(acoustid);")
    
    conn.commit()

def _get_existing_columns(conn: sqlite3.Connection, table_name: str) -> List[str]:
    \"\"\"Helper to retrieve a list of column names for a table.\"\"\"
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    return [row["name"] for row in cursor.fetchall()]
"""

QUERIES_PY = """
import sqlite3
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

from dedupe.storage.models import AudioFile

logger = logging.getLogger("dedupe")

def upsert_file(conn: sqlite3.Connection, file: AudioFile) -> None:
    \"\"\"
    Inserts or Updates a file record in the database.
    Uses 'path' as the unique key.
    \"\"\"
    query = \"\"\"
    INSERT INTO files (
        path, checksum, duration, bit_depth, sample_rate, bitrate, 
        metadata_json, flac_ok, acoustid
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(path) DO UPDATE SET
        checksum=excluded.checksum,
        duration=excluded.duration,
        bit_depth=excluded.bit_depth,
        sample_rate=excluded.sample_rate,
        bitrate=excluded.bitrate,
        metadata_json=excluded.metadata_json,
        flac_ok=excluded.flac_ok,
        acoustid=excluded.acoustid;
    \"\"\"
    
    # Serialize metadata to JSON for storage
    meta_json = json.dumps(file.metadata)
    
    try:
        conn.execute(query, (
            str(file.path),
            file.checksum,
            file.duration,
            file.bit_depth,
            file.sample_rate,
            file.bitrate,
            meta_json,
            1 if file.flac_ok else 0,
            file.acoustid
        ))
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"DB Error upserting {file.path}: {e}")
        raise

def get_file(conn: sqlite3.Connection, path: Path) -> Optional[AudioFile]:
    \"\"\"Retrieve a single file by path.\"\"\"
    cursor = conn.execute("SELECT * FROM files WHERE path = ?", (str(path),))
    row = cursor.fetchone()
    if not row:
        return None
    
    return _row_to_audiofile(row)

def get_files_by_checksum(conn: sqlite3.Connection, checksum: str) -> List[AudioFile]:
    \"\"\"Retrieve all files matching a specific checksum.\"\"\"
    cursor = conn.execute("SELECT * FROM files WHERE checksum = ?", (checksum,))
    return [_row_to_audiofile(row) for row in cursor.fetchall()]

def get_all_checksums(conn: sqlite3.Connection) -> List[str]:
    \"\"\"Retrieve all unique checksums present in the DB.\"\"\"
    cursor = conn.execute("SELECT DISTINCT checksum FROM files WHERE checksum IS NOT NULL")
    return [row["checksum"] for row in cursor.fetchall()]

def _row_to_audiofile(row: sqlite3.Row) -> AudioFile:
    \"\"\"Helper to convert a DB row back to an AudioFile object.\"\"\"
    # Handle JSON deserialization safely
    meta_json = row["metadata_json"]
    metadata: Dict[str, Any] = {}
    if meta_json:
        try:
            metadata = json.loads(meta_json)
        except json.JSONDecodeError:
            logger.warning(f"Corrupt metadata JSON for {row['path']}")
            metadata = {}

    return AudioFile(
        path=Path(row["path"]),
        checksum=row["checksum"],
        duration=row["duration"],
        bit_depth=row["bit_depth"],
        sample_rate=row["sample_rate"],
        bitrate=row["bitrate"],
        metadata=metadata,
        flac_ok=bool(row["flac_ok"]),
        acoustid=row["acoustid"]
    )
"""

PATHS_PY = """
import logging
import os
from pathlib import Path
from typing import Iterator, Set, Union

logger = logging.getLogger("dedupe")

def list_files(root: Union[str, Path], extensions: Set[str], recursive: bool = True) -> Iterator[Path]:
    \"\"\"
    Yields paths to files within root matching the given extensions (case-insensitive).
    \"\"\"
    root_path = Path(root).resolve()
    
    if not root_path.exists():
        logger.error(f"Root path does not exist: {root_path}")
        return

    # Normalize extensions to lowercase
    valid_exts = {e.lower() for e in extensions}

    try:
        if recursive:
            for dirpath, _, filenames in os.walk(root_path):
                for f in filenames:
                    if Path(f).suffix.lower() in valid_exts:
                        yield Path(dirpath) / f
        else:
            for item in root_path.iterdir():
                if item.is_file() and item.suffix.lower() in valid_exts:
                    yield item
    except OSError as e:
        logger.error(f"Error traversing {root_path}: {e}")

def sanitize_path(path: Union[str, Path]) -> Path:
    \"\"\"Returns a resolved, absolute Path object.\"\"\"
    return Path(path).resolve()
"""

PARALLEL_PY = """
import concurrent.futures
import logging
import multiprocessing
from typing import Callable, Iterable, List, TypeVar, Any, Optional

logger = logging.getLogger("dedupe")

T = TypeVar("T")
R = TypeVar("R")

def process_map(
    func: Callable[[T], R],
    items: Iterable[T],
    max_workers: Optional[int] = None,
    chunk_size: int = 1
) -> List[R]:
    \"\"\"
    Applies `func` to every item in `items` using a process pool.
    \"\"\"
    if max_workers is None:
        # Leave one core free for system/DB ops
        max_workers = max(1, multiprocessing.cpu_count() - 1)

    results: List[R] = []
    
    item_list = list(items) 
    if not item_list:
        return []

    logger.info(f"Starting parallel processing with {max_workers} workers for {len(item_list)} items.")

    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
            # We use map to maintain order
            results_iter = executor.map(func, item_list, chunksize=chunk_size)
            results = list(results_iter)
    except KeyboardInterrupt:
        logger.warning("Parallel processing interrupted by user.")
        raise
    except Exception as e:
        logger.error(f"Parallel processing failed: {e}")
        raise

    return results
"""

SCANNER_PY = """
import logging
import time
from pathlib import Path
from typing import List, Optional

from dedupe.core.metadata import extract_metadata
from dedupe.storage.models import AudioFile
from dedupe.storage.queries import upsert_file
from dedupe.storage.schema import get_connection, init_db
from dedupe.utils.paths import list_files
from dedupe.utils.parallel import process_map
from dedupe.utils.config import get_config

logger = logging.getLogger("dedupe")

def scan_library(
    library_path: Path, 
    db_path: Path,
    scan_integrity: bool = False,
    scan_hash: bool = False,
    recheck: bool = False
) -> None:
    \"\"\"
    Scans a library folder and updates the SQLite database.

    Args:
        library_path: Root folder to scan.
        db_path: Path to the SQLite database.
        scan_integrity: Run 'flac -t' on files.
        scan_hash: Calculate SHA256 checksums.
        recheck: If True, re-scan files even if they are in DB (not fully impl yet).
    \"\"\"
    config = get_config()
    workers = config.get("integrity.parallel_workers", None)

    logger.info(f"Scanning library: {library_path}")
    
    # 1. Initialize DB
    conn = get_connection(db_path)
    init_db(conn)
    conn.close() 

    # 2. Find files
    flac_files = list(list_files(library_path, {".flac"}))
    logger.info(f"Found {len(flac_files)} FLAC files.")

    if not flac_files:
        return

    # 3. Define the worker function (must be pickleable)
    def process_one(path: Path) -> Optional[AudioFile]:
        try:
            return extract_metadata(
                path, 
                scan_integrity=scan_integrity, 
                scan_hash=scan_hash
            )
        except Exception as e:
            logger.error(f"Failed to process {path}: {e}")
            return None

    # 4. Run Parallel Extraction
    start_time = time.time()
    results = process_map(process_one, flac_files, max_workers=workers)
    duration = time.time() - start_time
    
    logger.info(f"Metadata extraction complete in {duration:.2f}s")

    # 5. Write to DB (Serial operation)
    conn = get_connection(db_path)
    count = 0
    try:
        with conn: 
            for audio_file in results:
                if audio_file:
                    upsert_file(conn, audio_file)
                    count += 1
        logger.info(f"Upserted {count} records to database.")
    except Exception as e:
        logger.error(f"Database write failed: {e}")
    finally:
        conn.close()
"""

MATCHING_PY = """
import logging
import sqlite3
from typing import Iterator, List

from dedupe.storage.models import AudioFile, DuplicateGroup
from dedupe.storage.queries import _row_to_audiofile

logger = logging.getLogger("dedupe")

def find_exact_duplicates(conn: sqlite3.Connection) -> Iterator[DuplicateGroup]:
    \"\"\"
    Yields groups of files that share the exact same checksum.
    Only groups with >1 file are returned.
    \"\"\"
    # 1. Find checksums that appear more than once
    query_hashes = \"\"\"
    SELECT checksum, COUNT(*) as cnt
    FROM files
    WHERE checksum IS NOT NULL AND checksum != 'NOT_SCANNED'
    GROUP BY checksum
    HAVING cnt > 1
    \"\"\"
    
    try:
        cursor = conn.execute(query_hashes)
        duplicate_hashes = [row["checksum"] for row in cursor.fetchall()]
        
        for checksum in duplicate_hashes:
            # 2. Get all files for this checksum
            files_cursor = conn.execute(
                "SELECT * FROM files WHERE checksum = ?", 
                (checksum,)
            )
            files = [_row_to_audiofile(row) for row in files_cursor.fetchall()]
            
            if len(files) > 1:
                yield DuplicateGroup(
                    group_id=checksum,
                    files=files,
                    similarity=1.0,
                    source="checksum"
                )
                
    except sqlite3.Error as e:
        logger.error(f"Database error during matching: {e}")
"""

DECISIONS_PY = """
import logging
from typing import List, Tuple, Optional
from dedupe.storage.models import AudioFile, DuplicateGroup, Decision

logger = logging.getLogger("dedupe")

# Configuration for library priority (lower index = higher priority)
DEFAULT_PRIORITY = ["accepted", "staging"]

def get_library_priority(path: str, priorities: List[str]) -> int:
    \"\"\"Returns a sortable priority index for a file path.\"\"\"
    path_str = str(path)
    for i, keyword in enumerate(priorities):
        if keyword in path_str:
            return i
    return 999  # No match (lowest priority)

def assess_duplicate_group(group: DuplicateGroup, priority_order: List[str] = None) -> List[Decision]:
    \"\"\"
    Analyzes a group of duplicates and returns a decision for each file.
    \"\"\"
    if not group.files:
        return []

    priorities = priority_order or DEFAULT_PRIORITY
    
    def sort_key(f: AudioFile):
        # 1. Integrity 
        score_integrity = 1 if f.flac_ok else 0
        # 2. Priority 
        score_priority = -get_library_priority(f.path, priorities) 
        # 3. Technical Quality
        score_tech = (f.sample_rate, f.bit_depth, f.bitrate)
        # 4. Path preference (Shorter path usually means less nested/cluttered)
        score_path_len = -len(str(f.path))
        
        return (score_integrity, score_priority, score_tech, score_path_len)

    # Sort descending (best first)
    sorted_files = sorted(group.files, key=sort_key, reverse=True)
    best_file = sorted_files[0]
    
    decisions = []
    
    for f in sorted_files:
        if f.path == best_file.path:
            # The Winner
            action = "KEEP"
            reason = "Best match based on integrity, library priority, and quality."
            confidence = "HIGH"
            
            # Downgrade confidence if integrity is bad even for the winner
            if not f.flac_ok:
                action = "REVIEW"
                reason = "Best file available, but failed integrity check."
                confidence = "LOW"
                
        else:
            # The Losers
            action = "DROP"
            confidence = "HIGH"
            reason = f"Duplicate of {best_file.path.name}"

        decisions.append(Decision(
            file=f,
            action=action,
            reason=reason,
            confidence=confidence,
            evidence={
                "group_source": group.source, 
                "rank_index": sorted_files.index(f)
            }
        ))
        
    return decisions
"""

ACTIONS_PY = """
import logging
import os
import shutil
from pathlib import Path
from typing import Tuple

logger = logging.getLogger("dedupe")

def delete_file(path: Path, dry_run: bool = True) -> Tuple[bool, str]:
    \"\"\"
    Safely deletes a file.
    
    Args:
        path: Path to the file.
        dry_run: If True, only logs the action.
        
    Returns:
        Tuple[bool, str]: (Success, Message)
    \"\"\"
    if not path.exists():
        msg = f"File not found: {path}"
        logger.warning(msg)
        return False, msg

    if dry_run:
        logger.info(f"[DRY RUN] Would delete: {path}")
        return True, "Dry run simulated deletion"

    try:
        os.remove(path)
        logger.info(f"Deleted: {path}")
        return True, "Deleted"
    except OSError as e:
        msg = f"Failed to delete {path}: {e}"
        logger.error(msg)
        return False, msg

def move_file(src: Path, dest: Path, dry_run: bool = True) -> Tuple[bool, str]:
    \"\"\"
    Safely moves a file.
    \"\"\"
    if not src.exists():
        return False, f"Source not found: {src}"
    
    if dest.exists():
        return False, f"Destination exists: {dest}"

    if dry_run:
        logger.info(f"[DRY RUN] Would move: {src} -> {dest}")
        return True, "Dry run simulated move"

    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(src, dest)
        logger.info(f"Moved: {src} -> {dest}")
        return True, "Moved"
    except OSError as e:
        msg = f"Failed to move {src}: {e}"
        logger.error(msg)
        return False, msg
"""

CLI_HELPER_PY = """
import logging
import sys
from pathlib import Path
from typing import Optional

# Attempt to import click, handle if missing
try:
    import click
except ImportError:
    print("Error: 'click' is required. Please install it via pip.", file=sys.stderr)
    sys.exit(1)

from dedupe.utils.logging import setup_logger
from dedupe.utils.config import get_config

def common_options(func):
    \"\"\"Decorator to add common CLI options (verbose, config, etc).\"\"\"
    func = click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")(func)
    func = click.option("--config", "-c", type=click.Path(exists=True), help="Path to config file")(func)
    return func

def configure_execution(verbose: bool, config_path: Optional[str] = None):
    \"\"\"Sets up logging and config based on CLI args.\"\"\"
    level = logging.DEBUG if verbose else logging.INFO
    setup_logger(level=level)
    
    if config_path:
        logging.info(f"Custom config path provided: {config_path}")
"""

SCAN_TOOL_PY = """
import sys
import click
from pathlib import Path

# Ensure we can import dedupe from root
sys.path.insert(0, str(Path(__file__).parents[2]))

from dedupe.scanner import scan_library
from dedupe.utils.cli_helper import common_options, configure_execution

@click.command()
@click.argument("library_path", type=click.Path(exists=True, file_okay=False))
@click.option("--db", required=True, type=click.Path(dir_okay=False), help="Path to SQLite database")
@click.option("--check-integrity/--no-check-integrity", default=False, help="Run flac -t verification")
@click.option("--check-hash/--no-check-hash", default=True, help="Calculate SHA256 checksums")
@common_options
def scan(library_path, db, check_integrity, check_hash, verbose, config):
    \"\"\"
    Scans a library folder for FLAC files and populates the database.
    \"\"\"
    configure_execution(verbose, config)
    
    lib_path = Path(library_path)
    db_path = Path(db)
    
    click.echo(f"Scanning Library: {lib_path}")
    click.echo(f"Database: {db_path}")
    click.echo(f"Integrity Check: {'ON' if check_integrity else 'OFF'}")
    click.echo(f"Hash Calculation: {'ON' if check_hash else 'OFF'}")
    
    try:
        scan_library(
            library_path=lib_path,
            db_path=db_path,
            scan_integrity=check_integrity,
            scan_hash=check_hash
        )
        click.echo(click.style("Scan complete.", fg="green"))
    except Exception as e:
        click.echo(click.style(f"Scan failed: {e}", fg="red"), err=True)
        sys.exit(1)

if __name__ == "__main__":
    scan()
"""

RECOMMEND_TOOL_PY = """
import sys
import json
import click
import logging
from pathlib import Path
from typing import List, Dict, Any

# Ensure imports work
sys.path.insert(0, str(Path(__file__).parents[2]))

from dedupe.storage.schema import get_connection
from dedupe.core.matching import find_exact_duplicates
from dedupe.core.decisions import assess_duplicate_group
from dedupe.utils.cli_helper import common_options, configure_execution
from dedupe.utils.config import get_config

@click.command()
@click.option("--db", required=True, type=click.Path(exists=True, dir_okay=False), help="Path to SQLite database")
@click.option("--output", "-o", type=click.Path(writable=True), help="Output JSON file for the plan")
@click.option("--priority", "-p", multiple=True, help="Zone priority order (e.g. -p accepted -p staging).")
@common_options
def recommend(db, output, priority, verbose, config):
    \"\"\"
    Analyzes duplicates in the DB and recommends KEEP/DROP actions.
    Outputs a JSON plan.
    \"\"\"
    configure_execution(verbose, config)
    logger = logging.getLogger("dedupe")
    
    # Load config priorities if not overridden
    if not priority:
        app_config = get_config()
        priority = app_config.get("decisions.zone_priority", ["accepted", "staging"])

    logger.info(f"Using priority order: {priority}")

    conn = get_connection(Path(db))
    
    # 1. Find Duplicates
    logger.info("Searching for exact duplicates...")
    groups = list(find_exact_duplicates(conn))
    logger.info(f"Found {len(groups)} duplicate groups.")

    plan_entries = []
    
    # 2. Make Decisions
    for group in groups:
        decisions = assess_duplicate_group(group, priority_order=list(priority))
        
        # Convert Decision objects to JSON-serializable dicts
        group_entry = {
            "group_id": group.group_id,
            "similarity": group.similarity,
            "decisions": []
        }
        
        for d in decisions:
            group_entry["decisions"].append({
                "path": str(d.file.path),
                "action": d.action,
                "reason": d.reason,
                "confidence": d.confidence,
                "file_details": {
                    "flac_ok": d.file.flac_ok,
                    "bitrate": d.file.bitrate,
                    "sample_rate": d.file.sample_rate
                }
            })
        
        plan_entries.append(group_entry)

    # 3. Output
    summary = {
        "groups_count": len(plan_entries),
        "zone_priority": priority,
        "plan": plan_entries
    }

    if output:
        with open(output, "w") as f:
            json.dump(summary, f, indent=2)
        click.echo(f"Plan saved to {output}")
    else:
        # Print a friendly summary to stdout
        click.echo(json.dumps(summary, indent=2))
        
    conn.close()

if __name__ == "__main__":
    recommend()
"""

APPLY_TOOL_PY = """
import sys
import json
import click
import logging
from pathlib import Path

# Ensure imports work
sys.path.insert(0, str(Path(__file__).parents[2]))

from dedupe.core.actions import delete_file
from dedupe.utils.cli_helper import common_options, configure_execution

@click.command()
@click.argument("plan_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--dry-run/--execute", default=True, help="Simulate actions (default) or actually delete files")
@common_options
def apply(plan_file, dry_run, verbose, config):
    \"\"\"
    Executes a deduplication plan generated by 'recommend'.
    \"\"\"
    configure_execution(verbose, config)
    logger = logging.getLogger("dedupe")
    
    with open(plan_file, "r") as f:
        data = json.load(f)
        
    groups = data.get("plan", [])
    logger.info(f"Loaded plan with {len(groups)} groups.")
    
    stats = {"kept": 0, "dropped": 0, "reviewed": 0, "errors": 0}

    if dry_run:
        click.secho("--- DRY RUN MODE: No files will be touched ---", fg="yellow")

    for group in groups:
        for decision in group["decisions"]:
            path = Path(decision["path"])
            action = decision["action"]
            
            if action == "DROP":
                if decision["confidence"] == "LOW":
                    logger.warning(f"Skipping LOW confidence DROP for {path}")
                    stats["reviewed"] += 1
                    continue

                success, msg = delete_file(path, dry_run=dry_run)
                if success:
                    stats["dropped"] += 1
                else:
                    stats["errors"] += 1
                    
            elif action == "KEEP":
                stats["kept"] += 1
                
            elif action == "REVIEW":
                logger.info(f"Skipping REVIEW item: {path}")
                stats["reviewed"] += 1

    click.echo("\n--- Execution Summary ---")
    click.echo(f"Kept: {stats['kept']}")
    click.echo(f"Dropped: {stats['dropped']}")
    click.echo(f"Left for Review: {stats['reviewed']}")
    click.echo(f"Errors: {stats['errors']}")

if __name__ == "__main__":
    apply()
"""

PYPROJECT_TOML = """
[tool.poetry]
name = "flac-dedupe"
version = "2.0.0"
description = "Refactored FLAC music library deduplication system."
authors = ["Your Name <you@example.com>"]
readme = "README.md"
packages = [{include = "dedupe"}]

[tool.poetry.dependencies]
python = "^3.11"
click = "^8.1"
mutagen = "^1.46"
tomli = "^2.0"  # Only needed for Python < 3.11, but harmless to keep
jsonschema = "^4.0"

[tool.poetry.group.dev.dependencies]
pytest = "^7.0"
mypy = "^1.0"
flake8 = "^6.0"
types-click = "^7.1"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"

[tool.mypy]
strict = true
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
"""

README_MD = """
# FLAC Deduplication System

A robust, modular Python system for managing, deduplicating, and verifying large FLAC music libraries.

## Architecture

This repository has been refactored (2025) into a clean, layered architecture:

* **`dedupe/core/`**: Pure business logic (Hashing, Metadata, Integrity, Decisions).
* **`dedupe/storage/`**: SQLite persistence layer with additive migrations.
* **`dedupe/utils/`**: Shared utilities (Parallelism, Config, Logging).
* **`tools/`**: Command-line interfaces (CLIs) for user interaction.

## Installation

Requires Python 3.11+.

```bash
pip install -r requirements.txt
# OR
poetry install
```

## Configuration

Copy `config.example.toml` to `config.toml` or `~/.config/dedupe/config.toml`.

```toml
[library]
name = "COMMUNE"
root = "/Volumes/COMMUNE"

[library.zones]
staging = "10_STAGING"
accepted = "20_ACCEPTED"

[decisions]
zone_priority = ["accepted", "staging"]
```

## Tools & Usage

### 1. Scan & Verify Integrity
Scans a library, verifies FLAC integrity (`flac -t`), calculates SHA-256 hashes, and upserts to the DB.

```bash
python tools/integrity/scan.py /Volumes/Music/FLAC --db music.db --check-integrity
```

### 2. Find Duplicates & Recommend Actions
Analyzes the database for duplicates and generates a JSON plan for resolution.

```bash
python tools/decide/recommend.py --db music.db --output plan.json
```

**Decision Logic:**
1.  **Integrity**: Files passing `flac -t` are preferred.
2.  **Priority**: Folders listed earlier in `config.toml` are preferred.
3.  **Quality**: Higher sample rate/bit depth is preferred.

### 3. Apply Changes
Executes the deletion plan generated by the recommendation tool.

```bash
# Dry run (safe, default)
python tools/decide/apply.py plan.json

# Actually delete files
python tools/decide/apply.py plan.json --execute
```

## Development

* **Tests**: `pytest`
* **Type Checking**: `mypy dedupe tools`
* **Linting**: `flake8 dedupe tools`
"""

MIGRATION_MD = """
# Migration Guide (2025 Refactor)

This document outlines the changes from the legacy script collection to the new modular architecture.

## Tool Mapping

| Legacy Script | New Tool | Notes |
| :--- | :--- | :--- |
| `tools/scan_flac_integrity.py` | `tools/integrity/scan.py` | Now integrates directly with DB upsert. |
| `dedupe/deduper.py` | `tools/decide/recommend.py` | Logic moved to `dedupe.core.decisions`. |
| `scripts/python/rank_duplicates.py` | `tools/decide/recommend.py` | Ranking logic is now deterministic in core. |
| `scripts/shell/apply_dedupe_plan.sh` | `tools/decide/apply.py` | Now consumes JSON plans instead of text files. |

## Database Migration

The new system uses a stricter SQLite schema. 

1.  **Compatibility**: The new `dedupe.storage` layer is designed to be **additive**. It will open existing databases and add missing columns (e.g., `flac_ok`, `metadata_json`) automatically upon the first `scan.py` run.
2.  **Backup**: Always backup your existing `.sqlite` files before running the new tools.

## Workflow Changes

**Old Workflow:**
1.  Run loose scripts to generate CSVs.
2.  Manually inspect CSVs.
3.  Run shell scripts to parse CSVs and move files.

**New Workflow:**
1.  **Scan**: `python tools/integrity/scan.py ...` (Populates DB)
2.  **Plan**: `python tools/decide/recommend.py -o plan.json` (Generates readable JSON)
3.  **Apply**: `python tools/decide/apply.py plan.json` (Executes deletions safely)

## API Changes (For Developers)

* **No Global State**: All functions now require explicit arguments (e.g., `db_conn`).
* **Typed Models**: Dictionary passing is replaced by `dedupe.storage.models.AudioFile`.
* **Logging**: `print()` calls replaced by structured `logging`.
"""

REPO_STRUCTURE_TARGET_MD = """
# Target Repository Structure

## Source Code (`dedupe/`)

### Core Logic (`dedupe/core/`)
Pure business logic. No database connections or CLI args here.
- `hashing.py`: SHA-256 calculation logic.
- `metadata.py`: Mutagen/FLAC interaction logic.
- `integrity.py`: `flac -t` wrapper.
- `matching.py`: Logic to group duplicates.
- `decisions.py`: Deterministic KEEP/DROP ranking engine.
- `actions.py`: Safe `delete` and `move` functions.

### Storage Layer (`dedupe/storage/`)
Persistence and data models.
- `models.py`: `AudioFile`, `Decision`, `DuplicateGroup` dataclasses.
- `schema.py`: `init_db` and migration logic.
- `queries.py`: `upsert_file`, `get_duplicates`, etc.

### Utilities (`dedupe/utils/`)
Shared helpers.
- `config.py`: TOML loader singleton.
- `logging.py`: Standardized logger setup.
- `parallel.py`: `process_map` wrapper.
- `paths.py`: File discovery (`list_files`).
- `cli_helper.py`: Common Click decorators.

## Tools (`tools/`)
The entry points for the user.
- `integrity/scan.py`: The main scanner CLI.
- `decide/recommend.py`: Generates the JSON plan.
- `decide/apply.py`: Executes the JSON plan.
- `review/export.py`: (Future) Export to CSV for manual review.

## Tests (`tests/`)
Mirrors the source structure.
- `core/test_*.py`
- `storage/test_*.py`
- `utils/test_*.py`
- `tools/test_*.py`
"""

# --- Mapping Files to Paths ---

FILES = {
    "dedupe/storage/models.py": MODELS_PY,
    "dedupe/utils/config.py": CONFIG_PY,
    "dedupe/utils/logging.py": LOGGING_PY,
    "dedupe/core/integrity.py": INTEGRITY_PY,
    "dedupe/core/hashing.py": HASHING_PY,
    "dedupe/core/metadata.py": METADATA_PY,
    "dedupe/core/__init__.py": CORE_INIT_PY,
    "dedupe/storage/schema.py": SCHEMA_PY,
    "dedupe/storage/queries.py": QUERIES_PY,
    "dedupe/utils/paths.py": PATHS_PY,
    "dedupe/utils/parallel.py": PARALLEL_PY,
    "dedupe/scanner.py": SCANNER_PY,
    "dedupe/core/matching.py": MATCHING_PY,
    "dedupe/core/decisions.py": DECISIONS_PY,
    "dedupe/core/actions.py": ACTIONS_PY,
    "dedupe/utils/cli_helper.py": CLI_HELPER_PY,
    "tools/integrity/scan.py": SCAN_TOOL_PY,
    "tools/decide/recommend.py": RECOMMEND_TOOL_PY,
    "tools/decide/apply.py": APPLY_TOOL_PY,
    "pyproject.toml": PYPROJECT_TOML,
    "README.md": README_MD,
    "docs/MIGRATION.md": MIGRATION_MD,
    "docs/REPO_STRUCTURE_TARGET.md": REPO_STRUCTURE_TARGET_MD,
}

# --- Execution ---

def main():
    print("Starting refactor population...")
    root = Path.cwd()
    
    # 1. Create missing directories
    directories = [
        "dedupe/core",
        "dedupe/storage",
        "dedupe/utils",
        "dedupe/external",
        "tools/integrity",
        "tools/decide",
        "tools/review",
        "tools/ingest",
        "tests",
        "docs",
    ]
    
    for d in directories:
        (root / d).mkdir(parents=True, exist_ok=True)
        # Create __init__.py for python packages if missing
        if "docs" not in d and "tests" not in d:
             init_file = root / d / "__init__.py"
             if not init_file.exists():
                 init_file.touch()

    # 2. Write files
    for fpath, content in FILES.items():
        full_path = root / fpath
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content.strip() + "\n")
            print(f"✔  Wrote: {fpath}")
        except Exception as e:
            print(f"✘  Error writing {fpath}: {e}")

    print("\\nRefactor population complete.")

if __name__ == "__main__":
    main()
