<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# DEDUPE PRODUCTION SYSTEM — OPERATIONAL HANDOVER

**Date**: January 15, 2026, 12:00 PM EET
**Location**: Beirut, LB
**Repository**: `release/modernization-complete` ✅ PRODUCTION READY
**Status**: Active operations — Files staged for promotion

***

## EXECUTIVE SUMMARY

**Mission**: Maintain a canonically-correct, auditable FLAC library through systematic deduplication and recovery.

**Current State**:

- ✅ Infrastructure modernized (Thunderbolt 3 deployed)
- ✅ Database synchronized with filesystem
- ✅ Archives consolidated
- ✅ Recovered files staged for promotion
- ✅ All tools production-ready

**Next Phase**: Promote staged files to canonical library.

***

## PART A: VERIFY ACTUAL SYSTEM STATE

### Task 1: Audit Files by Location

```bash
# ALWAYS recount before making decisions
echo "=== STAGING DIRECTORY ===" && \
find /Volumes/bad/_integration_staging_20260115 -type f | wc -l && \
echo "" && \
echo "=== STAGING BY FORMAT ===" && \
find /Volumes/bad/_integration_staging_20260115 -type f | sed 's/.*\.//' | sort | uniq -c

echo "" && \
echo "=== CANONICAL LIBRARY ===" && \
find /Volumes/COMMUNE/M/Library -name "*.flac" -type f | wc -l

echo "" && \
echo "=== VAULT ===" && \
find /Volumes/Vault -name "*.flac" -type f | wc -l

echo "" && \
echo "=== TOTAL FLAC ON bad ===" && \
find /Volumes/bad -name "*.flac" -type f | wc -l
```

**Store results for reference**:

```bash
cat > /tmp/file_audit_20260115.txt <<'EOF'
STAGING_COUNT=$(find /Volumes/bad/_integration_staging_20260115 -type f | wc -l)
STAGING_FLAC=$(find /Volumes/bad/_integration_staging_20260115 -name "*.flac" | wc -l)
STAGING_MP3=$(find /Volumes/bad/_integration_staging_20260115 -name "*.mp3" | wc -l)
CANONICAL_FLAC=$(find /Volumes/COMMUNE/M/Library -name "*.flac" -type f | wc -l)
EOF
```


### Task 2: Verify Database State

```bash
# Query active database
sqlite3 /Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-09/music.db <<'SQL'
SELECT 'Total files in DB' as metric, COUNT(*) as count FROM files
UNION ALL
SELECT 'By zone', COUNT(*) FROM files WHERE zone = 'accepted'
UNION ALL
SELECT 'By zone', COUNT(*) FROM files WHERE zone = 'quarantine'
UNION ALL
SELECT 'Volumes tracked', COUNT(DISTINCT volume) FROM files;
SQL
```


### Task 3: Verify Archives

```bash
# Find all archive copies
echo "=== ARCHIVE LOCATIONS ===" && \
find /Volumes -name "_ARCHIVE_STATE_20260109*" -type d 2>/dev/null

# Verify checksums match
echo "" && \
echo "=== ARCHIVE INTEGRITY ===" && \
find /Volumes -name "music.db" -path "*ARCHIVE_STATE*" 2>/dev/null | \
while read db; do
  echo "File: $db"
  sha256sum "$db"
done
```


### Task 4: Check Disk Space

```bash
# Current allocation
df -h | grep -E "COMMUNE|bad|Vault"
```


***

## PART B: OPERATIONAL PROCEDURES

### Procedure 1: Decide What to Promote

**Decision Tree**:

```
IF staging contains ONLY FLAC files:
  → Promote all to /Volumes/COMMUNE/M/Library/
  
ELSE IF staging contains mixed formats (FLAC + MP3 + AAC):
  → OPTION A: Promote FLAC only
  → OPTION B: Archive non-FLAC separately
  → OPTION C: Verify source of non-FLAC and decide per-file

ELSE IF staging contains unknown/corrupt files:
  → Isolate questionable files
  → Scan with tools/anomaly_detection/ for issues
  → Generate report for operator review
```

**Recommended Command**:

