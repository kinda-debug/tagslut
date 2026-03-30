# CLI Verbose Progress Output

**COMMIT ALL CHANGES BEFORE EXITING. If you do not commit, the work is lost.**

**CRITICAL — READ BEFORE STARTING**: Do not modify any exec functions' core logic,
return types, or existing call signatures. Do not touch schema.py, migrations, or
any storage layer. Do not recreate files that already exist unless explicitly told to.

---

## Goal

Add a `--verbose` flag to all batch CLI commands. When `--verbose` is passed, each
processed item prints a progress line to stderr as it completes. When omitted, behavior
is identical to today (summary only).

---

## Implementation contract

### 1. Progress callback protocol

Define a shared type in `tagslut/cli/_progress.py` (new file):

```python
from __future__ import annotations
from typing import Callable, Optional

# Signature: progress_cb(label: str, index: int, total: int) -> None
ProgressCallback = Callable[[str, int, int], None]

def make_progress_cb(verbose: bool) -> Optional[ProgressCallback]:
    """Return a progress callback if verbose, else None."""
    if not verbose:
        return None
    import sys
    def _cb(label: str, index: int, total: int) -> None:
        print(f"[{index}/{total}] {label}", file=sys.stderr, flush=True)
    return _cb
```

### 2. Exec functions — add optional progress_cb parameter

For each exec function listed below, add `progress_cb: ProgressCallback | None = None`
as a keyword-only parameter. Call it once per item after the item completes:

```python
if progress_cb is not None:
    progress_cb(label_string, current_index, total_count)
```

Do NOT change return types, existing parameters, or internal logic. The callback is
purely additive — if None, the function behaves exactly as before.

**Exec functions to update:**

| File | Function |
|------|----------|
| `tagslut/exec/mp3_build.py` | `build_mp3_from_identity()` |
| `tagslut/exec/mp3_reconcile.py` | `reconcile_mp3_library()`, `reconcile_mp3_scan()` |
| `tagslut/exec/dj_backfill.py` | primary backfill function (read the file to find the name) |
| `tagslut/exec/dj_validate.py` | primary validate function (read the file to find the name) |
| `tagslut/exec/dj_xml_emit.py` | primary emit function (read the file to find the name) |

For each, determine the natural label string from the item being processed:
- mp3 build: FLAC path basename
- mp3 reconcile: MP3 file path basename
- dj backfill: identity_id or track title if available
- dj validate: identity_id
- dj xml emit: track title or identity_id

### 3. CLI commands — add --verbose flag and wire callback

For each command below, add:

```python
@click.option("--verbose", "-v", is_flag=True, default=False,
              help="Print per-item progress to stderr.")
```

And pass the callback into the exec function:

```python
from tagslut.cli._progress import make_progress_cb
cb = make_progress_cb(verbose)
result = exec_function(..., progress_cb=cb)
```

**Commands to update:**

| File | Command |
|------|---------|
| `tagslut/cli/commands/mp3.py` | `mp3 build`, `mp3 reconcile` |
| `tagslut/cli/commands/dj.py` | `dj backfill`, `dj validate`, `dj xml emit`, `dj xml patch` |
| `tagslut/cli/commands/index.py` | `index register`, `index enrich` |
| `tagslut/cli/commands/intake.py` | `intake url`, `intake run` |

For `index enrich` and `intake url`, the exec path may be more complex (multiple
internal calls). In those cases, wire the callback to the innermost loop that
processes individual tracks. Read the exec path before deciding where to hook in.

### 4. Label format

Use this format consistently:

```
[3/270] Fouk – Sundays.flac
[3/270] identity_id=42
```

Basename only for file paths. No full paths in progress output.

---

## Verification

After implementation:

```bash
poetry run pytest tests/cli/ -v -k "mp3 or dj or index or intake" --tb=short
tagslut mp3 build --dj-root /Volumes/MUSIC/DJ_LIBRARY --dry-run --verbose 2>&1 | head -20
tagslut dj backfill --dry-run --verbose 2>&1 | head -20
```

The `--verbose` dry-run must print per-item lines to stderr and the summary to stdout.
Without `--verbose`, output must be identical to pre-patch behavior.

---

## Commit message

```
feat(cli): add --verbose progress output to batch commands
```
