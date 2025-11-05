# Quick Reference: What Needs To Be Done

## TL;DR - The Remaining Work

**Problem:** `flac_scan.py` (2,602 LOC) and `flac_dedupe.py` (2,520 LOC) duplicate ~1,070 lines of identical code.

**Solution:** Extract shared code to `lib/common.py`

---

## The 3-Step Fix

### Step 1️⃣: Create lib/common.py

```bash
mkdir -p /Users/georgeskhawam/dedupe/scripts/lib
touch /Users/georgeskhawam/dedupe/scripts/lib/__init__.py
```

**Then copy these sections from flac_scan.py to lib/common.py:**

| Section | Lines | Content |
|---------|-------|---------|
| Imports | ~30 | All `import` statements + global variables |
| Globals | ~45 | Progress tracking, colors, timeouts, DIAGNOSTICS |
| Utility functions | ~210 | `log()`, `heartbeat()`, `sha1_hex()`, etc. |
| Database schema | ~195 | `ensure_schema()`, `_create_schema()` |
| Data containers | ~168 | `@dataclass` definitions |
| DB operations | ~225 | `load_file_from_db()`, `upsert_file()`, etc. |
| Fingerprint utils | ~200 | `parse_fpcalc_output()`, etc. |
| Health checking | ~30 | `check_health()` |
| Command execution | ~83 | `run_command()`, `CommandError` |

**Total: ~1,200 LOC to extract**

---

### Step 2️⃣: Update flac_scan.py

```python
# DELETE: Lines 1-1,200 (all the sections listed above)

# ADD: At the top after `from __future__ import annotations`
from lib.common import (
    CMD_TIMEOUT,
    DECODE_TIMEOUT,
    DIAGNOSTICS,
    DB_SCHEMA_VERSION,
    CommandError,
    DiagnosticsManager,
    FileInfo,
    GroupResult,
    SegmentHashes,
    active_ffmpeg_pgids,
    active_pgid_lock,
    check_health,
    colorize_path,
    compute_fingerprint,
    compute_segment_hash,
    compute_segment_hashes,
    ensure_directory,
    ensure_schema,
    fingerprint_similarity,
    freeze_detector_stop,
    gay_flag_colors,
    heartbeat,
    human_size,
    insert_fp_bands,
    insert_segments,
    is_tool_available,
    last_progress_file,
    last_progress_timestamp,
    load_file_from_db,
    load_slide_hashes,
    log,
    log_progress,
    log_skip,
    parse_fpcalc_output,
    progress_color_index,
    progress_update_lock,
    progress_word_offset,
    register_active_pgid,
    run_command,
    scan_processed_count,
    scan_progress_lock,
    scan_skipped_count,
    scan_total_files,
    sha1_hex,
    store_file_signals,
    timestamp_color_index,
    unregister_active_pgid,
    upsert_file,
)
```

**Result:**
- Lines reduce from 2,602 to ~1,400
- All unique logic remains
- Only imports change

---

### Step 3️⃣: Update flac_dedupe.py

**Identical to Step 2** - same import list, same deletions.

**Result:**
- Lines reduce from 2,520 to ~1,450
- All unique logic remains
- Only imports change

---

## Verification

```bash
# 1. Check syntax after changes
python -m py_compile scripts/lib/common.py
python -m py_compile scripts/flac_scan.py
python -m py_compile scripts/flac_dedupe.py

# 2. Test imports work
python -c "from lib.common import *; print('OK')"

# 3. Test CLI still works
python scripts/dedupe_cli.py --help
python scripts/flac_scan.py --help
python scripts/flac_dedupe.py --help

# 4. Check line counts
wc -l scripts/flac_scan.py scripts/flac_dedupe.py scripts/lib/common.py

# Before:
#  2602 flac_scan.py
#  2520 flac_dedupe.py
# After (expected):
#  1400 flac_scan.py    (-1,202)
#  1450 flac_dedupe.py  (-1,070)
#  1200 lib/common.py   (+1,200)
```

---

## Why This Matters

| Metric | Before | After |
|--------|--------|-------|
| Total Python LOC | 7,467 | 5,835 |
| Duplicate LOC | 1,070 | 0 |
| Maintainability | Lower | Higher ✓ |
| Single source of truth | No | Yes ✓ |

---

## Potential Issues & Fixes

### Issue: Imports fail
**Solution:** Make sure `lib/__init__.py` exists and is empty

### Issue: Global state doesn't update
**Solution:** Use `global` keyword when modifying globals in functions
```python
def log(message: str) -> None:
    global timestamp_color_index  # REQUIRED
    timestamp_color_index += 1
```

### Issue: DIAGNOSTICS is None
**Solution:** This is normal. Initialize it in main():
```python
# In flac_scan.py or flac_dedupe.py main():
from lib import common
common.DIAGNOSTICS = DiagnosticsManager(...)
```

---

## Files That Will Change

```
/Users/georgeskhawam/dedupe/scripts/
├── lib/                          [NEW]
│   ├── __init__.py               [NEW - empty file]
│   └── common.py                 [NEW - 1,200 LOC]
├── flac_scan.py                  [MODIFIED - delete 1,202 LOC, add imports]
├── flac_dedupe.py                [MODIFIED - delete 1,070 LOC, add imports]
└── [all other files unchanged]
```

---

## Success Criteria

✅ All 3 new/modified files have valid Python syntax  
✅ `python scripts/dedupe_cli.py --help` works  
✅ `python scripts/flac_scan.py --help` works  
✅ `python scripts/flac_dedupe.py --help` works  
✅ Line counts match expected reductions  
✅ No duplicate code remains between scan and dedupe  
✅ All functionality preserved (no features lost)

---

## Next Steps

1. Read `CONSOLIDATION_REFACTORING_GUIDE.md` for detailed instructions
2. Follow the 3 steps above
3. Run verification commands
4. If anything breaks, refer to "Potential Issues" section
5. Commit changes: `git add -A && git commit -m "Consolidate shared code to lib/common.py"`
