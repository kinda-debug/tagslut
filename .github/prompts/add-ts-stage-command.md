# Add `ts-stage` — one-shot staged-files intake command

Do not recreate existing files. Read before editing.

## Problem

Ingesting already-downloaded files from a staging directory requires three
sequential commands:

1. `poetry run tagslut index register <path> --source <source> --execute`
2. `poetry run tagslut index duration-check <path> --execute`
3. `poetry run tagslut admin intake process-root --root <path> --phases enrich,art,promote --library /Volumes/MUSIC/MASTER_LIBRARY`

The v3 DB guard in `tools/review/process_root.py` blocks `register` and
`integrity` phases, so they cannot be included in `process-root`. This means
there is no single command to ingest staged files end-to-end. Add one.

## Solution

Add a new CLI command `tagslut admin intake stage` (alias: `ts-stage` via
`~/.zshrc`) that runs all three steps in sequence for a given directory.

## Implementation

### 1. New command: `tagslut admin intake stage`

File: `tagslut/cli/commands/admin_intake.py` (or wherever `admin intake
process-root` is registered — find it first, do not guess).

Add a new Click command `stage` to the same group as `process-root`:

```
tagslut admin intake stage [OPTIONS] ROOT
```

Options:
- `--source TEXT` — download source passed to `index register`; required;
  accepted values: `bpdl`, `tidal`, `qobuz`, `spotiflacnext`, `legacy`
- `--library PATH` — destination for promote phase; defaults to
  `$MASTER_LIBRARY` env var; error if neither provided and env var unset
- `--providers TEXT` — passed to enrich phase; default `beatport,tidal`
- `--dry-run` — pass through to all three steps, no writes
- `--db PATH` — DB path; falls back to `$TAGSLUT_DB`
- `--force` — pass `--force` to process-root enrich phase

Steps executed in order (stop on first non-zero exit):

1. **Register**: equivalent to
   `tagslut index register <ROOT> --source <SOURCE> [--db] [--execute | dry-run noop]`

2. **Duration check**: equivalent to
   `tagslut index duration-check <ROOT> [--execute | dry-run noop]`
   Note: `duration-check` takes PATH as positional arg, not `--root`.

3. **Process-root** (enrich + art + promote only): equivalent to
   `tagslut admin intake process-root --root <ROOT> --phases enrich,art,promote --library <LIBRARY> [--providers] [--force] [--dry-run] [--db]`

Call the underlying Python functions directly rather than shelling out, if
they are importable. If shelling out is simpler and the functions are not
cleanly importable, shell out via `subprocess.run` with `sys.executable`.

Print a clear header before each step:
```
=== Step 1/3: register ===
=== Step 2/3: duration-check ===
=== Step 3/3: enrich + art + promote ===
```

Print a final summary with the key result counters from each step.

### 2. Shell alias

Append to `~/.zshrc` if not already present:

```zsh
alias ts-stage='cd /Users/georgeskhawam/Projects/tagslut && export PATH="$HOME/.local/bin:$PATH" && poetry run tagslut admin intake stage'
```

Check for existing `ts-stage` alias before appending. Do not duplicate.

### 3. SCRIPT_SURFACE.md

Add a brief entry under "Canonical Entry Points" section documenting
`tagslut admin intake stage` and its purpose.

## Tests

File: `tests/cli/test_admin_intake_stage.py`

- Mock all three underlying calls (register, duration-check, process-root).
- Test: all three steps called in order with correct args.
- Test: `--dry-run` skips writes on register and duration-check steps.
- Test: error in step 1 stops execution (steps 2 and 3 not called).
- Test: `--library` defaults to `$MASTER_LIBRARY` env var.
- Test: missing `--library` and unset `$MASTER_LIBRARY` raises `UsageError`.

Run: `poetry run pytest tests/cli/test_admin_intake_stage.py -v`

## Commit

`feat(intake): add ts-stage one-shot staged-files intake command`
