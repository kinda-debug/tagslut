# Dedupe V2: Synthesized Architecture

> Status note (2026-02-08): This is a synthesized/historical architecture snapshot.
> For the current operational script surface, use `docs/SCRIPT_SURFACE.md` and live CLI help output.

This document describes the current production architecture of the Dedupe system, synthesized from the "Unified" package structure.

---

## 🎯 Design Principles

1.  **Unified Entry Point**: All operations are routed through `python3 -m tagslut`, ensuring consistent environment loading and configuration.
2.  **Tiered Hashing**: Balanced performance and safety using Pre-hash (T1) and Full SHA256 (T2).
3.  **Deterministic Decisions**: Rule-based "Keeper" selection to eliminate ambiguity in duplicate resolution.
4.  **Evidence Preservation**: The database tracks every scan session and file outcome, creating a complete audit trail of the library's state.

---

## 📁 Synthesized Structure

```text
tagslut/
├── cli/                 # Click-based CLI router
│   └── main.py          # Command definitions (scan, recommend, apply)
├── core/                # Functional logic
│   ├── integrity_scanner.py # The primary engine for library indexing
│   ├── hashing.py       # Tiered hash implementations
│   ├── metadata.py      # Audio metadata extraction (FLAC tags)
│   └── matching.py      # Duplicate detection algorithms
├── storage/             # Database Layer
│   ├── schema.py        # SQLite schema and migration logic
│   └── queries.py       # Optimized SQL for library operations
└── utils/               # Shared helpers (Config, Logging, Paths)

legacy/tools/            # Archived workbench (legacy scripts)
├── integrity/           # scan.py (legacy scanner)
├── review/              # plan_removals.py (legacy decision tools)
└── decide/              # recommend.py (legacy analysis)
```

---

## ⚙️ Core Systems

### 1. The Scanner (`integrity_scanner.py`)
The engine iterates through library roots, identifies new or modified files, and extracts both technical (bitrate, sample rate) and descriptive (tags) metadata. It manages `scan_sessions` to allow for resumable and incremental operations.

### 2. Tiered Hashing
*   **Tier 1**: `size + head_bytes(4MB)`. Sufficient for 99% of duplicate triage.
*   **Tier 2**: `sha256(full_content)`. Mandatory for confirmation before any file move.

### 3. Storage Layer
Uses SQLite for local, high-speed querying. The schema is designed for surgical updates, allowing the system to update single file records without re-scanning the entire volume.

---

## ⚙️ CONFIGURATION SYSTEM

### config.yaml (Simple, readable)

```yaml
# Dedupe Configuration
# Paths support environment variable expansion: ${VAR_NAME}

database:
  path: ${TAGSLUT_DB_PATH:-~/.tagslut/music.db}
  auto_migrate: true

paths:
  artifacts: ${TAGSLUT_ARTIFACTS:-~/.tagslut/artifacts}
  logs: ${TAGSLUT_LOGS:-~/.tagslut/logs}

volumes:
  library:
    path: ${LIBRARY_PATH}
    zone: accepted
    priority: 1

  staging:
    path: ${STAGING_PATH}
    zone: staging
    priority: 2

  suspect:
    path: ${SUSPECT_PATH:-null}
    zone: suspect
    priority: 3

  quarantine:
    path: ${QUARANTINE_PATH}
    zone: quarantine
    priority: 4

scan:
  workers: ${SCAN_WORKERS:-8}
  check_integrity: true
  check_hash: true
  incremental: true
  progress_interval: 100

decisions:
  auto_approve_threshold: 0.95
  quarantine_days: 30
  prefer_high_bitrate: true
  prefer_high_sample_rate: true

logging:
  level: INFO
  format: structured
  file: ${TAGSLUT_LOGS}/tagslut.log
```

### .env.example

```bash
# Database
TAGSLUT_DB_PATH=/path/to/music.db

# Volumes - Update these for your system
LIBRARY_PATH=/Volumes/Library
STAGING_PATH=/Volumes/Staging
SUSPECT_PATH=/Volumes/Suspect
QUARANTINE_PATH=/Volumes/Quarantine

# Artifacts
TAGSLUT_ARTIFACTS=./artifacts
TAGSLUT_LOGS=./logs

# Scan options
SCAN_WORKERS=8
```

