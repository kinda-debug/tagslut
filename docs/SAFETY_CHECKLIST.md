# SAFETY_CHECKLIST.md

This checklist **must** be completed before every session to prevent data loss.

## Pre-Flight Checklist

### ☐ 1. Environment Verification

-   [ ] **DB_PATH is set:** `echo $DB_PATH` (Should point to your current database)
-   [ ] **VOLUME_LIBRARY is set:** `echo $VOLUME_LIBRARY` (Should point to your canonical music library)
-   [ ] **VOLUME_QUARANTINE is set:** `echo $VOLUME_QUARANTINE` (Should point to your quarantine directory)

### ☐ 2. Filesystem Verification

-   [ ] **All volumes are mounted:** `df -h` (Check for your music and quarantine volumes)
-   [ ] **Volumes are writable:** `touch $VOLUME_QUARANTINE/test.tmp && rm $VOLUME_QUARANTINE/test.tmp`
-   [ ] **Sufficient disk space:** Check `df -h` to ensure you have space for quarantined files.

### ☐ 3. Database Verification

-   [ ] **Database exists:** `ls -lh $DB_PATH`
-   [ ] **Database has integrity:** (Instructions for `sqlite3` integrity check to be added)
-   [ ] **No other processes are using the database:** `lsof | grep $DB_PATH` (Should be empty)

### ☐ 4. Source File Verification

-   [ ] **Source files exist:** `ls -l $VOLUME_LIBRARY | head -n 5` (Quick check to see files)
-   [ ] **Source files are not being written to:** (Ensure no other tools are modifying the library)

### ☐ 5. Risk Acknowledgment

To proceed, you must acknowledge the risks. Type the following phrase when prompted by the tool (this feature is part of `DEFENSIVE_CODE_ADDITIONS.md`):

> "I accept the risks and have verified my backups."

### ☐ 6. Dry-Run Verification

-   [ ] **Dry-run was completed first:** Have you run the command with `--dry-run`?
-   [ ] **Dry-run output was reviewed:** Did you read the output and confirm it is correct?

**Do not proceed if any of these checks fail.**
