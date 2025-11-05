# FLAC Deduplication Scripts Consolidation - Complete Refactoring Guide

**Status:** 80% complete. Core cleanup done. Code duplication remains unresolved.

**Date:** November 5, 2025

---

## Executive Summary

The scripts directory has been partially consolidated:
- ✅ **3 corrupt/useless wrapper files deleted** (repair_workflow.py, post_repair.py, dedupe_plan_manager.py)
- ✅ **Root directory cleaned** (no Python/shell wrappers at root level)
- ⚠️ **1000+ lines of code still duplicated** between flac_scan.py and flac_dedupe.py

This document provides a step-by-step guide to complete the consolidation properly.

---

## Part 1: Current State Analysis

### Scripts Directory Structure (Current)

```
scripts/
├── dedupe_cli.py           (267 LOC)     - Main CLI router
├── dedupe_sync.py          (486 LOC)     - Sync & health checking
├── file_operations.py      (320 LOC)     - File operations manager
├── flac_dedupe.py          (2,520 LOC)   - Deduplication algorithms [DUPE]
├── flac_repair.py          (715 LOC)     - FLAC repair utilities
├── flac_scan.py            (2,602 LOC)   - Database scanning [DUPE]
├── stage_hash_dupes.sh     (157 LOC)     - SQL+bash utility (KEEP)
├── scrd                    (shell alias) - Convenience wrapper (OPTIONAL)
└── README.md               - Documentation
```

**Total: 7,467 LOC (excludes duplicate count)**

### The Duplication Problem

**File: flac_scan.py** (2,602 LOC)  
**File: flac_dedupe.py** (2,520 LOC)

Both files contain **~1,070+ lines of identical code** in these sections:

#### Section 1: Imports & Globals (Lines 1-75 in both)
```python
# Identical in both:
import argparse, binascii, csv, datetime, hashlib, json, os, re, shutil, 
signal, sqlite3, subprocess, sys, tempfile, textwrap, threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple
import base64, struct, time

# Global state for progress tracking:
last_progress_timestamp, last_progress_file, freeze_detector_stop
active_ffmpeg_pgids, active_pgid_lock
scan_progress_lock, scan_processed_count, scan_total_files, scan_skipped_count
progress_update_lock, progress_color_index, timestamp_color_index, progress_word_offset
gay_flag_colors array, DIAGNOSTICS, CMD_TIMEOUT, DECODE_TIMEOUT
```
**Lines: ~75**

#### Section 2: Utility Helper Functions (Lines 76-285 in both)
```python
def register_active_pgid(pgid)          # ~10 LOC
def unregister_active_pgid(pgid)        # ~10 LOC
def colorize_path(path_str)             # ~15 LOC
def heartbeat(path)                     # ~15 LOC
def log(message)                        # ~65 LOC (complex colorizing logic)
def log_progress(path)                  # ~15 LOC
def log_skip(path)                      # ~15 LOC
def is_tool_available(tool)             # ~3 LOC
def sha1_hex(data)                      # ~3 LOC
def human_size(num_bytes)               # ~15 LOC
def ensure_directory(path)              # ~3 LOC
```
**Lines: ~210**

#### Section 3: Database Schema (Lines 286-450 in both)
```python
DB_SCHEMA_VERSION = 1

def ensure_schema(conn)                 # ~20 LOC
def _create_schema(conn)                # ~175 LOC (ENTIRE CREATE TABLE... statements)
    # All identical SQLite DDL for tables:
    # - files, file_signals, fp_bands, seg_slices, runs, groups, group_members
    # - Plus all indexes
```
**Lines: ~195**

#### Section 4: Data Containers (Lines 451-550 in both)
```python
@dataclass
class SegmentHashes                     # ~10 LOC
@dataclass
class FileInfo                          # ~30 LOC
@dataclass
class GroupResult                       # ~8 LOC
@dataclass
class DiagnosticsManager                # ~120 LOC (complex with many methods)
```
**Lines: ~168**

