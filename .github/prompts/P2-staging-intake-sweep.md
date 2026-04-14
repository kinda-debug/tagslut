# P2 — Staging Intake Sweep (v2)

## Context — read before implementing

The previous P2 attempt produced zero ingestions. Two root causes:

1. `tagslut intake spotiflac` resolves ISRCs from the `.txt` report only.
   The tag-enrichment hook added to `build_manifest` populates ISRCs from
   file tags AFTER path resolution, but only when called via `build_manifest`.
   The CLI calls `build_manifest` already — verify this is wired correctly
   before proceeding.

2. Most SpotiFLACnext batches have no `.txt` — only `.m3u8` files. The CLI
   requires a log file as the positional argument. For M3U8-only batches,
   we must synthesize a minimal log or use `--base-dir` with a dummy log.

## Do not recreate existing files. Do not run the full test suite.

---

## Step 1 — Verify tag enrichment is wired into CLI intake

Read `tagslut/cli/commands/intake.py`. Find the `intake_spotiflac` command.
Confirm that `build_manifest` is called there (not a bare `parse_log_next`).
`build_manifest` calls `_enrich_from_tags` — this is correct.

If `intake_spotiflac` calls `parse_log_next` or `parse_log` directly instead
of `build_manifest`, fix it to call `build_manifest` instead.

Do NOT add a separate enrichment call. `build_manifest` already does it.

---

## Step 2 — Inventory what batches exist in staging

Write `tools/intake_sweep_v2.py`. At startup it discovers all batches:

### SpotiFLACnext batches (`/Volumes/MUSIC/staging/SpotiFLACnext`)

A batch is defined as any `.m3u8` file (non-`_converted`) in the staging root
or any subdirectory. For each `.m3u8`:
- Look for a `.txt` with the same stem in the same directory.
- The batch anchor is the `.txt` if it exists, else the `.m3u8` itself.
- `--base-dir` is always `/Volumes/MUSIC/staging/SpotiFLACnext`.

### SpotiFLAC batches (`/Volumes/MUSIC/staging/SpotiFLAC`)

A batch is any `.txt` file that is NOT a `_Failed` file. Discover all.
`--base-dir` is `/Volumes/MUSIC/staging/SpotiFLAC`.

---

## Step 3 — Run intake for each batch

For each discovered batch, call:

```python
import subprocess, sys

cmd = [
    sys.executable, "-m", "tagslut.cli.main",
    "intake", "spotiflac",
    "--base-dir", base_dir,
    anchor_path,
]
result = subprocess.run(cmd, capture_output=True, text=True,
                        cwd="/Users/georgeskhawam/Projects/tagslut")
```

Parse stdout for lines matching:
- `ingested N tracks` or similar summary
- `[would-ingest]` lines (count them)
- `[failed/` lines (count them)
- `Error:` lines

If the CLI is not importable as a module, use the poetry entrypoint instead:
```python
cmd = ["poetry", "run", "tagslut", "intake", "spotiflac", ...]
```

---

## Step 4 — Per-batch report

Write to `/Volumes/MUSIC/logs/intake_sweep_v2_YYYYMMDD_HHMMSS.tsv`:
```
batch_name  source  anchor_type  total_tracks  ingested  already_in_db  failed  notes
```

- `anchor_type`: `txt` or `m3u8_only`
- Parse counts from CLI stdout/stderr

---

## Step 5 — Re-run P1 inventory after intake

After all batches complete, re-run the inventory scan for
`staging_spotiflacnext` and `staging_spotiflac` only and append a summary
showing how many files moved from `in_asset_file=0` to `in_asset_file=1`.

---

## Script entrypoint

```
cd /Users/georgeskhawam/Projects/tagslut
export PATH="$HOME/.local/bin:$PATH"
poetry run python3 tools/intake_sweep_v2.py
```

## Acceptance

- Script runs to completion.
- At least one batch shows `ingested > 0`.
- TSV report written.
- Print final summary:
```
Batches processed: N
Tracks ingested: N  |  Already in DB: N  |  Failed: N
Output: /Volumes/MUSIC/logs/intake_sweep_v2_YYYYMMDD_HHMMSS.tsv
```

## Commit

```
fix(tools): rewrite intake_sweep_v2 with correct CLI invocation and m3u8-only batch support
```
