# Prompt: DJ validation gate hardening

**Agent**: Codex
**Section**: ROADMAP §9
**Status**: Ready to execute

**COMMIT ALL CHANGES BEFORE EXITING.**

---

## Goal

Three targeted fixes to the DJ validation gate:

1. Widen `compute_dj_state_hash` to include MP3 path and status alongside identity ID
2. Add `issue_count` and `summary` columns to `dj_validation_state` (new migration 0015)
3. Replace brittle string equality error checks in CLI with a sentinel exception class

Issue 3 also requires a decision from you: **should `INACTIVE_PLAYLIST_MEMBER` block XML emit?**
The current blocking set in `_run_inline_validation` is:
`BAD_MP3_STATUS`, `MISSING_MP3_FILE`, `DUPLICATE_MP3_PATH`, `MISSING_METADATA`
`INACTIVE_PLAYLIST_MEMBER` is NOT in that set — a de-admitted track in a playlist does not
block emit. If playlists are authoritative, add it. If playlists are advisory, leave it out.
**Make this decision and encode it as a named constant in `xml_emit.py`**, not an inline set.

---

## Read first

1. `tagslut/storage/v3/dj_state.py` — `compute_dj_state_hash`, `record_validation_state`
2. `tagslut/storage/v3/schema.py` — `dj_validation_state` DDL (lines ~297-303)
3. `tagslut/storage/v3/migrations/0014_dj_validation_state.py` — existing migration pattern
4. `tagslut/dj/xml_emit.py` — `_run_inline_validation`, `_run_pre_emit_validation`, `emit_rekordbox_xml`, `patch_rekordbox_xml`
5. `tagslut/cli/commands/dj.py` — `dj_xml_emit` and `dj_xml_patch` error handling blocks
6. `tagslut/dj/admission.py` — `validate_dj_library`, `DjValidationIssue`

---

## Fix 1 — Widen `compute_dj_state_hash`

**File**: `tagslut/storage/v3/dj_state.py`

**Problem**: Hash only includes `identity_id`. An MP3 file replacement or path change after
`dj validate` passes is invisible to the gate — the hash matches a prior passing record.

**Fix**: Include `mp3_asset.path` and `mp3_asset.status` in the hash payload.

Replace the current query:
```python
rows = conn.execute(
    "SELECT identity_id FROM dj_admission WHERE status = 'admitted' ORDER BY identity_id ASC"
).fetchall()
```

With:
```python
rows = conn.execute(
    """
    SELECT da.identity_id, ma.path, ma.status
    FROM dj_admission da
    JOIN mp3_asset ma ON ma.id = da.mp3_asset_id
    WHERE da.status = 'admitted'
    ORDER BY da.identity_id ASC
    """
).fetchall()
```

Replace the payload construction:
```python
identity_ids = sorted([int(row[0]) for row in rows])
payload = ",".join(str(id) for id in identity_ids)
```

With:
```python
# Sort by identity_id for determinism
sorted_rows = sorted(rows, key=lambda r: int(r[0]))
payload = ";".join(f"{r[0]}:{r[1]}:{r[2]}" for r in sorted_rows)
```

Update the empty-rows fast path:
```python
if not rows:
    return hashlib.sha256(b"").hexdigest()
```
This is unchanged — keep it.

**Critical consequence**: All existing `dj_validation_state` rows will be stale after this
change because their `state_hash` values were computed with the old formula. The next
`dj validate` run will record a new passing row under the new hash. This is correct and
expected — add a comment in `compute_dj_state_hash` noting that the hash formula version
is implicit and that changing it invalidates all prior rows.

---

## Fix 2 — Add `issue_count` and `summary` columns (migration 0015)

**Files to create/modify**:
- Create: `tagslut/storage/v3/migrations/0015_dj_validation_state_audit.py`
- Modify: `tagslut/storage/v3/schema.py` (DDL and migration list)
- Modify: `tagslut/storage/v3/dj_state.py` (`record_validation_state` INSERT)

### 2a — New migration

Pattern from `0014_dj_validation_state.py`. New migration:

```python
"""Migration 0015: add issue_count and summary to dj_validation_state."""

SCHEMA_NAME = "v3"
VERSION = 15

def up(conn):
    conn.execute(
        "ALTER TABLE dj_validation_state ADD COLUMN issue_count INTEGER NOT NULL DEFAULT 0"
    )
    conn.execute(
        "ALTER TABLE dj_validation_state ADD COLUMN summary TEXT"
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (schema_name, version, note)
        VALUES (?, ?, ?)
        """,
        (SCHEMA_NAME, VERSION, "0015_dj_validation_state_audit.py"),
    )
    conn.commit()
```

