# Usage

This document captures end-to-end workflows for the unified `dedupe` CLI.  Each
stage builds on SQLite databases and CSV reports so work can resume even when
external volumes are unavailable.

## 1. Scan the reference library

```bash
python3 -m dedupe.cli scan-library --root /Volumes/dotad/MUSIC --out artifacts/db/library.db --verbose
```

Key options:

- `--fingerprints` – include Chromaprint fingerprints for downstream matching.
- `--root` – directory tree to scan (multiple invocations can populate the same
  database).
- `--out` – SQLite database storing the `library_files` table.

## 2. Parse R-Studio exports

```bash
python3 -m dedupe.cli parse-rstudio --input Recognized.txt --out artifacts/db/recovered.db --verbose
```

The parser normalises absolute paths, captures the suggested filenames provided
by R-Studio, and persists everything under the `recovered_files` table.  The
command is idempotent, so it can be re-run as more exports arrive.

## 3. Match recovered candidates

```bash
python3 -m dedupe.cli match \
  --library artifacts/db/library.db \
  --recovered artifacts/db/recovered.db \
  --out artifacts/reports/matches.csv \
  --verbose
```

The matcher compares filename similarity and file sizes to classify each
recovery candidate.  The resulting CSV includes:

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
tools/export_dupe_groups.py --csv /Volumes/sad/sad_dupeguru.csv \
                            --out /Volumes/sad/_DUPE_REVIEW
```

Creates clean A/B comparison directories:
```
_DUPE_REVIEW/
  group_0001/
    A_dotad_track.flac
    B_sad_track.flac
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
# Parallel integrity scan (writes flac_ok column to DB)
tools/scan_flac_integrity.py --db ~/Projects/_audit/sad_hash.sqlite --parallel 8

# Find corrupt files in any directory
tools/find_corrupt_flacs.sh /Volumes/sad/_DUPE_REVIEW

# Find and quarantine corrupt files
tools/find_corrupt_flacs.sh /Volumes/sad/_DUPE_REVIEW --move-to /Volumes/sad/_CORRUPT
```

### Automated keeper/loser recommendations

```bash
# Generate KEEP/DROP/REVIEW decisions (dry-run)
tools/recommend_keepers.py --db ~/Projects/_audit/sad_hash.sqlite \
                           --group-field dupeguru_group_id \
                           --out /tmp/sad_recommendations.csv

# Review files flagged REVIEW
tools/review_needed.sh /tmp/sad_recommendations.csv REVIEW

# Integrate dupeGuru similarity evidence
tools/dupeguru_bridge.py --db ~/Projects/_audit/sad_hash.sqlite \
                         --dupeguru /Volumes/sad/sad_dupeguru.csv \
                         --apply

# Apply final decisions to database
tools/recommend_keepers.py --db ~/Projects/_audit/sad_hash.sqlite \
                           --group-field dupeguru_group_id \
                           --out /tmp/sad_recommendations.csv \
                           --apply
```

### Decision hierarchy (enforced by recommend_keepers.py)

1. **FLAC integrity** – Corrupt files (`flac -t` fails) → auto-DROP (HIGH confidence)
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
