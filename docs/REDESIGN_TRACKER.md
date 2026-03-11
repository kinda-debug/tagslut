<!-- Status: Active document. Current-state migration ledger only.
     Historical phase detail lives in docs/archive/REDESIGN_TRACKER.md. -->

# REDESIGN TRACKER

This file is the current-state migration ledger for maintainers.
It records the active redesign baseline, what streams are closed,
what remains open, and where canonical detail lives.
It is not an architecture doc, not a backlog, and not a history dump.
Long phase narratives and superseded decisions belong in
`docs/archive/REDESIGN_TRACKER.md`.

---

## 1. Status

The redesign is active and ongoing. This file reflects current
maintainership decisions only. Entries must be phrased as settled
outcomes or concrete open items, not brainstorming notes.
Claims about canonical workflows must match the live surface docs
listed in §6.

---

## 2. Current Baseline

| Area | Current canonical decision |
|---|---|
| CLI surface | `tagslut intake / index / decide / execute / verify / report / auth / dj / gig / export / init` |
| DJ pool build | `tagslut dj pool-wizard` |
| process-root phase set | `identify, enrich, art, promote, dj` on a v3 DB |
| Identity model | v3 `track_identity` + `asset_link` + `identity_status`, with merge tracking via `merged_into_id` |
| Storage roots | `MASTER_LIBRARY` is the canonical source library root; `DJ_LIBRARY` is a derived DJ library/cache root used by DJ workflows |
| Zones | `accepted`, `archive`, `staging`, `suspect`, `quarantine` |
| DB surface | v3 schema with `v_dj_pool_candidates_v3` and `v_dj_export_metadata_v1` as canonical DJ query surfaces |
| Legacy wrapper policy | Hidden from operator surface; tolerated only as compatibility paths pending retirement (§5) |

---

## 3. Completed Streams

### CLI surface consolidation
- **Status:** complete
- **Outcome:** Canonical command groups are established and enforced by
  surface policy. Operator-facing docs point to the `tagslut` CLI
  surface, not legacy top-level wrappers.
- **Source of truth:** [SURFACE_POLICY.md](SURFACE_POLICY.md),
  [SCRIPT_SURFACE.md](SCRIPT_SURFACE.md)

### v3 schema and identity model adoption
- **Status:** complete
- **Outcome:** The v3 identity-backed model is the active baseline for
  assets, identities, status, preferred asset selection, DJ profile,
  analysis, and provenance. DJ pool/export workflows depend on the v3
  views rather than ad hoc `files`-only query logic.
- **Source of truth:** [DB_V3_SCHEMA.md](DB_V3_SCHEMA.md),
  `tagslut/storage/v3/schema.py`

### Legacy wrapper hiding policy
- **Status:** complete
- **Outcome:** Legacy wrappers and hidden compatibility commands are not
  part of the public operator surface. Active docs describe canonical
  replacements; retirement sequencing is tracked separately in §5.
- **Source of truth:** [SURFACE_POLICY.md](SURFACE_POLICY.md),
  [SCRIPT_SURFACE.md](SCRIPT_SURFACE.md)

### DJ pool wizard
- **Status:** complete
- **Outcome:** `tagslut dj pool-wizard` is the canonical operator path
  for building a final MP3 DJ pool from `MASTER_LIBRARY`. Plan,
  execute, interactive, and non-interactive flows are implemented.
  Runs are auditable through structured artifacts, relink-backed
  sources win over legacy cache paths, rows without a v3 identity are
  skipped explicitly with `reason=no_v3_identity`, and the feature is
  covered by unit and integration tests.
- **Source of truth:** [DJ_WORKFLOW.md](DJ_WORKFLOW.md),
  [DJ_POOL.md](DJ_POOL.md),
  `tagslut/exec/dj_pool_wizard.py`,
  `tests/exec/test_dj_pool_wizard.py`

### Pool-wizard docs surface alignment
- **Status:** complete
- **Outcome:** Active DJ workflow and surface docs point to
  `tagslut dj pool-wizard` as the primary pool-build workflow rather
  than archived or lower-level legacy paths.