---

## 🖥️ CLI INTERFACE

### Main Command
```bash
tagslut [--config PATH] [--verbose] [--quiet] COMMAND [ARGS...]
```

### Commands

#### 1. Scan
```bash
# Scan a volume
tagslut scan /path/to/volume --zone suspect

# Scan using config
tagslut scan library  # Uses path from config

# Resume interrupted scan
tagslut scan library --incremental
```

#### 2. Recommend
```bash
# Generate recommendations
tagslut recommend

# Custom thresholds
tagslut recommend --threshold 0.9

# Output to file
tagslut recommend --output plan.json
```

#### 3. Apply
```bash
# Dry run (default)
tagslut apply --plan plan.json

# Execute
tagslut apply --plan plan.json --execute

# Interactive mode
tagslut apply --plan plan.json --interactive
```

#### 4. Promote
```bash
# Promote from staging to library
tagslut promote staging library

# Custom paths
tagslut promote /path/from /path/to --move
```

#### 5. Quarantine
```bash
# List quarantined files
tagslut quarantine list

# Clean old files
tagslut quarantine clean --days 30

# Restore specific file
tagslut quarantine restore <file_id>
```

#### 6. Database
```bash
# Check database health
tagslut db doctor

# Run migrations
tagslut db migrate

# Export data
tagslut db export --format csv --output data.csv

# Backup
tagslut db backup --output backup.db
```

#### 7. Config
```bash
# Show current config
tagslut config show

# Validate config
tagslut config validate

# Initialize config
tagslut config init
```

---

## 🔄 WORKFLOW (Simplified)

```bash
# 1. Initialize (first time only)
tagslut config init
# Edit config.yaml or .env with your paths

# 2. Scan volumes
tagslut scan library
tagslut scan staging
tagslut scan suspect

# 3. Find duplicates & recommend actions
tagslut recommend --output plan.json

# 4. Review plan (manual step)
# Edit plan.json or use interactive mode

# 5. Apply decisions
tagslut apply --plan plan.json --execute

# 6. Promote staging to library
tagslut promote staging library --execute

# 7. Clean old quarantined files
tagslut quarantine clean --days 30
```

**That's it!** 7 simple steps instead of dozens of scripts.

---

## 💾 DATA MODELS

### File Model
```python
@dataclass
class AudioFile:
    path: Path
    size: int
    mtime: float
    sha256: str | None
    streaminfo_md5: str | None
    zone: str
    library: str
    duration: float | None
    sample_rate: int | None
    bit_depth: int | None
    bitrate: int | None
    integrity_ok: bool
    tags: dict[str, Any]
```

### Duplicate Group
```python
@dataclass
class DuplicateGroup:
    id: str
    files: list[AudioFile]
    match_type: Literal["sha256", "streaminfo", "acoustic"]
    confidence: float
    recommendation: Decision
```

### Decision
```python
@dataclass
class Decision:
    action: Literal["keep", "quarantine", "delete"]
    file: AudioFile
    reason: str
    confidence: float
    auto_approved: bool
```

---

## 📊 DATABASE SCHEMA (Simplified)

