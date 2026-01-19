# Audio Integrity Validation Workflow

This guide shows how to use duration validation, AcoustID fingerprinting, and the promote_by_tags workflow together to identify and handle problematic audio files.

## Three-Layer Validation Approach

### Layer 1: FLAC Integrity (Structure)
**Tool:** `flac -t` (via integrity scanner)  
**Detects:** Corrupt FLAC structure, bitstream errors, header issues

### Layer 2: Duration Validation (Length)
**Tool:** Duration validator  
**Detects:** Stitched recoveries (too long), truncated files (too short)

### Layer 3: AcoustID (Content)
**Tool:** AcoustID fingerprinting  
**Detects:** Wrong audio content, mismatched recordings

## Complete Workflow

### 1. Initial Scan with All Checks

```bash
# Scan recovered files with integrity checks
python tools/integrity/scan.py /Volumes/RECOVERY --check-integrity

# What this does:
# - FLAC integrity check (flac -t)
# - Duration validation (actual vs MusicBrainz expected)
# - SHA256 hashing for duplicate detection
# - Auto-assigns zones based on results
```

**Expected output:**
- Clean files in library → `accepted` zone
- Integrity failures → `suspect` zone
- Duration mismatches → `suspect` zone
- Duplicates → `suspect` zone

### 2. Review Duration Mismatches

```bash
# Check for stitched/truncated files in suspect zone
python tools/integrity/validate_durations.py \
  --zone suspect \
  --output duration_report.json \
  --verbose

# Review the JSON report
cat duration_report.json | jq '.critical_files[] | select(.likely_stitched == true)'
```

**Key indicators:**
- 🔴 Files >10 seconds longer → Likely stitched R-Studio recovery
- 🔴 Files shorter than expected → Truncated/incomplete
- 🟡 2-10 second difference → Minor encoding variance

### 3. Run AcoustID Duplicate Detection

```bash
# Find acoustic duplicates (same audio content)
python tools/decide/recommend_acoustic.py \
  --db /path/to/music.db \
  --output acoustic_dupes.json
```

**What this detects:**
- Multiple copies of same track with same audio
- Different encodings of same performance
- Verify stitched files don't match any known good copies

### 4. Cross-Reference Results

Create a triage list combining all three checks:

```bash
# Files failing multiple checks are highest priority
sqlite3 /path/to/music.db <<SQL
SELECT 
    path,
    flac_ok,
    zone,
    duration,
    (SELECT COUNT(*) FROM files f2 WHERE f2.streaminfo_md5 = files.streaminfo_md5) as dupe_count
FROM files
WHERE zone = 'suspect'
ORDER BY 
    CASE WHEN flac_ok = 0 THEN 1 ELSE 2 END,
    dupe_count DESC;
SQL
```

### 5. Manual Review & Decisions

#### For Stitched Files (Duration Too Long)

1. **Listen to the file** - Check for extra silence/noise at end
2. **Check AcoustID** - Does it match a known good copy?
3. **Decision:**
   - **If stitched:** Mark for quarantine, re-rip from source
   - **If legitimately longer:** Update MusicBrainz metadata or add `expected_length` tag

```bash
# Mark confirmed stitched file for removal
python tools/decide/mark_for_quarantine.py /path/to/stitched.flac
```

#### For Truncated Files (Duration Too Short)

1. **Check playback** - Does it cut off early?
2. **Check source** - Can you re-rip or re-download?
3. **Decision:**
   - **If truly truncated:** Quarantine, get new copy
   - **If false positive:** Update metadata

#### For AcoustID Duplicates

1. **Compare quality** - Check bitrate, sample rate, bit depth
2. **Check provenance** - Which has better metadata?
3. **Decision:**
   - **Keep best copy** - Higher quality, complete metadata
   - **Drop others** - Move to quarantine

### 6. Promote Clean Files

After triage, promote files from staging to library:

```bash
# Promote files with complete, verified metadata
python tools/review/promote_by_tags.py \
  /Volumes/STAGING \
  /Volumes/LIBRARY \
  --execute

# This preserves:
# - All MusicBrainz metadata (including track length)
# - AcoustID fingerprints
# - Duration data
# - Integrity check results
```

