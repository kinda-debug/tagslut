# Dedupe Operator Guide (Canonical V3 Surface)

This is the operator guide for the active tagslut workflow.

For full surface policy and phase runbooks:
- `docs/SCRIPT_SURFACE.md`
- `docs/SURFACE_POLICY.md`
- `docs/REDESIGN_TRACKER.md`

## Safety Invariants

1. Move-only semantics for relocation workflows.
2. Always preview/plan before bulk execution.
3. Inventory must be updated (`index register`) before downstream decisions.
4. DJ promotion must respect duration gates.
5. Keep all operational artifacts under `artifacts/`.

## Canonical Commands

- `tagslut intake`
- `tagslut index`
- `tagslut decide`
- `tagslut execute`
- `tagslut verify`
- `tagslut report`
- `tagslut auth`

Compatibility aliases:
- `dedupe ...`
- `taglslut ...`

Retired wrappers (`mgmt`, `metadata`, `recover`, `scan`, `recommend`, `apply`, `promote`, `quarantine`) are not part of the active workflow.

## End-to-End Workflow

### 1. Intake

```bash
poetry run tagslut intake run --batch-root /Volumes/DJSSD/beatport <url>
```

### 2. Index and duplicate prevention

```bash
poetry run tagslut index check <path> --source bpdl
poetry run tagslut index register <path> --source bpdl
```

### 3. Duration safety for DJ lane

```bash
poetry run tagslut index duration-check <path> --dj-only
poetry run tagslut index duration-audit --db <db>
```

### 4. Decide deterministic plans

```bash
poetry run tagslut decide profiles
poetry run tagslut decide plan --policy library_balanced --input <input.json> --output <plan.json>
```

### 5. Execute move workflows

```bash
poetry run tagslut execute move-plan <plan.csv>
poetry run tagslut execute quarantine-plan <plan.csv>
poetry run tagslut execute promote-tags --source-root <src> --dest-root <dest>
```

### 6. Verify outcomes

```bash
poetry run tagslut verify receipts --db <db>
poetry run tagslut verify parity --db <db>
poetry run tagslut verify recovery --db <db>
```

### 7. Reporting

```bash
poetry run tagslut report m3u <path>
poetry run tagslut report plan-summary <plan.json>
poetry run tagslut report duration --db <db>
```

### 8. Auth + metadata enrichment

```bash
poetry run tagslut auth status
poetry run tagslut auth login tidal
poetry run tagslut index enrich --db <db> --recovery --execute
```

## Download Tooling

Use the unified entrypoint when possible:

```bash
tools/get <beatport-or-tidal-url>
```

Routing:
- `tidal.com` -> `tools/tiddl`
- `beatport.com` -> `tools/beatportdl/bpdl/bpdl`

BeatportDL does not generate M3U playlists.
Use `tagslut report m3u` (or `tools/review/promote_by_tags.py` where appropriate).

## Operational Checks

```bash
poetry run python scripts/audit_repo_layout.py
poetry run python scripts/check_cli_docs_consistency.py
poetry run pytest -q tests/test_phase4_cli_surface.py tests/test_cli_transitional_warnings.py
```

## Legacy Material

Historical docs and superseded workflow notes are archived under:
- `docs/archive/`

They are reference-only and not part of the active operator path.
