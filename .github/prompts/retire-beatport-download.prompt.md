# retire-beatport-download — remove Beatport as download source

## Decision

Beatport is retired as an audio download source. It remains as a metadata
provider only (ISRC lookup, BPM, key, genre, label). The `bpdl` binary and
its surrounding orchestration are removed from the intake path.

TIDAL (via tiddl) is the sole audio download source going forward.

---

## Constraints

- Do NOT touch `tagslut/metadata/providers/beatport.py` — metadata provider
  stays entirely intact.
- Do NOT touch `tagslut/exec/intake_orchestrator.py` — the `providers=beatport`
  argument in the enrich stage is correct and must remain.
- Do NOT touch `tagslut/metadata/source_selection.py` — archive it (see below),
  do not delete or modify it.
- No full rewrites of `tools/get` or `tools/get-intake` — targeted removals only.
- Read each file before editing. Use `str_replace` / `edit_block` only.
- One commit per task.

---

## Task 1 — tools/get: remove Beatport download routing

File: `tools/get`

### What to remove

1. The `elif [[ "$URL" == *"beatport.com"* ]]` routing block in its entirety
   (the block that dispatches to `bpdl`, `get-report`, or `get-intake --source bpdl`).

2. The variable declarations that are now unused:
   - `BPDL_BIN="$SCRIPT_DIR/beatportdl/bpdl/bpdl"`
   - `GET_REPORT="$SCRIPT_DIR/get-report"`

3. In the `usage()` function: remove all lines referencing bpdl, get-report,
   `--raw-bpdl`, `--report`, and `beatport.com` as a *download* source.
   Keep any mention of Beatport as a metadata provider if present.

4. In the `build_intake_cmd()` function: remove `bpdl` from the `--source`
   argument. The only valid source for intake is now `tidal`.

### What to add

After removing the beatport routing block, add a stub that prints a clear
error if a Beatport URL is passed:

```bash
elif [[ "$URL" == *"beatport.com"* ]]; then
    echo "Error: Beatport downloads are retired. Beatport is metadata-only." >&2
    echo "Find the track on TIDAL and use that URL instead." >&2
    exit 1
```

### Do not touch

- The `elif [[ "$URL" == *"deezer.com"* ]]` block
- The `elif [[ "$URL" == *"tidal.com"* ]]` block
- The `build_intake_cmd()` logic for tidal
- The `--mp3` / `--dj` routing logic

---

## Task 2 — tools/get-intake: remove bpdl download machinery

File: `tools/get-intake`

### What to remove

Remove these variable declarations at the top:
```bash
BPDL_BIN="$SCRIPT_DIR/beatportdl/bpdl/bpdl"
BPDL_CONFIG="${BPDL_CONFIG:-$HOME/.config/beatportdl/config.yml}"
```

Remove these functions in their entirety (read the file first to confirm exact
line ranges before editing):
- `bpdl_downloads_dir_from_config()`
- `bpdl_binary_dir()`
- `bpdl_config_path()`
- `bpdl_workdir_from_config()`
- `ensure_bpdl_download_target()`
- `run_bpdl_batch()`

In the `usage()` function:
- Remove `bpdl` from the `--source TEXT` description. Change it to:
  `--source TEXT        Source label (tidal). Auto-inferred from URL if omitted.`
- Remove the example referencing a beatport.com URL from the Examples section.

In the argument parsing / source routing section:
- Remove the `bpdl` branch from `--source` handling. If `--source bpdl` is
  passed, print an error and exit:
  ```bash
  if [[ "$SOURCE" == "bpdl" ]]; then
      echo "Error: --source bpdl is retired. Use --source tidal." >&2
      exit 1
  fi
  ```
- Remove the `run_bpdl_batch` call site and the conditional block that routes
  beatport.com URLs to the bpdl downloader.

### Do not touch

- The TIDAL (`tiddl`) download path
- `--no-download` flag handling
- All pipeline stages after download (scan, fingerprint, plan, promote, m3u)
- `--source tidal` path

---

## Task 3 — archive source_selection.py

File: `tagslut/metadata/source_selection.py`

This module's sole purpose was selecting between Beatport and TIDAL as audio
download sources. With Beatport retired as a download source, it is dead code.

Action: Add a module-level deprecation comment at the top of the file:

```python
# ARCHIVED: This module is no longer active.
# Beatport was retired as an audio download source (2026-03-28).
# Beatport remains a metadata provider only.
# This file is kept for historical reference.
# Do not import from this module in new code.
```

Do NOT delete the file. Do NOT modify any of its logic.

Check whether anything imports from `source_selection` and still needs it:

```bash
grep -rn "from tagslut.metadata.source_selection\|import source_selection" \
    tagslut/ tests/ --include="*.py"
```

If any active (non-test, non-archive) file imports from it for download-source
selection purposes, note it in the commit message. Do not remove those imports
yet — flag them for operator review.

---

## Task 4 — tests: update or skip affected tests

Run targeted tests after each task:

```bash
# After Task 1+2
poetry run pytest tests/tools/test_get_intake.py -v 2>/dev/null || true
poetry run pytest tests/test_pre_download_check.py -v 2>/dev/null || true

# After Task 3
poetry run pytest tests/metadata/test_source_selection.py -v 2>/dev/null || true
```

If `test_source_selection.py` tests the download-source selection logic
(which is now archived), mark the test class/module with:

```python
import pytest
pytestmark = pytest.mark.skip(reason="source_selection archived: Beatport retired as download source")
```

Do NOT delete the test file.

Do not run the full test suite.

---

## Commits

```
chore(tools/get): retire Beatport as download source, add error stub
chore(tools/get-intake): remove bpdl download machinery
chore(metadata): archive source_selection — Beatport download-source retired
```

One commit per task, in order.

---

## Definition of done

- [ ] `tools/get https://www.beatport.com/...` prints clear error and exits 1
- [ ] `tools/get https://tidal.com/...` still works unchanged
- [ ] `tools/get-intake --source bpdl` prints clear error and exits 1
- [ ] `tools/get-intake --source tidal` still works unchanged
- [ ] `source_selection.py` has the archived header, logic untouched
- [ ] `beatport.py` metadata provider is completely unchanged
- [ ] `intake_orchestrator.py` is completely unchanged
- [ ] Three commits in order
