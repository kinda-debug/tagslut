# Prompt: §7.3 structural cleanup — migration naming, shim audit

**Agent**: Codex
**Section**: ROADMAP §7.3
**Status**: Ready to execute

**COMMIT ALL CHANGES BEFORE EXITING.**

---

## Background

Three structural issues were flagged in a repo audit. Investigation confirms:

- Issue A (0007 migration name collision): cosmetic ambiguity only — the legacy runner
  keys by filename, not version prefix, so both files run safely. Needs a rename + comment
  to prevent future confusion, not a logic fix.
- Issue B (models.py vs models/ package): already resolved. `models.py` is an intentional
  compatibility shim. No action needed.
- Issue C (cli/scan.py and cli/track_hub_cli.py wrappers): already resolved. Same shim
  pattern as Issue B. No action needed.

This prompt covers Issue A only.

---

## Read first

1. `tagslut/storage/migration_runner.py` — confirm it tracks by filename (line ~43-67)
2. `tagslut/storage/migrations/0007_isrc_primary_key.py` — legacy runner migration
3. `tagslut/storage/migrations/0007_v3_isrc_partial_unique.py` — also legacy runner migration
4. `tagslut/storage/v3/migrations/0007_track_identity_phase1_rename.py` — v3 runner, unrelated

---

## Task — rename the ambiguous legacy migration file

The two files `0007_isrc_primary_key.py` and `0007_v3_isrc_partial_unique.py` both live
in `tagslut/storage/migrations/` and both start with `0007_`. The legacy runner processes
them by sorted filename so they run in order, but the shared prefix looks like a versioning
error to any reader of the directory.

The correct fix is to renumber one of them to avoid the shared prefix. The file that was
added *later* and caused the ambiguity should be renumbered.

**Determine which is newer** by checking git log:
```bash
git log --oneline --follow -- tagslut/storage/migrations/0007_isrc_primary_key.py
git log --oneline --follow -- tagslut/storage/migrations/0007_v3_isrc_partial_unique.py
```

**Rename the newer file** by finding the next available prefix in
`tagslut/storage/migrations/`:
```bash
ls tagslut/storage/migrations/ | grep "^[0-9]" | sort | tail -5
```

Pick the next available number (e.g., if the highest is `0012_...`, rename to `0013_...`).

**Steps:**
1. `git mv tagslut/storage/migrations/0007_<newer>.py tagslut/storage/migrations/<next>_<same-suffix>.py`
2. Add a comment at the top of the renamed file:
   ```python
   # Renamed from 0007_<original_name>.py to avoid shared prefix with
   # 0007_<other_name>.py. The legacy migration runner (tagslut/storage/migration_runner.py)
   # tracks by filename — both files were applied correctly, but the shared prefix
   # was misleading. This file retains its migrations_applied entry under the OLD filename
   # for idempotency: the runner checks the original name before applying.
   ```
3. Add the old filename as a known alias in the file, so that if the runner checks
   `migrations_applied` by the old name, it can still detect "already applied":
   ```python
   LEGACY_FILENAME_ALIAS = "0007_<original_name>.py"
   ```
   Then check whether `migration_runner.py` has a mechanism to handle filename aliases.
   If it does, wire it. If it does not, simply leave the constant as documentation and
   add a comment that manual verification is needed on DBs where the old name was applied.

**Do not** modify the v3 runner or any v3 migration files — they are in a separate directory
and use a separate tracking table (`schema_migrations`) with version integers, not filenames.

---

## Verification

```bash
cd /Users/georgeskhawam/Projects/tagslut
export PATH="$HOME/.local/bin:$PATH"

# 1. No two files in the legacy migrations dir share the same numeric prefix
python3 -c "
from pathlib import Path
files = sorted(Path('tagslut/storage/migrations').glob('[0-9]*.py'))
prefixes = [f.name.split('_')[0] for f in files if f.name != '__init__.py']
dups = [p for p in prefixes if prefixes.count(p) > 1]
assert not dups, f'Duplicate prefixes found: {dups}'
print('No duplicate prefixes. Files:', [f.name for f in files])
"

# 2. Compile check
poetry run python -m compileall tagslut/storage/migrations -q

# 3. Migration runner still discovers both files (now under different names)
python3 -c "
from pathlib import Path
files = sorted(Path('tagslut/storage/migrations').glob('[0-9]*.py'))
names = [f.name for f in files]
print('Migration files in order:')
for n in names:
    print(' ', n)
"
```

---

## What NOT to change

- `tagslut/storage/v3/migrations/` — entirely separate runner and tracking table
- `tagslut/metadata/models.py` — intentional shim, leave as-is
- `tagslut/cli/scan.py` and `tagslut/cli/track_hub_cli.py` — intentional shims, leave as-is
- Any test that imports from the renamed file by its old name (update import path if needed)

---

## Done when

Verification step 1 passes (no duplicate numeric prefixes).
`poetry run python -m compileall tagslut/storage/migrations -q` exits 0.
`git log --oneline -5` shows one commit with the rename.

---

## Commit message

```
chore(migrations): rename ambiguous 0007 legacy migration to remove shared prefix
```
