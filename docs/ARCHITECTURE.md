# Architecture

## System Design and Data Flow

# Provenance and Recovery

This document covers audit trails, provenance tracking, and recovery procedures.

## Provenance Model

### What is Tracked

Every file in the database has:
- **path** - Current filesystem location
- **canonical_isrc** - ISRC identifier (if available)
- **beatport_id** - Beatport track ID (if available)
- **download_source** - Where the file came from (beatport, tidal, etc.)
- **metadata_json** - Full metadata snapshot
- **checksum** - File integrity hash

Every move operation creates:
- **Move receipt** in database `moves` table
- **JSONL log** in `artifacts/moves_*.jsonl`

### Move Receipt Fields

```json
{
  "timestamp": "2026-02-14T10:30:00Z",
  "source_path": "/Volumes/Staging/Artist - Track.flac",
  "dest_path": "/Volumes/Library/Artist/Album/Track.flac",
  "operation": "move",
  "status": "completed",
  "checksum_before": "abc123...",
  "checksum_after": "abc123..."
}
```

### Audit Log Location

```
artifacts/moves_<timestamp>.jsonl
```

## Recovery Scenarios

### Scenario 1: Interrupted Move Operation

**Symptoms:**
- Operation stopped midway
- Some files moved, some not
- Database may be inconsistent

**Recovery Steps:**

```bash
# 1. Check receipt status
tagslut verify receipts \
  --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db

# 2. Get recovery report
tagslut verify recovery \
  --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db

# 3. Generate detailed report
tagslut report recovery \
  --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db \
  --output artifacts/recovery_report.md

# 4. Review the report
cat artifacts/recovery_report.md

# 5. For each incomplete move, either:
#    a) Complete the move manually
#    b) Revert by moving file back to source
#    c) Update database to reflect current state
```

### Scenario 2: File Moved But Database Not Updated

**Symptoms:**
- File exists at new location
- Database shows old location
- `verify receipts` shows inconsistency

**Recovery Steps:**

```bash
# 1. Find the discrepancy
tagslut verify recovery \
  --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db

# 2. Option A: Update database to match filesystem
tagslut index register \
  --zone library \
  --recursive \
  /path/to/new/location

# 3. Option B: Move file back to match database
#    (Use if database record is authoritative)
mv "/path/to/new/file.flac" "/path/from/database.flac"
```

### Scenario 3: Database Updated But File Not Moved

**Symptoms:**
- Database shows new location
- File still at old location
- `verify receipts` shows incomplete

**Recovery Steps:**

```bash
# 1. Complete the move
mv "/old/path/file.flac" "/new/path/from/database/file.flac"

# 2. Verify
tagslut verify receipts \
  --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db
```

### Scenario 4: Corrupted File After Move

**Symptoms:**
- File at destination is corrupted
- Checksum mismatch
- Audio won't play

**Recovery Steps:**

```bash
# 1. Identify the issue
tagslut verify receipts \
  --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db

# 2. Check if source still exists
ls -la "/original/source/path.flac"

# 3. If source exists, restore from source
cp "/original/source/path.flac" "/destination/path.flac"

# 4. If source doesn't exist, re-download
#    Use download_source from database to find origin

# 5. Update database
tagslut index register \
  --zone library \
  /destination/path.flac
```

### Scenario 5: Lost Track of Files

**Symptoms:**
- Files exist on filesystem
- Not in database
- Pre-download check shows `keep` for known files

**Recovery Steps:**

```bash
# 1. Register all files in a directory
tagslut index register \
  --zone library \
  --recursive \
  /path/to/library

# 2. Enrich with metadata
tagslut index enrich \
  --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db

# 3. Verify
tagslut verify recovery \
  --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db
```

## JSONL Log Format

Move logs in `artifacts/moves_*.jsonl` use one JSON object per line:

```json
{"ts":"2026-02-14T10:30:00Z","op":"move","src":"/a/b.flac","dst":"/c/d.flac","status":"ok"}
{"ts":"2026-02-14T10:30:01Z","op":"move","src":"/a/c.flac","dst":"/c/e.flac","status":"ok"}
```

