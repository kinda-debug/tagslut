# Definitive FLAC Deduplication Workflow

> **This is the ONE workflow to follow.** Ignore other docs if they conflict.

---

## Prerequisites

### 1. Python 3.11+ Required

Your venv is broken. Fix it:

```bash
# Install Python 3.12 via Homebrew
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install python@3.12

# Recreate venv
cd /Users/georgeskhawam/Projects/dedupe
rm -rf .venv
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Verify Installation

```bash
source .venv/bin/activate
python --version  # Must be 3.11+
python -c "from dedupe.core.metadata import extract_metadata; print('OK')"
```

---

## The Workflow (5 Stages)

```
┌─────────────────────────────────────────────────────────────────────┐
│  STAGE 1: SCAN          →  Index all files with hashes             │
│  STAGE 2: PLAN          →  Generate duplicate decisions            │
│  STAGE 3: REVIEW        →  Human approval of plan                  │
│  STAGE 4: QUARANTINE    →  Move duplicates (non-destructive)       │
│  STAGE 5: DELETE        →  Permanent removal after 30 days         │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Stage 1: SCAN

**Goal:** Index all FLAC files with full integrity verification.

### Create Fresh Database

```bash
# Create new epoch directory
mkdir -p /Users/georgeskhawam/Projects/dedupe_db/EPOCH_$(date +%Y-%m-%d)
export DB_PATH="/Users/georgeskhawam/Projects/dedupe_db/EPOCH_$(date +%Y-%m-%d)/music.db"
```

### Scan Primary Library (KEEPER zone)

```bash
source .venv/bin/activate

python tools/integrity/scan.py //Volumes/COMMUNE/M/Library_CANONICAL \
  --db "$DB_PATH" \
  --zone accepted \
  --check-integrity \
  --check-hash \
  --create-db \
  --progress
```

### Scan Suspect Volumes

```bash
# Scan each suspect volume with appropriate zone tag
python tools/integrity/scan.py /Volumes/bad/archive \
  --db "$DB_PATH" \
  --zone suspect \
  --check-integrity \
  --check-hash\
  --create-db \ 
  --progress

python tools/integrity/scan.py /Volumes/xtralegroom \
  --db "$DB_PATH" \
  --zone suspect \
  --check-integrity \
  --check-hash \
  --progress
```

### Verify Scan Completeness

```bash
sqlite3 "$DB_PATH" "
SELECT
  'Total files' as metric, COUNT(*) as value FROM files
UNION ALL
SELECT 'With SHA256', COUNT(*) FROM files WHERE sha256 IS NOT NULL
UNION ALL
SELECT 'With integrity_state', COUNT(*) FROM files WHERE integrity_state IS NOT NULL
UNION ALL
SELECT 'Corrupt files', COUNT(*) FROM files WHERE integrity_state = 'corrupt';
"
```

**Expected:** All files should have SHA256 and integrity_state populated.

---

## Stage 2: PLAN

**Goal:** Generate deduplication decisions based on zone priority.

### Generate Removal Plan

```bash
python tools/review/plan_removals.py \
  --db "$DB_PATH" \
  --output removal_plan.csv
```

### Understand the Output

The CSV contains:

| Column          | Meaning                                                |
| --------------- | ------------------------------------------------------ |
| `sha256`      | File content hash                                      |
| `tier`        | TIER1 (auto-safe), TIER2 (quarantine), MANUAL (review) |
| `action`      | KEEP or DROP                                           |
| `path`        | File location                                          |
| `zone`        | accepted/staging/suspect/quarantine                    |
| `keeper_path` | Which file is being kept                               |

### Tier Classification

| Tier             | Meaning                              | Action                     |
| ---------------- | ------------------------------------ | -------------------------- |
| **TIER1**  | Valid keeper in higher-priority zone | Auto-quarantine duplicates |
| **TIER2**  | Keeper validity uncertain            | Quarantine for review      |
| **MANUAL** | Same-zone duplicates                 | Human decision required    |

---

## Stage 3: REVIEW

**Goal:** Human approval before any files are moved.

### Summary Statistics

```bash
# Count by tier
cut -d',' -f2 removal_plan.csv | sort | uniq -c

# Count by action
cut -d',' -f3 removal_plan.csv | sort | uniq -c

# Sample TIER1 (safe) removals
grep "TIER1,DROP" removal_plan.csv | head -20
```

### Review Checklist

- [ ] All KEEP files are in `/Volumes/COMMUNE/M/Library` (accepted zone)?
- [ ] No TIER1 DROP files are unique (have a keeper)?
- [ ] MANUAL tier files reviewed individually?
- [ ] Total file count matches expectations?

### Optional: Export for Spreadsheet Review

```bash
# Open in Excel/Numbers for detailed review
open removal_plan.csv
```

---

## Stage 4: QUARANTINE

