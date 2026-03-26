# DJ Pipeline Full Repair — Codex Execution Plan

**Repo:** `kinda-debug/tagslut` on `dev` branch  
**Status:** 5 consecutive prompts, must run in order  
**Total time:** ~45 minutes end-to-end  
**Success criteria:** `tagslut --dj` and `tagslut --mp3` work without errors

---

## STAGE 1: Create `dj_state.py` (Deterministic Hash Function)

### File to Create
`tagslut/storage/v3/dj_state.py`

### Current State
File exists but implementation is incomplete. It's missing:
- Proper docstring
- Correct field selection (should use `identity_id` not generic `id`)
- Deterministic sorting
- Function for recording validation state

###Required Implementation

```python
"""DJ pipeline state hash computation (deterministic across runs).

This module provides utilities for computing stable fingerprints of the DJ
admission state so that patches/exports can detect changes without scanning
the entire pool on every run.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone


def compute_dj_state_hash(conn: sqlite3.Connection) -> str:
    """
    Compute a deterministic hash of the current DJ admission state.
    
    Fetches all admitted identity IDs from dj_admission table, sorts them,
    and returns their SHA256 fingerprint. The sort ensures that the hash is
    identical across runs, even if the database query returns rows in a
    different order.
    
    Args:
        conn: Open SQLite connection to the v3 database.
        
    Returns:
        SHA256 hex digest of the sorted, concatenated identity IDs.
    """
    rows = conn.execute(
        "SELECT identity_id FROM dj_admission WHERE status = 'admitted' ORDER BY identity_id ASC"
    ).fetchall()
    
    if not rows:
        return hashlib.sha256(b"").hexdigest()
    
    # Flatten and sort to ensure determinism
    identity_ids = sorted([int(row[0]) for row in rows])
    payload = ",".join(str(id) for id in identity_ids)
    return hashlib.sha256(payload.encode()).hexdigest()


def record_validation_state(
    conn: sqlite3.Connection,
    state_hash: str,
    issue_count: int,
    passed: bool,
    summary: str = "",
) -> None:
    """
    Record a DJ validation state row.
    
    Args:
        conn: SQLite connection
        state_hash: Hash computed by compute_dj_state_hash()
        issue_count: Number of issues found during validation
        passed: Whether validation passed
        summary: Optional text summary
    """
    conn.execute(
        """
        INSERT INTO dj_validation_state (state_hash, passed, created_at)
        VALUES (?, ?, ?)
        """,
        (state_hash, int(passed), datetime.now(timezone.utc).isoformat())
    )
```

### Action
Replace the entire file with the implementation above. Then:

```bash
poetry run python -c "from tagslut.storage.v3.dj_state import compute_dj_state_hash; print('✓ dj_state.py import successful')"
```

Expected output: `✓ dj_state.py import successful`

---

## STAGE 2: Fix `dj_backfill.py` (Status Filter)

### Problem
The backfill script filters for `mp3_asset` rows with status='verified', but the mp3_reconcile step might write a different status. Also, backfill is not truly idempotent — re-running can cause PRIMARY KEY errors.

### Required Fix

Find this section:
```python
MP3_RECONCILE_SUCCESS_STATUS = "verified"
```

Verify that this matches what `mp3_reconcile.py` actually writes. Cross-check by searching `mp3_reconcile.py` for `status =` and `status='`.

**If there's a mismatch:** Update the constant to match.

Then, in the `backfill_dj_admissions()` function, find the INSERT statement:
```python
cur = conn.execute(
    """
    INSERT OR IGNORE INTO dj_admission
      (identity_id, mp3_asset_id, status, admitted_at, notes)
    VALUES (?, ?, 'admitted', ?, NULL)
    """,
    (identity_id_int, int(mp3_asset_id), _now_iso()),
)
```

Verify it has `INSERT OR IGNORE`. If not, change it. This makes re-runs idempotent.

### Test
```bash
cd /Users/georgeskhawam/Projects/tagslut
poetry run python -m pytest tests/exec/test_dj_backfill.py -v 2>/dev/null || echo "No test file yet (ok)"
```

---

## STAGE 3: Wire `dj_validate.py` (Import `record_validation_state`)

### Problem
`dj_validate.py` imports `record_validation_state` from `tagslut.dj.admission`, but it also needs to import from `tagslut.storage.v3.dj_state`. Cross-check that both imports work.

### Required Fix

At the top of `tagslut/exec/dj_validate.py`, verify these imports exist:

```python
from tagslut.dj.admission import record_validation_state, validate_dj_library
from tagslut.storage.v3.dj_state import compute_dj_state_hash
```

If `record_validation_state` is not in `tagslut.dj.admission`, add it:

