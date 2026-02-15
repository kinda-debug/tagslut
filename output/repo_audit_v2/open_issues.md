# Open Issues (Audit v2)

**Date:** 2026-02-14
**Audit Version:** 2.0

## High Priority

### 1. Commit Pending Changes

**Status:** Ready to commit

**Files to add (new):**
```bash
git add tools/deemix tools/get-auto
```

**Files to stage (modified):**
```bash
git add docs/README_OPERATIONS.md docs/WORKFLOWS.md tools/get tools/get-help tools/tiddl
```

**Commit command:**
```bash
git commit -m "Audit v2: Add Deezer support, get-auto precheck wrapper, update workflow docs

- tools/deemix: Deezer downloader with auto-registration (source=deezer)
- tools/get-auto: Precheck against DB + download only missing
- tools/get: Updated router to support deezer.com URLs
- docs/README_OPERATIONS.md: Added Deezer workflow
- docs/WORKFLOWS.md: Added get-auto and Deezer workflows, source registration matrix
- tools/tiddl: Updated for newer tiddl CLI syntax
"
```

---

### 2. Test get-auto End-to-End

**Status:** Needs manual verification

**Test command:**
```bash
# Test with a real URL
tools/get-auto "https://www.beatport.com/release/example/12345"
```

**Expected:**
1. Runs pre_download_check.py
2. Shows keep/skip decisions
3. Downloads only missing tracks
4. Prints completion summary

---

## Medium Priority

### 3. Tidal Token Refresh

**Issue:** Tidal extraction requires valid OAuth token.

**Verification:**
```bash
tagslut auth status
# If expired:
tagslut auth refresh
```

**Documentation:** Already in `docs/TROUBLESHOOTING.md`.

---

### 4. Deezer ARL Token

**Issue:** Deezer deemix requires ARL token for login.

**Configuration:**
- Default: `~/.config/deemix/.arl`
- Or pass via environment

**Documentation:** Should be added to `docs/TROUBLESHOOTING.md` if not present.

---

## Low Priority

### 5. FP-calc Planning Script Consolidation

**Files:**
- `tools/review/plan_fpcalc_bulk_promote_and_stash.py`
- `tools/review/plan_fpcalc_crossroot_promote_and_stash.py`
- `tools/review/plan_fpcalc_promote_unique_to_final_library.py`

**Status:** Deferred - document use cases rather than consolidate.

---

### 6. Periodic Artifact Cleanup

**Issue:** `artifacts/` has 941+ files.

**Recommendation:** Manual cleanup periodically:
```bash
# Remove files older than 30 days
find artifacts/ -type f -mtime +30 -name "*.csv" -delete
find artifacts/ -type f -mtime +30 -name "*.jsonl" -delete
```

---

## Resolved in This Audit

| Issue | Resolution |
|-------|------------|
| Deezer not in workflow | Added `tools/deemix` + routing |
| No precheck automation | Added `tools/get-auto` |
| Source registration not documented | Added matrix to WORKFLOWS.md |
| Downloader locations incomplete | Updated README_OPERATIONS.md |

## Not Issues

| Item | Status |
|------|--------|
| Qobuz not in workflows | Intentional per requirements |
| dedupe alias deprecated | Scheduled for June 2026 |
| Beatport no interactive token | Working as designed (stored config) |

## Summary

**Blocking issues:** 0
**Action items:** 2 (commit changes, test get-auto)
**Deferred items:** 3 (FP-calc consolidation, artifact cleanup, Tidal/Deezer token docs)