### 2b — Update schema DDL

In `tagslut/storage/v3/schema.py`, find the `dj_validation_state` CREATE TABLE and add the
two new columns:

```sql
CREATE TABLE IF NOT EXISTS dj_validation_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    state_hash TEXT NOT NULL,
    passed INTEGER NOT NULL DEFAULT 0,
    issue_count INTEGER NOT NULL DEFAULT 0,
    summary TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

Also add `"0015_dj_validation_state_audit.py"` to the migration list in `schema.py`.

### 2c — Update `record_validation_state` INSERT

In `dj_state.py`, update the INSERT to include the new columns:

```python
conn.execute(
    """
    INSERT INTO dj_validation_state (state_hash, passed, issue_count, summary, created_at)
    VALUES (?, ?, ?, ?, ?)
    """,
    (state_hash, int(passed), issue_count, summary or None,
     datetime.now(timezone.utc).isoformat()),
)
```

The function signature already accepts `issue_count` and `summary` — they were being dropped.

---

## Fix 3 — Sentinel exception class for validation gate errors

**Problem**: `dj_xml_emit` and `dj_xml_patch` in `cli/commands/dj.py` catch `ValueError`
and compare its string representation against the full error message to determine exit code.
Any wording change in `_run_pre_emit_validation` silently breaks the exit code path.

**Fix**: Define a sentinel exception class in `xml_emit.py` and raise it instead.

### 3a — Add sentinel class to `xml_emit.py`

At the top of `tagslut/dj/xml_emit.py`, after imports:

```python
class DjValidationGateError(ValueError):
    """Raised when the DJ validation gate blocks XML emit.

    Use this instead of ValueError so CLI callers can catch it specifically
    without string-matching the error message.
    """
```

### 3b — Raise `DjValidationGateError` in `_run_pre_emit_validation`

Replace the current raise in `_run_pre_emit_validation`:
```python
raise ValueError(
    "ERROR: no passing dj validate record for current state.\n"
    "Run `tagslut dj validate` first."
)
```

With:
```python
raise DjValidationGateError(
    "No passing dj validate record for current state. "
    "Run `tagslut dj validate` first."
)
```

### 3c — Update blocking issue set to a named constant

In `_run_inline_validation`, replace the inline set:
```python
blocking = [i for i in report.issues if i.kind in (
    "BAD_MP3_STATUS", "MISSING_MP3_FILE", "DUPLICATE_MP3_PATH", "MISSING_METADATA"
)]
```

With a module-level constant (place near the top of `xml_emit.py`):
```python
# Issue kinds that block XML emit.
# INACTIVE_PLAYLIST_MEMBER is intentionally excluded: playlists are advisory,
# not authoritative. A de-admitted track in a playlist does not block emit —
# it simply won't appear in the exported playlist.
# Change this constant (not the call site) if policy changes.
EMIT_BLOCKING_ISSUE_KINDS: frozenset[str] = frozenset({
    "BAD_MP3_STATUS",
    "MISSING_MP3_FILE",
    "DUPLICATE_MP3_PATH",
    "MISSING_METADATA",
})
```

Then use it:
```python
blocking = [i for i in report.issues if i.kind in EMIT_BLOCKING_ISSUE_KINDS]
```

**Decision encoded**: `INACTIVE_PLAYLIST_MEMBER` is NOT in the blocking set.
Playlists are advisory. If you want to change this, add the kind to
`EMIT_BLOCKING_ISSUE_KINDS` — not to the call site.

### 3d — Update CLI error handling in `dj.py`

In `dj_xml_emit` and `dj_xml_patch`, replace:
```python
from tagslut.dj.xml_emit import emit_rekordbox_xml
```
With:
```python
from tagslut.dj.xml_emit import DjValidationGateError, emit_rekordbox_xml
```

Replace the brittle string check:
```python
except ValueError as exc:
    conn.close()
    if str(exc) == (
        "ERROR: no passing dj validate record for current state.\n"
        "Run `tagslut dj validate` first."
    ):
        click.echo(str(exc), err=True)
        sys.exit(1)
    raise click.ClickException(str(exc)) from exc
