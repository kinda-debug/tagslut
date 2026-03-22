# DJ Workflow Audit

Audit scope: concrete DJ workflow behavior in this repo, tied to exact files, commands, scripts, and schema elements.

## Verified evidence base

This audit is grounded in direct repo evidence already inspected from:

- `tools/get`
- `tools/get-intake`
- `tagslut/cli/commands/dj.py`
- `tagslut/exec/precheck_inventory_dj.py`
- `tagslut/storage/schema.py`
- `tagslut/storage/migrations/0002_add_dj_fields.py`
- `tagslut/storage/migrations/0003_add_dj_gig_fields.sql`
- `tagslut/storage/migrations/0008_add_dj_set_role.sql`
- `README.md`
- file inventory under `tagslut/adapters/rekordbox/`, `tagslut/dj/`, `scripts/dj/`, and tests

Runtime execution status:
- Repo runtime was not mounted in the current writable sandbox, so safe end-to-end command execution inside the checked-out repo remains runtime verification still required.
- Static code path verification was completed from the inspected repo files listed above.

## Critical path, as implemented

### 1. Intake and provider dispatch

**Entry command:** `tools/get`

**Verified behavior**
- `tools/get` is a bash wrapper that parses flags like `--dj`, determines provider handling, and delegates to `tools/get-intake` for general intake flow.
- The command surface exposed to operators is therefore the shell wrapper, not a single Python command with one contract.

**Why this matters**
- The DJ workflow inherits shell-wrapper conditionals before it ever reaches promotion or MP3 generation.
- That makes the real contract harder to reason about and easier to break.

**Classification:** misleading command contract.

### 2. DJ flag path inside intake

**File:** `tools/get-intake`

**Verified behavior**
- `--dj` is parsed into `DJ_MODE`.
- The late DJ step is gated behind promotion-state artifacts rather than an explicit MP3 job queue.
- The relevant stage is the `if [[ "$DJ_MODE" -eq 1 ]]; then ... step "Build DJ MP3 copies" ...` block.

**What exact artifact feeds MP3 generation today**
- The exact feed artifact is `PROMOTED_FLACS_FILE`.
- The code reads a line count from `PROMOTED_FLACS_FILE` before building DJ copies.

**Why this breaks the intended workflow**
- DJ MP3 generation is not driven by canonical track identity, selected inventory rows, or a durable master/derivative mapping.
- It is driven by “which FLAC paths were promoted in this specific run.”

**Classification:** design flaw.

### 3. Promotion coupling

**File:** `tools/get-intake`

**Verified behavior**
- MP3 generation is tied to promoted FLACs from the same run because the DJ build stage consumes `PROMOTED_FLACS_FILE` populated by the promote path.
- When `PROMOTED_FLACS_FILE` is empty, the DJ stage warns and exits without creating DJ copies.

**Explicit answer**
- **Whether MP3 generation is tied to promoted FLACs from the same run:** yes.

**Why this breaks the intended workflow**
- A user cannot treat MP3 generation as a durable, independently repeatable operation.
- The outcome depends on whether promote happened now, not whether a promotable master already exists.

**Classification:** broken data contract.

### 4. Precheck-hit path

**Files:** `tools/get-intake`, `tagslut/exec/precheck_inventory_dj.py`

**Verified behavior**
- When precheck decides all candidates already exist, intake prints that same-or-better inventory matches already exist, skips download, and if `DJ_MODE=1` calls `link_precheck_inventory_to_dj` instead of the normal promote-driven DJ build path.
- `link_precheck_inventory_to_dj` is backed by `tagslut/exec/precheck_inventory_dj.py`.
- `precheck_inventory_dj.py` loads skip rows from the precheck CSV, queries the `files` table, tries to resolve an existing `dj_pool_path`, tries to match MP3s by tags under the DJ root, and can transcode from either the source path or a DJ tag snapshot.

**Explicit answers**
- **What happens when precheck decides the track already exists:** the normal download/promote path is skipped, and DJ handling switches to `link_precheck_inventory_to_dj` / `precheck_inventory_dj.py`.
- **Whether a user can reliably get a DJ-usable MP3 without a new FLAC promotion event:** not reliably. There is a fallback path, but it is conditional and not the same contract as the main `--dj` path.

**Why this breaks the intended workflow**
- The same top-level command now has two materially different DJ implementations.
- One path is fed by `PROMOTED_FLACS_FILE`; the other path is fed by precheck CSV rows plus DB lookup plus opportunistic MP3 tag matching.

