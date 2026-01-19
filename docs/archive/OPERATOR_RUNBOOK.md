# OPERATOR_RUNBOOK: Step-by-Step Dedupe Workflows

This is your operational guide for running dedupe. Follow these workflows deterministically for consistent, auditable results.

## Prerequisites

```bash
# Install
make install

# Configure (create config.toml in project root)
[library]
path = "/path/to/flac/library"
db_path = "./artifacts/dedupe.db"

[quarantine]
enabled = true
path = "./artifacts/quarantine"
```

## Workflow 1: Scan & Audit (Read-Only)

**Purpose**: Discover duplicates without any modifications.

### Step 1: Initialize Database

```bash
dedupe init --db-path ./artifacts/dedupe.db
```

Creates SQLite database for storing file metadata.

### Step 2: Scan Library

```bash
dedupe scan --library-path /path/to/library --db-path ./artifacts/dedupe.db --verbose
```

**Output**:
- `scan_report_TIMESTAMP.json` - Raw findings
- `artifacts/MANIFEST.json` - Immutable record

**Manifest contains**:
```json
{
  "timestamp": "2026-01-15T08:00:00Z",
  "operation": "scan",
  "library_path": "/path/to/library",
  "files_scanned": 5000,
  "duplicates_found": 237,
  "checksum": "sha256...",
  "status": "completed"
}
```

### Step 3: Generate Audit Report

```bash
dedupe audit report --input scan_report_*.json --output audit_report.json
```

**Review the report**:
```bash
cat audit_report.json | jq '.duplicates[] | select(.risk_score > 0.8)'
```

**Fields**:
- `file_hash`: SHA256 of FLAC content
- `checksum_type`: STREAMINFO or SHA256
- `bitrate`: kbps (e.g., 320 or 1411 for lossless)
- `duration`: seconds
- `risk_score`: 0-1, higher = more likely to delete

## Workflow 2: Make Decisions (Interactive)

**Purpose**: Decide which files to keep/quarantine/delete.

### Step 4: Interactive Decision Mode

```bash
dedupe decide --mode interactive --input scan_report_*.json
```

**For each duplicate group, choose**:

```
Duplicate Group #1 (3 files)

1. /path/to/song_v1.flac (320kbps, 2020-01-15)
2. /path/to/song_v2.flac (320kbps, 2021-03-20)
3. /path/to/song_master.flac (320kbps, 2018-06-10)

Action [keep/quarantine/delete]? keep
Which file to keep (1-3)? 3
Reason (optional): [enter text or skip]
```

### Step 5: Review Decision Matrix

```bash
cat decisions_TIMESTAMP.json | jq '.decisions[]'
```

Each decision includes:
- `file_path`: Target file
- `action`: keep | quarantine | delete
- `reason`: User-provided rationale
- `timestamp`: When decision was made
- `reversible`: Whether action can be undone

## Workflow 3: Apply Changes (Destructive)

**Purpose**: Execute decisions with safety checks.

### Step 6: Dry-Run (Always First)

```bash
dedupe apply --dry-run --input decisions_*.json --verbose
```

**Output**:
```
[DRY RUN] Would quarantine: /path/to/song_v1.flac (42 MB)
[DRY RUN] Would delete: /path/to/song_v2.flac (41 MB)
[DRY RUN] Space saved: 83 MB
```

**Review carefully**. If satisfied, proceed.

### Step 7: Execute with Approval

```bash
dedupe apply --input decisions_*.json --confirm
```

**Executes in order**:
1. Pre-flight checks (disk space, permissions)
2. Backup metadata to `artifacts/backup_TIMESTAMP.json`
3. Move files to quarantine (if enabled)
4. Delete files
5. Update database
6. Write final manifest

**Output**:
```
[SUCCESS] Quarantined 5 files (210 MB)
[SUCCESS] Deleted 3 files (145 MB)
[SUCCESS] Space freed: 355 MB
```

## Workflow 4: Rollback (If Needed)

**Purpose**: Undo recent changes.

```bash
dedupe rollback --backup-file artifacts/backup_TIMESTAMP.json
```

