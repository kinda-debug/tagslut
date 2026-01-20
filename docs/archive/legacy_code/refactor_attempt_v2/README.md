# Dedupe V2: Auto-Zone Assignment System

## Overview

The V2 system implements **automatic zone assignment** based on scan results and file location. This eliminates the need to manually specify zones during scanning, making the workflow simpler and more reliable.

## Key Differences from V1

| Aspect | V1 (Legacy) | V2 (Current) |
|--------|-------------|--------------|
| Zone Assignment | Manual via `--zone` flag | Automatic based on integrity + location |
| Workflow | Scan → Manually assign zone | Scan → Auto-assign zone |
| Integrity Checks | Optional | Integrated into zone logic |
| Configuration | Hardcoded paths | `.env` config with `VOLUME_LIBRARY`, `VOLUME_STAGING` |

## Zone Assignment Logic

### Automatic Assignment Rules

Zones are assigned **during scanning** based on two factors:

1. **File Health** (integrity check + duration validation)
2. **File Location** (path relative to configured roots)

```
┌─────────────────────────────────────────────────────────────┐
│ File scanned with integrity check + SHA256                  │
└─────────────────────────┬───────────────────────────────────┘
                          │
                    ┌─────▼──────┐
                    │ Integrity  │
                    │   Failed?  │
                    └─────┬──────┘
                          │
                  ┌───────┴───────┐
                  │               │
                YES              NO
                  │               │
             SUSPECT         ┌────▼─────┐
                             │ Duration │
                             │  Failed? │
                             └────┬─────┘
                                  │
                          ┌───────┴───────┐
                          │               │
                        YES              NO
                          │               │
                     SUSPECT         ┌────▼──────┐
                                     │ Duplicate │
                                     │ Detected? │
                                     └────┬──────┘
                                          │
                                  ┌───────┴───────┐
                                  │               │
                                YES              NO
                                  │               │
                             SUSPECT         ┌────▼────────┐
                                             │ Check Path  │
                                             └────┬────────┘
                                                  │
                        ┌─────────────────────────┼──────────────────────┐
                        │                         │                      │
                   In LIBRARY                In STAGING            Elsewhere
                        │                         │                      │
                    ACCEPTED                  STAGING                SUSPECT
```

### Zone Descriptions

- **`accepted`**: Clean files in the canonical library (`VOLUME_LIBRARY`)
  - ✓ Integrity passed
  - ✓ Duration valid (if metadata available)
  - ✓ No duplicates detected
  - ✓ Located in library root

- **`staging`**: Clean files ready to promote (`VOLUME_STAGING`)
  - ✓ Integrity passed
  - ✓ Duration valid
  - ✓ No duplicates detected
  - ✓ Located in staging area
  - ⚠️ Not yet moved to library

- **`suspect`**: Files requiring review
  - ⚠️ Integrity failed OR
  - ⚠️ Duration mismatch (likely R-Studio stitched/truncated) OR
  - ⚠️ Duplicate detected OR
  - ⚠️ Unknown location (not in library/staging)

- **`quarantine`**: Permanently excluded files
  - ❌ Manual decision to exclude
  - ❌ Corrupt beyond repair
  - ❌ Confirmed duplicates to delete

## Configuration

Edit `.env` in the project root:

```bash
# Database location
DEDUPE_DB=/Users/you/Projects/dedupe_db/EPOCH_20260119/music.db

# Library root (accepted zone)
VOLUME_LIBRARY=/Volumes/COMMUNE/M/Library_CANONICAL

# Staging root (staging zone)
VOLUME_STAGING=/Volumes/COMMUNE/M/Staging
```

## Usage

### Scanning with Auto-Zone Assignment

```bash
# Load environment and scan
export $(cat .env | grep -v '^#' | xargs)

# Scan with integrity check only
python tools/integrity/scan.py /Volumes/MyDrive --check-integrity -v

# Scan with integrity + SHA256 hashing
python tools/integrity/scan.py /Volumes/MyDrive --check-integrity --check-hash -v

# Scan with parallel processing (faster)
python tools/integrity/scan.py /Volumes/MyDrive --check-integrity --check-hash --parallel 8 -v
```

**No `--zone` flag needed!** Zones are automatically assigned.

### Reviewing Auto-Assigned Zones

```bash
# Check zone distribution
sqlite3 $DEDUPE_DB "
SELECT zone, COUNT(*) as count 
FROM files 
GROUP BY zone 
ORDER BY zone;
"

# Find suspect files
sqlite3 $DEDUPE_DB "
SELECT path, flac_ok, integrity_state 
FROM files 
WHERE zone='suspect' 
LIMIT 10;
"
```


### Manual Zone Overrides

If you need to manually change a zone assignment:

```bash
# Move specific file to quarantine
sqlite3 $DEDUPE_DB "
UPDATE files 
SET zone='quarantine' 
WHERE path='/path/to/corrupt/file.flac';
"

# Promote staging files to accepted
sqlite3 $DEDUPE_DB "
UPDATE files 
SET zone='accepted' 
WHERE zone='staging' AND flac_ok=1;
"
```

### Applying a Plan (Decisions)

To apply a plan (such as from deduplication or review), use:

