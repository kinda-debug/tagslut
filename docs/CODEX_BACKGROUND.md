# Dedupe Integrity System — Forensic Background

> **Purpose:** This document provides context for any AI/agent tasked with fixing the integrity subsystem.
> It is **read-only context**, not instructions.

---

## 1. What This Project Does

`dedupe` is a Python tool for managing large FLAC music libraries recovered from damaged drives.

Core workflow:
1. **Discover** files on disk (paths, sizes, mtimes)
2. **Extract metadata** (tags, duration, sample rate, bit depth)
3. **Verify integrity** (optional: `flac -t` decode test)
4. **Deduplicate** (match by checksum, duration, metadata)
5. **Relocate** winners to canonical library

---

## 2. What Went Wrong

### 2.1 The Tuple Bug (Confirmed in Code)

**Location:** `dedupe/core/metadata.py` line 69

```python
if scan_integrity:
    integrity_state = classify_flac_integrity(path_obj)  # Returns Tuple[str, str]!
    flac_ok = (integrity_state == "valid")  # Always False
```

But `classify_flac_integrity()` returns `Tuple[IntegrityState, str]` — always a tuple.

**Result:**
- `flac_ok` is always `False` when integrity runs
- DB write crashes: `Error binding parameter 13: type 'tuple' is not supported`

### 2.2 Semantic Lie (Confirmed in Code)

**Location:** `dedupe/core/metadata.py` lines 123-125

```python
if not scan_integrity:
    integrity_state = "valid"
    flac_ok = True
```

Files that were **never integrity-checked** are marked `"valid"`.

**Result:** The DB lies. You cannot distinguish "checked and passed" from "never checked".

### 2.3 No Audit Trail

The system cannot answer:
- When was this file integrity-checked?
- How many times?
- With which flags?
- Was the session interrupted?

There is no `integrity_checks` table, no `checked_at` column, no session concept.

### 2.4 Accidental Full Rescans

`--recheck` + `--check-integrity` with `--incremental OFF` causes a full library scan.

There is no:
- `--only-failed` filter
- `--only-never-checked` filter
- `--dry-run` preflight
- Confirmation prompt for large scans

---

## 3. Current Schema (Relevant Parts)

```sql
-- files table (simplified)
CREATE TABLE files (
    id INTEGER PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,
    library TEXT,
    zone TEXT,
    checksum TEXT,
    duration REAL,
    bit_depth INTEGER,
    sample_rate INTEGER,
    bitrate INTEGER,
    metadata_json TEXT,
    flac_ok INTEGER,          -- Boolean: 0/1
    integrity_state TEXT,     -- "valid" / "corrupt" / "recoverable"
    mtime REAL,
    size INTEGER,
    acoustid TEXT
);
```

**Missing:**
- `integrity_checked_at` (timestamp)
- `integrity_tool` / `integrity_tool_version`
- `integrity_exit_code` / `integrity_stderr`
- Session linkage

---

## 4. Relevant Source Files

| File | Purpose |
|------|---------|
| `dedupe/core/integrity.py` | `classify_flac_integrity()` — runs `flac -t` |
| `dedupe/core/metadata.py` | `extract_metadata()` — caller that stores integrity |
| `dedupe/storage/models.py` | `AudioFile` dataclass |
| `dedupe/storage/queries.py` | `upsert_file()` — DB writes |
| `dedupe/integrity_scanner.py` | `scan_library()` — orchestrator |
| `tools/integrity/scan.py` | CLI entry point |

---

## 5. What a Fix Must Achieve

1. **Type stability:** `classify_flac_integrity()` returns a structure, callers unpack it.
2. **Semantic correctness:** "never checked" → `integrity_state = NULL` or `"unknown"`, not `"valid"`.
3. **Auditability:** New table or columns to record check history.
4. **Targeting:** CLI flags for `--only-failed`, `--only-never-checked`, `--paths-file`.
5. **Interrupt safety:** Batch commits, partial sessions marked incomplete.
6. **Preflight summary:** Show what will be scanned before scanning.

---

## 6. Why This Matters

This is a **recovery tool** for irreplaceable music.

If the system cannot prove a file is corrupt, it must not claim it is corrupt.
If the system cannot prove a file was checked, it must not claim it is valid.

**Uncertainty must be explicit.**
