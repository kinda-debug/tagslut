# Dedupe Complete Guide (V2)

This is the authoritative guide for the Dedupe Library Management system.

## 1. Introduction
Dedupe is a recovery-first FLAC deduplication and integrity management system. It ensures that your music library is canonical, bit-perfect, and free of redundant copies across multiple volumes.

## 2. Configuration
The system is now driven by environment variables. Configure these in a `.env` file in the project root.

### Environment Variables
- `DEDUPE_DB`: Path to the SQLite database (e.g., `~/dedupe_db/EPOCH_20260119/music.db`).
- `VOLUME_LIBRARY`: Primary library root.
- `VOLUME_QUARANTINE`: Root for moved duplicates.
- `DEDUPE_REPORTS`: Directory for logs and plans.
- `DEDUPE_ALLOW_DROP`: Set to `1` to enable actual deletions (advanced).

## 3. Unified CLI
Instead of dozens of standalone scripts, use the unified `dedupe` command:

```bash
# Run via module
python3 -m dedupe COMMAND [ARGS]
```

### Commands
- `scan`: Index files and verify integrity.
- `recommend`: Identify duplicates and suggest actions.
- `apply`: Execute the deduplication plan.

## 4. The Workflow

### Step 1: Scan
Scan your library or recovered files to index them.
```bash
python3 -m dedupe scan /Volumes/Untitled/Recovered_FLACs --check-integrity --check-hash
```

### Step 2: Recommend
Generate a plan to handle duplicates.
```bash
python3 -m dedupe recommend --priority accepted --priority suspect --output artifacts/plan.json
```

### Step 3: Review
Inspect the generated `plan.json` in your reports directory.

### Step 4: Apply
Apply the plan (moves files to quarantine by default).
```bash
python3 -m dedupe apply artifacts/plan.json --confirm
```

## 5. Maintenance
- **Promotion**: Use `tools/review/promote_by_tags.py` to move new unique files into the canonical library.
- **Auditing**: Check the `files` and `file_quarantine` tables in the database for a full audit trail.
