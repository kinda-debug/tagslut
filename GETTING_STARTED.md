# Getting Started with Dedupe CLI

Now that all scripts are organized and consolidated, here's how to use them.

## Quick Start

### 1. Basic Scanning

```bash
# Scan your music library
./dedupe scan --root /Volumes/dotad/MUSIC

# With verbose output
./dedupe scan --root /Volumes/dotad/MUSIC --verbose

# With multiple workers for faster scanning
./dedupe scan --root /Volumes/dotad/MUSIC --workers 6
```

### 2. Repair Broken Files

```bash
# Repair a specific file
./dedupe repair --file /path/to/broken.flac

# Repair with output directory
./dedupe repair --file /path/to/broken.flac --output /Volumes/dotad/MUSIC/REPAIRED

# Overwrite in place
./dedupe repair --file /path/to/broken.flac --overwrite
```

### 3. Find and Remove Duplicates

```bash
# Preview duplicates (dry run)
./dedupe dedupe --root /Volumes/dotad/MUSIC --dry-run

# Actually remove duplicates
./dedupe dedupe --root /Volumes/dotad/MUSIC --commit
```

### 4. Promote Healthy Copies

```bash
# Preview sync operations
./dedupe sync --dry-run

# Execute sync
./dedupe sync
```

### 5. Complete Workflow

Run everything from scan to dedupe:

```bash
# Preview the entire workflow
./dedupe workflow  # (dry-run by default)

# Actually execute the workflow
./dedupe workflow --commit
```

## Advanced: Utility Managers

### Manage Dedupe Plans

For working with dedupe CSV reports:

```bash
# Check plan integrity
./dedupe plan check --csv /path/to/report.csv

# Preview moves
./dedupe plan apply --dry-run

# Apply moves in batches
./dedupe plan apply --commit --batch-size 100

# Verify all moves succeeded
./dedupe plan verify
```

### Repair Workflow Manager

For finding and repairing unhealthy files:

```bash
# Search for missing files
./dedupe repair-workflow search --basenames missing.txt

# Combine search results
./dedupe repair-workflow combine --indir /tmp --out candidates.txt

# Mark unfound as irretrievable
./dedupe repair-workflow mark-irretrievable report.json

# Find and repair unhealthy keepers
./dedupe repair-workflow run --list unhealthy.txt --apply
```

### Post-Repair Utilities

```bash
# Clean up broken file playlists
./dedupe post-repair clean-playlist

# Promote repaired files to final location
./dedupe post-repair promote --src file.flac --dest-root /path/to/music
```

## Help & Documentation

### Get Help

```bash
# General help
./dedupe --help

# Help for specific command
./dedupe scan --help
./dedupe dedupe --help
./dedupe plan --help
```

### Read Full Documentation

- **README.md** - Project overview and main commands
- **scripts/README.md** - Complete scripts directory guide
- **COMPLETE_CONSOLIDATION.md** - Consolidation summary
- **USAGE.md** - Detailed usage guide

## Direct Script Access

You can also call scripts directly from `scripts/` if needed:

```bash
# Python script direct invocation
python scripts/flac_scan.py --root /path/to/music
python scripts/dedupe_plan_manager.py check --csv report.csv

# Shell script direct invocation
bash scripts/stage_hash_dupes.sh "$db" "/path/to/music" 25 true
```

## Common Tasks

### Task: Scan and identify duplicates

```bash
./dedupe scan --root /Volumes/dotad/MUSIC --verbose
./dedupe dedupe --dry-run
```

### Task: Repair broken files

```bash
./dedupe repair --file /path/to/broken.flac --output /Volumes/dotad/MUSIC/REPAIRED
./dedupe post-repair promote --src /path/to/repaired.flac
```

### Task: Full cleanup workflow

```bash
# 1. Scan
./dedupe scan --root /Volumes/dotad/MUSIC

# 2. Repair any broken files
./dedupe repair --file /path/to/broken.flac

# 3. Remove duplicates
./dedupe dedupe --commit

# 4. Sync healthy copies
./dedupe sync

# 5. Verify everything
./dedupe plan verify
```

## File Organization

All scripts are in `scripts/` directory:

```
scripts/
├── Core workflow scripts
│   ├── flac_scan.py
│   ├── flac_repair.py
│   ├── flac_dedupe.py
│   ├── dedupe_sync.py
│   └── flac_workflow.py
│
├── Consolidated managers
│   ├── dedupe_plan_manager.py
│   ├── repair_workflow.py
│   └── post_repair.py
│
└── Utilities and shell scripts
    ├── find_missing_candidates.py
    ├── combine_found_candidates.py
    ├── mark_irretrievable.py
    ├── stage_hash_dupes.sh
    └── ... (other utilities)
```

## Troubleshooting

### "Command not found: dedupe"

Make sure you're running it from the project root:
```bash
cd /path/to/dedupe
./dedupe scan --help
```

Or use the Python version:
```bash
python dedupe.py scan --help
```

### Scripts not found error

Make sure the `scripts/` directory exists and contains the expected files:
```bash
ls scripts/flac_scan.py
```

### Permission denied

Make the CLI executable:
```bash
chmod +x dedupe
```

## Tips

1. **Always use `--dry-run` first** to preview changes before committing
2. **Use `-verbose` for detailed output** when debugging issues
3. **Check `--help`** for all available options for any command
4. **Read error messages carefully** - they often suggest fixes
5. **Keep backups** of important files before running `--commit`

## Support

For issues with specific scripts:
1. Check the script's help: `./dedupe <command> --help`
2. Read the README: `cat README.md`
3. Check scripts directory README: `cat scripts/README.md`
4. Review the code comments in the specific script