```

With:
```python
except DjValidationGateError as exc:
    conn.close()
    click.echo(str(exc), err=True)
    sys.exit(1)
except ValueError as exc:
    conn.close()
    raise click.ClickException(str(exc)) from exc
```

Apply this change to both `dj_xml_emit` and `dj_xml_patch`.

---

## What NOT to change

- `admission.py` `backfill_admissions` — leave as-is (parallel implementation, separate concern)
- `exec/dj_backfill.py` — leave as-is
- `dj_track_id_map` assignment logic — correct as-is
- `validate_dj_library` checks — correct as-is
- Any test that exercises the current hash format — update hash fixture values, not logic

---

## Verification

```bash
cd /Users/georgeskhawam/Projects/tagslut
export PATH="$HOME/.local/bin:$PATH"

# 1. Compile check
poetry run python -m compileall tagslut -q

# 2. Migration applies cleanly against FRESH DB
poetry run python3 -c "
import sqlite3
from tagslut.storage.v3.migrations import migration_runner_v3
conn = sqlite3.connect(':memory:')
migration_runner_v3.run_migrations(conn)
cols = [r[1] for r in conn.execute('PRAGMA table_info(dj_validation_state)').fetchall()]
assert 'issue_count' in cols, f'issue_count missing: {cols}'
assert 'summary' in cols, f'summary missing: {cols}'
print('migration OK:', cols)
"

# 3. State hash is wider (includes path/status)
poetry run python3 -c "
import sqlite3
from tagslut.storage.v3.dj_state import compute_dj_state_hash
conn = sqlite3.connect(':memory:')
conn.execute('CREATE TABLE dj_admission (id INTEGER PRIMARY KEY, identity_id INTEGER, mp3_asset_id INTEGER, status TEXT)')
conn.execute('CREATE TABLE mp3_asset (id INTEGER PRIMARY KEY, path TEXT, status TEXT)')
conn.execute(\"INSERT INTO mp3_asset VALUES (1, '/music/a.mp3', 'verified')\")
conn.execute(\"INSERT INTO dj_admission VALUES (1, 42, 1, 'admitted')\")
h1 = compute_dj_state_hash(conn)
# Change the path — hash must change
conn.execute(\"UPDATE mp3_asset SET path = '/music/b.mp3' WHERE id = 1\")
h2 = compute_dj_state_hash(conn)
assert h1 != h2, 'Hash must differ when MP3 path changes'
print('hash sensitivity OK:', h1[:12], '!=', h2[:12])
"

# 4. DjValidationGateError is importable and is a subclass of ValueError
poetry run python3 -c "
from tagslut.dj.xml_emit import DjValidationGateError, EMIT_BLOCKING_ISSUE_KINDS
assert issubclass(DjValidationGateError, ValueError)
assert 'BAD_MP3_STATUS' in EMIT_BLOCKING_ISSUE_KINDS
assert 'INACTIVE_PLAYLIST_MEMBER' not in EMIT_BLOCKING_ISSUE_KINDS
print('sentinel OK, blocking set OK')
"

# 5. Targeted tests
poetry run pytest tests/exec/test_dj_xml_preflight_validation.py tests/storage/v3/test_migration_runner_v3.py -v
```

---

## Tests required

Update or add to `tests/exec/test_dj_xml_preflight_validation.py`:

1. `test_state_hash_changes_when_mp3_path_changes` — assert h1 != h2 after path update.
2. `test_state_hash_changes_when_mp3_status_changes` — assert h1 != h2 after status update.
3. `test_validation_gate_raises_dj_validation_gate_error` — mock no passing record, assert `DjValidationGateError` raised (not plain `ValueError`).
4. `test_record_validation_state_persists_issue_count_and_summary` — assert `issue_count` and `summary` are readable after `record_validation_state(...)`.
5. `test_emit_blocking_kinds_constant_excludes_playlist_member` — assert `INACTIVE_PLAYLIST_MEMBER not in EMIT_BLOCKING_ISSUE_KINDS`.

Update any existing test that compares `compute_dj_state_hash` output against a hardcoded
hex value — the hash formula changed, fixtures must be recomputed.

---

## Done when

All five verification steps pass.
`poetry run pytest tests/exec/test_dj_xml_preflight_validation.py -v` — all pass.
`poetry run pytest tests/storage/v3/test_migration_runner_v3.py -v` — all pass.

---

## Commit message

```
fix(dj): widen state hash, add validation audit columns, sentinel gate error
```
