# Operator Visual Guide: Dedupe Workflow State Machine

**For operators who need to understand WHERE they are in the workflow and WHAT DECISION comes next.**

---

## 🎯 The Five Workflow States

```
┌─────────────────────────────────────────────────────────────────┐
│                     DEDUPE WORKFLOW STATES                      │
└─────────────────────────────────────────────────────────────────┘

    ┌──────────┐
    │  INIT    │  ← You are here first
    │ (Read DB)│    Setup database, load config
    └────┬─────┘
         │
         v
    ┌──────────┐
    │  SCAN    │  ← Data Collection Phase
    │(Read FS) │    Crawl volumes, compute checksums
    └────┬─────┘    Read-only: No files deleted yet
         │
         v
    ┌──────────┐
    │  AUDIT   │  ← Analysis Phase
    │(Analyze) │    Find duplicates, compute risk scores
    └────┬─────┘    Still read-only
         │
         v
    ┌──────────┐
    │  DECIDE  │  ← OPERATOR DECISION GATE #1
    │(Approve) │    ★ Operator chooses KEEP or QUARANTINE or DELETE
    └────┬─────┘    ★ Review "plan.json" with automated choices
         │
         v
    ┌──────────┐
    │  APPLY   │  ← Execution Phase (Destructive!)
    │(Execute) │    ★ Operator runs --dry-run FIRST
    └────┬─────┘    ★ Then runs --confirm to ACTUALLY delete
         │          Quarantine folder preserved for recovery
         v
    ┌──────────┐
    │  DONE    │  ← Complete
    │(Archive) │    Backup metadata, create immutable manifest
    └──────────┘
```

---

## 📋 OPERATOR CHECKLIST: What to Do at Each Step

### STEP 1: INIT (One-time setup)

**Goal**: Setup database

```bash
☐ Run:  make install
☐ Edit: config.toml with paths (db_path, library paths)
☐ Run:  dedupe init --db-path ./artifacts/dedupe.db
☐ Verify: ls -la ./artifacts/dedupe.db (file exists)
```

**Check**: Database initialized? → Y: Go to STEP 2 | N: Fix error, retry

---

### STEP 2: SCAN (Data collection - 30 min to 2 hours)

**Goal**: Read all volumes, find all FLAC files, compute checksums

```bash
☐ Check mounted volumes: df -h
☐ Run scan:
   python3 tools/integrity/scan.py /path/to/library \
     --db ./artifacts/dedupe.db \
     --incremental \
     --progress \
     --check-integrity
☐ Wait for completion (shows progress: "X files/sec")
☐ Check output: cat scan_errors.log (should be 0-5 errors)
```

**Check**: Scan completed without timeout? → Y: Go to STEP 3 | N: Resume with --incremental flag

---

### STEP 3: AUDIT (Analysis - 5-10 min)

**Goal**: Identify duplicates and compute risk scores

```bash
☐ Run recommendation:
   python3 tools/decide/recommend.py \
     --db ./artifacts/dedupe.db \
     --output plan.json
☐ Check results:
   cat plan.json | jq '.summary'  (How many duplicates?)
☐ If > 10,000 duplicates: Review by volume
   jq '.decisions[] | select(.path | contains("Volume1"))' plan.json > volume1.json
```

**Check**: Found duplicates? → Y: Go to STEP 4 | N: All files unique, done!

---

### STEP 4: DECIDE ⭐ OPERATOR DECISION GATE #1

**Goal**: Review the automated decisions in `plan.json`

The `recommend.py` tool has already analyzed the duplicates and made recommendations (KEEP vs DROP) based on your configured priorities.

**Review the Plan**:
```bash
☐ Check summary:
   cat plan.json | jq '.summary'
☐ List proposed deletions:
   cat plan.json | jq '.plan[].decisions[] | select(.action=="DROP") | .path'
```

