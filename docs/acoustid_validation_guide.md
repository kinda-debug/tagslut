# AcoustID-Based Repair Validation

## Overview

This document explains the AcoustID fingerprint-based validation system for verifying that repaired FLAC files are correct and contain no spliced/concatenated audio residue from other tracks.

## Problem Statement

When repairing corrupted FLAC files, it's possible that:
1. **Duration metadata** gets corrupted or incorrect (e.g., file claims to be 3 minutes but is actually 5)
2. **Spliced audio** occurs where residue from another track is concatenated to the file (producing wrong content)
3. **Partial re-encoding** leaves the file in an inconsistent state

Simply checking duration alone is insufficient—you need **audio content verification**.

## Solution: Chromaprint Fingerprinting

The `validate_repair_with_acoustid.py` script uses **Chromaprint** (via `fpcalc`) to:

1. **Extract audio fingerprints** from multiple sliding windows across the file
2. **Compare fingerprints** to detect if audio changes unexpectedly (indicating a splice)
3. **Flag problematic files** that show inconsistent fingerprints across windows

### Sliding Window Strategy

Instead of a single fingerprint for the entire file, we use **multiple overlapping windows**:

```
Window 1: [0-30s]
Window 2: [20-50s]
Window 3: [40-70s]
Window 4: [60-90s]
Window 5: [80-110s]
...
```

**Why this works:**
- If all windows produce the **same fingerprint** → Single track, no splice ✅
- If fingerprints **vary significantly** → Possible splice detected ⚠️

### Consistency Ratio

The script calculates:

$$\text{Consistency Ratio} = 1 - \frac{\text{Unique Fingerprints} - 1}{\text{Total Fingerprints}}$$

**Interpretation:**
- **Ratio ≥ 0.8**: Highly consistent (safe) ✅
- **Ratio 0.6-0.8**: Mostly consistent (acceptable)
- **Ratio < 0.6**: Highly inconsistent (possible splice detected) ⚠️

## Usage

### Basic Validation

```bash
python3 scripts/validate_repair_with_acoustid.py /Volumes/dotad/REPAIRED_STAGING --verbose
```

### With CSV Output

```bash
python3 scripts/validate_repair_with_acoustid.py /Volumes/dotad/REPAIRED_STAGING \
  --output-csv /tmp/repair_validation.csv \
  --verbose
```

### With Expected Duration

```bash
python3 scripts/validate_repair_with_acoustid.py /Volumes/dotad/REPAIRED_STAGING \
  --expected-duration 240.0 \
  --tolerance 2.0 \
  --output-csv /tmp/repair_validation.csv
```

## Output Fields

The validation script generates a report with these fields:

| Field | Type | Description |
|-------|------|-------------|
| `path` | string | Full file path |
| `valid` | boolean | Overall validation result |
| `reason` | string | If invalid, why it failed |
| `duration` | float | Detected duration in seconds |
| `duration_delta` | float | Difference from expected (if provided) |
| `codec` | string | Audio codec (e.g., "flac") |
| `fingerprint_count` | int | Number of fingerprints extracted |
| `consistency_ratio` | float | Fingerprint consistency (0.0-1.0) |
| `error` | string | Any exceptions encountered |

## Interpreting Results

### Valid File ✅

```json
{
  "path": "/Volumes/dotad/REPAIRED_STAGING/song.flac",
  "valid": true,
  "reason": "OK",
  "duration": 245.3,
  "codec": "flac",
  "fingerprint_count": 5,
  "consistency_ratio": 0.95
}
```

### Invalid: Duration Mismatch ⚠️

```json
{
  "path": "/Volumes/dotad/REPAIRED_STAGING/song.flac",
  "valid": false,
  "reason": "Duration mismatch: 180.5s vs expected 240.0s (delta=59.5s)",
  "duration": 180.5,
  "duration_delta": 59.5,
  "codec": "flac"
}
```

### Invalid: Splice Detected ⚠️