```bash
export $(cat .env | grep -v '^#' | xargs)
python tools/decide/apply.py plan.json
```

**Note:**
- Do NOT use `--db` with `apply.py`. The database is resolved from your `.env` file (DEDUPE_DB).
- The plan file is a positional argument.

## Promoting Files by Plan (KEPT)

To promote only the files marked as "KEPT" in your deduplication plan:

1. **Run your plan/apply step:**
   ```bash
   python tools/decide/apply.py plan.json
   # Output: Kept: XXXX, Dropped: XXXX, etc.
   ```

2. **Extract KEPT file paths from plan.json:**
   ```bash
   python3 -c "import json; d=json.load(open('plan.json')); out=open('kept.txt','w'); [out.write(dec['path']+'\n') for group in d['plan'] for dec in group['decisions'] if dec.get('action')=='KEEP']; out.close()"
   # This creates kept.txt with one file path per line
   ```

3. **Promote the KEPT files using promote_by_tags.py:**
   ```bash
   python tools/review/promote_by_tags.py --paths-from-file kept.txt --dest-root /Volumes/COMMUNE/M/Library_CANONICAL --execute
   # Add --db "$DEDUPE_DB" if you want to track promotions in the database
   ```

- This process allows you to promote only the reviewed/approved files, regardless of their original location.
- You can use any text file with one path per line as input to --paths-from-file.

## Testing

The V2 system includes comprehensive tests:

```bash
# Test zone assignment logic
python dedupe_v2/test_zone_logic.py

# Test database compatibility
python dedupe_v2/test_db_compatibility.py
```

## Migration from V1

If you have existing scans with manual zones:

1. **Files are compatible**: The database schema hasn't changed
2. **Re-scan to auto-assign**: New scans will use V2 auto-assignment
3. **Old zones preserved**: Files scanned with V1 keep their manual zones until re-scanned

## Integration with Other Tools

### Duration Validation

The auto-zone system integrates with duration validation:

```python
# In metadata.py
duration_suspicious = check_file_duration(actual_duration, tags)

# In zone_assignment.py
zone = determine_zone(
    integrity_ok=flac_ok and not duration_suspicious,  # ← Duration treated as integrity
    is_duplicate=False,
    file_path=path,
    library_root=library_root,
    staging_root=staging_root,
)
```

Files with duration mismatches (>2s difference from expected) are assigned to `suspect`.

### Roon Integration

Files in the library (`accepted` zone) can be enhanced with Roon metadata:

```bash
# Import MusicBrainz IDs from Roon export
python tools/integrity/import_roon.py --roon-export roon.xlsx --update-musicbrainz --execute

# Then validate durations
python tools/integrity/validate_durations.py --zone accepted -o duration_report.json
```

## Architecture

### Module Structure

```
dedupe_v2/
├── README.md                    # This file
├── __init__.py
├── core/
│   ├── __init__.py
│   └── zone_assignment.py       # Core zone logic
├── utils/
│   └── __init__.py
├── test_zone_logic.py           # Unit tests
└── test_db_compatibility.py     # Integration tests
```

### Core Function

```python
def determine_zone(
    *,
    integrity_ok: bool,           # Integrity + duration validation
    is_duplicate: bool,           # SHA256 duplicate detection
    file_path: Path,              # File being scanned
    library_root: Optional[Path], # From VOLUME_LIBRARY
    staging_root: Optional[Path], # From VOLUME_STAGING
) -> ZoneType:
    """Auto-assign zone based on scan results and location."""
```

## Troubleshooting

### Files assigned to wrong zone?

Check your `.env` configuration:

```bash
# Verify paths
cat .env | grep VOLUME_

# Expected output:
# VOLUME_LIBRARY=/Volumes/COMMUNE/M/Library_CANONICAL
# VOLUME_STAGING=/Volumes/COMMUNE/M/Staging
```

### All files going to `suspect`?

This usually means:
1. Files are not in `VOLUME_LIBRARY` or `VOLUME_STAGING` paths
2. Integrity checks are failing
3. Duration validation is detecting mismatches

Check the scan logs:
```bash
python tools/integrity/scan.py /Volumes/MyDrive --check-integrity -v 2>&1 | grep "Zone="
```

### Need to bypass auto-assignment?

The auto-zone system is the recommended workflow. If you need manual control, you can:

1. Let auto-assignment run
2. Use SQL to override zones manually
3. Use the promotion workflow for manual curation

## Benefits

1. **No human error**: No forgetting to specify `--zone` or using wrong zone
2. **Consistent logic**: Same rules applied across all scans
3. **Location-aware**: Files automatically inherit zone from their location
4. **Integrity-first**: Failed files always go to suspect, never accepted
5. **Audit trail**: Zone assignment is logged and traceable

## See Also

- [docs/SCANNING.md](../docs/SCANNING.md) - Complete scanning workflow
- [docs/DURATION_VALIDATION.md](../docs/DURATION_VALIDATION.md) - Duration validation details
- [ROON_INTEGRATION.md](../ROON_INTEGRATION.md) - Roon metadata integration
- [docs/CONFIG.md](../docs/CONFIG.md) - Environment configuration