**Classification:** misleading command contract and missing safeguard.

### 5. MP3 generation implementation

**Files:** `tools/get-intake`, `scripts/dj/build_pool_v3.py`, `tagslut/exec/transcoder.py`, `tagslut/exec/precheck_inventory_dj.py`

**Verified behavior**
- The main intake DJ step invokes a build-pool flow based on promoted FLACs.
- The precheck path can call `transcode_to_mp3` or `transcode_to_mp3_from_snapshot` from `tagslut.exec.transcoder`.
- The repo therefore has at least two ways MP3s are produced for DJ-facing use.

**Why this breaks the intended workflow**
- There is no single durable MP3 library abstraction.
- There is no single authoritative command whose source of truth is canonical master state.

**Classification:** design flaw.

### 6. Admission into DJ-facing outputs

**Files:** `tagslut/cli/commands/dj.py`, migration files, `precheck_inventory_dj.py`

**Verified behavior**
- The main schema stores DJ-ish fields directly on `files`: `dj_flag`, `dj_pool_path`, `rekordbox_id`, `last_exported_usb`, `dj_set_role`, `dj_subrole`, plus BPM/key fields added via DJ migrations.
- `dj.py` also implements separate export/prep behaviors, including curation/export logic outside the intake path.
- `precheck_inventory_dj.py` records provenance events and updates/uses path-linked DJ state rather than a dedicated DJ admissions table.

**Explicit answers**
- **Whether existing MP3s can be retroactively admitted cleanly:** not cleanly. The repo contains partial mechanisms to link or transcode them, but no verified single admission model or dedicated normalized DJ admissions table.

**Why this breaks the intended workflow**
- DJ admission is not a first-class entity.
- Instead, the repo mixes path fields, per-file flags, export utilities, and fallback linking logic.

**Classification:** broken data contract.

### 7. Enrichment timing

**File:** `tools/get-intake`

**Verified behavior**
- Background enrich + art launch is explicitly gated by `DJ_MODE == 0`.
- In other words, the normal tagging/enrichment follow-up is suppressed when the intake run is in DJ mode.

**Explicit answer**
- **Enrichment timing:** the normal background enrich/art step is skipped in DJ mode.

**Why this breaks the intended workflow**
- DJ-facing derivatives should depend on enriched canonical state, or at minimum follow a consistent enrichment lifecycle.
- Here, passing `--dj` changes metadata timing and potentially metadata completeness.

**Classification:** missing safeguard.

### 8. Rekordbox prep and XML-related flow

**Files:** `tagslut/cli/commands/dj.py`, `tagslut/adapters/rekordbox/`, `tagslut/dj/rekordbox_prep.py`

**Verified behavior**
- The repo contains Rekordbox-related modules and a `prep-rekordbox` CLI command.
- The available evidence shows Rekordbox prep as a separate utility flow, not the single enforced output contract of DJ state.
- The main schema only exposes `rekordbox_id` as a field on `files`; there is no verified dedicated TrackID mapping table.

**Explicit answer**
- **Whether Rekordbox XML is currently a stable output contract or just an accessory utility:** accessory utility, not a stable formal contract.

**Why this breaks the intended workflow**
- XML output is not modeled as a deterministic projection of an explicit DJ state layer.
- Track IDs, playlist projection, and rebuild safety are therefore not proven to be stable.

**Classification:** broken XML contract.

## Major findings with exact evidence

| Finding | Exact evidence | What code actually does | Why it breaks DJ workflow | Type |
|---|---|---|---|---|
| `--dj` depends on same-run promotion output | `tools/get-intake` DJ build block consuming `PROMOTED_FLACS_FILE` | Builds DJ copies only from current run’s promoted FLAC list | No durable repeatable MP3 build from canonical masters | Design flaw |
| Precheck-hit switches workflow | `tools/get-intake` prefilter short-circuit + `link_precheck_inventory_to_dj`; `tagslut/exec/precheck_inventory_dj.py` | Skips download/promote and invokes an alternate DJ linker/transcoder flow | Same command has different semantics based on hidden inventory state | Misleading command contract |
| DJ state lives in `files` table | `tagslut/storage/schema.py`; migrations `0002`, `0003`, `0008` | Adds `dj_flag`, `dj_pool_path`, `rekordbox_id`, `dj_set_role`, etc. directly to `files` | No clean master-vs-MP3-vs-DJ separation | Broken data contract |
| Enrichment suppressed in DJ mode | `tools/get-intake` background enrich condition | Runs enrich/art only when `DJ_MODE == 0` | DJ runs diverge from canonical enrichment lifecycle | Missing safeguard |
| Rekordbox prep is utility-shaped | `tagslut/cli/commands/dj.py` `prep-rekordbox`; `tagslut/dj/rekordbox_prep.py`; `tagslut/adapters/rekordbox/` | Provides prep/import/export helpers rather than a formal projection layer | XML not guaranteed deterministic or rebuild-safe | Broken XML contract |