#### Section 5: File Database Operations (Lines 630-950 in both)
```python
def load_file_from_db(conn, path)       # ~50 LOC
def upsert_file(conn, info)             # ~70 LOC
def insert_segments(conn, file_id, segments)  # ~30 LOC
def load_slide_hashes(conn, file_id, segments)  # ~20 LOC
def store_file_signals(conn, info)      # ~30 LOC
def insert_fp_bands(conn, file_id, fingerprint)  # ~25 LOC
```
**Lines: ~225**

#### Section 6: Fingerprint Utilities (Lines 1000-1200 in both)
```python
def _normalize_base64_payload(data)     # ~15 LOC
def _decode_base64_fingerprint(encoded) # ~20 LOC
def _coerce_fingerprint_sequence(values)  # ~15 LOC
def parse_fpcalc_output(output)         # ~80 LOC
def compute_fingerprint(path)           # ~30 LOC
def fingerprint_similarity(fp_a, fp_b, ...)  # ~40 LOC
```
**Lines: ~200**

#### Section 7: Health Checking (Lines 1200-1250 in both)
```python
def check_health(path)                  # ~30 LOC
```
**Lines: ~30**

#### Section 8: Command Execution (Lines 1250-1350 in both)
```python
class CommandError(RuntimeError)        # ~3 LOC
def run_command(command, timeout)       # ~80 LOC (complex with pgid tracking)
```
**Lines: ~83**

---

## Part 2: The Proper Consolidation Plan

### Step 1: Create lib/common.py

**Location:** `/Users/georgeskhawam/dedupe/scripts/lib/common.py`

**Contents:** All duplicated code + shared state management

```python
"""
Shared utilities for FLAC scanning and deduplication.

This module consolidates common functionality:
- Database schema and operations
- Logging and progress tracking
- Fingerprint utilities
- Health checking
- Command execution with process group management
"""

from __future__ import annotations

import argparse
import base64
import binascii
import binascii
import csv
import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import signal
import sqlite3
import struct
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

# ===== Global State =====
last_progress_timestamp = time.time()
last_progress_file = None
freeze_detector_stop = threading.Event()

active_ffmpeg_pgids: Set[int] = set()
active_pgid_lock = threading.Lock()

scan_progress_lock = threading.Lock()
scan_processed_count = 0
scan_total_files = 0
scan_skipped_count = 0

progress_update_lock = threading.Lock()
progress_color_index = 0
timestamp_color_index = 0
progress_word_offset = 0
last_timestamp_color = "\033[31m"
gay_flag_colors = [
    "\033[31m",  # Red
    "\033[33m",  # Yellow (for orange)
    "\033[33m",  # Yellow
    "\033[32m",  # Green
    "\033[34m",  # Blue
    "\033[35m"   # Purple
]

DIAGNOSTICS: Optional[DiagnosticsManager] = None
CMD_TIMEOUT: int = 45
DECODE_TIMEOUT: int = 30

# ===== Section 1: Data Containers =====
# [Copy all @dataclass definitions]
# - SegmentHashes
# - FileInfo
# - GroupResult
# - DiagnosticsManager (with all methods)

# ===== Section 2: Utility Helpers =====
# [Copy all simple functions]
# - register_active_pgid()
# - unregister_active_pgid()
# - colorize_path()
# - heartbeat()
# - log()
# - log_progress()
# - log_skip()
# - is_tool_available()
# - sha1_hex()
# - human_size()
# - ensure_directory()

# ===== Section 3: Database Management =====
# DB_SCHEMA_VERSION = 1
# [Copy database functions]
# - ensure_schema()
# - _create_schema()

# ===== Section 4: File Database Operations =====
# [Copy all database query/insert functions]
# - load_file_from_db()
# - upsert_file()
# - insert_segments()
# - load_slide_hashes()
# - store_file_signals()
# - insert_fp_bands()

# ===== Section 5: Fingerprint Utilities =====
# [Copy all fingerprint functions]
# - _normalize_base64_payload()
# - _decode_base64_fingerprint()
# - _coerce_fingerprint_sequence()
# - parse_fpcalc_output()
# - fingerprint_similarity()

# ===== Section 6: Health Checking =====
# [Copy check_health()]

# ===== Section 7: Command Execution =====
# class CommandError(RuntimeError)
# def run_command(command, timeout)
```

**Estimated lines:** ~1,200 LOC

