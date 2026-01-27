# Dedupe Library Management: Complete Operator Guide (V2)

This is the authoritative documentation for the Dedupe system—a high-performance, **COPY-ONLY**, evidence-preserving toolkit for managing large FLAC libraries.

### 🛑 CRITICAL SAFETY RULE: NO DELETION
**ABSOLUTELY NO CODE in this repository is allowed to remove any file.**
Every tool follows a strict **"Copy then Validate"** pattern. Your original source files remain untouched. Any deduplication or organization results in new copies in the designated work zones, leaving you in full control of when and how to manually clear space.

---

## 🏁 The Definitive Workflow (5 Stages)

Follow these steps in order to safely audit and deduplicate your entire library.

### Stage 0: Environment Setup
Before running any tools, ensure your environment is configured.

1.  **Mount Volumes**: Ensure all relevant disks (`COMMUNE`, `Untitled`, etc.) are mounted.
2.  **Initialize Directory Structure**:
    Create a dedicated "Work Zone" on your volume to handle the results of the scan.
    ```bash
    # Run this on your primary volume (e.g., /Volumes/COMMUNE/M/)
    mkdir -p _work/staging _work/quarantine _work/suspect
    mkdir -p Music_Library
    ```
3.  **Configure `.env`**:
    Set `VOLUME_QUARANTINE` to your newly created `_work/quarantine` folder.
4.  **Initialize Database Directory**:
    Create a new epoch directory for your database to maintain an audit trail.
    ```bash
    mkdir -p /Users/georgeskhawam/Projects/dedupe_db/EPOCH_$(date +%Y-%m-%d)
    export DB_PATH="/Users/georgeskhawam/Projects/dedupe_db/EPOCH_$(date +%Y-%m-%d)/music.db"
    ```

---

## Stage 1: SCAN
**Goal:** Index all FLAC files and auto-assign status based on quality and uniqueness.

The scanner automatically determines the status (**zone**) for each file based on the scan results:
*   **`accepted`**: All unique files that pass the integrity check (`flac -t`).
*   **`suspect`**: Files that are identified as redundant copies or are corrupt/truncated.

```bash
# Scan any path (Zones are auto-assigned)
python tools/integrity/scan.py /Volumes/SAD/MU \
  --library MU \
  --db "$DB_PATH" \
  --library MU \
  --check-integrity \
  --check-hash \
  --create-db \
  --progress \
  --verbose
```

### Verify Scan Completeness
Run this SQL to ensure all files are hashed and checked.
```bash
sqlite3 "$DB_PATH" "
SELECT
  'Total files' as metric, COUNT(*) as value FROM files
UNION ALL
SELECT 'With SHA256', COUNT(*) FROM files WHERE sha256 IS NOT NULL
UNION ALL
SELECT 'Corrupt files', COUNT(*) FROM files WHERE flac_ok = 0;
"
```

---

## Stage 2: PLAN
**Goal:** Generate deduplication decisions based on zone priority.

```bash
python tools/review/plan_removals.py \
  --db "$DB_PATH" \
  --output removal_plan.csv
```

---

## Stage 3: REVIEW
**Goal:** Human approval before any files are moved.

### Summary Statistics
```bash
# Count by action (KEEP vs DROP)
cut -d',' -f3 removal_plan.csv | sort | uniq -c

# Sample TIER1 (safe) removals
grep "TIER1,DROP" removal_plan.csv | head -20
```

---

## Stage 4: QUARANTINE
**Goal:** Copy duplicates to quarantine folder for safe keeping.

### Dry Run First
```bash
python tools/review/apply_removals.py \
  --db "$DB_PATH" \
  --plan removal_plan.csv \
  --quarantine-root /Volumes/SAD/QU \
  --dry-run
```

### Execute Quarantine (COPY ONLY)
This command will only perform copies. Your originals will not be touched.
```bash
python tools/review/apply_removals.py \
  --db "$DB_PATH" \
  --plan removal_plan.csv \
  --quarantine-root /Volumes/SAD/QU \
  --execute
```

### Stage 4.5: Isolate Corrupt Files (COPY ONLY)
**Goal:** Copy files that failed integrity checks to a separate folder.

```bash
# Copy corrupt files to the suspect folder (preserving structure)
python tools/review/isolate_suspects.py \
  --db "$DB_PATH" \
  --dest /Volumes/SAD/SU \
  --execute
```

---

## Stage 5: DELETE (DISABLED)
**Goal:** NO DELETION IS PERMITTED BY CODE.

All automatic retention logic has been removed. You must manually review and delete files if you wish to reclaim disk space.

---

### Stage 6: PROMOTE UNIQUE FILES (Optional)
**Goal:** Organize unique files into your primary music directory (COPY ONLY).

The promotion tool organizes your files into Artist/Album/Track structure. It will **not** move the source files; it will create new, organized copies at the destination.

