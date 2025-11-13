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

## Operational tips

- All commands respect `--verbose` for detailed logging.
- SQLite outputs are safe to version-control; they enable offline analysis when
  the original volumes are not mounted.
- External tools (`ffprobe`, `fpcalc`) are optional.  When unavailable, the
  pipeline still records basic filesystem metadata, allowing matching to proceed
  with reduced fidelity.

## Testing and linting

```bash
pytest -q
flake8 dedupe
```

Run both commands before committing changes or opening a pull request.
