# Integrity System Design Failures

**Status:** Active Design Debt  
**Impact:** High - affects trust, performance, and recoverability

---

## Problem Summary

The integrity checking system re-checks files unnecessarily, misclassifies state, and mutates database truth in non-deterministic ways.

**Consequences:**
- Forced full rescans when none are required
- Integrity checks applied to already-verified files
- Cannot distinguish newly discovered corruption from known corruption
- Database writes fail mid-run, corrupting scan state
- Loss of user trust in DB as source of truth

---

## Core Design Failures

### 1. `--recheck` Forces Integrity on Everything

**Current behavior:**
```python
if scan_integrity:
    run_flac_test(file)
```

No guard based on:
- `integrity_checked_at IS NULL`
- `integrity_state = 'unknown'`
- `integrity_version < CURRENT_VERSION`

**Result:**
- Files already integrity-checked are re-tested
- Users cannot sample, audit, or selectively verify
- Second scan produces "new" corruption findings even when nothing changed on disk

**This breaks trust in the DB.**

---

### 2. No Integrity Versioning or Provenance

**Current schema stores:**
- `integrity_state` (valid/corrupt/recoverable)
- `flac_ok` (boolean)

**Does NOT store:**
- Which command produced the result
- Which `flac` version was used
- Whether result is authoritative or provisional
- Whether user-triggered or automatic
- Timestamp of last integrity check

**Result:**
- Cannot distinguish "known bad from first scan" vs "newly detected bad from recheck"
- Integrity results overwritten silently
- Historical correctness lost
- No audit trail

---

### 3. Integrity Mixed Into Scan (Not First-Class Operation)

**Current design:**
Integrity checking is embedded inside `scan.py` as a flag.

**Should be:**
- Separate, explicit phase
- Targeted operation on defined file set
- Independent from metadata scanning

**Result:**
- Full library rescans just to verify handful of files
- Accidental integrity runs when user only wanted metadata refresh
- Very long operations that cannot be cleanly aborted
- No way to say "verify only these 20 files"

---

### 4. Ctrl-C Leaves DB in Broken State

**What happens on interrupt:**
```
Parallel processing interrupted by user. Returning partial results.
```

Then:
- Partial results still upserted
- Tuple passed into SQLite bind → crash
- Scan ends in half-written, inconsistent state

**Indicates:**
- No transaction boundary around scan
- No rollback on interruption (partially fixed)
- No type validation before DB writes (partially fixed)

**Status:** Partially mitigated by recent transaction rollback additions, but still fragile.

---

### 5. Integrity Classification Too Brittle

**Current logic:**
`flac -t` failures treated as absolute truth.

**Problem:**
Even when:
- Errors occur late in stream
- Partial decoding succeeds
- File is playable but technically malformed

**No classification tier:**
- `valid`
- `minor_corruption` (late-stream errors, partial recovery possible)
- `major_corruption` (unplayable)
- `unparseable` (not FLAC)
- `not_flac`

Everything collapses into **"corrupt"**.

**Result:** 
- Cannot prioritize which files to fix
- Cannot distinguish "bit rot in silence padding" from "completely unreadable"
- No recoverability assessment

---

## What Needs to Be Fixed

### 1. Integrity Must Be Idempotent

**Required behavior:**
- Never recheck unless explicitly requested
- Default: skip if integrity already known
- Guard: `WHERE integrity_checked_at IS NULL OR recheck_forced`

### 2. Integrity Must Be Versioned

**Add to schema:**
```sql
ALTER TABLE files ADD COLUMN integrity_checked_at REAL;
ALTER TABLE files ADD COLUMN integrity_tool_version TEXT;
ALTER TABLE files ADD COLUMN integrity_command TEXT;
ALTER TABLE files ADD COLUMN integrity_errors_json TEXT;
```

**Never overwrite without explicit intent.**

### 3. Separate Integrity from Scan

**Proposed:**
- `scan.py` → discovers + extracts metadata only
- `verify.py` → runs integrity checks on targeted file sets
- `--paths-from-file` → already implemented for targeting

**Clear separation of concerns.**

### 4. Transactional Safety

**Required:**
- One scan = one DB transaction
- Ctrl-C must roll back cleanly
- Type validation before all DB writes

**Status:** Partially implemented (rollback on KeyboardInterrupt added).

### 5. Better Integrity Taxonomy

**Not all `flac -t` failures are equal.**

Capture:
- Severity (minor/major/critical)
- Offset where corruption detected
- Recoverability (partial decode possible?)
- Error codes from decoder

Store as structured JSON in `integrity_errors_json`.

---

## Migration Path

### Phase 1 (Immediate)
- [x] Add transaction rollback on interrupt
- [x] Add tuple normalization before SQLite binding
- [x] Add `should_run_integrity()` guard
- [ ] Add `integrity_checked_at` column
- [ ] Skip integrity if already checked (unless `--recheck`)

### Phase 2 (Short-term)
- [ ] Add versioning columns
- [ ] Capture structured error details
- [ ] Create `tools/verify.py` as separate integrity tool
- [ ] Update `--recheck` to be explicit scope flag

### Phase 3 (Long-term)
- [ ] Implement nuanced corruption classification
- [ ] Add recoverability assessment
- [ ] Audit trail for all integrity state changes
- [ ] Version bumping on flac binary upgrade

---

## Bottom Line

The integrity system currently behaves like a **global side-effect**, not a controlled verification step.

It should be:
- **Explicit** - user knows what's being checked
- **Minimal** - only check what's necessary
- **Reversible** - can undo/redo without loss
- **Auditable** - know who, what, when, why

**Right now, it is none of those.**

---

## Related Documents

- [FAST_WORKFLOW.md](FAST_WORKFLOW.md) - 3-phase scanning strategy
- [PATHS_FROM_FILE_USAGE.md](PATHS_FROM_FILE_USAGE.md) - Targeted verification
- [SYSTEM_SPEC.md](SYSTEM_SPEC.md) - Overall system design