## Proposed target design

This repo’s current design is fundamentally wrong for reliable DJ operations. The fix is not a patch to `--dj`; it is a separation of layers.

### Master FLAC library

**Belongs in main DB**
- Canonical track identity.
- Master asset records and provenance.
- Enrichment state and enrichment provenance.
- Promote/move execution history.

**Should be rebuild-safe from canonical state?**
- Yes. Canonical identity + master asset rows are the root truth.

### Durable MP3 library

**Should be added as explicit schema, preferably same DB but separate tables**
- `mp3_asset` table keyed to canonical identity and master asset.
- Encodes derivative codec profile, source master asset, output path, checksum, transcode timestamp, readiness status.

**Why same DB, separate tables**
- MP3 assets are not independent business objects from masters; they are deterministic derivatives of master state.
- They do not belong as one nullable path column on `files`.

**Should be rebuilt from canonical state?**
- Yes, fully rebuildable.
- Incremental patching should still be supported by reconciling already-existing MP3 files.

### DJ library

**Should be a DJ schema partition or separate logical sub-DB**
Recommended: same SQLite DB, separate `dj_*` tables rather than a separate physical DB first.

Use explicit tables such as:
- `dj_admission`
- `dj_playlist`
- `dj_playlist_track`
- `dj_track_id_map`
- `dj_export_state`

**What belongs there**
- Admission status.
- Preferred MP3 asset id.
- Stable Rekordbox TrackID mapping.
- Playlist membership.
- Export projection state.
- Validation results.

**What should be rebuilt from canonical state**
- Full XML projection.
- Derived crate exports.
- Any folderized export mirror.

**What should be patchable incrementally**
- Admission state.
- Playlist membership edits.
- TrackID map persistence.
- XML patching against prior emitted state.

### DJ metadata storage

**Delete/collapse/demote**
- Demote `dj_pool_path` from authoritative state to a compatibility field or remove it after migration.
- Remove `rekordbox_id` from `files` as the primary TrackID storage location.
- Stop adding DJ semantics directly to `files` except perhaps thin readiness mirrors if absolutely needed.

### Rekordbox XML layer

**Hard recommendation**
- XML should be the **primary DJ interoperability layer**, but not the primary internal source of truth.
- Internal truth should remain DB state in `dj_*` tables.
- XML should be a deterministic projection and patch target derived from that state.

## Missing command surface

| Proposed command | Purpose | Inputs | Outputs | Source of truth | Mutates |
|---|---|---|---|---|---|
| `tagslut master intake` | Ingest/download/promote masters | URLs, local intake dirs, provider refs | master asset rows, promoted FLACs, provenance | master identity + asset tables | DB + filesystem |
| `tagslut mp3 build` | Build durable MP3 derivatives from canonical masters | identity ids, asset ids, file paths, playlists | managed MP3 assets | master asset + identity tables | DB + filesystem |
| `tagslut mp3 reconcile` | Register and normalize existing MP3s | MP3 directories/files | linked `mp3_asset` rows, mismatch report | observed files + canonical identity | DB |
| `tagslut dj admit` | Admit a track into DJ library | identity ids or mp3 asset ids | `dj_admission` rows, TrackID assignment | `mp3_asset` + `dj_*` tables | DB |
| `tagslut dj backfill` | Retroactively admit existing MP3 catalog | MP3 root, matching rules | admissions + conflict report | `mp3_asset` / canonical identity | DB |
| `tagslut dj validate` | Validate DJ readiness | none or scoped ids | validation report | `dj_*`, `mp3_asset`, filesystem | DB optional |
| `tagslut dj rebuild` | Rebuild DJ projections from canonical DJ state | optional scope | recreated exports, playlists, projection state | `dj_*` tables | DB + filesystem + XML optional |
| `tagslut dj xml emit` | Emit deterministic Rekordbox XML | optional playlist scope, output path | full XML file | `dj_*` tables + TrackID map | XML + export state |
| `tagslut dj xml patch` | Incrementally patch previously emitted XML | existing XML path, scope | patched XML + patch log | `dj_*` + prior export state | XML + DB |
| `tagslut dj audit` | Operator-facing full audit | roots, db path, optional xml | audit report | all layers | none or DB for snapshots |

