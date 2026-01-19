# Duration Validation

## Overview

The duration validation system detects corrupted or improperly recovered audio files by comparing actual file duration against expected duration from metadata sources (MusicBrainz, Discogs, etc.).

## Common Issues Detected

### 1. **Stitched Recovery Files** (R-Studio artifacts)
When files are recovered using R-Studio or similar tools, multiple audio fragments may be incorrectly concatenated into a single file, resulting in:
- File plays longer than the actual track
- Extra silence or garbage data at the end
- Typically >10 seconds longer than expected

### 2. **Truncated Files**
Files that are shorter than expected may indicate:
- Incomplete downloads
- Corrupt or damaged files
- Recording failures

### 3. **Metadata Inconsistencies**
Files with missing or incorrect MusicBrainz metadata that prevents validation.

## How It Works

### Automatic Detection During Scanning

During file scanning, the system:

1. **Extracts actual duration** from FLAC metadata (`audio.info.length`)
2. **Extracts expected duration** from tags:
   - `MUSICBRAINZ_TRACK_LENGTH` (milliseconds)
   - `EXPECTED_LENGTH` (seconds)
   - `ORIGINAL_LENGTH` (seconds)
   - `DISCOGS_DURATION` (various formats)
3. **Compares durations** with tolerance threshold (default: 2 seconds)
4. **Flags suspicious files**:
   - \u26a0\ufe0f Critical: >10 seconds difference (likely stitched)
   - \u26a0\ufe0f Critical: Shorter than expected (truncated)
   - \ud83d\udfe1 Warning: 2-10 seconds difference (minor mismatch)
5. **Auto-assigns zone**: Files with suspicious durations go to `suspect` zone

### Integration with Zone Assignment

Files failing duration validation are treated like integrity failures:

```python
zone_str = determine_zone(
    integrity_ok=flac_ok and not duration_suspicious,
    is_duplicate=False,
    file_path=path_obj,
    library_root=library_root,
    staging_root=staging_root,
)
```

**Result**: Suspicious files automatically assigned to `suspect` zone for manual review.

## Usage

### 1. **Automatic During Scanning**

Duration validation runs automatically when scanning files:

```bash
python tools/integrity/scan.py /path/to/music --check-integrity
```

Files with duration mismatches will:
- Log warnings during scan
- Be assigned to `suspect` zone
- Appear in scan summary

### 2. **Dedicated Duration Validation Tool**

Scan existing database for duration issues:

```bash
# Check all files
python tools/integrity/validate_durations.py

# Check only suspect zone
python tools/integrity/validate_durations.py --zone suspect

# Use strict tolerance (0.5 seconds instead of 2)
python tools/integrity/validate_durations.py --strict

# Generate JSON report
python tools/integrity/validate_durations.py -o duration_report.json -v
```

### 3. **Review Flagged Files**

After validation, review files in the JSON report:

```json
{
  "summary": {
    "total_checked": 5000,
    "with_expected_duration": 3200,
    "critical_count": 45,
    "warning_count": 120
  },
  "critical_files": [
    {
      "path": "/path/to/track.flac",
      "actual_duration": 245.5,
      "expected_duration": 215.3,
      "difference": 30.2,
      "type": "too_long",
      "likely_stitched": true
    }
  ]
}
```

## Configuration

### Tolerance Thresholds

Defined in [dedupe/core/duration_validator.py](../dedupe/core/duration_validator.py):

```python
DEFAULT_TOLERANCE_SECONDS = 2.0   # Standard tolerance
STRICT_TOLERANCE_SECONDS = 0.5    # Strict mode
STITCHED_FILE_THRESHOLD = 10.0    # Flag if >10s longer
```

### Expected Duration Sources

Priority order for expected duration:

1. **MusicBrainz**: `MUSICBRAINZ_TRACK_LENGTH` tag (milliseconds)
2. **Custom tags**: `EXPECTED_LENGTH`, `ORIGINAL_LENGTH` (seconds)
3. **Discogs**: `DISCOGS_DURATION` (various formats)

## Integration with Other Tools

### AcoustID Fingerprinting

Duration validation complements AcoustID for identifying problematic files:

- **AcoustID**: Verifies audio content matches expected recording
- **Duration**: Verifies file length matches expected track length

Combined approach:
```bash
# 1. Scan with integrity checks (includes duration)
python tools/integrity/scan.py /path --check-integrity

# 2. Run acoustic duplicate detection
python tools/decide/recommend_acoustic.py --db music.db

# 3. Validate durations in suspect zone
python tools/integrity/validate_durations.py --db music.db --zone suspect
```

### Promote by Tags

The [promote_by_tags.py](../tools/review/promote_by_tags.py) script preserves MusicBrainz metadata during promotion:

- Keeps `MUSICBRAINZ_TRACK_LENGTH` for future validation
- Preserves all metadata tags during file organization
- Tracks promotions in database for audit trail

## Workflow Example

### Identifying and Fixing Stitched Files

1. **Scan recovered files**:
   ```bash
   python tools/integrity/scan.py /Volumes/RECOVERY --check-integrity
   ```

2. **Review duration report**:
   ```bash
   python tools/integrity/validate_durations.py --db music.db --zone suspect -o stitched_report.json
   ```

3. **Examine critical files** (likely stitched):
   - Files >10 seconds longer than expected
   - Check `likely_stitched: true` in JSON report

4. **Manual triage**:
   - Listen to files to confirm stitching
   - Re-rip or find clean source
   - Mark for quarantine if unfixable

5. **Update zone decisions**:
   ```bash
   # If file is confirmed bad
   UPDATE files SET zone = 'quarantine' WHERE path = '/path/to/stitched.flac';
   ```

## Technical Details

### DurationMismatch Object

```python
@dataclass
class DurationMismatch:
    path: Path
    actual_duration: float
    expected_duration: float
    difference: float
    mismatch_type: str  # "too_long", "too_short", "within_tolerance"
    severity: str       # "critical", "warning", "info"
    source: str         # "musicbrainz", "metadata", "manual"
    
    @property
    def is_suspicious(self) -> bool:
        return self.severity in ("critical", "warning")
    
    @property
    def is_likely_stitched(self) -> bool:
        return self.mismatch_type == "too_long" and self.difference > 10.0
```

### Database Schema

Duration stored in `files` table:

```sql
CREATE TABLE files (
    path TEXT PRIMARY KEY,
    duration REAL,          -- Actual duration from FLAC metadata
    metadata_json TEXT,     -- Contains expected duration tags
    zone TEXT,              -- Auto-assigned based on validation
    ...
);
```

## See Also

- [Integrity Scanning](SCANNING.md) - FLAC integrity checks
- [Duplicate Detection](../tools/decide/README.md) - AcoustID and SHA256 matching
- [Zone Assignment](../dedupe/core/zone_assignment.py) - Auto-zone logic
- [Promote by Tags](../tools/review/promote_by_tags.py) - File organization workflow
