# P2 — Staging Intake Sweep

## Purpose
Process all unprocessed staging batches into the DB. Reads the TSV produced
by P1 to know what exists. No files are moved to MASTER_LIBRARY yet — this
prompt only updates the DB and produces a per-batch report.

## Prerequisite
P1 must have run. TSV exists at `/Volumes/MUSIC/logs/inventory_*.tsv` (use
the most recent one).

## Do not recreate existing files. Do not run the full test suite.

---

## What "unprocessed" means

A staging batch is unprocessed if its files appear in the P1 TSV with
`in_asset_file=0`. Batches already fully in the DB are skipped.

## Locations to process, in order

1. `staging/SpotiFLACnext` — use `tagslut intake spotiflac` with `--base-dir`
   for each `.txt` Download Report found. Use the non-`_converted` `.m3u8`
   for path resolution.
2. `staging/SpotiFLAC` — same, for each `.txt` log file found.
3. `staging/bpdl` — use `tagslut intake bpdl` if implemented, else log as
   "manual required" and skip.
4. `staging/StreamripDownloads` — use `tagslut intake streamrip` if
   implemented, else log as "manual required" and skip.
5. `staging/tidal` — use `tagslut intake tidal` if implemented, else log.
6. Any remaining files in `staging/` not covered above — log as
   "unrecognised source, manual required".

## Per-batch report

For each batch write one line to
`/Volumes/MUSIC/logs/intake_sweep_YYYYMMDD_HHMMSS.tsv`:
```
batch_name  source  total_tracks  ingested  already_in_db  failed  notes
```

## Implementation

Write as `tools/intake_sweep.py`. It:
- Discovers batches by scanning staging subdirs for `.txt` files and
  known folder structures
- Calls the appropriate `tagslut intake` CLI command per batch via subprocess,
  capturing stdout/stderr
- Parses CLI output for success/fail counts
- Writes the per-batch TSV report
- Never touches `_UNRESOLVED`, `_UNRESOLVED_FROM_LIBRARY`, `MP3_LIBRARY`,
  `MASTER_LIBRARY` proper, or `_work`

## Script entrypoint

```
cd /Users/georgeskhawam/Projects/tagslut
export PATH="$HOME/.local/bin:$PATH"
poetry run python3 tools/intake_sweep.py
```

## Acceptance

Script runs to completion. TSV report written. Print final summary:
```
Batches processed: N
Tracks ingested: N  |  Already in DB: N  |  Failed: N  |  Manual required: N
Output: /Volumes/MUSIC/logs/intake_sweep_YYYYMMDD_HHMMSS.tsv
```

## Commit

```
feat(tools): add intake_sweep.py for automated staging batch intake
```
