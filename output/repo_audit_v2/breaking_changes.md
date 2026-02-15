# Breaking Changes (Audit v2)

**Date:** 2026-02-14
**Audit Version:** 2.0

## Summary

**No breaking changes** in this audit. All changes are additive.

## Additive Changes (Non-Breaking)

### New Wrappers

| Wrapper | Purpose | Impact |
|---------|---------|--------|
| `tools/deemix` | Deezer downloader with auto-registration | New capability |
| `tools/get-auto` | Precheck + download missing | New capability |

### Updated Wrappers

| Wrapper | Change | Backward Compatible |
|---------|--------|---------------------|
| `tools/get` | Added Deezer routing | **Yes** - existing Beatport/Tidal URLs work unchanged |
| `tools/tiddl` | Updated CLI syntax for newer tiddl | **Yes** - wrapper handles compatibility |

### Documentation Updates

| File | Change | Impact |
|------|--------|--------|
| `docs/README_OPERATIONS.md` | Added Deezer workflow | Documentation only |
| `docs/WORKFLOWS.md` | Added get-auto and Deezer workflows | Documentation only |

## Compatibility Notes

### URL Routing

The unified `tools/get` router now handles three domains:

```
beatport.com → tools/get-sync
tidal.com    → tools/tiddl
deezer.com   → tools/deemix
```

All existing Beatport and Tidal workflows continue to work unchanged.

### Source Registration

Explicit source flags remain unchanged:

```bash
# These commands work exactly as before
tagslut index register /path --source bpdl --execute
tagslut index register /path --source tidal --execute

# New: Deezer (auto-registered, but manual also works)
tagslut index register /path --source deezer --execute
```

### Pre-Download Check

The `pre_download_check.py` tool continues to work for all sources. The new `get-auto` wrapper is optional convenience.

## No Deprecated Items

Nothing deprecated in this audit. Items previously deprecated (in v1 audit) remain:

| Item | Status | Removal Date |
|------|--------|--------------|
| `dedupe` CLI alias | Deprecated (warning shown) | After June 15, 2026 |
| Archived scripts in `tools/archive/` | Archived (not usable) | Retained for reference |

## Migration Required

**None.** All existing workflows continue to work.

## Questions?

If you encounter issues:

1. Check `docs/README_OPERATIONS.md` for current command reference
2. Check `docs/WORKFLOWS.md` for step-by-step guides
3. Run `tagslut --help` for CLI help