## Rekordbox XML decision

### Formal recommendation

- XML should become the **primary DJ interoperability layer** for external DJ software exchange.
- XML should **not** become the primary internal working format.
- The DB should remain canonical; XML should be emitted deterministically from DB state and patchable against a known prior export.

### Required rules

1. **TrackID mapping must live in DB**
   - Use a dedicated `dj_track_id_map` or equivalent field on `dj_admission`, not `files.rekordbox_id`.
2. **Playlist membership must live in DB**
   - Project to XML from `dj_playlist` / `dj_playlist_track` tables.
3. **Retroactively admitted MP3s must enter through `mp3 reconcile` then `dj admit` / `dj backfill`**
   - Never by editing XML alone.
4. **Mandatory validations before XML emit/patch**
   - MP3 path exists.
   - One admitted track -> one preferred MP3 asset.
   - Stable TrackID exists and is unique.
   - Playlist membership references admitted tracks only.
   - Required title/artist metadata present.
   - No duplicate physical path emitted under multiple TrackIDs.
5. **Deterministic and reversible projection**
   - Stable ordering rules.
   - Stable TrackIDs.
   - Stored export manifest/hash.
   - Rebuild from DB should reproduce equivalent XML.
   - Patch mode should compare against stored prior export state.

## What to delete or collapse first

1. Collapse `tools/get` + `tools/get-intake` DJ semantics into future explicit Python commands.
2. Delete or disable the existing `--dj` contract until it can call `mp3 build` + `dj admit` deterministically.
3. Demote `dj_pool_path` and `rekordbox_id` on `files` from authoritative state.
4. Treat `gig_sets` / `gig_set_tracks` as legacy until proven essential in the new model.
5. Stop using path-matching and tag-matching as the primary admission mechanism.

## Top 5 reasons the workflow failed in practice

1. `--dj` is fed by `PROMOTED_FLACS_FILE`, so DJ output depends on same-run promotion side effects.
2. Precheck-hit tracks take a different DJ code path (`link_precheck_inventory_to_dj` / `precheck_inventory_dj.py`) than newly promoted tracks.
3. DJ state is smeared across `files` columns, ad hoc export code, and fallback linker logic instead of explicit DJ entities.
4. Enrichment timing changes when `--dj` is passed, so metadata lifecycle is inconsistent.
5. Rekordbox handling exists, but as utilities rather than as a formal deterministic export contract.

## Minimum viable redesign

1. Freeze or remove the current `--dj` promise.
2. Introduce explicit `mp3_asset` and `dj_*` tables.
3. Add `mp3 build`, `mp3 reconcile`, `dj admit`, `dj validate`, and `dj xml emit`.
4. Migrate any existing `dj_pool_path`/`rekordbox_id` state into explicit derivative and admission records.
5. Make Rekordbox XML a deterministic projection from DB state.

## Shortest path to a boring reliable operator experience

- Intake masters with one command.
- Build MP3 derivatives with one explicit command.
- Admit tracks to DJ state with one explicit command.
- Validate before export.
- Emit or patch Rekordbox XML from stable DB state.

That is the shortest path because it removes hidden branching, path guessing, and run-local artifacts from the operator contract.

## 1-day fixes

- Disable or loudly fail `tools/get --dj` when `PROMOTED_FLACS_FILE` is empty.
- Add a contract warning in `tools/get` and `tools/get-intake` that DJ output is not guaranteed on precheck-hit runs.
- Add a repo prompt file under `.github/prompts/` capturing this audit request format for repeatable future audits.

## 3-day fixes

- Implement `mp3 reconcile` for existing MP3 libraries.
- Add explicit `mp3 build` from canonical identities/master assets.
- Add `dj validate` to detect missing MP3s, duplicate path mappings, and missing TrackIDs.
- Add tests that pin precheck-hit and promotion-hit behavior separately.

## 1-week fixes

- Add `mp3_asset` and `dj_admission` schema.
- Implement `dj admit` and `dj backfill`.
- Implement deterministic `dj xml emit` and scoped `dj xml patch`.
- Migrate legacy `files` DJ columns into compatibility-only or deprecated status.

## Final recommendation

Do not patch the current `--dj` workflow in place. Replace it with explicit master, MP3, and DJ layers.