```sql
-- Main files table
CREATE TABLE files (
    id INTEGER PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,
    library TEXT NOT NULL,
    zone TEXT NOT NULL,
    size INTEGER,
    mtime REAL,
    sha256 TEXT,
    streaminfo_md5 TEXT,
    duration REAL,
    sample_rate INTEGER,
    bit_depth INTEGER,
    bitrate INTEGER,
    integrity_ok BOOLEAN,
    metadata JSON,
    scanned_at DATETIME,
    INDEX(sha256),
    INDEX(streaminfo_md5),
    INDEX(library, zone)
);

-- Duplicate groups
CREATE TABLE duplicate_groups (
    id INTEGER PRIMARY KEY,
    match_type TEXT,
    confidence REAL,
    created_at DATETIME
);

-- Files in groups
CREATE TABLE group_members (
    group_id INTEGER REFERENCES duplicate_groups(id),
    file_id INTEGER REFERENCES files(id),
    is_keeper BOOLEAN,
    PRIMARY KEY (group_id, file_id)
);

-- Decisions/actions
CREATE TABLE decisions (
    id INTEGER PRIMARY KEY,
    file_id INTEGER REFERENCES files(id),
    action TEXT,
    reason TEXT,
    confidence REAL,
    auto_approved BOOLEAN,
    executed_at DATETIME,
    INDEX(file_id)
);

-- Quarantine tracking
CREATE TABLE quarantine (
    id INTEGER PRIMARY KEY,
    original_path TEXT,
    quarantine_path TEXT,
    quarantined_at DATETIME,
    delete_after DATETIME,
    reason TEXT,
    INDEX(delete_after)
);

-- Promotions tracking
CREATE TABLE promotions (
    id INTEGER PRIMARY KEY,
    source_path TEXT,
    dest_path TEXT,
    mode TEXT,
    promoted_at DATETIME
);
```

---

## 🧪 TESTING STRATEGY

### Unit Tests
```python
tests/
├── test_scanner.py       # Scanning logic
├── test_hasher.py        # Hash calculation
├── test_matcher.py       # Duplicate detection
├── test_recommender.py   # Decision logic
└── test_config.py        # Config loading
```

### Integration Tests
```python
tests/integration/
├── test_scan_workflow.py
├── test_recommend_workflow.py
└── test_apply_workflow.py
```

### End-to-End Tests
```python
tests/e2e/
└── test_full_workflow.py  # Complete scan → recommend → apply
```

---

## 📚 DOCUMENTATION (Consolidated)

### 1. README.md (1 page)
- What is tagslut?
- Quick install
- 5-minute quick start
- Link to full guide

### 2. GUIDE.md (Complete reference)
- Detailed installation
- Configuration
- All commands with examples
- Workflows
- Troubleshooting
- FAQ

### 3. API.md (For developers)
- Code architecture
- Module documentation
- Extension points
- Contributing guide

### 4. CHANGELOG.md
- Version history
- Breaking changes
- Migration guides

**That's it!** 4 files instead of 20.

---

## 🚀 MIGRATION PATH

### Phase 1: Add Config Support (Non-Breaking)
```bash
# Old way still works (legacy script)
python legacy/tools/integrity/scan.py /path --db /db/path

# New way
tagslut scan /path  # Uses config
```

### Phase 2: Deprecation Warnings
```bash
python legacy/tools/integrity/scan.py /path
# Warning: This script is deprecated. Use 'tagslut scan' instead.
```

### Phase 3: Migration Tool
```bash
tagslut migrate --from-v1
# Converts old hardcoded paths to config
# Provides .env file
# Shows what changed
```

### Phase 4: Remove Old Scripts (v2.0)
- Old scripts deleted
- Only CLI remains

---

## ✅ BENEFITS

### For Users
- **Simpler**: 1 command vs 30 scripts
- **Portable**: Config file, not hardcoded paths
- **Discoverable**: `tagslut --help` shows everything
- **Safe**: Dry-run by default
- **Fast**: Less overhead, better caching

### For Developers
- **Maintainable**: Clear structure
- **Testable**: Isolated modules
- **Extensible**: Plugin system possible
- **Documented**: Self-explanatory code

### For Operations
- **Predictable**: Config-driven behavior
- **Auditable**: Structured logs
- **Recoverable**: Resume support everywhere
- **Monitorable**: Progress tracking built-in

---

## 🎓 LEARNING FROM MISTAKES

### What V1 Did Wrong
1. Scripts proliferated without planning
2. Hardcoded paths for "quick fixes"
3. Documentation never consolidated
4. No central configuration

### What V2 Does Right
1. Design config system first
2. All paths from config/env
3. Documentation = code
4. Single entry point

---

**END OF ARCHITECTURE**