### Reading Logs

```bash
# View all moves
cat artifacts/moves_*.jsonl | jq .

# Filter by status
cat artifacts/moves_*.jsonl | jq 'select(.status != "ok")'

# Count operations
wc -l artifacts/moves_*.jsonl

# Get unique source directories
cat artifacts/moves_*.jsonl | jq -r '.src' | xargs dirname | sort -u
```

## Database Backup

### Creating Backup

```bash
# Backup before major operations
cp ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db \
   ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db.backup_$(date +%Y%m%d_%H%M%S)
```

### Restoring Backup

```bash
# Stop any running operations first
cp ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db.backup_YYYYMMDD_HHMMSS \
   ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db
```

## Provenance Queries

### Find All Files from Beatport

```bash
sqlite3 ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db \
  "SELECT path, beatport_id FROM files WHERE download_source = 'beatport' LIMIT 10;"
```

### Find Files with ISRC

```bash
sqlite3 ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db \
  "SELECT COUNT(*) FROM files WHERE canonical_isrc IS NOT NULL AND canonical_isrc != '';"
```

### Find Recent Moves

```bash
sqlite3 ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db \
  "SELECT * FROM moves ORDER BY timestamp DESC LIMIT 10;"
```

### Find Orphaned Database Records

```bash
# Files in DB but not on filesystem
sqlite3 ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db \
  "SELECT path FROM files;" | while read -r path; do
  [ ! -f "$path" ] && echo "Missing: $path"
done
```

## Safety Principles

1. **Move-only semantics** - Files are moved, never copied (avoids duplicates)
2. **Pre-move checksums** - Integrity verified before operation
3. **Post-move checksums** - Integrity verified after operation
4. **Receipt logging** - Every move creates an audit record
5. **Database as truth** - Database is authoritative for file locations
6. **Idempotent operations** - Safe to retry failed operations

## Emergency Contacts

If recovery fails and you need to rebuild from scratch:

1. All JSONL logs are in `artifacts/`
2. All original files should still exist somewhere
3. The pre-download check tool can rebuild knowledge of what you have
4. `tagslut index register` can rebuild database from filesystem

## Move Executor Contract

# Move Executor Compatibility Contract

Canonical reference for the centralized move execution engine and its compatibility adapter.

## Contract Versions

| Version | Module | Role |
|---------|--------|------|
| `move_exec.v2` | `tagslut.exec.engine` | Canonical move executor with receipts and verification |
| `move_exec_adapter.v1` | `tagslut.exec.compat` | Legacy adapter preserving `MoveExecutionResult` shape |

New code must import from `tagslut.exec.engine` directly. The compat adapter exists only
for legacy callers and will be removed in a future release.

## Public API

### `execute_move(src, dest, *, execute, collision_policy)` → `MoveReceipt`

Canonical entry point. Performs safety checks, collision handling, and post-move verification.

### `execute_move_action(src, dest, *, execute, collision_policy)` → `MoveExecutionResult`

Legacy compatibility wrapper. Delegates to `execute_move()` and reshapes the receipt.

## Collision Policies

| Policy | Behaviour |
|--------|-----------|
| `skip` | Skip silently if destination exists |
| `dedupe` | Rename destination with content-hash suffix to avoid collision |
| `abort` | Raise `FileExistsError` if destination exists |

## Receipt Schema (`MoveReceipt`)

| Field | Type | Description |
|-------|------|-------------|
| `status` | `MoveStatus` | `moved`, `dry_run`, `skip_missing`, `skip_dest_exists`, `error` |
| `src` | `Path` | Source path at invocation time |
| `dest_requested` | `Path` | Requested destination path |
| `dest_final` | `Path \| None` | Actual destination (may differ under `dedupe` policy) |
| `execute` | `bool` | Whether the move was live or dry-run |
| `source_size` | `int \| None` | Source file size in bytes |
| `dest_size` | `int \| None` | Destination file size after move |
| `verification` | `str \| None` | Post-move verification status |
| `content_hash` | `str \| None` | Stable content hash for audit trail |
| `error` | `str \| None` | Error message if status is `error` |
| `executor_contract` | `str` | Contract version string |
| `timestamp` | `str` | ISO-8601 UTC timestamp |

