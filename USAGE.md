# Usage

This document captures end-to-end workflows for the unified `dedupe` CLI.  Each
stage builds on SQLite databases and CSV reports so work can resume even when
external volumes are unavailable.

## 1. Scan the reference library

```bash
dedupe scan-library --root /Volumes/dotad/MUSIC --out artifacts/db/library.db --resume
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
dedupe scan-library --root /Volumes/dotad/MUSIC --out artifacts/db/library.db --resume --fingerprints
```

Run the command against additional volumes to build a consolidated database:

```bash
dedupe scan-library --root /Volumes/Vault --out artifacts/db/library.db --resume
dedupe scan-library --root /Volumes/sad --out artifacts/db/library.db --resume
```

After each run you can verify new entries via SQLite:

```bash
sqlite3 artifacts/db/library.db "SELECT path, fingerprint IS NOT NULL AS has_fp FROM library_files ORDER BY mtime DESC LIMIT 5;"
```

## 2. Parse R-Studio exports

```bash
python3 -m dedupe.cli parse-rstudio --input Recognized.txt --out artifacts/db/recovered.db --verbose
```

The parser normalises absolute paths, captures the suggested filenames provided
by R-Studio, and persists everything under the `recovered_files` table.  The
command is idempotent, so it can be re-run as more exports arrive.

## 3. Match recovered candidates

```bash
dedupe match \
  --library artifacts/db/library.db \
  --recovered artifacts/db/recovered.db \
  --out artifacts/reports/matches.csv
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
dedupe generate-manifest \
  --matches artifacts/reports/matches.csv \
  --out artifacts/reports/recovery_manifest.csv
```

The manifest attaches priorities and operator notes to every match, highlighting
files that need manual review or immediate attention.  Rows marked `critical`
should be prioritised for restoration.

## Operational tips

- All commands respect `--verbose` for detailed logging.
- SQLite outputs are safe to version-control; they enable offline analysis when
  the original volumes are not mounted.
- External tools (`ffprobe`, `fpcalc`) are optional.  When unavailable, the
  pipeline still records checksums, duration, bitrate, and filenames so matching
  continues uninterrupted.
- To refresh fingerprints only, rerun the scan command with `--resume --fingerprints`.
  Existing metadata is preserved and new fingerprints are added where missing.

## Testing and linting

```bash
pytest -q
flake8 dedupe
```

Run both commands before committing changes or opening a pull request.
