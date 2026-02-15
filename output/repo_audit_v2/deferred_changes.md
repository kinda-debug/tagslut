# Deferred Changes

**Date:** 2026-02-14
**Audit Version:** 2.0

These changes were identified but deferred for future consideration.

## Medium Priority

### 1. Consolidate FP-calc Planning Scripts

**Files:**
- `tools/review/plan_fpcalc_bulk_promote_and_stash.py`
- `tools/review/plan_fpcalc_crossroot_promote_and_stash.py`
- `tools/review/plan_fpcalc_promote_unique_to_final_library.py`

**Status:** Deferred

**Reason:** These have overlapping functionality but different scopes (bulk vs crossroot vs unique). Need operator input to determine if consolidation is appropriate or if distinct use cases warrant separate scripts.

**Recommendation:** Document distinct use cases in `tools/review/README.md` rather than consolidating.

---

### 2. Tidal Auto-Registration

**Issue:** Tidal downloads via `tools/tiddl` do not auto-register to DB (unlike Deezer).

**Status:** Deferred

**Reason:** Would require wrapping tiddl output path detection, which may vary. Current manual registration is explicit and safe.

**Alternative:** Use `tools/get-auto` which handles precheck but still requires manual registration after download.

---

### 3. Beatport Auto-Registration

**Issue:** Beatport downloads via `tools/get-sync` do not auto-register.

**Status:** Deferred

**Reason:** Beatport workflow already has complex get-intake logic. Adding auto-registration would increase coupling.

**Alternative:** Operator runs `tagslut index register --source bpdl` after download.

---

## Low Priority

### 4. Archive Additional Legacy Items

**Files:**
- `tools/inspect_api.py` - API introspection utility (unclear if still used)
- `tools/playlist-sync` - Large script (17KB), status unclear

**Status:** Deferred

**Reason:** May still be in active use. Need to verify with operator before archiving.

---

### 5. Output Directory Cleanup

**Issue:** `output/` has 67+ files that may be stale.

**Status:** Deferred

**Reason:** Runtime outputs should not be in repo. They are already gitignored. Manual cleanup is operator responsibility.

---

### 6. Artifacts Directory Cleanup

**Issue:** `artifacts/` has 941+ files including old reports and logs.

**Status:** Deferred

**Reason:** These are operational outputs with potential historical value. Recommend periodic manual cleanup rather than automated deletion.

---

## Not Changing

### Qobuz Provider

**File:** `dedupe/metadata/providers/qobuz.py`

**Status:** Preserved but not in active workflows

**Reason:** Per requirements, Qobuz is excluded from active workflows but code is preserved for potential future use.

### dedupe CLI Alias

**Status:** Preserved until June 2026

**Reason:** Compatibility alias scheduled for retirement after June 15, 2026 per existing plan.