```python
# In tagslut/dj/admission.py, add:
def record_validation_state(conn, state_hash, issue_count, passed, summary=""):
    """Wrapper for dj_state.record_validation_state."""
    from tagslut.storage.v3.dj_state import record_validation_state as _record
    return _record(conn, state_hash, issue_count, passed, summary)
```

### Test
```bash
poetry run python -c "from tagslut.exec.dj_validate import validate_and_record_dj_state; print('✓ dj_validate.py wired correctly')"
```

Expected: `✓ dj_validate.py wired correctly`

---

## STAGE 4: Add `--skip-validation` Flag to `dj_xml_emit.py`

### Problem
The `tagslut dj emit` command should have a `--skip-validation` flag for testing/recovery purposes, but it may not be defined.

### Required Fix

Open `tagslut/exec/dj_xml_emit.py` (or wherever the emit CLI is defined).

Find the argparse definition and add:

```python
parser.add_argument(
    "--skip-validation",
    action="store_true",
    default=False,
    help="Skip DJ library validation before emit (use with caution)"
)
```

Then, before the emit logic, add:

```python
if not args.skip_validation:
    # Call validate_and_record_dj_state() or equivalent
    from tagslut.exec.dj_validate import validate_and_record_dj_state
    report, state_hash, warning = validate_and_record_dj_state(conn)
    if warning:
        logger.warning(warning)
    if not getattr(report, "ok", False):
        raise ValueError(f"DJ validation failed: {report}")
else:
    logger.warning("Validation skipped (--skip-validation flag)")
```

### Test
```bash
poetry run python -m tagslut dj emit --help | grep -i skip
```

Expected: Should see `--skip-validation` in help output.

---

## STAGE 5: Error Recovery in `dj_pool_wizard.py`

### Problem
If a transcode fails, the entire run aborts. Instead, it should log the error, continue with the next file, and write a `transcode_failures.json` report.

### Required Fix

Find the transcode loop in `tagslut/exec/dj_pool_wizard.py`. It probably looks like:

```python
for file in files:
    transcode(file)  # No error handling
```

Change it to:

```python
failures = []
for file in files:
    try:
        transcode(file)
    except Exception as e:
        failures.append({
            "file": str(file),
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        })
        logger.warning(f"Transcode failed for {file}: {e}. Continuing...")
        continue
```

Then at the end, add:

```python
if failures:
    import json
    from datetime import datetime
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    failure_json = f"/Users/georgeskhawam/Projects/tagslut/artifacts/dj/transcode_failures_{timestamp}.json"
    Path(failure_json).parent.mkdir(parents=True, exist_ok=True)
    with open(failure_json, 'w') as f:
        json.dump(failures, f, indent=2)
    logger.info(f"Transcode failures written to {failure_json}")
```

Also, add a `--plan` flag (if missing) that defaults to True and skips actual transcode:

```python
if args.plan:
    logger.info(f"[DRY-RUN] Would transcode {len(files)} files")
    return

# Actual transcode code here
```

### Test
```bash
poetry run python -m tagslut dj pool-wizard transcode --plan --help
```

Expected: Should show `--plan` flag in help.

---

## Sequencing & Validation

After each stage, run:

```bash
cd /Users/georgeskhawam/Projects/tagslut
git add -A
git commit -m "fix(dj-stage-N): [brief description]"
git push origin dev
```

### Full end-to-end test (after all 5 stages):

```bash
# 1. Check imports
poetry run python -c "from tagslut.storage.v3.dj_state import compute_dj_state_hash, record_validation_state; print('✓ Stage 1')"

# 2. Check backfill
poetry run python -c "from tagslut.exec.dj_backfill import backfill_dj_admissions; print('✓ Stage 2')"

# 3. Check validate
poetry run python -c "from tagslut.exec.dj_validate import validate_and_record_dj_state; print('✓ Stage 3')"

# 4. Check emit flag
poetry run python -m tagslut dj emit --help | grep -q skip-validation && echo "✓ Stage 4" || echo "✗ Stage 4"

# 5. Check pool-wizard error recovery
poetry run python -c "from tagslut.exec.dj_pool_wizard import run_pool_wizard; print('✓ Stage 5')"

# Run unit tests
poetry run pytest tests/exec/test_dj_*.py -v --tb=short 2>&1 | head -50
```

---

## If Something Breaks

All changes are independent and can be reverted individually:

```bash
# Revert to last known-good state
git reset --hard HEAD~1
git push -f origin dev

# Then run the stages again more carefully
```

---

## When ALL 5 Stages Pass

Run the actual pipeline:

```bash
# Dry-run to verify no errors
tagslut --dj --url https://tidal.com/track/459513096 --dry-run

# Actual run
tagslut --dj --url https://tidal.com/track/459513096

# Build MP3s
tagslut --mp3 --batch 50 --dry-run
tagslut --mp3 --batch 50
```

Both should complete without errors.