**Key considerations:**
- Keep global state mutable (needed for progress tracking across modules)
- Preserve ALL logic exactly as-is (no refactoring)
- Do NOT modify imports or function signatures
- Test imports work from both flac_scan.py and flac_dedupe.py

---

### Step 2: Update flac_scan.py

**Remove:** Lines 1-1200 (all duplicate sections 1-5)

**Replace with:** Import statements

```python
from __future__ import annotations

# Import ALL shared utilities from lib.common
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

# Keep specific to flac_scan.py:
# - All remaining functions that are UNIQUE to scan (lines 1200+)
# - Main entry point code
# - CLI argument parsing
```

**Changes needed:**
1. Delete lines 1-1200 (all duplicate imports and functions)
2. Add the import block above
3. Verify no functionality is lost
4. Test: `python flac_scan.py --help`

---

### Step 3: Update flac_dedupe.py

**Identical to Step 2:**

```python
from __future__ import annotations

# Import ALL shared utilities from lib.common
from lib.common import (
    # [Same imports as flac_scan.py]
)

# Keep specific to flac_dedupe.py:
# - All remaining functions UNIQUE to dedupe (lines 1200+)
# - Main entry point code
# - CLI argument parsing
```

**Changes needed:**
1. Delete lines 1-1200 (all duplicate imports and functions)
2. Add the import block
3. Verify no functionality is lost
4. Test: `python flac_dedupe.py --help`

---

## Part 3: Verification Checklist

### Before Starting

- [ ] Backup current scripts: `cp -r scripts scripts.backup`
- [ ] Current state runs: `python scripts/dedupe_cli.py --help`
- [ ] Git is clean: `git status` shows no uncommitted changes

### Step 1 - Create lib/common.py

- [ ] Create `/Users/georgeskhawam/dedupe/scripts/lib/` directory
- [ ] Create `/Users/georgeskhawam/dedupe/scripts/lib/__init__.py` (empty)
- [ ] Copy all duplicate code from flac_scan.py lines 1-1200 to lib/common.py
- [ ] Verify lib/common.py imports work: `python -c "from lib.common import *"`
- [ ] Check for syntax errors: `python -m py_compile scripts/lib/common.py`

### Step 2 - Update flac_scan.py

- [ ] Backup: `cp scripts/flac_scan.py scripts/flac_scan.py.backup`
- [ ] Delete lines 1-1200
- [ ] Add import block (see Step 2 above)
- [ ] Verify syntax: `python -m py_compile scripts/flac_scan.py`
- [ ] Run help: `python scripts/flac_scan.py --help`
- [ ] Run scan (dry): `python scripts/flac_scan.py --help` (check all args work)

### Step 3 - Update flac_dedupe.py

- [ ] Backup: `cp scripts/flac_dedupe.py scripts/flac_dedupe.py.backup`
- [ ] Delete lines 1-1200
- [ ] Add import block
- [ ] Verify syntax: `python -m py_compile scripts/flac_dedupe.py`
- [ ] Run help: `python scripts/flac_dedupe.py --help`
- [ ] Run dedupe (dry): `python scripts/flac_dedupe.py --help` (check all args work)

### Final Verification

- [ ] Test full CLI: `python scripts/dedupe_cli.py --help`
- [ ] Test scan subcommand: `python scripts/dedupe_cli.py scan --help`
- [ ] Test dedupe subcommand: `python scripts/dedupe_cli.py dedupe --help`
- [ ] Check line counts:
  - flac_scan.py: should reduce from 2,602 to ~1,400 LOC
  - flac_dedupe.py: should reduce from 2,520 to ~1,450 LOC
  - lib/common.py: should be ~1,200 LOC
- [ ] Git diff shows expected deletions:
  ```bash
  git diff scripts/flac_scan.py | grep "^-" | wc -l  # Should be ~1,200
  git diff scripts/flac_dedupe.py | grep "^-" | wc -l # Should be ~1,200
  ```
- [ ] All functionality preserved (no features lost)

---

## Part 4: Potential Issues & Solutions

### Issue 1: Import Cycles

**Problem:** If lib/common.py imports from flac_scan.py or flac_dedupe.py

**Solution:** Ensure lib/common.py has NO imports from the other scripts