Restores files from quarantine and updates database.

## Safety Features

### Quarantine Before Delete

Files are moved to `artifacts/quarantine/` before permanent deletion. You can review and restore them:

```bash
ls -la artifacts/quarantine/
rm -rf artifacts/quarantine/*  # Only when confident
```

### Immutable Manifests

Each operation creates a manifest with:
- Checksums of all modified files
- Timestamp
- Operation type
- Status (completed/failed)

These cannot be edited, ensuring audit trail integrity.

### Time-Based Commits

Database commits every 60 seconds during long operations. If interrupted:

```bash
dedupe resume --db-path ./artifacts/dedupe.db
```

## Troubleshooting

### Issue: "Permission denied" during delete

**Check**:
```bash
ls -la /path/to/file.flac  # Check permissions
sudo chown $USER /path/to/file.flac  # Fix if needed
```

### Issue: Duplicate detection too aggressive

**Adjust thresholds**:
```bash
dedupe scan --similarity-threshold 0.95  # Default: 0.99
```

### Issue: Database corrupted

**Reset**:
```bash
rm ./artifacts/dedupe.db
dedupe init --db-path ./artifacts/dedupe.db
```

## Example: Full Workflow

```bash
# 1. Initialize
make install
dedupe init --db-path ./artifacts/dedupe.db

# 2. Scan (read-only)
dedupe scan --library-path /music/flac --db-path ./artifacts/dedupe.db

# 3. Review audit
dedupe audit report --input scan_report_*.json | less

# 4. Make decisions (interactive)
dedupe decide --mode interactive --input scan_report_*.json

# 5. Dry-run
dedupe apply --dry-run --input decisions_*.json --verbose

# 6. Execute
dedupe apply --input decisions_*.json --confirm

# 7. Verify
ls -la artifacts/quarantine/
duplicates_removed=$(cat decisions_*.json | jq '.deleted | length')
echo "Removed $duplicates_removed duplicates"
```

## Workflow 3: Promote Files to Canonical Layout

**Purpose**: Move/copy KEEP files from staging to the canonical library with tag-based naming.

### Step 8: Dry-Run Promotion

```bash
# Preview what would be promoted
make promote-dry

# Or with custom paths:
KEEP_DIR=/Volumes/COMMUNE/M/_staging \
LIBRARY_ROOT=/Volumes/COMMUNE/M/Library \
DB_PATH=./artifacts/dedupe.db \
make promote-dry
```

### Step 9: Execute Promotion

```bash
# Interactive confirmation before execution
make promote

# Or with full control:
python tools/review/promote_by_tags.py \
  --source-root /path/to/staging \
  --dest-root /path/to/library \
  --db ./artifacts/dedupe.db \
  --mode move \
  --execute \
  --progress-only
```

**Naming Convention** (Picard-compatible):
- Top folder: `Label` (if compilation) or `AlbumArtist/Artist`
- Album folder: `(YYYY) Album [Type]` (Type: Bootleg, Live, EP, Single, etc.)
- Filename: `NN. Artist - Title.flac` (featuring → feat.)

**Features**:
- Resume support: Rerun same command to continue after interruption
- Disk space management: Auto-spill to secondary destination when primary is low
- Database tracking: All promotions logged to `promotions` table
- Skip existing: Won't overwrite files that already exist in target location

### Step 10: Verify Promotion

```bash
# Check promotion log
tail -n 100 artifacts/M/03_reports/promote_by_tags.log

# Query database for promotion history
sqlite3 ./artifacts/dedupe.db "SELECT * FROM promotions ORDER BY timestamp DESC LIMIT 20;"

# Verify file counts
find /Volumes/COMMUNE/M/Library -name "*.flac" | wc -l
```

## Key Principles

- **Deterministic**: Same input → Same output
- **Resumable**: Interrupted operations can continue
- **Non-destructive**: Quarantine before delete
- **Auditable**: All decisions logged with checksums
- **Explicit**: No auto-execute; always review first

## Next Steps

See [README.md](../README.md) for API usage and [CONTRIBUTING.md](../CONTRIBUTING.md) for development guidelines.
