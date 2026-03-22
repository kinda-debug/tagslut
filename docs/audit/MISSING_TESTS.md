# Missing Tests

This plan names repo-specific gaps that should be covered first because they would have caught the observed DJ workflow failure before real use.

## Highest priority tests

### 1. `tools/get --dj` with precheck-hit inventory

**Workflow not covered**
- `tools/get <url> --dj` where precheck determines all tracks already exist.

**Exact commands needing coverage**
- `tools/get`
- `tools/get-intake`
- `link_precheck_inventory_to_dj`
- `tagslut/exec/precheck_inventory_dj.py`

**Regression risk caught**
- The command silently taking a different DJ path than the promote-driven path.
- Failure to produce usable MP3 output when inventory already exists.
- Drift between `PROMOTED_FLACS_FILE` path and precheck-link path semantics.

**Why highest priority**
- This is the exact class of failure that makes `--dj` misleading in real use.

### 2. `tools/get --dj` with no promoted FLACs

**Workflow not covered**
- Intake run reaches DJ stage with empty `PROMOTED_FLACS_FILE`.

**Exact commands needing coverage**
- `tools/get-intake` DJ build block.

**Regression risk caught**
- Silent success with no DJ output.
- False operator confidence that DJ copies were produced.

### 3. Promote-hit vs precheck-hit equivalence test

**Workflow not covered**
- Same logical track requested in two scenarios: newly promoted vs already in inventory.

**Exact commands needing coverage**
- `tools/get`
- `tools/get-intake`
- `tagslut/exec/precheck_inventory_dj.py`
- any build-pool script invoked from intake DJ stage

**Regression risk caught**
- Same operator command producing different DB fields, paths, provenance, or usable outputs.

## Next priority tests

### 4. Existing MP3 retroactive admission test

**Workflow not covered**
- Existing MP3 under DJ root matched back to canonical inventory without new FLAC promotion.

**Exact code paths needing coverage**
- `tagslut/exec/precheck_inventory_dj.py`
- any DB resolution helpers it imports

**Regression risk caught**
- Wrong MP3 matched by loose tags.
- Missing or inconsistent provenance recording.
- Inability to admit existing MP3s reproducibly.

### 5. Enrichment timing regression test

**Workflow not covered**
- Compare normal intake vs DJ-mode intake on same material.

**Exact command needing coverage**
- `tools/get-intake`

**Regression risk caught**
- `--dj` changing enrichment/art behavior and leaving DJ-facing assets under-enriched.

### 6. Rekordbox prep determinism test

**Workflow not covered**
- Re-running Rekordbox prep/export for unchanged input state.

**Exact commands/modules needing coverage**
- `tagslut/cli/commands/dj.py` `prep-rekordbox`
- `tagslut/dj/rekordbox_prep.py`
- `tagslut/adapters/rekordbox/`

**Regression risk caught**
- Unstable TrackID/path output.
- Non-rebuild-safe XML-related exports.

### 7. Schema migration consistency test for DJ fields

**Workflow not covered**
- Applying `0002`, `0003`, `0008` over fresh and existing DBs, then exercising DJ code.

**Exact files needing coverage**
- `tagslut/storage/migrations/0002_add_dj_fields.py`
- `tagslut/storage/migrations/0003_add_dj_gig_fields.sql`
- `tagslut/storage/migrations/0008_add_dj_set_role.sql`

**Regression risk caught**
- Code assuming DJ columns/tables exist or mean the same thing across DB states.

## Proposed end-to-end test matrix

| Priority | Scenario | Expected assertion |
|---|---|---|
| P0 | `tools/get --dj` with all tracks precheck-hit | command must not silently succeed without explicit DJ admission result |
| P0 | `tools/get --dj` with empty `PROMOTED_FLACS_FILE` | command must fail loudly or emit explicit zero-output contract |
| P0 | same track: promote-hit vs precheck-hit | resulting DJ-visible state must be equivalent or command must differ |
| P1 | existing MP3 backfill | canonical identity and MP3 asset linkage must be deterministic |
| P1 | DJ mode enrichment | metadata/enrichment results must be explicit and validated |
| P1 | Rekordbox repeat emit | same DB state must yield stable output |
| P2 | migration state variants | DJ code must behave consistently on migrated DBs |

## Test harness recommendation

- Keep shell-level E2E coverage for `tools/get` / `tools/get-intake` because those wrappers are part of the bug surface.
- Add Python-level tests around `precheck_inventory_dj.py` resolution behavior with fixture MP3 tags and DB rows.
- Add golden-file tests for future `dj xml emit` output once implemented.
