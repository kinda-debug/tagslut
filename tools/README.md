# Tools Directory

Operational utilities for duplicate review, integrity checking, and automated decision-making.

## Duplicate Review Workflow

### export_dupe_groups.py
Export dupeGuru CSV results into organized A/B comparison directories.

```bash
tools/export_dupe_groups.py --csv /path/to/dupeguru.csv \
                            --out /Volumes/COMMUNE/10_STAGING/_DUPE_REVIEW
```

**Output structure:**
```
_DUPE_REVIEW/
  group_0001/
    A_library_track.flac
    B_library_track.flac
  group_0002/
    A_library_track.flac
    C_library_track.flac
```

### listen_dupes.sh
Interactive FLAC listening tool using fzf + mpv for fast terminal-based audio preview.

```bash
# Browse all files in review root
tools/listen_dupes.sh

# Browse specific group
tools/listen_dupes.sh group_0001

# Browse from file list
tools/listen_dupes.sh candidates.txt
```

**Environment variables:**
- `DUPE_REVIEW_ROOT` - Review directory (default: `/Volumes/COMMUNE/10_STAGING/_DUPE_REVIEW`)
- `PREVIEW_LENGTH` - Preview duration in seconds (default: 15)
- `PREVIEW_VOLUME` - Playback volume 0-100 (default: 50)

### open_dupe_pair.sh
Open duplicate group files side-by-side in VS Code for visual comparison.

```bash
tools/open_dupe_pair.sh group_0001
```

**Recommended VS Code extensions:**
- **Audio Preview** - Play audio files directly in editor
- **VSCode-Spectrogram** - Waveform and frequency visualization

## Decision Engine

### recommend_keepers.py
Deterministic KEEP/REVIEW decision engine for duplicate audio files.

**Decision hierarchy:**
1. **FLAC integrity** - Corrupt files → flag for review
2. **Identity** - AcoustID conflicts → REVIEW
3. **Duration** - ±0.2s from reference (longer never wins)
4. **Quality** - Bit depth > sample rate > bitrate
5. **Metadata** - Tie-breaker only

```bash
# Dry-run (report only)
tools/recommend_keepers.py --db "$DEDUPE_DB" \
                           --group-field dupeguru_group_id \
                           --out /tmp/recommendations.csv

# Apply decisions to database
tools/recommend_keepers.py --db "$DEDUPE_DB" \
                           --group-field dupeguru_group_id \
                           --out /tmp/recommendations.csv \
                           --apply
```

**Output columns:**
- `path` - File path
- `decision` - KEEP | REVIEW
- `decision_reason` - Explanation (e.g., `flac_corrupt`, `best_quality`, `duration_mismatch`)
- `decision_confidence` - HIGH | MEDIUM | LOW
- `duration_delta` - Seconds from reference duration

### review_needed.sh
Helper for reviewing files flagged REVIEW by decision engine.

```bash
# Review all REVIEW decisions
tools/review_needed.sh /tmp/recommendations.csv REVIEW

# Review specific group
tools/review_needed.sh /tmp/recommendations.csv group_0042

# Review specific file
tools/review_needed.sh /tmp/recommendations.csv "/Volumes/COMMUNE/10_STAGING/..."
```

### dupeguru_bridge.py
Integrate dupeGuru similarity evidence into decision confidence.

**Evidence integration rules:**
- Similarity < 95% + same checksum → REVIEW (metadata confusion)
- Similarity ≥ 95% + duration Δ > 0.5s → flag as TAINTED (stitched file)
- Similarity < 80% + decision=KEEP → downgrade confidence to MEDIUM

```bash
# Import dupeGuru similarity scores
tools/dupeguru_bridge.py --db "$DEDUPE_DB" \
                         --dupeguru /path/to/dupeguru.csv \
                         --apply
```

## Integrity Checking

### scan_flac_integrity.py
Parallel FLAC integrity testing using `flac -t`. Writes `flac_ok` and `integrity_state` columns to the database.

```bash
# Scan all files in database (parallel)
tools/scan_flac_integrity.py --db "$DEDUPE_DB" --parallel 8

# Scan only unchecked files
tools/scan_flac_integrity.py --db "$DEDUPE_DB" --unchecked-only
```

### find_corrupt_flacs.sh
Find corrupt FLAC files in any directory tree.

```bash
# Find and list corrupt files
tools/find_corrupt_flacs.sh /Volumes/COMMUNE/10_STAGING/_DUPE_REVIEW

# Save to file
tools/find_corrupt_flacs.sh /Volumes/COMMUNE/10_STAGING/_DUPE_REVIEW > corrupt_list.txt

# Find and reject
tools/find_corrupt_flacs.sh /Volumes/COMMUNE/10_STAGING/_DUPE_REVIEW --move-to /Volumes/COMMUNE/90_REJECTED
```

## Database Utilities

### db_upgrade.py
Database schema migration tool (legacy).

### manual_ingest.py
Manual file ingestion helper (legacy).

### move_to_hrm.py
Move files to HRM directory structure (legacy).

## Workflow Summary

**Complete duplicate resolution workflow:**

```bash
# 1. Export dupeGuru groups to organized folders
tools/export_dupe_groups.py --csv /path/to/dupeguru.csv \
                            --out /Volumes/COMMUNE/10_STAGING/_DUPE_REVIEW

# 2. Scan FLAC integrity (parallel)
tools/scan_flac_integrity.py --db "$DEDUPE_DB" --parallel 8

# 3. Generate keeper recommendations (dry-run first)
tools/recommend_keepers.py --db "$DEDUPE_DB" \
                           --group-field dupeguru_group_id \
                           --out /tmp/recovery_recs.csv

# 4. Review flagged cases
tools/review_needed.sh /tmp/recovery_recs.csv REVIEW

# 5. Integrate dupeGuru similarity evidence
tools/dupeguru_bridge.py --db "$DEDUPE_DB" \
                         --dupeguru /path/to/dupeguru.csv \
                         --apply

# 6. Regenerate recommendations with evidence
tools/recommend_keepers.py --db "$DEDUPE_DB" \
                           --group-field dupeguru_group_id \
                           --out /tmp/recovery_recs_final.csv

# 7. Apply decisions to database
tools/recommend_keepers.py --db "$DEDUPE_DB" \
                           --group-field dupeguru_group_id \
                           --out /tmp/recovery_recs_final.csv \
                           --apply
```

## Core Principles

1. **Hash before flatten** - Always compute checksums before flattening directory structures
2. **Integrity beats everything** - Corrupt files are always flagged for review
3. **Duration authority** - "Longer never wins" (rejects stitched/padded files)
4. **Listen to verify, not decide** - Automated recommendations; listening confirms edge cases
5. **Non-destructive by default** - All tools dry-run unless `--apply` specified