## DB Mutation Rule

`files.path` may only be updated in the v3 DB when a `move_execution` receipt with
`status='moved'` exists. No DB path mutation without a successful receipt.

See `tagslut.exec.receipts` for the persistence layer.

## Verification Hooks

`verify_receipt(receipt)` enforces postconditions:

1. Source path no longer exists.
2. Destination path exists.
3. Source and destination sizes match.

## Caller Inventory

All plan execution scripts route through the centralized executor:

- `tools/review/move_from_plan.py`
- `tools/review/quarantine_from_plan.py`
- `tools/review/promote_by_tags.py`

Raw `shutil.move` / `os.replace` usage outside `tagslut.exec.engine` is prohibited.
`scripts/audit_repo_layout.py` enforces this constraint.

## Change Control

Updates to the move execution contract must co-update:

- `docs/ARCHITECTURE.md#move-executor-contract` (this document)
- `docs/SURFACE_POLICY.md`
- `docs/SCRIPT_SURFACE.md`

## Zones and Trust Model

# Zones (V2)

Zones are first-class trust/lifecycle stages. They are **not** just labels. Zones drive keeper selection, safety rules, and the staged workflow. Zones are stored in the DB (`files.zone`) and are always auditable.

## Zone Definitions

- **accepted**: Canonical library content. Highest trust.
- **archive**: Long-term storage. High trust but not necessarily canonical.
- **staging**: Incoming/working area. Medium trust.
- **suspect**: Duplicates, corrupt, or unverified files. Low trust.
- **quarantine**: Duplicates copied into a safety net. Lowest trust.
- **inbox / rejected**: Optional legacy zones (supported for compatibility).

## Core Rules

- **No deletion**: Code never deletes source files. Quarantine is copy-only.
- **Reversible**: All actions must be auditable in DB/logs.
- **Zones remain central**: Keeper selection always considers zones unless no library zones exist.

## Zone Configuration

Zones are configured via YAML (preferred) or TOML (legacy). YAML allows explicit priorities and path-level overrides.

### YAML (preferred)

Set `TAGSLUT_ZONES_CONFIG` to a YAML file:

```
export TAGSLUT_ZONES_CONFIG=~/.config/tagslut/zones.yaml
```

The YAML structure uses these top-level keys:

- `defaults.zone`: fallback zone (usually `suspect`)
- `roots.base`: optional base for relative paths
- `zones`: mapping of zone → {paths, priority, description}
- `path_priorities`: optional path-level tie-breakers

See `config.example.yaml` for three scenarios.

### TOML (legacy)

The existing `config.toml` supports `library.root` and `library.zones`. When present, ZoneManager loads from TOML but uses default priorities.

## Scenarios

### Scenario A — Single main library

- One canonical `accepted` root.
- `staging`, `suspect`, and `quarantine` live under a work area.
- `path_priorities` can nudge tie-breaks within the accepted library.

### Scenario B — Multiple peer libraries (no single main)

- Multiple `accepted` roots with the **same base priority**.
- `path_priorities` break ties between peers if needed.
- Keeper selection still prefers accepted over staging/suspect/quarantine.

### Scenario C — No main library

- No `accepted` zone at all.
- Keeper selection ignores zone priority and ranks purely by quality, size, and hygiene.
- Best for transient/staging-only collections.

## Keeper Selection Order

1. **Zone priority** (from ZoneManager)
2. **Path priority** (within zone, if configured)
3. **Audio quality** (sample rate, bit depth, bitrate, integrity)
4. **File size** (larger tends to be more complete)
5. **Path hygiene** (shorter and cleaner paths win ties)

If **no accepted zone** exists, step 1 is skipped automatically.

## CLI Helpers

- `tagslut show-zone --path /path/to/file`
- `tagslut explain-keeper --db /path/to/music.db --group-id <checksum>`

Both commands are safe, read-only diagnostics.
