# Usage

This document captures end-to-end workflows for the unified `dedupe` CLI.  Each
stage builds on SQLite databases and CSV reports so work can resume even when
external volumes are unavailable.

## 1. Scan the reference library

```bash
export DEDUPE_DB="/Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-08/music.db"
export LEGACY_LIBRARY_DB="/Users/georgeskhawam/Projects/dedupe_db/legacy/library.db"
export RECOVERED_DB="/Users/georgeskhawam/Projects/dedupe_db/legacy/recovered.db"

python3 -m dedupe.cli scan-library --root /Volumes/RECOVERY_TARGET/Root/FINAL_LIBRARY --db "$LEGACY_LIBRARY_DB" --resume --verbose --batch-size 2000
# If you are scanning a COMMUNE layout, tag the rows with:
#   --zone accepted
```

Chromaprint fingerprints are optional.  Use them only when you must
differentiate files that match on duration and size but originate from different
masters.

- `--resume` skips unchanged files using a size + modification-time check and
  only recomputes metadata for new or modified files.
- `--fingerprints` requests Chromaprint extraction when `fpcalc` is on `PATH`.
  If `fpcalc` is missing, the scan completes without warnings and fingerprints
  are left as `NULL`.

Optional fingerprint-enabled scan:

```bash
python3 -m dedupe.cli scan-library --root /Volumes/RECOVERY_TARGET/Root/FINAL_LIBRARY --db "$LEGACY_LIBRARY_DB" --resume --fingerprints --verbose --batch-size 2000
# Optional (COMMUNE layout): add --zone accepted|staging
```

Run the command against additional volumes only when needed. If you're using a COMMUNE layout, pass `--zone accepted` or `--zone staging` so decision tooling can prioritize keepers correctly.

After each run you can verify new entries via SQLite:

```bash
sqlite3 "$LEGACY_LIBRARY_DB" "SELECT path, fingerprint IS NOT NULL AS has_fp FROM library_files ORDER BY mtime DESC LIMIT 5;"
```

## 2. Parse R-Studio exports

```bash
python3 -m dedupe.cli parse-rstudio --input Recognized.txt --out "$RECOVERED_DB" --verbose
```

The parser normalises absolute paths, captures the suggested filenames provided
by R-Studio, and persists everything under the `recovered_files` table.  The
command is idempotent, so it can be re-run as more exports arrive.

## 3. Match recovered candidates

```bash
python3 -m dedupe.cli match \
  --library "$LEGACY_LIBRARY_DB" \
  --recovered "$RECOVERED_DB" \
  --out artifacts/reports/matches.csv \
  --verbose
```

Matching proceeds through checksum → duration → bitrate → filename similarity
heuristics.  Fingerprints, when present, are treated as an enhancement on top of
those signals; their absence does not alter the default ordering.

The resulting CSV includes:

- `classification` – `exact`, `truncated`, `potential_upgrade`, `missing`, or
  `orphan`.
- `score` – overall confidence (0–1).
- `filename_similarity` – raw ratio from the matcher.
- `size_difference` – signed byte delta (`recovered - library`).

## 4. Generate a recovery manifest

```bash
python3 -m dedupe.cli generate-manifest \
  --matches artifacts/reports/matches.csv \
  --out artifacts/reports/recovery_manifest.csv \
  --verbose
```

The manifest attaches priorities and operator notes to every match, highlighting
files that need manual review or immediate attention.  Rows marked `critical`
should be prioritised for restoration.

## 5. Duplicate review and decision workflow

### Export dupeGuru results to organized folders

```bash
tools/export_dupe_groups.py --csv /path/to/dupeguru.csv \
                            --out /Volumes/COMMUNE/10_STAGING/_DUPE_REVIEW
```

Creates clean A/B comparison directories:
```
_DUPE_REVIEW/
  group_0001/
    A_library_track.flac
    B_library_track.flac
  group_0002/
    ...
```

### Interactive listening and comparison

```bash
# Terminal-based listening with fzf + mpv
tools/listen_dupes.sh group_0001

# Visual comparison in VS Code (waveform + spectrogram)
tools/open_dupe_pair.sh group_0001
```

### FLAC integrity checking

```bash
# Parallel integrity scan (writes integrity_state and flac_ok columns to DB)
tools/scan_flac_integrity.py --db "$DEDUPE_DB" --parallel 8

# Find corrupt files in any directory
tools/find_corrupt_flacs.sh /Volumes/COMMUNE/10_STAGING/_DUPE_REVIEW

# Find and reject corrupt files
tools/find_corrupt_flacs.sh /Volumes/COMMUNE/10_STAGING/_DUPE_REVIEW --move-to /Volumes/COMMUNE/90_REJECTED
```

### Automated keeper/loser recommendations

```bash
# Generate KEEP/REVIEW decisions (dry-run)
tools/recommend_keepers.py --db "$DEDUPE_DB" \
                           --group-field dupeguru_group_id \
                           --out /tmp/recovery_recommendations.csv

# Review files flagged REVIEW
tools/review_needed.sh /tmp/recovery_recommendations.csv REVIEW

# Integrate dupeGuru similarity evidence
tools/dupeguru_bridge.py --db "$DEDUPE_DB" \
                         --dupeguru /path/to/dupeguru.csv \
                         --apply

# Apply final decisions to database (review markers only)
tools/recommend_keepers.py --db "$DEDUPE_DB" \
                           --group-field dupeguru_group_id \
                           --out /tmp/recovery_recommendations.csv \
                           --apply
```

### Decision hierarchy (enforced by recommend_keepers.py)

1. **FLAC integrity** – `valid`, `recoverable`, `corrupt` states are recorded; non-valid files are flagged for review.
2. **Identity** – AcoustID recording ID conflicts → REVIEW
3. **Duration** – Within ±0.2s of reference → VALID; longer files never auto-win
4. **Quality** – Bit depth > sample rate > bitrate (among VALID files only)
5. **Metadata** – Tie-breaker for identical technical specs

### VS Code extensions for audio review

Recommended for visual comparison:
- **Audio Preview** – Play FLAC/WAV/M4A directly in editor
- **VSCode-Spectrogram** – Waveform and frequency analysis

## Operational tips

- All commands respect `--verbose` for detailed logging.
- SQLite outputs are safe to version-control; they enable offline analysis when
  the original volumes are not mounted.
- External tools (`ffprobe`, `fpcalc`) are optional.  When unavailable, the
  pipeline still records basic filesystem metadata, allowing matching to proceed
  with reduced fidelity.
- **Hash before flatten**: Always compute checksums before flattening directory structures
- **Integrity before quality**: Run FLAC integrity checks before quality-based decisions
- **Listen to verify, not decide**: Use automated recommendations; listening confirms edge cases

## Testing and linting

```bash
pytest -q
flake8 dedupe
```

Run both commands before committing changes or opening a pull request.