**Critical Questions**:
- ❓ Are you SURE about deleting files? (Can't undo permanently)
- ❓ Do you have backups of critical files?
- ❓ Is there a quarantine folder for 30-day recovery window?

**Check**: Decisions reviewed and saved? → Y: Go to STEP 5 | N: Review again

---

### STEP 5: DRY-RUN ⭐ OPERATOR SAFETY CHECK

**Goal**: See what WOULD happen WITHOUT actually doing it

```bash
☐ Run:
   python3 tools/decide/apply.py \
     --dry-run \
     --input decisions.json \
     --verbose
☐ Review output:
   - Files to DELETE
   - Space that would be freed
   - Expected artifacts created
☐ Ask yourself: "Are these deletions correct?"
☐ If NO: Go back to STEP 4, edit decisions.json
☐ If YES: Proceed to STEP 6
```

**Example Output**:
```
[DRY RUN] Would delete: /path/file1.flac (42 MB)
[DRY RUN] Would delete: /path/file2.flac (41 MB)
[DRY RUN] Space freed: 83 MB
[DRY RUN] Status: OK, safe to proceed
```

**Check**: Dry-run output looks correct? → Y: Go to STEP 6 | N: Abort, fix decisions

---

### STEP 6: APPLY ⚠️ ACTUAL DELETIONS (Point of No Return!)

**Goal**: ACTUALLY delete files (with quarantine backup)

```bash
☐ ONE MORE TIME: Review decisions.json
☐ Run:
   python3 tools/decide/apply.py \
     --input decisions.json \
     --confirm
☐ WAIT for completion (shows: "Deleted X files, freed Y GB")
☐ Verify:
   - Check quarantine folder created
   - Verify space freed: df -h
   - Check database updated
```

**Recovery Window**:
- 30 days: Files in quarantine can be restored
- After 30 days: Files permanently deleted

**Check**: Apply completed successfully? → Y: Go to STEP 7 | N: Contact support, don't retry

---

### STEP 7: ARCHIVE (Audit Trail)

**Goal**: Create immutable record of what happened

```bash
☐ Run:
   python3 tools/archive/snapshot.py \
     --db ./artifacts/dedupe.db \
     --decisions decisions.json \
     --output manifest.json
☐ Verify manifest:
   cat manifest.json | jq '.summary'  (Total files, freed space, etc.)
☐ Lock down evidence:
   chflags -R uchg ./artifacts/ARCHIVE_STATE_*
☐ Backup to external drive
```

**Check**: Archive created and locked? → Y: DONE! | N: Fix and retry

---

## 🚨 DECISION TREE: "What should I do with this duplicate group?"

```
          START HERE
              ↓
    Did ANY file fail integrity?
          ↙        ↘
        YES         NO
         ↓           ↓
     KEEP best   Go to next
     DELETE rest  question
         ↓          ↓
    Did ANY file come from Zone:Accepted?
          ↙        ↘
        YES         NO
         ↓           ↓
    KEEP Accepted  Go to next
    DELETE others  question
         ↓          ↓
    Are file sizes VERY different (> 15%)?
          ↙        ↘
        YES         NO
         ↓           ↓
     QUARANTINE  Go to next
     (suspicious)  question
         ↓          ↓
    Use your judgment:
    KEEP most recent or best metadata?
          ↓
      DECIDE
```

---

## ❌ ERROR RECOVERY: "What if something goes wrong?"

### "Scan timed out after 24 hours"
```bash
→ Don't panic! Run SAME COMMAND again with --incremental
→ It will skip already-scanned files and resume
→ Each run adds new files/checksums to database
```

### "I approved decisions I shouldn't have"
```bash
→ Did you run --dry-run? If YES, edit decisions.json, retry dry-run
→ Did you run --confirm? 
   - If < 30 minutes ago: Files still in quarantine, restore manually
   - If > 30 minutes: Contact support
```

### "Files deleted but still showing in database"
```bash
→ Run: python3 tools/db/cleanup.py
→ This removes deleted paths from database
→ Verify: dedupe audit report (should show fewer files)
```

---

## 🎯 SUCCESS CRITERIA

You're done when:

- ✅ INIT: Database created
- ✅ SCAN: All volumes scanned, no timeout errors
- ✅ AUDIT: Duplicates identified and ranked
- ✅ DECIDE: You've made conscious choices for ALL duplicates
- ✅ DRY-RUN: Output reviewed and approved
- ✅ APPLY: Files deleted (or quarantined)
- ✅ ARCHIVE: Manifest created and locked

Your library is now deduped! 🎉

---

## 📞 Need Help?

- "Where am I in the workflow?" → Check the STATE MACHINE above
- "What's my next action?" → Check the CHECKLIST for your current step
- "Which files should I keep/delete?" → Use the DECISION TREE
- "Something failed!" → Check ERROR RECOVERY
