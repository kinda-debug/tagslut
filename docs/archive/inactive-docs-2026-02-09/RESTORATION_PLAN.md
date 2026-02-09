# Library Restoration & Recovery Guide

This document outlines the procedures for restoring files from quarantine, recovering missing library items, and resolving path conflicts.

---

## 1. Restoring from Quarantine

When the system quarantines a file, it preserves the original relative folder structure under the quarantine root.

### Manual Restoration
To restore a file manually, move it from its location in the quarantine folder back to its original path.
*   **Quarantine Root**: Defined by `VOLUME_QUARANTINE` in `.env`.
*   **Sub-folders**: Named by scan session (e.g., `DEDUPE_20260120_XXXXXX`).

### Bulk Restoration (Safety First)
If you need to undo a large deduplication action:
1.  Identify the scan session ID from the quarantine folder name.
2.  Use the `legacy/tools/recovery/restore_from_quarantine.py` script (if available) or a standard `shutil.move` loop.

---

## 2. Recovering Missing Library Files

If your database shows files that are missing from your canonical library (e.g., after a drive failure), use the following workflow.

### Step 1: Readiness Audit
Compare the missing list against recovered/extra volumes.
```bash
# Analyze recovery status
python3 legacy/tools/recovery/audit_readiness.py --missing-manifest artifacts/missing_files.txt
```

### Step 2: Step-by-Step Restoration
Use the `restore_library.py` tool to move identified matches back to their canonical locations.

| Mode | Command | Description |
| :--- | :--- | :--- |
| **Dry Run** | `python3 restore_library.py --source-root "/Volumes/Untitled/Recovered_FLACs"` | Simulates the move. |
| **Execute** | `python3 restore_library.py --source-root "/Volumes/Untitled/Recovered_FLACs" --execute` | Performs the copy. |
| **Verify** | `python3 restore_library.py --source-root "/Volumes/Untitled/Recovered_FLACs" --execute --verify` | Re-hashes every file before moving. |

---

## 3. Troubleshooting & Common Issues

### "Missing" RECOVERY_TARGET Files
If the scanner reports thousands of missing files on a recovery drive, ensure the drive is mounted with the correct volume name. The system identifies files by **absolute path** in the database.

### Path Conflicts
If two files have the same path but different hashes, the scanner will update the record with the latest `mtime` and `size`. Use `python3 legacy/tools/analysis/path_conflicts.py` to identify these rare edge cases.

### Integrity Failures
Files that fail the `flac -t` check are marked in the database. You can find them with:
```sql
SELECT path FROM files WHERE flac_ok = 0;
```
Replace these files from your backups or recovered sets as soon as possible.
