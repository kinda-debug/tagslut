# Breaking Changes

**Date:** 2026-02-14

## Summary

This document records any breaking changes introduced during the repo cleanup audit. Breaking changes require operator action or awareness.

## Breaking Changes

### BC1: Archived Script Paths Changed

**Impact:** Low (scripts were already superseded)

| Old Path | New Path | Mitigation |
|----------|----------|------------|
| `tools/review/match_unknowns_to_epoch_2026_02_08.py` | `tools/archive/match_unknowns_to_epoch_2026_02_08.py` | Use `tools/review/match_unknowns_to_epoch_2026_02_08_fast.py` instead |
| `scripts/reassess_playlist_duration_unknowns.py` | `tools/archive/reassess_playlist_duration_unknowns.py` | Use `scripts/reassess_playlist_duration_unknowns_tokenless.py` instead |
| `tools/review/promote_by_tags_versions/*` | `tools/archive/promote_by_tags_versions/*` | Use `tools/review/promote_by_tags.py` (active version) |

**Action Required:** Update any personal scripts or notes that reference the old paths.

### BC2: Stale Config Files Removed

**Impact:** None (files were not in active use)

| Removed File | Replacement |
|--------------|-------------|
| `config.toml` | `.env` |
| `config.example.toml` | `.env.example` |
| `config.example.yaml` | `.env.example` |

**Action Required:** None. These were superseded by `.env` configuration.

### BC3: Phase Docs Moved to Archive

**Impact:** None (docs are reference only)

All `PHASE*.md` files moved from `docs/` to `docs/archive/phase-specs-2026-02-09/`.

**Action Required:** None. These are completed specifications. Active policy docs remain in `docs/`.

## Non-Breaking Changes

The following changes do NOT require operator action:

1. **Created `tools/archive/`** - New directory for archived scripts
2. **Created `output/repo_audit/`** - New directory for audit outputs
3. **Moved `flacs_inventory_*.xlsx`** - Data file relocated, not referenced by active code
4. **Deleted `script.log`** - Empty file with no data

## Compatibility Notes

### CLI Surface Unchanged

All canonical CLI commands remain unchanged:

```
tagslut intake
tagslut index
tagslut decide
tagslut execute
tagslut verify
tagslut report
tagslut auth
```

### Active Tools Unchanged

All tools in `tools/review/` that were not archived remain at their original paths and function identically.

### Database Unchanged

No changes to database schema or data.

## Future Deprecations

The following items are scheduled for future deprecation but remain functional:

| Item | Deprecation Date | Replacement |
|------|------------------|-------------|
| `dedupe` CLI alias | After June 15, 2026 | `tagslut` |

## Questions?

If you encounter issues after this cleanup, check:

1. `output/repo_audit/change_plan_applied.md` for complete change list
2. `tools/archive/README.md` for archived script locations
3. `docs/SURFACE_POLICY.md` for canonical command surface
