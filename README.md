# dedupe — unified audio repair and deduplication toolkit

The repository now ships a single, well-documented command line interface that
wraps the historical scripts for scanning, repairing, deduplicating, and
auditing large music libraries.  The codebase has been reorganised into a
`dedupe` package with reusable modules for health checking, synchronisation, and
quarantine analysis.

## Highlights

- **Single entry point** – `python -m dedupe.cli …` or `poetry run dedupe …`
  provides sub-commands for sync and quarantine workflows.
- **Reusable modules** – `dedupe.sync`, `dedupe.health`, and
  `dedupe.quarantine` expose typed helper functions that replace ad-hoc scripts.
- **Compatibility wrappers** – legacy scripts remain as thin adapters around the
  new package, so existing automation keeps working.
- **Comprehensive documentation** – `docs/` captures architecture diagrams,
  configuration guidance, and workflow notes.

## Quick start

1. Create a virtual environment and install dependencies:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Run the test-suite to confirm the environment:

   ```bash
   pytest -q
   ```

3. Inspect the available sub-commands:

   ```bash
   python -m dedupe.cli --help
   ```

## Command line interface

```
usage: dedupe [-h] {health,sync,quarantine} ...
```

### `health`
Run integrity probes against files either discovered recursively under a root
directory or listed explicitly in a spreadsheet.  The command replaces the
historical `audio_health_check*.py` scripts and keeps the behaviour available in
two sub-modes:

- `health scan ROOT` – walk `ROOT` recursively, checking supported extensions
  with `flac -t` or an `ffmpeg` decode fallback.
- `health from-spreadsheet SHEET` – load file paths from the first column of an
  `.xlsx` or `.csv` file and run the same health probes.

Both sub-commands accept `--log` to redirect log output and `--workers` to tune
the thread pool size.

### `sync`
Synchronise the staged dedupe directory with the primary library, moving the
healthiest copy into place and pruning stale duplicates.

Key options:
- `--library-root PATH` – music library root (auto-detected from `config.toml`).
- `--dedupe-root PATH` – override the staging directory discovered via
  `DEDUPE_DIR.txt`.
- `--health-check {auto,none}` – control playback verification behaviour.
- `--verify-library` – perform a full playback audit after synchronisation.

### `quarantine`
Analyse quarantine directories using three dedicated sub-commands:
- `quarantine analyse` – full ffprobe/fingerprint/PCM hash capture.
- `quarantine scan` – lightweight duration/size inventory.
- `quarantine length` – detect reported/decoded duration mismatches.

Each command accepts `--limit` to cap processed files and `--output` to write a
CSV report.

## Project layout

```
src/dedupe/
    cli.py          # argparse based CLI with health/sync/quarantine sub-commands
    health.py       # shared health check primitives
    health_cli.py   # helpers shared by the health CLI entry points
    quarantine.py   # quarantine analysis utilities
    sync.py         # core dedupe synchronisation logic
scripts/
    dedupe_sync.py                  # compatibility wrapper around dedupe.sync
    analyze_quarantine_subdir.py    # compatibility wrappers for quarantine tools
    simple_quarantine_scan.py
    detect_playback_length_issues.py
```

Additional documentation lives under `docs/`.

## Data artifacts

Historical quarantine reports, reconciliation CSVs, and helper playlists are
now collected under `artifacts/` to keep the project root focused on source
code.  The directory is subdivided into:

- `artifacts/reports/` – CSV and text exports produced by repair and
  reconciliation workflows.
- `artifacts/playlists/` – Playlist snapshots that document past dedupe runs.

The move is organisational only; scripts that need to consume the files can
reference the new paths without any further changes.

## Testing

All unit tests reside under `tests/` and focus on pure Python helpers.  Run the
suite with `pytest`.  CI or local development should also exercise
`make lint` when available.

## Further reading

- [Architecture overview](docs/architecture.md)
- [Process flow diagrams](docs/process_flow.md)
- [Configuration reference](docs/configuration.md)
- [Usage examples](USAGE.md)
- [Change history](CHANGELOG.md)
