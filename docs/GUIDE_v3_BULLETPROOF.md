# GUIDE_v3_BULLETPROOF.md

This guide provides a bulletproof, step-by-step workflow for using the dedupe tool safely.

## 🚨 CRITICAL: READ THIS FIRST

This system is designed to be **safe by default**, but **you are in control**. Human error is the primary risk. Follow these steps **exactly** to protect your data.

**Golden Rules:**
1.  **ALWAYS** run `--dry-run` before any command that modifies files.
2.  **ALWAYS** verify the output of one stage before proceeding to the next.
3.  **NEVER** skip the 24-hour waiting period before final deletion.
4.  **ALWAYS** use the `SAFETY_CHECKLIST.md` before each session.

## Workflow Stages

The workflow is divided into 5 distinct stages. Do not proceed to the next stage until the current one is fully complete and verified.

---

### Stage 1: Scan (Index & Verify Source Files)

**Goal:** Create a database of your music files and their checksums. This is a **read-only** operation.

**Commands:**

```bash
# 1. Define your database path. Use a new one for each major run.
export DB_PATH=~/dedupe_db/EPOCH_$(date +%Y-%m-%d)/music.db

# 2. Create the parent directory for the database
mkdir -p "$(dirname "$DB_PATH")"

# 3. Run the scan.
#    --create-db: Creates the database if it doesn't exist.
#    --check-hash: Verifies checksums of existing files.
#    --limit: For testing, scan a small subset of files first.
python3 tools/integrity/scan.py /path/to/your/music \
  --db "$DB_PATH" \
  --create-db \
  --check-hash \
  # --limit 100 # Uncomment for testing
```

**Verification:**
-   Check the command output for any errors.
-   Ensure the database file is created at `$DB_PATH`.
-   Query the database to ensure files were added (optional, for advanced users).

---

### Stage 2: Plan (Identify Duplicates)

**Goal:** Generate a removal plan based on the scanned data. This is a **read-only** operation.

**Commands:**

```bash
# 1. Generate the removal plan.
#    --output: The CSV file where the plan will be saved.
python3 tools/review/plan_removals.py \
  --db "$DB_PATH" \
  --output removal_plan.csv
```

**Verification:**
-   Open `removal_plan.csv` in a spreadsheet editor.
-   **CRITICAL:** Review the plan carefully. Do the proposed actions make sense?
-   Are the files marked for removal truly duplicates?
-   If you are unsure, **do not proceed**.

---

### Stage 3: Quarantine (Copy Duplicates to a Safe Location)

**Goal:** Move the files marked for removal into a safe "quarantine" directory. This is a **copy-then-verify** operation. The original files are **not yet deleted**.

**Commands:**

```bash
# 1. Define your quarantine location.
export VOLUME_QUARANTINE="/path/to/your/quarantine/folder"

# 2. Perform a --dry-run first.
#    This will simulate the operation without moving any files.
python3 tools/review/apply_removals.py \
  --db "$DB_PATH" \
  --plan removal_plan.csv \
  --quarantine-root "$VOLUME_QUARANTINE" \
  --dry-run

# 3. CRITICAL: REVIEW THE DRY RUN OUTPUT.
#    Does the output match what you expect?
#    Are the correct files being targeted?

# 4. If the dry run is correct, execute the quarantine.
python3 tools/review/apply_removals.py \
  --db "$DB_PATH" \
  --plan removal_plan.csv \
  --quarantine-root "$VOLUME_QUARANTINE" \
  --execute
```

**Verification:**
-   Check the quarantine directory. Are the files there?
-   Verify the checksums of the quarantined files against the originals (the `DEFENSIVE_CODE_ADDITIONS.md` proposes automating this).
-   Ensure the original files are still in their original location.

---

### Stage 4: Wait (The 24-Hour Rule)

**Goal:** Prevent accidental, hasty deletion.

-   **WAIT AT LEAST 24 HOURS** before proceeding to the final stage.
-   Use this time to spot-check your library. Is anything missing?
-   This is your last chance to easily recover from a mistake. The quarantined files are your backup.

---

### Stage 5: Delete (Manual, Confirmed Deletion)

**Goal:** Delete the original files that have been safely quarantined.

**THIS IS THE ONLY DESTRUCTIVE STEP.**

**Prerequisites:**
-   You have completed stages 1-3.
-   You have waited at least 24 hours.
-   You have verified the quarantined files are correct.
-   You have backed up `removal_plan.csv` and the database file.

**This functionality is intentionally not yet implemented in the core tool to prevent accidents. Deletion should be a manual, deliberate act until the defensive code additions are in place.**

**Manual Deletion (Example):**

If you are **absolutely certain**, you can manually delete the files listed in your `removal_plan.csv`. This is a high-risk operation.

**It is strongly recommended to implement the defensive code from `DEFENSIVE_CODE_ADDITIONS.md` before proceeding with any deletions.** The `OperationConfirmation` feature outlined in that document is critical here.

```