```json
{
  "path": "/Volumes/dotad/REPAIRED_STAGING/song.flac",
  "valid": false,
  "reason": "Fingerprints inconsistent (ratio=0.35); possible splice detected",
  "duration": 240.0,
  "fingerprint_count": 5,
  "consistency_ratio": 0.35
}
```

## Dependencies

The validation requires:

```bash
# System packages
ffmpeg          # Audio re-encoding and extraction
ffprobe         # Metadata extraction
fpcalc          # Chromaprint fingerprint calculator

# Python packages
tqdm            # Progress bars (optional but recommended)
```

### Installation

```bash
# macOS
brew install ffmpeg chromaprint

# Verify installation
which ffmpeg ffprobe fpcalc
```

## Comparison with Manual Checks

### ✗ Insufficient: Just checking duration

```python
if abs(file_duration - expected) < 2.0:
    print("OK")
```

**Problem:** Doesn't detect spliced audio if durations happen to match.

### ✓ Better: Chromaprint fingerprinting

```python
fps = get_fingerprints_sliding_windows(path)
consistency_ratio = assess_fingerprint_consistency(fps)
if consistency_ratio > 0.6:
    print("OK - Single track, no splice")
```

**Benefit:** Catches spliced audio even if duration matches.

## Integration with Repair Pipeline

1. **Repair files** → Output to `/Volumes/dotad/REPAIRED_STAGING`
2. **Validate repairs** → Run `validate_repair_with_acoustid.py`
3. **Review results** → Check CSV for any invalid files
4. **Handle failures** → Re-repair or manual inspection of flagged files
5. **Move to production** → Move validated files back to `/Volumes/dotad/Quarantine`

## Performance

- **Per-file validation time:** ~0.7-1.2 seconds (50 files ≈ 40-60 seconds)
- **Bottleneck:** ffmpeg window extraction (CPU-bound)
- **Fingerprint extraction:** Fast (~0.1s per window after ffmpeg)

### Optimization Options

1. **Reduce window count:** `--max-windows 3` (faster, slightly less accurate)
2. **Parallel processing:** Run validation on multiple files simultaneously
3. **Skip validation:** If files already validated at source

## Advanced: Direct Usage in Python

```python
from scripts.validate_repair_with_acoustid import validate_repair

# Single file validation
result = validate_repair(
    Path("/path/to/file.flac"),
    expected_duration=240.0,
    tolerance_sec=2.0,
)

if result["valid"]:
    print(f"✅ File validated: {result['consistency_ratio']:.2f} ratio")
else:
    print(f"⚠️ File failed: {result['reason']}")

# Fingerprint inspection
from scripts.validate_repair_with_acoustid import get_fingerprints_sliding_windows

fps, duration = get_fingerprints_sliding_windows(Path("song.flac"))
print(f"Duration: {duration}s")
print(f"Fingerprints: {fps}")
```

## Troubleshooting

### ❌ "fpcalc not found"

```bash
brew install chromaprint
# Then restart terminal or add to PATH
```

### ❌ "ffprobe not found"

```bash
brew install ffmpeg
```

### ❌ "timeout on {file}"

File is taking too long to decode. This usually indicates:
- Very large file (> 1GB)
- Corrupted encoding that's slow to process
- Insufficient system resources

**Solution:** Increase timeout or validate separately

### ❌ Low consistency ratio but file plays fine

Possible causes:
1. **Dynamic audio** (e.g., electronic music with phase shifts between windows)
2. **Very short files** (< 30 seconds) that don't have 5 windows
3. **Unusual encoding** (e.g., VBR with drastic bitrate changes)

**Solution:** Review manually before flagging as invalid

## Next Steps

After validation:

1. **All valid?** → Move files: `cp -r /Volumes/dotad/REPAIRED_STAGING/* /Volumes/dotad/Quarantine/`
2. **Some invalid?** → Investigate and potentially re-repair
3. **Many invalid?** → Review repair strategy (may need different encoder settings)

## References

- [Chromaprint Documentation](https://acoustid.org/chromaprint)
- [AcoustID API](https://acoustid.org/webservice)
- [FLAC Specification](https://xiph.org/flac/)
