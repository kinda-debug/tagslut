# Usage and examples

This document contains common usage examples for the scanner and tips for
troubleshooting.

Running the scanner

From the repository root:

```bash
export PYTHONPATH="$(pwd)"
python3 scripts/flac_scan.py --root /path/to/music --workers 8 --verbose
```

Important options (common):
- `--root` — root directory to scan (default in script is a sample path).
- `--workers` — number of worker threads for audio analysis (increase for CPU-heavy machines).
- `--recompute` — force recomputation of fingerprints and segment hashes.
- `--skip-broken` — skip files that fail health checks (useful for large libraries with some corrupted files).
- `--auto-quarantine` — attempt to move frozen files into a `_BROKEN` directory when a freeze is detected.
- `--segwin-seconds` / `--segwin-step` / `--segwin-max-slices` — configure segment hashing parameters.

Diagnostics and troubleshooting
- Ensure external tools are installed: `ffmpeg`, `fpcalc` (Chromaprint), `flac`, and `metaflac`.
- If the scanner appears to hang, the watchdog and freeze detector attempt to
  recover by killing stalled ffmpeg instances. On macOS the process escalation
  uses `pkill` (TERM then KILL) or falls back to `killall`.
- Diagnostic dumps are written to the diagnostic root configured via
  `--diagnostic-root` (default: `~/.dedupe_diagnostics` or the CLI-provided path).

Optional progress bars
----------------------

If you want a progress bar during long scans, install `tqdm` into your
environment and run the command with `--verbose`. Without `tqdm` the CLI will
still honour `--verbose` but print coarse progress messages instead of a
progress bar:

```bash
python3 -m pip install tqdm
python3 scripts/flac_scan.py --root /path/to/music --workers 8 --verbose
```

Testing
- Tests assume you run them from the repository root with the project on
  `PYTHONPATH`:

```bash
export PYTHONPATH="$(pwd)"
pytest -q
```

Example: running a quick, limited scan (dry run flow)

```bash
# Create a small directory with a few FLACs and run the scanner with 2 workers
python3 scripts/flac_scan.py --root /tmp/mytestmusic --workers 2 --verbose
```

If you need help with a specific failure, include the diagnostic outputs from
the diagnostics root and the log file `_DEDUP_SCAN_LOG.txt` written into the
scanned root directory.