**Goal:** Move duplicates to quarantine folder (reversible).

### Dry Run First

```bash
python tools/review/apply_removals.py \
  --db "$DB_PATH" \
  --plan removal_plan.csv \
  --quarantine-root /Volumes/COMMUNE/M/_quarantine \
  --dry-run
```

Review the output. If it looks correct:

### Execute Quarantine

```bash
python tools/review/apply_removals.py \
  --db "$DB_PATH" \
  --plan removal_plan.csv \
  --quarantine-root /Volumes/COMMUNE/M/_quarantine \
  --execute
```

### Verify Quarantine

```bash
# Check quarantine table
sqlite3 "$DB_PATH" "
SELECT tier, COUNT(*) as count
FROM file_quarantine
WHERE deleted_at IS NULL
GROUP BY tier;
"

# Check disk usage
du -sh /Volumes/COMMUNE/M/_quarantine
```

---

## Stage 5: DELETE (After 30 Days)

**Goal:** Permanently delete quarantined files after retention period.

### Check What Will Be Deleted

```bash
python tools/review/apply_removals.py \
  --db "$DB_PATH" \
  --delete-after-days 30 \
  --dry-run
```

### Execute Permanent Deletion

```bash
python tools/review/apply_removals.py \
  --db "$DB_PATH" \
  --delete-after-days 30 \
  --execute
```

### Verify Deletion

```bash
sqlite3 "$DB_PATH" "
SELECT
  COUNT(*) as deleted_count,
  SUM(CASE WHEN deleted_at IS NOT NULL THEN 1 ELSE 0 END) as confirmed_deleted
FROM file_quarantine;
"
```

---

## Quick Reference Commands

### Check Database State

```bash
sqlite3 "$DB_PATH" "
SELECT zone, COUNT(*) as files,
       ROUND(SUM(size)/1024.0/1024.0/1024.0, 2) as gb
FROM files
GROUP BY zone
ORDER BY files DESC;
"
```

### Find Duplicates

```bash
sqlite3 "$DB_PATH" "
SELECT sha256, COUNT(*) as copies
FROM files
WHERE sha256 IS NOT NULL
GROUP BY sha256
HAVING COUNT(*) > 1
ORDER BY copies DESC
LIMIT 10;
"
```

### Check Scan Coverage

```bash
sqlite3 "$DB_PATH" "
SELECT
  CASE
    WHEN sha256 IS NOT NULL THEN 'Has SHA256'
    WHEN streaminfo_md5 IS NOT NULL THEN 'Has STREAMINFO only'
    ELSE 'No hash'
  END as status,
  COUNT(*) as files
FROM files
GROUP BY status;
"
```

---

## Zone Priority (DO NOT CHANGE)

| Priority    | Zone           | Meaning                 |
| ----------- | -------------- | ----------------------- |
| 1 (highest) | `accepted`   | Verified keeper files   |
| 2           | `staging`    | Candidates under review |
| 3           | `suspect`    | Questionable files      |
| 4 (lowest)  | `quarantine` | Marked for deletion     |

When duplicates exist across zones, the file in the **highest priority zone** is kept.

---

## Critical Rules

1. **ALWAYS scan with `--check-hash`** — without SHA256, deduplication cannot work
2. **NEVER skip the review stage** — always verify the plan before quarantine
3. **Quarantine is reversible** — files are moved, not deleted
4. **30-day retention** — you have 30 days to recover from mistakes
5. **One database per epoch** — don't reuse databases across major changes

---

## Troubleshooting

### "No module named 'dedupe'"

```bash
source .venv/bin/activate
pip install -e .
```

### "TypeError: unsupported operand type(s) for |"

Python version too old. Need 3.11+.

### "Missing SHA256 for files"

Re-scan with `--check-hash --recheck`:

```bash
python tools/integrity/scan.py /path/to/files \
  --db "$DB_PATH" \
  --zone accepted \
  --check-hash \
  --recheck
```

### "Database is locked"

Another process is using the database. Close other terminals or use `--db` flag consistently.

---

## File Locations

| Resource        | Path                                                                  |
| --------------- | --------------------------------------------------------------------- |
| Repository      | `/Users/georgeskhawam/Projects/dedupe`                              |
| Database        | `/Users/georgeskhawam/Projects/dedupe_db/EPOCH_YYYY-MM-DD/music.db` |
| Config          | `/Users/georgeskhawam/Projects/dedupe/config.toml`                  |
| Primary Library | `/Volumes/COMMUNE/M/Library`                                        |
| Quarantine      | `/Volumes/COMMUNE/M/_quarantine`                                    |

---

## Summary

```
1. SCAN    → python tools/integrity/scan.py ... --check-hash --check-integrity
2. PLAN    → python tools/review/plan_removals.py --output removal_plan.csv
3. REVIEW  → Inspect removal_plan.csv, verify keeper selection
4. QUARANTINE → python tools/review/apply_removals.py --execute
5. DELETE  → python tools/review/apply_removals.py --delete-after-days 30 --execute
```