```bash
# 1. Dry Run (Simulates the organization by tags)
python tools/review/promote_by_tags.py \
  --source-root '/Volumes/SAD/Music Hi-Res'\
  --dest-root /Volumes/SAD/M 

# 2. Execute (Organizes and creates new copies)
python tools/review/promote_by_tags.py \
  --source-root /Users/georgeskhawam/Music/INCOMING \
  --dest-root /Volumes/SAD/MU \
  --execute
```

### Stage 7: Final Audit
Run a final incremental scan of your main library to ensure everything is perfectly indexed and integrity-checked.
```bash
python tools/integrity/scan.py /Volumes/COMMUNE/M/Library_CANONICAL \
  --db "$DB_PATH" \
  --library COMMUNE \
  --check-integrity \
  --progress \
  --verbose
```

---

## 🚨 Critical Rules
1. **NO DELETION** — No code in this repository will remove your source files.
2. **ALWAYS scan with `--check-hash`** — without SHA256, deduplication cannot work.
3. **NEVER skip the review stage** — always verify the plan before copying.
4. **One database per epoch** — don't reuse databases across major changes.

---

## 🛠️ Troubleshooting
*   **"Missing SHA256"**: Re-scan with `--check-hash --recheck`.
*   **"Database is locked"**: Close other terminals using the same DB.
*   **"No module named 'dedupe'"**: Run `pip install -e .` in your venv.

---

## 1. Core Concepts

### 🛡️ Recovery-First Philosophy
Every action in Dedupe is non-destructive by default. Instead of deleting files, the system **quarantines** them to a safe location while preserving their original folder structure. This ensures you can restore any deduplication decision instantly.

### ⚡ Tiered Hashing
To handle libraries with 100k+ files efficiently, Dedupe uses a two-tier hashing system:
*   **Tier 1 (Pre-hash)**: A fast checksum of the file size + the first 4MB. Used for rapid triage and initial duplicate grouping.
*   **Tier 2 (Full-hash)**: A complete SHA-256 checksum of the entire file. Used for absolute, bit-exact verification before any move or deletion.

### ⚖️ Keeper Selection Logic
When multiple identical files are found, the system picks the "Keeper" using a deterministic 4-stage tie-breaker:
1.  **Zone Priority**: Prefer `accepted` (Library) > `staging` > `suspect` > `quarantine`.
2.  **Audio Quality**: Prefer higher sample rates and bit depths.
3.  **Integrity Status**: Prefer files that have passed a full `flac -t` check.
4.  **Path Hygiene**: Prefer shorter, cleaner paths (e.g., in `Library_CANONICAL`).

---

## 2. Configuration & Environment

The system is configured via a `.env` file in the project root.

| Variable | Description | Example |
| :--- | :--- | :--- |
| `DEDUPE_DB` | Path to the SQLite database. | `~/dedupe_db/EPOCH_20260119/music.db` |
| `VOLUME_LIBRARY` | Your canonical library root. | `/Volumes/COMMUNE/M/Library` |
| `VOLUME_QUARANTINE`| Root for moved redundant files. | `/Volumes/COMMUNE/M/_quarantine` |
| `SCAN_WORKERS` | Number of parallel threads for hashing. | `8` |
| `SCAN_CHECK_HASH` | Enable full SHA256 hashing by default. | `true` |

---

## 3. Operations Workflow

### Step 1: Scanning (`scan`)
Indexes your files and extracts technical metadata.
```bash
# Basic scan (Fast: T1 hashing only)
python3 -m dedupe scan /Volumes/Untitled/Recovered_FLACs

# Full Integrity Scan (Slow: bit-exact hash + flac -t check)
python3 -m dedupe scan /Volumes/Untitled/Recovered_FLACs --check-integrity --check-hash
```

### Step 2: Recommendations (`recommend`)
Identifies duplicate groups and generates a JSON removal plan.
```bash
# Generate plan favoring 'accepted' zone
python3 -m dedupe recommend --priority accepted --output artifacts/removal_plan.json
```

### Step 3: Execution (`apply`)
Executes the moves based on the reviewed plan.
```bash
# Dry run (Always do this first!)
python3 -m dedupe apply artifacts/removal_plan.json

# Execute (Moves files to quarantine)
python3 -m dedupe apply artifacts/removal_plan.json --confirm
```

---

## 4. Advanced Maintenance

### Incremental Scanning
By default, the scanner is incremental. It will skip files that haven't changed (based on `mtime` and `size`) unless you use `--force-all`.

### Database Auditing
You can query the SQLite database directly for custom reports:
*   `files`: Primary metadata and hash storage.
*   `scan_sessions`: History of every scan run.
*   `file_scan_runs`: Detailed per-file outcome of the last scan.

### Promotion
Use `python3 tools/review/promote_by_tags.py` to identify unique files in `staging` or `suspect` zones that should be "promoted" to your main library.