**Benefits:**
- Files organized in canonical structure
- All validation metadata preserved
- Database tracks promotion for audit trail
- Future scans can re-validate

## Real-World Examples

### Example 1: R-Studio Recovered Album

**Scenario:** Recovered 12-track album, some tracks might be stitched

```bash
# Step 1: Scan with integrity
python tools/integrity/scan.py /Volumes/RECOVERY/Album --check-integrity

# Step 2: Check durations
python tools/integrity/validate_durations.py --db music.db --zone suspect

# Output shows:
# Track 03.flac: 🔴 CRITICAL - 32 seconds too long (likely stitched)
# Track 07.flac: 🔴 CRITICAL - 25 seconds too long (likely stitched)
# Track 11.flac: 🟡 WARNING - 3 seconds too long

# Step 3: Manual review
# - Listen to Track 03, Track 07 → Confirm stitching, extra noise at end
# - Listen to Track 11 → Fade-out is longer, legitimate

# Step 4: Action
# - Quarantine Track 03, Track 07
# - Update Track 11 metadata: expected_length = actual duration
# - Promote remaining 10 clean tracks
```

### Example 2: Duplicate Detection with Duration

**Scenario:** Multiple versions of same album from different sources

```bash
# Step 1: Run acoustic duplicate detection
python tools/decide/recommend_acoustic.py --db music.db

# Output shows 3 copies of "Track.flac":
# Copy A: 215.3s, 16/44.1, MusicBrainz metadata ✓
# Copy B: 245.5s, 16/44.1, No metadata (stitched!)
# Copy C: 215.2s, 24/96, MusicBrainz metadata ✓

# Step 2: Duration validation confirms:
# Copy A: ✓ OK (matches expected 215.3s)
# Copy B: 🔴 CRITICAL (30s too long, likely stitched)
# Copy C: ✓ OK (0.1s variance, within tolerance)

# Step 3: Decision
# - Keep Copy C (highest quality, valid duration)
# - Drop Copy A (lower quality duplicate)
# - Quarantine Copy B (stitched recovery)
```

## Quick Reference Commands

```bash
# Full integrity scan with duration validation
python tools/integrity/scan.py /path --check-integrity

# Check durations in suspect zone
python tools/integrity/validate_durations.py --zone suspect

# Strict duration checking (0.5s tolerance)
python tools/integrity/validate_durations.py --strict

# Find acoustic duplicates
python tools/decide/recommend_acoustic.py -o dupes.json

# Promote clean files
python tools/review/promote_by_tags.py /source /dest --execute

# Query suspect files
sqlite3 "$DEDUPE_DB" "SELECT path, flac_ok, duration FROM files WHERE zone='suspect';"
```

## Configuration Tips

### Adjust Duration Tolerance

Edit `dedupe/core/duration_validator.py`:

```python
# For classical music or live recordings (more variance)
DEFAULT_TOLERANCE_SECONDS = 5.0

# For electronic/pop (tight timing)
DEFAULT_TOLERANCE_SECONDS = 1.0
```

### Zone Priority for Duplicates

Edit `config.toml`:

```toml
[decisions]
zone_priority = ["accepted", "staging", "suspect"]
metadata_tiebreaker = true
```

## Troubleshooting

### "No expected duration found"

**Problem:** File has no MusicBrainz metadata  
**Solution:** Tag with MusicBrainz Picard, or add manual `expected_length` tag

### "False positive - file is legitimately longer"

**Problem:** Extended version, live recording, etc.  
**Solution:** Update metadata:
```bash
metaflac --set-tag=EXPECTED_LENGTH=<actual> file.flac
```

### "AcoustID not working"

**Problem:** pyacoustid not installed  
**Solution:** 
```bash
pip install pyacoustid
# Also install fpcalc binary (Chromaprint)
brew install chromaprint  # macOS
apt install libchromaprint-tools  # Linux
```

## See Also

- [DURATION_VALIDATION.md](DURATION_VALIDATION.md) - Detailed duration validation guide
- [SCANNING.md](SCANNING.md) - Integrity scanning documentation
- [OPERATOR_GUIDE.md](OPERATOR_GUIDE.md) - Complete workflow guide
- [promote_by_tags.py](../tools/review/promote_by_tags.py) - File promotion tool