- **Source of truth:** [DJ_WORKFLOW.md](DJ_WORKFLOW.md),
  [SCRIPT_SURFACE.md](SCRIPT_SURFACE.md),
  [SURFACE_POLICY.md](SURFACE_POLICY.md)

---

## 4. Open Streams

### Legacy wrapper hard removal
- **Why open:** Compatibility wrappers remain hidden but not fully
  deleted. Final removal requires confirming no internal caller still
  depends on them and that documented replacements are stable.
- **Next milestone:** Audit remaining internal callers and produce
  focused removal PRs by wrapper family.
- **Detail:** [SURFACE_POLICY.md](SURFACE_POLICY.md),
  [PHASE5_LEGACY_DECOMMISSION.md](PHASE5_LEGACY_DECOMMISSION.md)

### Pool-wizard transcode path live verification
- **Why open:** The transcode execution path is implemented, but the
  current live cohort is relink-backed, so that path is not yet covered
  by a real execution run against representative data.
- **Next milestone:** Exercise the transcode path using a disposable
  fixture or copied development DB state that includes a row with
  `identity_id` and no reusable MP3 source.
- **Detail:** [DJ_POOL.md](DJ_POOL.md),
  `tagslut/exec/dj_pool_wizard.py`

### `process-root` phase contract documentation
- **Why open:** The v3-safe phase set is declared as baseline, but the
  per-phase contracts are not yet documented clearly enough for
  maintainers in the active workflow docs.
- **Next milestone:** Expand the `process-root` section in
  [WORKFLOWS.md](WORKFLOWS.md) with concise per-phase input/output
  contract notes.

---

## 5. Decommission Ledger

| Surface / feature | Status | Notes |
|---|---|---|
| Legacy DJ export/build paths | Hidden or superseded | Operator docs should point to `tagslut dj pool-wizard`; lower-level script paths remain compatibility or implementation detail |
| Hidden compatibility commands | Retained internally | Not operator-facing; removal depends on caller audit |
| Pre-v3 `files`-only DJ pool logic | Superseded | Replaced by the v3 identity-backed model and DJ views |
| Active tracker as archive stub | Replaced | This file now holds current state; historical tracker content remains in archive |

Decommission policy and historical rationale:
[SURFACE_POLICY.md](SURFACE_POLICY.md),
[PHASE5_LEGACY_DECOMMISSION.md](PHASE5_LEGACY_DECOMMISSION.md),
[`docs/archive/REDESIGN_TRACKER.md`](archive/REDESIGN_TRACKER.md)

---

## 6. Canonical Docs Map

| Doc | Owns |
|---|---|
| [WORKFLOWS.md](WORKFLOWS.md) | Operator workflow sequences end-to-end, including `process-root` usage |
| [SURFACE_POLICY.md](SURFACE_POLICY.md) | CLI surface rules, ownership, hidden/retired command policy |
| [SCRIPT_SURFACE.md](SCRIPT_SURFACE.md) | Enumerated canonical commands and script-level status |
| [ZONES.md](ZONES.md) | Active zone vocabulary and the root-vs-zone distinction |
| [DJ_WORKFLOW.md](DJ_WORKFLOW.md) | DJ-specific operator workflows, including pool-wizard usage |
| [DJ_POOL.md](DJ_POOL.md) | DJ pool contract, boundaries, and output/audit expectations |
| [DB_V3_SCHEMA.md](DB_V3_SCHEMA.md) | v3 schema tables, views, and ownership boundaries |
| [ARCHITECTURE.md](ARCHITECTURE.md) | High-level system components and data flow |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Common failure modes and remediation paths |

---

## 7. Archive Boundary

Everything in this file is current state.
The following material belongs exclusively in
[`docs/archive/REDESIGN_TRACKER.md`](archive/REDESIGN_TRACKER.md):

- pre-v3 architecture descriptions
- historical phase narratives written before implementation
- superseded command designs
- decisions that were reversed or replaced

Do not copy archive content back into this file.
If a historical decision becomes relevant again, open a new stream
entry in §4 and link to the archived source.