```bash
# Separate by format
mkdir -p /Volumes/bad/_STAGING_BY_FORMAT/{FLAC,MP3,AAC,WAV,OTHER}

python3 - <<'PYTHON'
from pathlib import Path
import os

staging_dir = Path("/Volumes/bad/_integration_staging_20260115")
format_bins = {}

for file in staging_dir.rglob("*"):
    if file.is_file():
        ext = file.suffix.lstrip('.').lower() or 'NO_EXT'
        format_bins.setdefault(ext, []).append(str(file))

for fmt, files in sorted(format_bins.items()):
    print(f"{fmt.upper()}: {len(files)} files")
    target_dir = f"/Volumes/bad/_STAGING_BY_FORMAT/{fmt.upper()}"
    os.makedirs(target_dir, exist_ok=True)
    for f in files[:5]:  # Show sample
        print(f"  {Path(f).name}")
PYTHON
```


### Procedure 2: Promote FLAC Files

**Prerequisites**:

- Verify no corruption: `ffprobe` test on sample files
- Verify format separation: FLAC isolated from MP3/AAC
- Verify metadata: Check for encoding issues (Arabic characters, special characters)
- Generate decision plan (read-only)

**Command Sequence**:

```bash
# 1. Test first 10 files for playability
python3 - <<'PYTHON'
from pathlib import Path
import subprocess

staging = Path("/Volumes/bad/_integration_staging_20260115")
flac_files = list(staging.glob("*.flac"))[:10]

errors = []
for flac_file in flac_files:
    result = subprocess.run(
        ["ffprobe", str(flac_file), "-show_format", "-show_streams"],
        capture_output=True
    )
    if result.returncode != 0:
        errors.append(str(flac_file))

if errors:
    print(f"❌ {len(errors)} files have issues")
    for e in errors:
        print(f"  {e}")
else:
    print("✅ Sample test passed")
PYTHON

# 2. Generate promotion plan
python3 tools/decide/recommend.py \
  --db "/Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-09/music.db" \
  --source /Volumes/bad/_integration_staging_20260115 \
  --output /tmp/promotion_plan.json \
  --dry-run

# 3. Review plan
cat /tmp/promotion_plan.json | jq '.summary'

# 4. Apply (promote to canonical)
python3 tools/review/promote_by_tags.py \
  --source /Volumes/bad/_integration_staging_20260115 \
  --target /Volumes/COMMUNE/M/Library \
  --verify \
  --log /Volumes/COMMUNE/M/03_reports/promotion_20260115.log
```


### Procedure 3: Archive Non-FLAC Files

**Options**:

```bash
# Option A: Archive separately (preserve for later decision)
mkdir -p /Volumes/bad/_STAGING_ARCHIVE/non_flac_20260115
find /Volumes/bad/_integration_staging_20260115 -NOT -name "*.flac" \
  -exec mv {} /Volumes/bad/_STAGING_ARCHIVE/non_flac_20260115/ \;

# Option B: Verify they're duplicates before deleting
python3 - <<'PYTHON'
import sqlite3
from pathlib import Path
import hashlib

db_path = "/Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-09/music.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

non_flac_dir = Path("/Volumes/bad/_integration_staging_20260115")
duplicates = 0

for file in non_flac_dir.glob("*"):
    if file.suffix.lower() != '.flac':
        with open(file, 'rb') as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()
        
        cursor.execute("SELECT COUNT(*) FROM files WHERE checksum_sha256 = ?", (file_hash,))
        if cursor.fetchone()[0] > 0:
            duplicates += 1
            print(f"DUP: {file.name}")

print(f"\nTotal non-FLAC: {len(list(non_flac_dir.glob('*')))}")
print(f"Duplicates of library: {duplicates}")
conn.close()
PYTHON
```


***

## PART C: CRITICAL PATHS

```
Active Database:        /Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-09/music.db
Staging Directory:      /Volumes/bad/_integration_staging_20260115/
Canonical Library:      /Volumes/COMMUNE/M/Library/
Operation Logs:         /Volumes/COMMUNE/M/03_reports/
Archive (Master):       /Volumes/COMMUNE/M/_ARCHIVE_STATE_20260109_011532/
Quarantine (COMMUNE):   /Volumes/bad/_commune_quarantine_2026-01-14_FINAL/
Quarantine (Vault):     /Volumes/bad/_vault_quarantine/
```


***

## PART D: DECISION MATRIX FOR AI AGENT

### What's Safe to Do?

```
✅ SAFE OPERATIONS (Reversible):
  • Scan staging files for corruption
  • Generate decision plans (--dry-run)
  • Verify checksums
  • Separate files by format/metadata
  • Archive non-FLAC files
  • Check database consistency

⚠️  CAREFUL OPERATIONS (Requires approval):
  • Move files to canonical library
  • Delete from quarantine zones
  • Modify database records
  • Delete archived copies

❌ NEVER DO:
  • Delete /ARCHIVE_STATE_* without verification
  • Delete /03_reports/ (audit evidence)
  • Delete /Quarantine/ without immutable backup
  • Modify database directly (use tools instead)
```


