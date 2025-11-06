# dedupe — audio deduplication toolkit

Small utilities for scanning, detecting and managing duplicated or corrupted
lossless audio files (primarily FLAC). This repository provides a scanner that
indexes FLAC files, computes fingerprints and segment hashes, and a set of
tools to detect and plan removal or quarantine of duplicates.

This repository is meant to be run from the repository root. The primary
scripts live under `scripts/` and helper modules live under
`scripts/lib/`.

Key features
- Fast multithreaded FLAC scanning (fingerprint, PCM hash, segment hashes)
- Freeze-detection and automatic targeted kills of stalled `ffmpeg` processes
- Diagnostics collection for `fpcalc` and `ffmpeg` failures
- Database-backed index (`_DEDUP_INDEX.db`) and run history

Quick start

1. Create a venv and install dependencies (macOS / Linux):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Run the test suite to confirm the environment is working:

```bash
export PYTHONPATH="$(pwd)"
pytest -q
```

3. Run a scan (example):

```bash
python scripts/flac_scan.py --root /path/to/music --workers 4 --verbose
```

Important notes
- The scanner expects command-line tools like `ffmpeg`, `fpcalc`, `flac`,
  and `metaflac` to be available on PATH. Use your package manager to install
  them if missing.
- On macOS the freeze detector will attempt targeted kills of ffmpeg process
  groups. If that fails it falls back to `pkill`/`killall` (TERM then KILL).
- When running from tests or CI, set `PYTHONPATH` to the project root so the
  `scripts` package is importable (see test commands above).

Files of interest
- `scripts/flac_scan.py` — main scanner CLI.
- `scripts/flac_dedupe.py` — grouping and dedupe planning tools.
- `scripts/lib/common.py` — shared helpers, watchdog and freeze detector logic.
- `tests/` — unit tests.

Where to get help
- See `USAGE.md` for common CLI examples and troubleshooting tips.
- Check `CHANGELOG.md` for recent behavioral changes.