**Check:**
```bash
grep "from flac_scan import\|from flac_dedupe import\|import flac_scan\|import flac_dedupe" scripts/lib/common.py
# Should return nothing
```

### Issue 2: Global State Not Updating

**Problem:** Progress tracking globals don't update properly

**Solution:** Keep globals mutable in lib/common.py, use `global` keyword when modifying

**Example in log():**
```python
def log(message: str) -> None:
    global timestamp_color_index  # Must declare to modify
    timestamp_color = gay_flag_colors[timestamp_color_index % 6]
    timestamp_color_index += 1
    # ...
```

### Issue 3: DIAGNOSTICS Initialization

**Problem:** `DIAGNOSTICS = None` in lib/common.py, but initialized in flac_scan.py

**Solution:** Keep as `None` in lib/common.py, initialize it in flac_scan.py/flac_dedupe.py

**Example:**
```python
# In lib/common.py:
DIAGNOSTICS: Optional[DiagnosticsManager] = None

# In flac_scan.py (after imports):
from lib import common
# ... later in main():
common.DIAGNOSTICS = DiagnosticsManager(...)
```

### Issue 4: Module-level Code Execution

**Problem:** Some code in lib/common.py might execute on import

**Solution:** Move into functions, only execute in main()

**Example:**
```python
# BAD (executes on import):
some_value = expensive_computation()

# GOOD (only executes when called):
def init_common():
    global some_value
    some_value = expensive_computation()

# Call in main()
```

---

## Part 5: Timeline & Effort

| Phase | Task | Time | Difficulty |
|-------|------|------|------------|
| 1 | Create lib/common.py | 30 min | Low (copy-paste) |
| 2 | Update flac_scan.py imports | 15 min | Low (delete + add imports) |
| 3 | Update flac_dedupe.py imports | 15 min | Low (delete + add imports) |
| 4 | Test both scripts individually | 15 min | Medium (may need fixes) |
| 5 | Test CLI integration | 15 min | Medium (may need fixes) |
| 6 | Cleanup backup files | 5 min | Trivial |

**Total: ~1.5 hours**

---

## Part 6: Final Result

### After Consolidation

```
scripts/
├── lib/
│   ├── __init__.py
│   └── common.py            (~1,200 LOC - shared utilities)
├── dedupe_cli.py            (267 LOC - unchanged)
├── dedupe_sync.py           (486 LOC - unchanged)
├── file_operations.py       (320 LOC - unchanged)
├── flac_dedupe.py           (1,450 LOC - was 2,520, -1,070)
├── flac_repair.py           (715 LOC - unchanged)
├── flac_scan.py             (1,400 LOC - was 2,602, -1,202)
├── stage_hash_dupes.sh      (157 LOC - unchanged)
├── scrd                     (unchanged)
└── README.md                (unchanged)
```

### Metrics

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Total Python LOC | 7,467 | 5,835 | **-22% (-1,632 LOC)** |
| Duplicate code | 1,070 | 0 | **100% eliminated** |
| Main files (scan + dedupe) | 5,122 | 2,850 | **-44%** |
| Number of files | 9 | 10 | +1 (lib/common.py) |
| Code clarity | Lower | Higher | Single source of truth ✓ |

---

## Part 7: Git Commands for Verification

```bash
# Before cleanup, backup current state:
cd /Users/georgeskhawam/dedupe
git add -A
git commit -m "Pre-consolidation backup"

# After making changes, verify:
git diff scripts/flac_scan.py | head -50      # See what was removed
git diff scripts/flac_dedupe.py | head -50    # See what was removed
git diff scripts/lib/common.py | head -50     # See what was added

# Line count verification:
wc -l scripts/flac_scan.py scripts/flac_dedupe.py scripts/lib/common.py

# Syntax check all:
python -m py_compile scripts/*.py scripts/lib/*.py
```

---

## Summary

**This document provides:**
✅ Exact sections of code to extract (with line numbers)  
✅ Step-by-step implementation instructions  
✅ Complete import list for both files  
✅ Verification checklist  
✅ Common pitfalls and solutions  
✅ Final metrics and results

**When complete:**
- 22% reduction in Python LOC
- 100% elimination of code duplication
- Single source of truth for all shared utilities
- Same functionality, cleaner architecture
