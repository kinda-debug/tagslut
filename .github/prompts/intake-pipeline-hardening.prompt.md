You are an expert Python/bash engineer working in the tagslut repository.

Goal:
Fix three concrete bugs in the intake pipeline. Each is independent and
well-scoped. Apply as three separate commits.

Read first (in order):
1. AGENT.md
2. .codex/CODEX_AGENT.md
3. docs/PROJECT_DIRECTIVES.md
4. tools/get-intake (full file)
5. tagslut/exec/intake_pretty_summary.py

Verify before editing:
- Run: bash -n tools/get-intake && echo "SYNTAX OK"
- Run: poetry run pytest tests/exec/ -v -k "intake or pretty or summary" 2>&1 | tail -20

Constraints:
- Smallest reversible patch per fix. One commit per fix.
- Do not modify DB files directly.
- Do not touch mounted volume paths.
- No new dependencies.
- Targeted pytest only.

---

## Fix 1 — POST_MOVE_LOG default path writes into artifacts/

**Problem**: `POST_MOVE_LOG` is assigned inside the background enrich launch block
in tools/get-intake. Its default path goes to `$OUT_DIR/post_move_enrich_art_*.log`
which is `artifacts/compare/`. Logs should go to the epoch directory, not artifacts/.

**Locate**: Search for `POST_MOVE_LOG=` in tools/get-intake. It appears twice
(the variable and the pid file). Both point to `$OUT_DIR`.

**Fix**: Change the two log-path assignments to write to `$BATCH_ROOT/../logs/`
instead of `$OUT_DIR`. Create the directory if missing with `mkdir -p`.

Example:
```bash
LOG_EPOCH_DIR="$(dirname "$BATCH_ROOT")/logs"
mkdir -p "$LOG_EPOCH_DIR"
POST_MOVE_LOG="$LOG_EPOCH_DIR/post_move_enrich_art_$(date +%Y%m%d_%H%M%S).log"
POST_MOVE_PID_FILE="$LOG_EPOCH_DIR/post_move_enrich_art_$(date +%Y%m%d_%H%M%S).pid"
```

**Verification**: `bash -n tools/get-intake && echo SYNTAX OK`

**Done when**: The two path assignments use a logs subdirectory outside artifacts/.

**Commit**: `fix(intake): redirect POST_MOVE_LOG to epoch logs dir`

---

## Fix 2 — intake_pretty_summary counter accuracy

**Problem**: `intake_pretty_summary.py` reads `promote`, `stash`, `quarantine`
from the plan summary JSON with multiple fallback keys, but the actual key written
by `plan_fpcalc_promote_unique_to_final_library.py` is `promote_move` (not
`promote` or `promote_count`). When the primary key is absent, the displayed
count is blank, not zero.

**Locate**: In `tagslut/exec/intake_pretty_summary.py`, the `_read_plan_summary`
function returns the raw dict. In `main()`, look for the lines:
```python
promote = str(payload.get("promote", payload.get("promote_move", ...)))
```

**Fix**: Simplify the fallback chain. The canonical keys in the summary JSON are
`promote_move`, `stash_move`, `quarantine_move`. Use those as primary keys with
a `0` default, not blank string:

```python
promote = payload.get("planned", {}).get("promote_move", payload.get("promote_move", 0))
stash   = payload.get("planned", {}).get("stash_move",   payload.get("stash_move",   0))
quar    = payload.get("planned", {}).get("quarantine_move", payload.get("quarantine_move", 0))
```

Note: the summary JSON has a `"planned"` sub-key containing these values.
Always check `payload["planned"]` first, then fall back to the top level.

**Verification**:
```bash
poetry run pytest tests/exec/ -v -k "pretty_summary or intake_summary" 2>&1 | tail -20
```
If no tests cover this, add one fixture-based test in
`tests/exec/test_intake_pretty_summary.py` that creates a minimal JSON matching
the real summary structure and asserts the correct counts are printed.

**Done when**: Running intake_pretty_summary against a real or fixture summary JSON
shows correct integer counts, not blank or wrong values.

**Commit**: `fix(summary): resolve promote/stash/quarantine counter from planned sub-key`

---

## Fix 3 — precheck_inventory_dj fallback missing for --dj-only runs

**Problem**: When `--dj` is passed without `--m3u`, and all tracks are precheck
hits (no new downloads), the `link_precheck_inventory_to_dj` fallback path is
called, but `DJ_ROOT` and `DJ_M3U_DIR` validation happens after the fallback
branch exits. If either is unset, the pipeline aborts with a misleading error
before reaching the validation block.

**Locate**: In tools/get-intake, find the block:
```bash
if [[ "$DJ_MODE" -eq 1 && ! ( ... ) ]]; then
    ...
    link_precheck_inventory_to_dj ...
    echo "No new candidates to download; intake pipeline finished (DJ mode)."
    exit 0
fi
```

**Fix**: Add a guard before the `link_precheck_inventory_to_dj` call that
validates `DJ_ROOT` and `DJ_M3U_DIR` are set, with a clear error message if not:

```bash
if [[ "$DJ_MODE" -eq 1 && ! ( ... ) ]]; then
    if [[ -z "${DJ_ROOT:-}" ]]; then
        err "DJ mode requires --dj-root or DJ_MP3_ROOT / DJ_LIBRARY to be set"
    fi
    if [[ -z "${DJ_M3U_DIR:-}" ]]; then
        err "DJ mode requires --dj-m3u-dir or DJ_PLAYLIST_ROOT to be set"
    fi
    ...
    link_precheck_inventory_to_dj ...
    exit 0
fi
```

**Verification**: `bash -n tools/get-intake && echo SYNTAX OK`

**Done when**: Running `tools/get --enrich <url> --dj` when DJ_ROOT is unset
produces a clear `ERROR: DJ mode requires...` message instead of an unrelated
downstream error.

**Commit**: `fix(intake): validate DJ_ROOT and DJ_M3U_DIR before precheck-inventory fallback`
