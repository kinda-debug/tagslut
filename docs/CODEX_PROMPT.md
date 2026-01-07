# Codex Execution Prompt — Dedupe Integrity Refactor

> **MANDATORY:** Read `docs/CODEX_BACKGROUND.md` first for context.
> This file contains **instructions only**.

---

## Role & Authority

You are a senior systems engineer fixing a broken integrity subsystem.

You have **full authority** to:
- Rewrite, delete, or move code
- Introduce new DB schemas with migrations
- Add new CLI flags
- Rewrite documentation

**Hard constraints:**
- Do not delete user data
- Do not assume prior scan results are trustworthy
- Preserve forensic traceability

---

## Mission

Fix the `dedupe` integrity system so it is:

1. **Type-stable** — No tuples where scalars are expected
2. **Semantically correct** — "never checked" ≠ "valid"
3. **Auditable** — DB answers "when/how/how-many-times checked"
4. **Targetable** — Scan only failed, only unchecked, or explicit paths
5. **Interrupt-safe** — Partial runs don't corrupt state

---

## Deliverables

### A. Fix the Tuple Bug

**File:** `dedupe/core/metadata.py` line 69

**Current (broken):**
```python
integrity_state = classify_flac_integrity(path_obj)  # Returns tuple
flac_ok = (integrity_state == "valid")  # Always False
```

**Fix:** Unpack the tuple:
```python
integrity_state, integrity_detail = classify_flac_integrity(path_obj)
flac_ok = (integrity_state == "valid")
```

Store `integrity_detail` (stderr) somewhere queryable.

---

### B. Fix Semantic Lie

**File:** `dedupe/core/metadata.py` lines 123-125

**Current (broken):**
```python
if not scan_integrity:
    integrity_state = "valid"
    flac_ok = True
```

**Fix:**
```python
if not scan_integrity:
    integrity_state = None  # or "unknown"
    flac_ok = None
```

Update `AudioFile.integrity_state` type hint to allow `None`.

---

### C. Add Integrity History (Preferred) or Columns

**Option 1 (preferred):** New table

```sql
CREATE TABLE IF NOT EXISTS integrity_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    checked_at REAL NOT NULL,
    tool TEXT NOT NULL DEFAULT 'flac',
    tool_version TEXT,
    exit_code INTEGER,
    state TEXT NOT NULL,  -- "valid" / "corrupt" / "recoverable"
    stderr TEXT,
    session_id TEXT
);

CREATE INDEX idx_integrity_checks_file_id ON integrity_checks(file_id);
CREATE INDEX idx_integrity_checks_checked_at ON integrity_checks(checked_at);
```

**Option 2:** Add columns to `files` table:
- `integrity_checked_at REAL`
- `integrity_tool TEXT`
- `integrity_exit_code INTEGER`
- `integrity_stderr TEXT`

Write a migration in `dedupe/db/migrations/` that runs automatically on DB open.

---

### D. Add CLI Targeting Flags

**File:** `tools/integrity/scan.py`

Add these flags:

| Flag | Behavior |
|------|----------|
| `--only-failed` | Scan only files where last `integrity_state != 'valid'` |
| `--only-never-checked` | Scan only files with no integrity check history |
| `--paths-file <path>` | Scan exactly these paths (one per line) |
| `--dry-run` | Print counts and exit without scanning |

Modify `--recheck` behavior:
- If `--recheck` targets > 1000 files without `--only-failed` or `--paths-file`, require `--yes-i-mean-it` or exit with warning.

---

### E. Add Preflight Summary

Before scanning, print:

```
=== Preflight Summary ===
Discovered files: 16521
Known in DB: 14200
To process: 2321
  - New (not in DB): 500
  - Changed (mtime/size): 821
  - Never integrity-checked: 1000
  - Previously failed: 0
  - Forced recheck: 0

Proceed? [y/N]
```

If `--dry-run`, print summary and exit.

---

### F. Make Interrupts Safe

- Process and commit in batches (e.g., 100 files)
- On SIGINT: commit completed batch, mark session as `partial`, exit cleanly
- Never attempt to write a tuple/list to SQLite
- Log: `"Interrupted. Committed N files. Session marked partial."`

---

### G. Tests

Add tests in `tests/test_integrity.py`:

1. `test_classify_flac_integrity_returns_tuple` — Both success and failure return `Tuple[str, str]`
2. `test_no_integrity_check_stores_null` — `scan_integrity=False` → `integrity_state=None`
3. `test_upsert_accepts_integrity_fields` — No crash on DB write
4. `test_only_failed_filter` — `--only-failed` selects correct files
5. `test_only_never_checked_filter` — `--only-never-checked` selects correct files

Use pytest fixtures with temp SQLite DB and mock `subprocess.run`.

---

### H. Documentation

Create or update `docs/INTEGRITY.md`:

1. **Integrity States:** `valid`, `corrupt`, `recoverable`, `unknown`/`NULL`
2. **Scan Modes:** Discovery, metadata, integrity (explicit opt-in)
3. **CLI Reference:** All flags with examples
4. **Querying History:**
   ```sql
   -- Files never checked
   SELECT path FROM files WHERE integrity_state IS NULL;
   
   -- Last 20 failures with timestamps
   SELECT f.path, ic.state, ic.checked_at, ic.stderr
   FROM integrity_checks ic
   JOIN files f ON ic.file_id = f.id
   WHERE ic.state != 'valid'
   ORDER BY ic.checked_at DESC
   LIMIT 20;
   ```

---

## Validation Commands

After implementation, these must work:

```bash
# 1. Migrate DB
python3 -c "from dedupe.storage.schema import init_db; init_db('$DEDUPE_DB')"

# 2. Dry-run counts
python3 tools/integrity/scan.py /path/to/library --db "$DEDUPE_DB" --dry-run

# 3. Scan only failed
python3 tools/integrity/scan.py /path/to/library --db "$DEDUPE_DB" \
    --check-integrity --only-failed

# 4. Scan explicit paths
python3 tools/integrity/scan.py --db "$DEDUPE_DB" \
    --check-integrity --paths-file artifacts/tmp/suspect_paths.txt

# 5. Query last 20 failures
sqlite3 "$DEDUPE_DB" "
SELECT f.path, ic.state, datetime(ic.checked_at, 'unixepoch') as checked
FROM integrity_checks ic
JOIN files f ON ic.file_id = f.id
WHERE ic.state != 'valid'
ORDER BY ic.checked_at DESC
LIMIT 20;
"
```

---

## Anti-Goals

❌ Do not preserve broken behavior for "compatibility"
❌ Do not assume existing `integrity_state = 'valid'` rows are truthful
❌ Do not optimize for speed before correctness
❌ Do not hide uncertainty — model it explicitly

---

## Guiding Principle

> If the system cannot explain why a file is marked corrupt,
> the system is wrong — even if the file is actually corrupt.

---

**Proceed.**
