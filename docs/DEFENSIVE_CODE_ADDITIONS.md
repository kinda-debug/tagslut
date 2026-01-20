# DEFENSIVE_CODE_ADDITIONS.md

This document outlines five critical code improvements to make the `dedupe` tool safer and prevent accidental data loss.

---

### 1. `FileOperationValidator`

**Goal:** Verify every file copy with checksums to ensure integrity.

**Location:** `tools/review/apply_removals.py`

**Logic:**
1.  After a file is copied to quarantine, calculate the checksum of the **newly created file**.
2.  Compare this checksum with the checksum of the **original file** stored in the database.
3.  If the checksums do not match, log a critical error, move the corrupted quarantined file to a `failed` directory, and **do not** mark the original file as quarantined in the database.

**Pseudocode:**

```python
def quarantine_file(file_path, quarantine_root, db_connection):
    # ... existing copy logic ...
    new_path = copy_file(file_path, quarantine_root)

    original_checksum = db_connection.get_checksum(file_path)
    new_checksum = calculate_checksum(new_path)

    if original_checksum != new_checksum:
        log.critical(f"Checksum mismatch for {file_path}! Quarantined file is corrupt.")
        move_to_failed_dir(new_path)
        return False
    else:
        db_connection.mark_as_quarantined(file_path)
        return True
```

---


### 2. `OperationConfirmation`

**Goal:** Require explicit user confirmation for destructive operations.

**Location:** `tools/review/apply_removals.py` (and any future tools that delete files)

**Logic:**
1.  Before executing a destructive operation (like `_execute_removals`), check for a `--confirm` flag.
2.  If the flag is not present, print a warning and exit.
3.  If the flag is present, prompt the user to type a specific confirmation phrase.

**Example Implementation:**

```python
def _execute_removals(...):
    if not args.confirm:
        print("This is a destructive operation. Please use --confirm to proceed.")
        return

    confirmation = input("To confirm, type 'I accept the risks and have verified my backups.': ")
    if confirmation != "I accept the risks and have verified my backups.":
        print("Confirmation failed. Aborting.")
        return

    # ... proceed with removals ...
```

---


### 3. `PreFlightValidator`

**Goal:** Perform system state checks before any operations begin.

**Location:** `dedupe/utils/cli_helper.py` or a new `validators.py` module.

**Logic:**
1.  Create a `PreFlightValidator` class.
2.  Add methods to check for the conditions listed in `SAFETY_CHECKLIST.md`:
    -   `check_env_vars()`
    -   `check_volumes_mounted()`
    -   `check_disk_space()`
    -   `check_db_integrity()`
3.  In the `main` function of each tool, instantiate the validator and run the checks. If any check fails, exit with a clear error message.

**Example:**

```python
# In main function of a tool
preflight = PreFlightValidator(db_path=args.db, quarantine_root=args.quarantine_root)
if not preflight.run_all():
    log.critical("Pre-flight checks failed. Aborting.")
    sys.exit(1)
```

---


### 4. `OperationLog`

**Goal:** Track the progress of long-running operations to enable resumption.

**Location:** `dedupe/utils/progress_tracker.py`

**Logic:**
1.  For operations like quarantine, create a simple log file (e.g., `quarantine_progress.log`).
2.  Before processing each file, write its path to the log.
3.  If the operation is interrupted, the tool can be restarted with a `--resume` flag.
4.  The tool then reads the log file to see which files have already been processed and skips them.

**Example:**

```python
# In apply_removals.py
processed_files = set()
if args.resume:
    with open("quarantine_progress.log", "r") as f:
        processed_files = {line.strip() for line in f}

# In the processing loop
with open("quarantine_progress.log", "a") as log_file:
    for file_to_quarantine in plan:
        if file_to_quarantine.path in processed_files:
            continue
        
        # ... process file ...
        log_file.write(f"{file_to_quarantine.path}\n")
```

---


### 5. Comprehensive Logging

**Goal:** Track every file operation for auditing and debugging.

**Location:** `dedupe/utils/logging.py`

**Logic:**
1.  Configure the existing logging system to output to a file.
2.  Add specific log messages for every file operation:
    -   `log.info(f"COPY: {src} -> {dest}")`
    -   `log.info(f"DELETE: {path}")`
    -   `log.warning(f"File not found: {path}")`
3.  Ensure that timestamps and log levels are correctly configured.
This will create an audit trail that can be used to reconstruct events if something goes wrong.

```