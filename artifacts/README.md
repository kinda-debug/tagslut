# Artifacts Directory

Runtime outputs from recovery workflows. Large files (databases) are gitignored; structure is preserved.

## Subdirectories

### `db/`
SQLite databases (gitignored - too large)
- `music.db` - Primary multi-library database
- `library.db` - Legacy library database
- Snapshots and backups

### `logs/`
Execution logs from scan/match/relocate operations
- Scan progress logs
- Error logs
- Move operation logs

### `manifests/`
TSV manifests from file relocation operations
- Source path, destination path, checksums
- Used for audit trail and rollback

### `tmp/`
Temporary files during processing
- Batch file lists
- Intermediate plans

### `reports/` (created by workflows)
CSV/JSON reports from analysis
- Match results
- Decision plans
- Duplicate group exports

## What Gets Committed

- `.gitkeep` files (preserve structure)
- This README
- Small config/reference files

## What's Gitignored

- `*.db`, `*.sqlite` (databases)
- `*.log` (runtime logs)
- Large CSVs (reports > 1MB)

## Recreating Artifacts

After fresh clone:
```bash
# Directories exist via .gitkeep
# Databases created by scanning:
python3 -m dedupe.cli scan-library --root /path/to/music --db artifacts/db/music.db
```
