# AI Agent Handover Report

> **Generated:** 2026-01-16
> **Database:** `/Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-16/music.db`
> **Repository:** `/Users/georgeskhawam/Projects/dedupe`
> **Branch:** `release/modernization-complete`

---

## Executive Summary

| Attribute | Value |
|-----------|-------|
| **Project** | flac-dedupe v2.0.0 — Recovery-first FLAC deduplication system |
| **Current Phase** | POST-SCAN / READY FOR DEDUPLICATION EXECUTION |
| **Safety Status** | ✅ All destructive actions BLOCKED by review-first mode |

### Key Metrics

| Metric | Value | Notes |
|--------|-------|-------|
| Total Files Indexed | 24,676 | All reachable files |
| Unique Files (SHA256) | 20,251 | Distinct content |
| Duplicates Detected | 4,425 (17.9%) | Candidates for deduplication |
| Potential Space Recovery | ~170 GB | Estimated savings |
| Corrupt Files | 1,863 (7.5%) | Excluded from deduplication |
| Current Storage | 970 GB | Total across all volumes |

### ⚠️ Current Blocker

**`apply.py` has a hardcoded safety lock** (lines 39–42) preventing all DROP actions for the COMMUNE library. 4,861 files are marked for deletion but execution is blocked.

---

## Table of Contents

