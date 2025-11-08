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

## Workflow playbook

### Overview
The toolkit wraps scanning, repair, quarantine analysis, and deduplication into
reusable commands so you can tame very large music libraries from a single entry
point (`python -m dedupe.cli`). The CLI exposes health, sync, and quarantine
workflows, each targeting a specific stage in restoring your library’s
integrity and removing duplicates.

### Process-by-process breakdown
1. **Comprehensive health scanning**  
   `dedupe health scan ROOT` walks a directory tree, validating every supported
   file with `flac -t` and falling back to an `ffmpeg` decode when necessary,
   flagging truncated or otherwise unreadable audio in the process.  
   Run the legacy `flac_scan.py` script when you want the historical SQLite
   database (`_DEDUP_INDEX.db`) and M3U playlists of broken files; the POST-SCAN
   workflow shows exactly how to invoke it and store all failures for triage.

   *Example for truncated or stitched-together recoveries*

   - Scan the entire library and capture a playlist of every file that fails
     playback tests:

     ```bash
     python scripts/flac_scan.py --root "$ROOT" --workers 4 --verbose --broken-playlist "$ROOT/broken_files_unrepaired.m3u"
     ```

   - Pull specific problem cases (e.g., truncated tails) from the SQLite
     database by querying the `health_note` column so you can target them in
     batches.

2. **Repair in a staging area**  
   Always copy suspect files into an isolated `REPAIRED` directory before
   touching the originals; the repair helper re-encodes problematic tracks with
   `ffmpeg`, keeps per-file logs, and avoids surprises in the main library.  
   Re-run the scan against the staging directory to confirm the repairs actually
   fixed the truncation or accidental concatenation issues before syncing
   anything back.

   *Example workflow for truncated plus misnamed files*

   - Feed the broken playlist into `flac_repair.py`, outputting to a timestamped
     staging folder:

     ```bash
     python scripts/flac_repair.py --playlist broken_files_unrepaired.m3u --output "$REPAIRED" --capture-stderr
     ```

   - If you discover a file actually contains two stitched tracks, split it
     manually (or re-rip), then re-run the health scan on the repaired versions
     to make sure durations now match expectations.

3. **Quarantine deep dives**  
   The quarantine sub-commands focus on metadata vs. reality mismatches.
   `quarantine analyse` captures `ffprobe` details, PCM hashes, and Chromaprint
   fingerprints—perfect for spotting two files that look similar but differ in
   bit-depth or length.  
   `quarantine length` specifically compares container-reported durations with
   decoded audio lengths so you can isolate overlong or underlong files—the
   exact symptom you described for stitched recordings.

   *Example for “longer than displayed length”*

   - Point `quarantine length` at the suspect directory to emit a CSV of every
     mismatch between tag-based and decoded durations.
   - Sort the CSV by absolute duration delta; the worst offenders typically
     signal either hidden appended content or truncated metadata. Follow up with
     `quarantine analyse` on those files to cross-check PCM hashes and
     fingerprints before deciding whether to keep, split, or discard them.

4. **Deduplication and synchronisation**  
   Once repairs succeed, `dedupe sync` compares each staged copy against the
   primary library, choosing the healthiest version using size, mtime, and
   health scores, then moving, deleting, or swapping files as needed while
   pruning empty directories.  
   The POST-SCAN guide shows how to dry-run dedupe operations, inspect CSV
   reports of winners vs. losers, and only commit deletions after you’ve verified
   that the “losers” are corrupt, low-bitrate, or unwanted duplicates.

   - Creating M3U playlists of loser files lets you audition them manually before
     committing deletions, which is helpful when filenames differ slightly but
     you want to keep the highest-quality encode.

   *Example for slightly different names, sizes, and bitrates*

   - After scanning and repairing, run:

     ```bash
     python scripts/flac_dedupe.py --root "$ROOT" --dry-run --verbose --trash-dir "$ROOT/_TRASH_DUPES_preview"
     ```

     to produce a CSV that ranks duplicates by health, size, and modification
     time.
   - Export the “losers” playlist and audition any pairs where the names or
     metadata diverge; fix tags or rename in the staging area as needed.
   - When satisfied, re-run `flac_dedupe.py` with `--commit` to move confirmed
     duplicates into `_TRASH_DUPES`, keeping a reversible audit trail.

### Putting it together for your library
1. Scan and classify every file, generating both the SQLite index and playlists
   of broken or suspicious tracks. This surfaces truncated recoveries, hidden
   concatenations, and files whose metadata contradicts their contents.
2. Repair or re-rip in isolation, validate the fixes, and only then reintegrate
   the clean versions. Keep backups of the originals until you’re confident the
   repairs are correct.
3. Use quarantine analytics to focus on duration mismatches and subtle quality
   differences. CSV outputs make it easy to filter by anomalies such as extra
   duration or unexpected bit-depth changes.
4. Synchronise and dedupe using staged directories, dry-run reports, and loser
   playlists so you can resolve naming inconsistencies and choose the
   best-quality copies before committing changes.

Following this loop—scan ➜ repair ➜ analyse ➜ dedupe—gives you a repeatable path
to untangle a huge, messy collection while preserving backups and audit trails
at every step.

## Project layout

```
src/dedupe/
    cli.py          # argparse based CLI with health/sync/quarantine sub-commands
    health.py       # shared health check primitives and CLI helpers
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
