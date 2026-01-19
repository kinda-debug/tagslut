# Dedupe V2: Simplified Architecture
**Vision:** Simple, portable, config-driven FLAC deduplication system

---

## 🎯 CORE PRINCIPLES

1. **Zero Hardcoded Paths** - Everything from config/env
2. **Single Entry Point** - One CLI, many commands
3. **Config-Driven** - Behavior controlled by config file
4. **Self-Documenting** - Help text explains everything
5. **Fail-Fast** - Clear errors, not silent failures

---

## 📁 NEW DIRECTORY STRUCTURE

```
dedupe/
├── README.md                    # Quick start only
├── GUIDE.md                     # Complete user guide
├── .env.example                 # Template for paths
├── config.yaml                  # Default config (YAML, simpler than TOML)
├── pyproject.toml               # Python project config
├── Makefile                     # Common tasks
│
├── dedupe/                      # Main package
│   ├── __init__.py
│   ├── __main__.py             # Entry point: `python -m dedupe`
│   │
│   ├── cli/                     # Command-line interface
│   │   ├── __init__.py
│   │   ├── main.py             # CLI router
│   │   ├── scan.py             # dedupe scan
│   │   ├── recommend.py        # dedupe recommend
│   │   ├── apply.py            # dedupe apply
│   │   ├── promote.py          # dedupe promote
│   │   ├── quarantine.py       # dedupe quarantine
│   │   └── db.py               # dedupe db
│   │
│   ├── config/                  # Configuration management
│   │   ├── __init__.py
│   │   ├── loader.py           # Load config from file/env
│   │   ├── schema.py           # Config validation
│   │   └── defaults.py         # Default values
│   │
│   ├── core/                    # Core business logic
│   │   ├── __init__.py
│   │   ├── scanner.py          # File scanning
│   │   ├── hasher.py           # Hash calculation
│   │   ├── matcher.py          # Duplicate detection
│   │   ├── recommender.py      # Decision logic
│   │   └── executor.py         # Apply actions
│   │
│   ├── models/                  # Data models
│   │   ├── __init__.py
│   │   ├── file.py             # File metadata
│   │   ├── duplicate.py        # Duplicate group
│   │   └── decision.py         # Action decision
│   │
│   ├── storage/                 # Database layer
│   │   ├── __init__.py
│   │   ├── db.py               # Database manager
│   │   ├── schema.py           # Schema definition
│   │   └── queries.py          # Common queries
│   │
│   └── utils/                   # Utilities
│       ├── __init__.py
│       ├── logging.py          # Structured logging
│       ├── paths.py            # Path utilities
│       └── progress.py         # Progress tracking
│
├── tests/                       # Tests mirror structure
│   ├── conftest.py
│   ├── test_scanner.py
│   ├── test_matcher.py
│   └── ...
│
└── docs/                        # Minimal docs
    ├── QUICKSTART.md
    ├── GUIDE.md
    ├── API.md
    └── CHANGELOG.md
```

---

## ⚙️ CONFIGURATION SYSTEM

### config.yaml (Simple, readable)

```yaml
# Dedupe Configuration
# Paths support environment variable expansion: ${VAR_NAME}

database:
  path: ${DEDUPE_DB_PATH:-~/.dedupe/music.db}
  auto_migrate: true

paths:
  artifacts: ${DEDUPE_ARTIFACTS:-~/.dedupe/artifacts}
  logs: ${DEDUPE_LOGS:-~/.dedupe/logs}

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
  file: ${DEDUPE_LOGS}/dedupe.log
```

### .env.example

```bash
# Database
DEDUPE_DB_PATH=/path/to/music.db

# Volumes - Update these for your system
LIBRARY_PATH=/Volumes/Library
STAGING_PATH=/Volumes/Staging
SUSPECT_PATH=/Volumes/Suspect
QUARANTINE_PATH=/Volumes/Quarantine

# Artifacts
DEDUPE_ARTIFACTS=./artifacts
DEDUPE_LOGS=./logs

# Scan options
SCAN_WORKERS=8
```

---

## 🖥️ CLI INTERFACE

### Main Command
```bash
dedupe [--config PATH] [--verbose] [--quiet] COMMAND [ARGS...]
```

### Commands

#### 1. Scan
```bash
# Scan a volume
dedupe scan /path/to/volume --zone suspect

# Scan using config
dedupe scan library  # Uses path from config

# Resume interrupted scan
dedupe scan library --incremental
```

#### 2. Recommend
```bash
# Generate recommendations
dedupe recommend

# Custom thresholds
dedupe recommend --threshold 0.9

# Output to file
dedupe recommend --output plan.json
```

#### 3. Apply
```bash
# Dry run (default)
dedupe apply --plan plan.json

# Execute
dedupe apply --plan plan.json --execute

# Interactive mode
dedupe apply --plan plan.json --interactive
```

#### 4. Promote
```bash
# Promote from staging to library
dedupe promote staging library

# Custom paths
dedupe promote /path/from /path/to --mode move
```

#### 5. Quarantine
```bash
# List quarantined files
dedupe quarantine list

# Clean old files
dedupe quarantine clean --days 30

# Restore specific file
dedupe quarantine restore <file_id>
```

#### 6. Database
```bash
# Check database health
dedupe db doctor

# Run migrations
dedupe db migrate

# Export data
dedupe db export --format csv --output data.csv

# Backup
dedupe db backup --output backup.db
```

#### 7. Config
```bash
# Show current config
dedupe config show

# Validate config
dedupe config validate

# Initialize config
dedupe config init
```

---

## 🔄 WORKFLOW (Simplified)

```bash
# 1. Initialize (first time only)
dedupe config init
# Edit config.yaml or .env with your paths

# 2. Scan volumes
dedupe scan library
dedupe scan staging
dedupe scan suspect

# 3. Find duplicates & recommend actions
dedupe recommend --output plan.json

# 4. Review plan (manual step)
# Edit plan.json or use interactive mode

# 5. Apply decisions
dedupe apply --plan plan.json --execute

# 6. Promote staging to library
dedupe promote staging library --execute

# 7. Clean old quarantined files
dedupe quarantine clean --days 30
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
- What is dedupe?
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
# Old way still works
python tools/integrity/scan.py /path --db /db/path

# New way
dedupe scan /path  # Uses config
```

### Phase 2: Deprecation Warnings
```bash
python tools/integrity/scan.py /path
# Warning: This script is deprecated. Use 'dedupe scan' instead.
```

### Phase 3: Migration Tool
```bash
dedupe migrate --from-v1
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
- **Discoverable**: `dedupe --help` shows everything
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