1. [Database State Analysis](#database-state-analysis)
2. [System Architecture](#system-architecture)
3. [Deduplication Logic](#deduplication-logic)
4. [Immediate Next Steps](#immediate-next-steps)
5. [Key File Locations](#key-file-locations)
6. [Risk Assessment](#risk-assessment)
7. [Recommended AI Agent Actions](#recommended-ai-agent-actions)
8. [Emergency Rollback](#emergency-rollback)
9. [Questions for Human Operator](#questions-for-human-operator)
10. [Command Reference](#command-reference)
11. [Technical Debt / Known Issues](#technical-debt--known-issues)

---

## Database State Analysis

### File Distribution by Zone

Files are organized by zone (priority order) and integrity status:

| Zone | Library | Files | Size (GB) | Integrity | Status |
|------|---------|------:|----------:|-----------|--------|
| accepted | COMMUNE | 11,123 | 461.3 | Valid | ✅ KEEPER ZONE |
| accepted | COMMUNE | 1,063 | 0.0 | Corrupt | ⚠️ Need cleanup |
| quarantine | COMMUNE | 7,502 | 336.1 | Valid | 🔍 Under review |
| quarantine | COMMUNE | 436 | 0.01 | Corrupt | ⚠️ Need cleanup |
| suspect | bad | 4,188 | 172.2 | Valid | 🗑️ Low priority |
| suspect | xtralegroom | 1,284 | — | Valid | 🗑️ Low priority |
| suspect | bad | 364 | 0.12 | Corrupt | ⚠️ Need cleanup |

### Scanning Coverage

| Status | Files | Percentage | Description |
|--------|------:|------------|-------------|
| SHA256_FULL | 22,813 | 92.5% | Deep verification complete |
| NOT_SCANNED | 1,863 | 7.5% | Corrupt files excluded |
| **Total** | **24,676** | **100%** | All reachable files scanned |

### Duplicate Examples

```
4× copies: James Hype & Tita Lau - On the Ground.flac
   ├─ /Volumes/COMMUNE/M/Library/...              → KEEPER
   ├─ /Volumes/bad/archive/...                    → CANDIDATE FOR DELETION
   ├─ /Volumes/bad/archive/.../_DEDUPED_DISCARDS/ → CANDIDATE
   └─ /Volumes/xtralegroom/...                    → CANDIDATE

4× copies: !K7 - DJ-Kicks: Crank It Up.flac
   ├─ /Volumes/COMMUNE/M/Library/...              → KEEPER
   ├─ /Volumes/bad/quarantine/...                 → CANDIDATE
   ├─ /Volumes/bad/quarantine/.../hex_suffix/...  → CANDIDATE
   └─ /Volumes/xtralegroom/...                    → CANDIDATE
```

### Deduplication Plan Status

| Attribute | Value |
|-----------|-------|
| Plan File | `plan.json` (5.5 MB) |
| Duplicate Groups | 2,299 |
| Total Decisions | 4,861 files marked for REVIEW |

**Actions Breakdown:**

| Action | Count | Notes |
|--------|------:|-------|
| KEEP | 0 | Implicit — keepers excluded from plan |
| DROP | 0 | Blocked by safety lock |
| REVIEW | 4,861 | All DROP actions converted |

---

## System Architecture

### Core Components

```
dedupe/
├── integrity_scanner.py       # FLAC validation & metadata extraction
├── storage/
│   └── schema.py              # Database initialization & migrations
├── core/
│   ├── matching.py            # Duplicate detection (find_exact_duplicates)
│   └── decisions.py           # Keeper selection (assess_duplicate_group)
├── filters/                   # File selection rules
└── utils/                     # Config, CLI helpers, logging

tools/
├── integrity/scan.py          # Main scanning CLI (resumable)
├── decide/
│   ├── recommend.py           # Generate deduplication plan
│   └── apply.py               # Execute plan (CURRENTLY BLOCKED)
├── analysis/                  # Reporting tools
└── review/                    # Manual inspection utilities
```

### Database Schema (v1)

The SQLite database contains 5 tables:

| Table | Rows | Purpose |
|-------|-----:|---------|
| `files` | 24,676 | Primary inventory — path, library, zone, checksums, integrity |
| `scan_sessions` | 7 | Audit trail — discovered, succeeded, failed per scan |
| `file_scan_runs` | — | Per-file scan history (FK → scan_sessions) |
| `file_quarantine` | 0 | Deletion tracking (EMPTY — no deletions executed) |
| `schema_migrations` | 1 | Version control (v1 applied 2026-01-09) |

**Key indexes on `files`:** `checksum`, `sha256`, `streaminfo_md5`, `acoustid`

### Configuration (`config.toml`)

```toml
[db]
path = "/Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-16/music.db"

[library]
name = "COMMUNE"
root = "/Volumes/COMMUNE/M"

[library.zones]
staging = "01_candidates"
accepted = "Library"

[decisions]
zone_priority = ["accepted", "staging", "suspect", "quarantine"]
metadata_tiebreaker = true

[integrity]
parallel_workers = 8
db_write_batch_size = 50
db_flush_interval = 60
incremental = true
```

---

## Deduplication Logic

### Priority-Based Keeper Selection

**Source:** `dedupe/core/decisions.py` → `assess_duplicate_group()`

**Algorithm:**

1. Group files by identical SHA256 hash
2. Rank by zone priority: `accepted > staging > suspect > quarantine`
3. Select highest-priority file as **KEEPER**
4. Mark lower-priority copies as **DROP**
5. Apply metadata tiebreaker if enabled (artist/album/title completeness)

**Current Behavior:**
- All DROP actions are converted to REVIEW by the safety lock
- Keepers are excluded from the deletion list (implicit KEEP)

### Safety Mechanisms

#### 1. Hardcoded DROP Block

**Location:** `tools/decide/apply.py` (lines 39–42)

```python
if action == "DROP":
    logger.warning("Skipping DROP action for %s (COMMUNE is review-first)", path)
    stats["reviewed"] += 1
    continue
```

#### 2. Dry-Run Default

The `apply.py` command defaults to `--dry-run`. Requires explicit `--execute` flag.

#### 3. Quarantine Table

All deletions are logged to `file_quarantine` with:
- `original_path` — Where the file was
- `quarantine_path` — Where it was moved (if applicable)
- `keeper_path` — The file that was kept
- `tier` — Classification level
- `deleted_at` — Timestamp

---

## Immediate Next Steps

### Option 1: Enable Deletions (⚠️ HIGH RISK)

```bash
# 1. Edit tools/decide/apply.py — remove lines 39–42
# 2. Execute:
python3 tools/decide/apply.py plan.json --execute
```

**Warning:** Will permanently delete 4,861 files based on zone priority.

### Option 2: Selective Approval (MODERATE RISK)

Filter `plan.json` to only high-confidence deletions:

```bash
python3 -c "
import json
data = json.load(open('plan.json'))
filtered = [g for g in data['plan'] if any(d['confidence'] == 'high' for d in g['decisions'])]
json.dump({'plan': filtered}, open('plan_filtered.json', 'w'), indent=2)
"
# Then manually review and approve filtered plan
```

### Option 3: Move to Quarantine (✅ SAFER)

Modify `apply.py` to move files instead of deleting:

```python
import shutil
from pathlib import Path

quarantine_dir = Path("/Volumes/COMMUNE/M/quarantine/auto_deduped")
quarantine_dir.mkdir(parents=True, exist_ok=True)
shutil.move(str(path), quarantine_dir / path.name)
```

---

## Key File Locations

### Critical Paths

| Resource | Path |
|----------|------|
| Database | `/Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-16/music.db` |
| Config | `/Users/georgeskhawam/Projects/dedupe/config.toml` |
| Plan | `/Users/georgeskhawam/Projects/dedupe/plan.json` (5.5 MB) |

### Volume Locations

| Volume | Path | Files |
|--------|------|------:|
| Primary (Library) | `/Volumes/COMMUNE/M/Library` | 12,186 |
| Quarantine | `/Volumes/COMMUNE/M/quarantine` | 7,938 |
| Suspect | `/Volumes/bad/archive` | 3,268 |
| Suspect | `/Volumes/xtralegroom` | 1,284 |

### Documentation

All docs in `/Users/georgeskhawam/Projects/dedupe/docs/`:

| File | Description |
|------|-------------|
| `OPERATOR_GUIDE.md` | Complete workflow |
| `TOOLS.md` | CLI reference |
| `SCANNING.md` | Scan behavior |
| `CONFIG.md` | Configuration options |
| `QUICKSTART.md` | Fast onboarding |

---

## Risk Assessment

### ✅ High Confidence (Safe to Delete)

- Files in `/Volumes/bad/archive/.../_DEDUPED_DISCARDS/` — already marked as trash
- Files with `hex_suffix` pattern — automated quarantine markers
- Duplicates with keeper in `COMMUNE/accepted` zone + valid integrity

### 🔍 Review Required

- Files in `COMMUNE/quarantine` (7,938 files) — unclear classification
- Corrupt files in all zones (1,863 total) — need separate cleanup
- Files in suspect zones without clear keeper — verify zone_priority logic

### 🚫 Blockers

| Blocker | Description |
|---------|-------------|
| Safety lock | `apply.py` lines 39–42 — intentional protection, must be manually removed |
| No tier classification | `recommend.py` doesn't output tier info in plan.json |
| Corrupt file handling | No automated cleanup for `integrity_state='corrupt'` |

---

## Recommended AI Agent Actions

### Phase 1: Validation (DO THIS FIRST)

1. Sample 10–20 duplicate groups from `plan.json`
2. Verify keeper selection logic is correct
3. Check that all keepers exist in `COMMUNE/accepted`
4. Confirm no valid files in accepted zone are marked DROP

### Phase 2: Safe Execution

1. Filter `plan.json` to only files in:
   - `/Volumes/bad/archive/.../_DEDUPED_DISCARDS/`
   - `/Volumes/bad/quarantine/.../hex_suffix/`
2. Create new plan: `plan_safe.json`
3. Modify `apply.py` to log all deletions to `file_quarantine` table
4. Execute with `--execute` flag on filtered plan

### Phase 3: Full Deduplication

1. Review `file_quarantine` table after Phase 2
2. If no issues, remove `apply.py` safety lock
3. Execute full `plan.json` with `--execute`
4. Monitor `file_quarantine` table for audit trail

### Phase 4: Corrupt File Cleanup

```sql
-- Generate list of corrupt files for review
SELECT path, library, zone, size
FROM files
WHERE integrity_state = 'corrupt'
ORDER BY zone, library;
```

---

## Emergency Rollback

### If Deletions Go Wrong

**Step 1:** Check `file_quarantine` table for deletion log:

```sql
SELECT * FROM file_quarantine WHERE deleted_at IS NOT NULL;
```

**Step 2:** If files were moved (not deleted), restore from `quarantine_path`:

```bash
sqlite3 music.db "SELECT original_path, quarantine_path FROM file_quarantine" | \
while IFS='|' read orig quar; do mv "$quar" "$orig"; done
```

**Step 3:** If files were permanently deleted, restore from backup volumes.

---

## Questions for Human Operator

Before proceeding, please clarify:

1. **Is it safe to delete files in `COMMUNE/quarantine` zone?** (7,938 files)
2. **Should corrupt files be deleted automatically?** (1,863 files)
3. **Are there backups of all volumes?** (Confirm before executing deletions)
4. **What is the intended purpose of `bad/archive/_DEDUPED_DISCARDS/`?** (Already marked as trash?)
5. **Should xtralegroom volume be considered for deletion?** (1,284 files)

---

## Command Reference

### Generate Fresh Plan

```bash
python3 tools/decide/recommend.py \
  --db "/Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-16/music.db" \
  --output plan.json \
  --priority accepted --priority staging --priority suspect --priority quarantine
```

### Analyze Plan

```bash
python3 -c "
import json
data = json.load(open('plan.json'))
print(f'Groups: {len(data[\"plan\"])}')
actions = {}
for g in data['plan']:
    for d in g['decisions']:
        actions[d['action']] = actions.get(d['action'], 0) + 1
print(f'Actions: {actions}')
"
```

### Execute Deletions (⚠️ DANGEROUS)

```bash
# Dry run (safe)
python3 tools/decide/apply.py plan.json

# Real execution (REMOVE SAFETY LOCK FIRST)
python3 tools/decide/apply.py plan.json --execute
```

---

## Technical Debt / Known Issues

| Issue | Description | Priority |
|-------|-------------|----------|
| Incomplete `apply.py` | Only logs actions, doesn't execute deletions | High |
| No tier classification | `recommend.py` should output TIER1/TIER2 like old workflow | Medium |
| Corrupt file handling | Need separate tool for `integrity_state` cleanup | Medium |
| Unused quarantine table | `file_quarantine` has 0 rows despite 1,551 in old DB | Low |
| No acoustic fingerprinting | `acoustid` column is empty (future feature?) | Low |

---

## Contact / Escalation

| Resource | Location |
|----------|----------|
| Repository | https://github.com/tagslut/dedupe |
| Current Branch | `release/modernization-complete` |
| Docs Index | `/Users/georgeskhawam/Projects/dedupe/docs/INDEX.md` |
| Config Example | `/Users/georgeskhawam/Projects/dedupe/config.example.toml` |

### ⚠️ Human Operator Approval Required Before:

- Executing deletions in accepted/quarantine zones
- Removing safety locks from `apply.py`
- Deleting corrupt files without backup verification
