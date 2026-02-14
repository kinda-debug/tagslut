# Open Issues

**Date:** 2026-02-14
**Audit Version:** 1.0

## Resolved in This Audit

| Issue | Resolution |
|-------|------------|
| Stale version snapshots | Archived to tools/archive/ |
| Superseded scripts | Archived to tools/archive/ |
| Stale config files | Deleted |
| Documentation sprawl | Archived phase docs, created new operator docs |
| Hardcoded paths in pre_download_check.py | Fixed - auto-detects repo root |
| Missing confidence scoring | Added to pre_download_check.py |
| No single source of truth for operations | Created docs/README_OPERATIONS.md |

## Remaining Issues

### High Priority

#### 1. Commit Changes

The audit changes are not yet committed. Run:

```bash
cd ~/Projects/dedupe
git add -A
git commit -m "Repo cleanup audit: archive obsolete, add operator docs, enhance pre-download check"
```

#### 2. Test Pre-Download Check Tool

The enhanced pre_download_check.py should be tested with real data:

```bash
python tools/review/pre_download_check.py \
  --input ~/test_links.txt \
  --db ~/Projects/dedupe_db/EPOCH_2026-02-10_RELINK/music.db \
  --out-dir output/precheck_test
```

### Medium Priority

#### 3. Tidal Token Dependency

Tidal link extraction requires valid OAuth token. The pre-download check will work for Beatport without tokens, but Tidal links need:

```bash
tagslut auth status   # Check if token is valid
tagslut auth refresh  # Refresh if expired
```

**Mitigation:** Documented in TROUBLESHOOTING.md.

#### 4. Three FP-calc Planning Variants

Three `plan_fpcalc_*.py` scripts exist with overlapping scope:
- `plan_fpcalc_bulk_promote_and_stash.py`
- `plan_fpcalc_crossroot_promote_and_stash.py`
- `plan_fpcalc_promote_unique_to_final_library.py`

**Recommendation:** Review and potentially consolidate or document distinct use cases.

### Low Priority

#### 5. Qobuz Not in Workflows

Per requirements, Qobuz is not included in active workflows. This is intentional, not an issue.

#### 6. dedupe CLI Alias Retirement

The `dedupe` CLI alias is scheduled for retirement after June 15, 2026. No action needed now.

#### 7. tools/review/ Script Consolidation

34 scripts remain in tools/review/. Some may have overlapping functionality. Future audit could further consolidate.

## Not Issues (Confirmed Working)

| Item | Status |
|------|--------|
| Beatport without interactive token | Works (uses web scraping + API fallback) |
| Canonical CLI surface (7 commands) | Unchanged and functional |
| Move-only semantics | Preserved |
| Audit logging | Working (JSONL logs) |

## Next Actions

1. **Commit changes** - Make the audit permanent
2. **Test pre_download_check.py** - Verify with real Beatport/Tidal links
3. **Review FP-calc variants** - Determine if consolidation is needed

## Future Considerations

1. **Automated tests for pre_download_check.py** - Add pytest coverage
2. **CI integration for docs consistency** - Extend check_cli_docs_consistency.py
3. **Periodic cleanup audits** - Run similar audit quarterly