### Common Questions → Answers

**Q: Should I promote all files or verify first?**

```bash
→ Verify first. Always run anomaly detection on sample before bulk promotion.
Command: python3 tools/anomaly_detection/find_duration_anomalies.py [sample]
```

**Q: What if files already exist in the canonical library?**

```bash
→ The deduplication tools will handle via checksum matching.
Check: sqlite3 music.db "SELECT COUNT(*) FROM files WHERE checksum_sha256 = '...'"
```

**Q: Should I archive or delete the staging directory after promotion?**

```bash
→ Keep for 30 days, then delete after verification.
Safety: Keep /03_reports/promotion_*.log as proof.
```

**Q: What about the MP3/AAC/WAV files?**

```bash
→ Operator decision. Options:
  1. Archive separately (safest)
  2. Verify duplicates first, then delete
  3. Leave in staging for later review
```


***

## PART E: VERIFICATION CHECKLIST (Before \& After)

### Before Promotion

- [ ] Recount staging files (store in audit log)
- [ ] Verify file formats (FLAC vs mixed)
- [ ] Test sample files for corruption (`ffprobe`)
- [ ] Check for metadata encoding issues (especially non-Latin characters)
- [ ] Query database for existing checksums
- [ ] Generate promotion plan (--dry-run)
- [ ] Verify disk space available on COMMUNE


### During Promotion

- [ ] Monitor promotion progress
- [ ] Log all operations in `/03_reports/`
- [ ] Verify checksums post-transfer
- [ ] Update database with new files


### After Promotion

- [ ] Recount canonical library (compare before/after)
- [ ] Verify database reflects new count
- [ ] Audit promotion log for errors
- [ ] Archive staging directory (or delete)
- [ ] Generate final audit report

***

## PART F: EMERGENCY PROCEDURES

### If Promotion Fails Partway

```bash
# 1. Check resume state
ls -lh /tmp/*resume*.json

# 2. View last error
tail -100 /Volumes/COMMUNE/M/03_reports/promotion_*.log

# 3. Determine if safe to retry
python3 tools/decide/apply.py \
  --resume [resume_file.json] \
  --dry-run

# 4. Retry or rollback
# Retry: Re-run exact command
# Rollback: Delete promoted files from COMMUNE, restore from quarantine
```


### If Database Gets Corrupted

```bash
# Restore from master archive
cp /Volumes/COMMUNE/M/_ARCHIVE_STATE_20260109_011532/dedupe_db/music.db \
   /Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-09/music.db.backup

# Then restart operations from checkpoint
```


***

## PART G: FOR AI AGENT — ESSENTIAL RULES

### Rule 1: Always Recount First

Never trust handover numbers. Always verify:

```bash
find [DIR] -type f | wc -l  # Total count
find [DIR] -name "*.flac" | wc -l  # FLAC count
du -sh [DIR]  # Total size
```


### Rule 2: Preserve Immutable Archives

Never delete:

- `/Volumes/COMMUNE/M/_ARCHIVE_STATE_20260109_011532/`
- `/Volumes/COMMUNE/M/03_reports/`
- Any `.resume.json` file (state recovery)


### Rule 3: Log Everything

Every operation must have an immutable record:

```bash
cat >> /Volumes/COMMUNE/M/03_reports/OPERATIONS_LOG.txt <<'LOG'
[$(date)] ACTION: [description]
Command: [exact command run]
Result: [stdout/stderr]
Checksum: [verification hash if applicable]
LOG
```


### Rule 4: Reversibility First

Before any destructive operation:

```bash
# Always have a backup plan
# Always run --dry-run first
# Always verify the operation can be undone
```


***

## STATUS

✅ **System is operational and ready for next phase**

**Next Steps**:

1. Verify staging files (recount, format check)
2. Decide promotion strategy (FLAC-only or mixed)
3. Execute promotion to canonical library
4. Archive/delete staging directory
5. Update database and verify integrity

**Estimated Duration**: 30-45 minutes
**Risk Level**: Low (all operations reversible)
**Operator Approval**: Required before promotion

***

**Handover Document — AI Agent Edition**
*This handover intentionally omits specific counts to ensure the AI agent verifies all numbers independently.*