**That's it. No other tools needed.**

---

## Stage 6: PROMOTE UNIQUE FILES (Optional)

**Goal:** Copy files that exist only in suspect zones to the canonical library.

### Find Unique Files

```bash
# Files in suspect zone with no duplicate in accepted zone
sqlite3 "$DB_PATH" "
SELECT path FROM files
WHERE zone = 'suspect'
  AND sha256 IS NOT NULL
  AND sha256 NOT IN (SELECT sha256 FROM files WHERE zone = 'accepted' AND sha256 IS NOT NULL)
ORDER BY path;
" > unique_files_to_promote.txt

# Count
wc -l unique_files_to_promote.txt
```

### Dry Run Promotion

```bash
python tools/review/promote_by_tags.py \
  --paths-from-file unique_files_to_promote.txt \
  --dest-root /Volumes/COMMUNE/M/Library_CANONICAL \
  --mode copy \
  --no-resume \
  --progress-every-seconds 5
```

Review output for errors (filename too long, missing tags, etc.)

### Execute Promotion

```bash
python tools/review/promote_by_tags.py \
  --paths-from-file unique_files_to_promote.txt \
  --dest-root /Volumes/COMMUNE/M/Library_CANONICAL_final \
  --mode copy \
  --no-resume \
  --execute \
  --progress-every-seconds 5 \
  --log-file promote_execute.log
```

### Verify Promotion

```bash
# Check log for errors
grep -i error promote_execute.log

# Rescan accepted zone to index new files
python tools/integrity/scan.py /Volumes/COMMUNE/M/Library_CANONICAL \
  --db "$DB_PATH" \
  --zone accepted \
  --check-integrity \
  --check-hash \
  --progress
```

### Handle Problem Files

Files with extremely long names may fail. Exclude and handle manually:

```bash
# Find files with long paths
awk 'length > 200' unique_files_to_promote.txt

# Remove problematic files from list
grep -v "problematic pattern" unique_files_to_promote.txt > unique_files_fixed.txt
```

---

## Complete Batch Workflow Example

For processing a new batch of files:

```bash
# 1. Set database path
export DB_PATH="/Users/georgeskhawam/Projects/dedupe_db/EPOCH_$(date +%Y-%m-%d)/music.db"
cd /Users/georgeskhawam/Projects/dedupe
source .venv/bin/activate

# 2. Scan canonical library (accepted zone)
python tools/integrity/scan.py /Volumes/COMMUNE/M/Library_CANONICAL \
  --db "$DB_PATH" --zone accepted --check-integrity --check-hash --create-db --progress

# 3. Scan new batch (suspect zone)
python tools/integrity/scan.py /path/to/new/batch \
  --db "$DB_PATH" --zone suspect --check-integrity --check-hash --progress

# 4. Check database state
sqlite3 "$DB_PATH" "
SELECT zone, COUNT(*) as files,
       SUM(CASE WHEN integrity_state='valid' THEN 1 ELSE 0 END) as valid,
       SUM(CASE WHEN integrity_state='corrupt' THEN 1 ELSE 0 END) as corrupt
FROM files GROUP BY zone;
"

# 5. Generate removal plan
python tools/review/plan_removals.py \
  --db "$DB_PATH" --output removal_plan.csv --zone-priority "accepted,suspect"

# 6. Review plan
head -20 removal_plan.csv
cut -d',' -f2 removal_plan.csv | sort | uniq -c  # Count by tier

# 7. Find unique files (not in canonical library)
sqlite3 "$DB_PATH" "
SELECT path FROM files
WHERE zone = 'suspect' AND sha256 IS NOT NULL
  AND sha256 NOT IN (SELECT sha256 FROM files WHERE zone = 'accepted')
" > unique_files.txt

# 8. Promote unique files (dry run first)
python tools/review/promote_by_tags.py \
  --paths-from-file unique_files.txt \
  --dest-root /Volumes/COMMUNE/M/Library_CANONICAL \
  --mode copy --no-resume

# 9. Execute promotion
python tools/review/promote_by_tags.py \
  --paths-from-file unique_files.txt \
  --dest-root /Volumes/COMMUNE/M/Library_CANONICAL \
  --mode copy --no-resume --execute

# 10. Quarantine duplicates (dry run first)
python tools/review/apply_removals.py \
  --db "$DB_PATH" --plan removal_plan.csv \
  --quarantine-root /Volumes/COMMUNE/M/_quarantine --dry-run

# 11. Execute quarantine
python tools/review/apply_removals.py \
  --db "$DB_PATH" --plan removal_plan.csv \
  --quarantine-root /Volumes/COMMUNE/M/_quarantine --execute
```
