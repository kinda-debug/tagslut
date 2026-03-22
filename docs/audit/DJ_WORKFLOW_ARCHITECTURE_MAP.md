# DJ Workflow Architecture Map

**Generated:** March 22, 2026
**Scope:** Complete DJ workflow architecture inventory: code, documentation, tests, scripts, schema

---

## Executive Summary

The tagslut DJ workflow is structured as a **canonical 4-stage pipeline** with explicit database-backed state at each stage:

1. **Stage 1: Intake** — ingest/refresh canonical FLAC masters via `tagslut intake <provider-url>`
2. **Stage 2: MP3 Registration** — build or reconcile MP3s via `tagslut mp3 build|reconcile`
3. **Stage 3: DJ Admission** — admit verified MP3s via `tagslut dj admit|backfill` and validate via `tagslut dj validate`
4. **Stage 4: Rekordbox Export** — emit/patch XML via `tagslut dj xml emit|patch`

**Note:** `tools/get --dj` is **deprecated** and emits warnings. All new work uses the 4-stage pipeline.

---

## 1. CODE ARCHITECTURE

### 1.1 DJ Module: Core Business Logic (`tagslut/dj/`)

| File | Purpose | Key Functions/Classes |
|------|---------|----------------------|
| [admission.py](tagslut/dj/admission.py) | DJ library admission layer; tracks admission state and validation | `admit_track()`, `backfill_admissions()`, `validate_dj_library()`, `DjAdmissionError` |
| [classify.py](tagslut/dj/classify.py) | Track classification for DJ worthiness using scan reports and overrides | `ClassifiedTrack`, `classify_tracks()`, `promote_safe_tracks()`, `append_overrides()` |
| [curation.py](tagslut/dj/curation.py) | DJ curation scoring: BPM ranges, genre filters, blocklists, review lists | `DjCurationConfig`, `DjScoreResult`, `calculate_dj_score()`, `resolve_track_override()`, `CurationResult` |
| [export.py](tagslut/dj/export.py) | Export planning and execution: pools, curation, transcoding orchestration | `PoolProfile`, `ExportPlan`, `ExportStats`, `plan_export()`, `run_export()`, `pool_profile_from_dict()` |
| [gig_prep.py](tagslut/dj/gig_prep.py) | DJ set role assignment and gig-specific track filtering | `GigPrepTrack`, `parse_roles_filter()`, gig export columns |
| [key_detection.py](tagslut/dj/key_detection.py) | Musical key detection via KeyFinder CLI wrapper | `detect_key()`, `is_keyfinder_available()`, Camelot notation support |
| [key_utils.py](tagslut/dj/key_utils.py) | Key conversion utilities: Camelot ↔ classical notation | `camelot_to_classical()`, `classical_to_camelot()`, key validation sets |
| [lexicon.py](tagslut/dj/lexicon.py) | Lexicon DJ integration: track overrides, scan reports, export formatting | `LexiconTrack`, `load_scan_report()`, `load_track_overrides()`, `write_lexicon_csv()` |
| [rekordbox_prep.py](tagslut/dj/rekordbox_prep.py) | Rekordbox prep subprocess orchestration and report parsing | `RekordboxPrepSummary`, `build_rekordbox_prep_command()`, `parse_rekordbox_report_summary()` |
| [transcode.py](tagslut/dj/transcode.py) | MP3 transcoding manifest and track row model | `TrackRow`, `load_tracks()`, `make_dedupe_key()`, `assign_output_paths()` |
| [xml_emit.py](tagslut/dj/xml_emit.py) | **Stage 4 authoritative XML emission** — deterministic Rekordbox XML generation with stable TrackID preservation | `emit_rekordbox_xml()`, `patch_rekordbox_xml()`, `_assign_track_ids()`, `_build_track_element()`, XML determinism logic |

**DJ Submodules:**

| Path | Purpose |
|------|---------|
| `tagslut/dj/reconcile/` | MP3 reconciliation: Lexicon backfill, identity linking |
| `tagslut/dj/reconcile/lexicon_backfill.py` | Import Lexicon DJ metadata and backfill `track_identity.canonical_payload_json` |

### 1.2 MP3 Build & Reconciliation (`tagslut/exec/mp3_build.py`)

| Function | Purpose |
|----------|---------|
| `build_mp3_from_identity()` | **Stage 2a:** Transcode preferred FLAC master to MP3, register in `mp3_asset` table with `status='verified'` |
| `reconcile_mp3_library()` | **Stage 2b:** Scan existing MP3 root, match to canonical identities via ISRC or title+artist, register without re-transcoding |
| `build_full_tag_mp3_assets_from_flac_paths()` | Bulk MP3 build from FLAC path list |

**Key Profiles:**
- `MP3_ASSET_PROFILE_FULL_TAGS = "mp3_asset_320_cbr_full"` — 320 kbps, full ID3 tags
- `DJ_COPY_PROFILE = "dj_copy_320_cbr"` — 320 kbps, DJ-optimized tagging

### 1.3 CLI Commands (`tagslut/cli/commands/`)

| File | Commands | Stage | Purpose |
|------|----------|-------|---------|
| [mp3.py](tagslut/cli/commands/mp3.py) | `tagslut mp3 build`, `tagslut mp3 reconcile` | 2 | Build or register MP3 derivatives |
| [dj.py](tagslut/cli/commands/dj.py) | `tagslut dj admit`, `tagslut dj backfill`, `tagslut dj validate`, `tagslut dj xml emit`, `tagslut dj xml patch` | 3–4 | Admission, validation, XML export |
| [gig.py](tagslut/cli/commands/gig.py) | `tagslut gig build`, `tagslut gig list`, `tagslut gig apply-rekordbox-overlay` | 3.5+ | Gig set building + Rekordbox overlay |
| [dj_role.py](tagslut/cli/commands/dj_role.py) | DJ set role CLI utilities | 3 | Role/subrole assignment and export |

### 1.4 Gig Builder (`tagslut/exec/gig_builder.py`)

**Purpose:** End-to-end gig set orchestration (filter → transcode → USB export → manifest)

**Key Classes:**
- `GigBuilder` — main orchestrator
  - `build(name, filter_expr, usb_path, dry_run)` — query inventory, transcode if needed, copy to USB
- `GigBuildResult` — summary with error tracking

### 1.5 Rekordbox Adapters (`tagslut/adapters/rekordbox/`)

| File | Purpose | Key Functions |
|------|---------|-------------------|
| [importer.py](tagslut/adapters/rekordbox/importer.py) | Rekordbox XML importing; track aliasing and source provenance | `import_rekordbox_xml()`, `_parse_rekordbox_xml()` |
| [overlay.py](tagslut/adapters/rekordbox/overlay.py) | Rekordbox track overlay (Rating, Colour) for gig prep | `OverlayConfig`, `apply_rekordbox_overlay()`, heuristic decision logic |

### 1.6 Enrichment & Metadata (`tagslut/metadata/`, `tagslut/exec/enrich_dj_tags.py`)

| File | Purpose |
|------|---------|
| `enricher.py` | Main enrichment orchestrator; Beatport + TIDAL provider workflow |
| `enrich_dj_tags.py` | DJ tag resolution wrapper (BPM, musical key, energy) |
| `providers/beatport.py` | Beatport metadata fetcher (primary source) |
| `providers/tidal.py` | TIDAL metadata fetcher (cross-source verification) |
| `rekordbox_sync.py` | Rekordbox USB → FLAC tags sync (confirmed BPM, key, play count) |

### 1.7 Metadata Models & Configuration

| Path | Purpose |
|------|---------|
| `tagslut/storage/models.py` | DJ set roles: `DJ_SET_ROLES`, `DJ_SUBROLES`, `DJ_SET_ROLE_ORDER` |
| `config/dj/dj_curation_usb_v8.yaml` | Default DJ curation policy (BPM ranges, genres, blocklists) |
| `config/dj/track_overrides.csv` | Manual track override statuses (safe/block/review) and crate assignment |
| `config/gig_overlay_rules.yaml` | Rekordbox overlay heuristics and manual overrides |

---

## 2. DOCUMENTATION

### 2.1 Canonical Pipeline References

| File | Purpose | Audience |
|------|---------|----------|
| [docs/DJ_PIPELINE.md](docs/DJ_PIPELINE.md) | **PRIMARY REFERENCE** — concise 4-stage operator workflow | Operators, integrators |
| [docs/DJ_WORKFLOW.md](docs/DJ_WORKFLOW.md) | Extended operator guide; deprecation notice for `tools/get --dj` | Operators |
| [docs/DJ_POOL.md](docs/DJ_POOL.md) | DJ pool contract (v3 identity model, read-only upstream, determinism) | Architects, integrators |
| [README.md](README.md#4-stage-dj-pipeline) | Top-level summary; 4-stage pipeline walkthrough | New users |

### 2.2 Audit & Architecture Documentation

| File | Purpose |
|------|---------|
| [docs/audit/DJ_WORKFLOW_AUDIT.md](docs/audit/DJ_WORKFLOW_AUDIT.md) | Evidence-based audit of implemented behavior vs. intended design |
| [docs/audit/DJ_WORKFLOW_TRACE.md](docs/audit/DJ_WORKFLOW_TRACE.md) | Runtime trace of legacy `tools/get --dj` vs. canonical pipeline |
| [docs/audit/DJ_WORKFLOW_GAP_TABLE.md](docs/audit/DJ_WORKFLOW_GAP_TABLE.md) | Gap analysis: what's broken, why, target fixes |
| [docs/audit/DJ_PIPELINE_DOC_TRIAGE.md](docs/audit/DJ_PIPELINE_DOC_TRIAGE.md) | Documentation file classification and update status |

### 2.3 Agent & Contributor Documentation

| File | Audience |
|------|----------|
| [AGENT.md](AGENT.md) | Global agent rules; canonical DJ workflow, legacy wrapper status, tool division of labor |
| [CLAUDE.md](CLAUDE.md) | Claude-specific instructions; workflow defaults, safety guidelines |
| [.claude/CLAUDE.md](.claude/CLAUDE.md) | Synced copy of CLAUDE.md for Claude Code CLI startup |

---

## 3. TESTS

### 3.1 DJ Pipeline & End-to-End Tests

| Test File | Scope |
|-----------|-------|
| [tests/dj/test_dj_pipeline_e2e.py](tests/dj/test_dj_pipeline_e2e.py) | E2E pipeline test; all 4 stages |
| [tests/e2e/test_dj_pipeline.py](tests/e2e/test_dj_pipeline.py) | Alternative E2E test suite |

### 3.2 DJ Command & CLI Tests

| Test File | Scope |
|-----------|-------|
| [tests/cli/test_dj_role_commands.py](tests/cli/test_dj_role_commands.py) | DJ role assignment CLI |
| [tests/cli/test_index_dj_commands.py](tests/cli/test_index_dj_commands.py) | DJ command indexing |
| [tests/cli/test_gig_rekordbox_overlay.py](tests/cli/test_gig_rekordbox_overlay.py) | Gig overlay CLI |

### 3.3 DJ Feature Tests

| Test File | Coverage |
|-----------|----------|
| [tests/test_dj_profile_v3.py](tests/test_dj_profile_v3.py) | DJ profile scoring (BPM, genres, curation) |
| [tests/test_dj_export_builder_v3.py](tests/test_dj_export_builder_v3.py) | Export builder orchestration |
| [tests/exec/test_dj_pool_wizard.py](tests/exec/test_dj_pool_wizard.py) | DJ pool wizard (deterministic pool generation) |
| [tests/exec/test_dj_library_normalize.py](tests/exec/test_dj_library_normalize.py) | DJ library path normalization |
| [tests/exec/test_dj_manifest_receipts.py](tests/exec/test_dj_manifest_receipts.py) | DJ export manifests and audit trails |
| [tests/tools/test_dj_usb_analyzer.py](tests/tools/test_dj_usb_analyzer.py) | DJ USB analysis tools |

### 3.4 Rekordbox Integration Tests

| Test File | Coverage |
|-----------|----------|
| [tests/dj/test_import_rekordbox.py](tests/dj/test_import_rekordbox.py) | Rekordbox XML importing |
| [tests/dj/test_rekordbox_prep.py](tests/dj/test_rekordbox_prep.py) | Rekordbox prep subprocess orchestration |
| [tests/dj/test_rekordbox_overlay.py](tests/dj/test_rekordbox_overlay.py) | Overlay heuristics and application |
| [tests/tools/test_build_rekordbox_xml_from_pool.py](tests/tools/test_build_rekordbox_xml_from_pool.py) | XML generation from pool |

### 3.5 MP3 Build & Enrichment Tests

| Test File | Coverage |
|-----------|----------|
| [tests/storage/test_mp3_dj_migration.py](tests/storage/test_mp3_dj_migration.py) | MP3 + DJ table migrations |
| [tests/exec/test_transcoder.py](tests/exec/test_transcoder.py) | MP3 transcoding workflows |
| [tests/test_transcoder.py](tests/test_transcoder.py) | Transcoder utilities |
| [tests/tools/test_sync_mp3_tags_from_flac.py](tests/tools/test_sync_mp3_tags_from_flac.py) | MP3 tag sync from FLAC |
| [tests/test_enrich_dj_tags.py](tests/test_enrich_dj_tags.py) | DJ tag enrichment (BPM, key, energy) |

### 3.6 Database Schema Tests

| Test File | Coverage |
|-----------|----------|
| [tests/storage/test_dj_schema.py](tests/storage/test_dj_schema.py) | DJ table schema |
| [tests/storage/test_dj_migration.py](tests/storage/test_dj_migration.py) | DJ migration correctness |
| [tests/storage/test_dj_set_role_migration.py](tests/storage/test_dj_set_role_migration.py) | DJ set role column migration |
| [tests/storage/test_audiofile_dj_roles.py](tests/storage/test_audiofile_dj_roles.py) | DJ role model persistence |
| [tests/storage/v3/test_dj_exports.py](tests/storage/v3/test_dj_exports.py) | DJ export state tracking |

### 3.7 Enrichment & Metadata Tests

| Test File | Coverage |
|-----------|----------|
| [tests/test_enrichment_cascade.py](tests/test_enrichment_cascade.py) | Enrichment cascade rules (priority ordering) |
| [tests/test_tidal_beatport_enrichment.py](tests/test_tidal_beatport_enrichment.py) | TIDAL + Beatport merge enrichment |
| [tests/metadata/test_enricher_policy.py](tests/metadata/test_enricher_policy.py) | Enricher confidencepolicy |

---

## 4. SCRIPTS & TOOLS

### 4.1 Legacy Wrapper Scripts (`tools/`)

| Script | Status | Purpose | Note |
|--------|--------|---------|------|
| [tools/get](tools/get) | LEGACY (deprecated) | High-level intake orchestrator; forwards to `tools/get-intake` | Emits deprecation warning for `--dj`; use 4-stage pipeline |
| [tools/get-intake](tools/get-intake) | LEGACY (mixed) | Detailed intake orchestration with precheck, download, scan, identify, promote | Contains `--dj` mode (fallback path); prefer `tagslut mp3 reconcile \| build` |

### 4.2 DJ Build & Export Scripts (`tools/dj/`, `scripts/dj/`)

| Script | Purpose | Input | Output |
|--------|---------|-------|--------|
| [tools/dj/build_special_pool_from_m3u.py](tools/dj/build_special_pool_from_m3u.py) | Build DJ pool from M3U playlist; transcode and tag-sync | M3U file, optional DB | MP3 pool + manifest |
| [tools/dj/build_rekordbox_xml_from_pool.py](tools/dj/build_rekordbox_xml_from_pool.py) | Generate Rekordbox XML from DJ pool directory | Pool root + optional rules | `rekordbox.xml` |
| [scripts/dj/build_pool_v3.py](scripts/dj/build_pool_v3.py) | Build DJ pool from canonical identity IDs (Stage 2 output) | Identity ID list, DB | Pool with manifest + receipts |

### 4.3 MP3 & Transcoding Scripts

| Script | Purpose |
|--------|---------|
| [scripts/transcode_m3u_to_mp3_macos.sh](scripts/transcode_m3u_to_mp3_macos.sh) | Bash wrapper to transcode M3U playlist to MP3 on macOS |
| [tools/metadata_scripts/sync_mp3_tags_from_flac.py](tools/metadata_scripts/sync_mp3_tags_from_flac.py) | Sync ID3 tags from FLAC manifest |

### 4.4 Lexicon & Scanning Tools

| Script | Purpose |
|--------|---------|
| [tools/metadata_scripts/lexicon_export.py](tools/metadata_scripts/lexicon_export.py) | Export DJ data to Lexicon DJ format |
| [tools/metadata_scripts/lexicon_compare.py](tools/metadata_scripts/lexicon_compare.py) | Compare Lexicon metadata against tagslut state |
| [scripts/reconcile_track_overrides.py](scripts/reconcile_track_overrides.py) | Reconcile track override CSV against filesystem |

---

## 5. DATABASE SCHEMA

### 5.1 Core DJ Tables (Migrations 0009, 0010)

#### `mp3_asset`
**Purpose:** Derivative MP3 assets; links to canonical identity and master asset.

| Column | Type | Purpose |
|--------|------|---------|
| `id` | INTEGER PRIMARY KEY | Unique asset row |
| `identity_id` | INTEGER | Links to `track_identity.id` (nullable for legacy imports) |
| `asset_id` | INTEGER | Links to `asset_file.id` (master FLAC master) |
| `path` | TEXT UNIQUE | Filesystem path (canonical location) |
| `content_sha256` | TEXT | Integrity anchor |
| `size_bytes` | INTEGER | File size |
| `bitrate` | INTEGER | MP3 bitrate (typically 320) |
| `sample_rate` | INTEGER | Sample rate (Hz) |
| `duration_s` | REAL | Duration (seconds) |
| `profile` | TEXT | Encoding profile (`standard`, `mp3_320_cbr_full`, etc.) |
| `status` | TEXT | Admin state (`unverified`, `verified`, `missing`, `superseded`) |
| `source` | TEXT | How registered (`build`, `reconcile`, `import`, `unknown`) |
| `zone` | TEXT | Optional zone identifier |
| `transcoded_at` | TEXT | Timestamp when built |
| `reconciled_at` | TEXT | Timestamp when reconciled |
| `lexicon_track_id` | INTEGER | Optional Lexicon Dj track reference |
| `created_at` | TEXT | Row creation time |
| `updated_at` | TEXT | Last update time |

**Indexes:** `identity`, `zone`, `lexicon`

---

#### `dj_admission`
**Purpose:** DJ library admission; one row per track_identity admitted to live DJ pool.

| Column | Type | Purpose |
|--------|------|---------|
| `id` | INTEGER PRIMARY KEY | Unique admission row |
| `identity_id` | INTEGER UNIQUE | Links to admitted `track_identity.id` |
| `mp3_asset_id` | INTEGER | Preferred MP3 asset for this admission |
| `status` | TEXT | Admission state (`pending`, `admitted`, `rejected`, `needs_review`) |
| `source` | TEXT | How admitted (`manual`, `backfill`, `import`, `unknown`) |
| `notes` | TEXT | Admin notes |
| `admitted_at` | TEXT | Timestamp of admission |
| `created_at` | TEXT | Row creation time |
| `updated_at` | TEXT | Last update time |

**Indexes:** `identity`

---

#### `dj_track_id_map`
**Purpose:** Stable Rekordbox TrackID assignment; decoupled from admission so IDs survive re-admission or asset swaps.

| Column | Type | Purpose |
|--------|------|---------|
| `id` | INTEGER PRIMARY KEY | Unique mapping row |
| `dj_admission_id` | INTEGER UNIQUE | Links to `dj_admission.id` |
| `rekordbox_track_id` | INTEGER UNIQUE | Stable Rekordbox TrackID |
| `assigned_at` | TEXT | Timestamp of assignment |

---

#### `dj_playlist` (Hierarchical Playlist Tree)
**Purpose:** Mirror Rekordbox folder/playlist hierarchy; nested structure for organization.

| Column | Type | Purpose |
|--------|------|---------|
| `id` | INTEGER PRIMARY KEY | Unique playlist/folder ID |
| `name` | TEXT | Folder or playlist name |
| `parent_id` | INTEGER | Optional parent playlist/folder |
| `lexicon_playlist_id` | INTEGER | Optional Lexicon DJ playlist reference |
| `sort_key` | TEXT | Sort order hint |
| `playlist_type` | TEXT | Type (`standard`, `crate`, etc.) |
| `created_at` | TEXT | Creation time |

**Unique Constraint:** `(name, parent_id)` — ensures no duplicate folder names at same level

---

#### `dj_playlist_track`
**Purpose:** Ordered track membership in playlists.

| Column | Type | Purpose |
|--------|------|---------|
| `playlist_id` | INTEGER | Link to `dj_playlist.id` |
| `dj_admission_id` | INTEGER | Link to `dj_admission.id` |
| `ordinal` | INTEGER | Track order in playlist |

**Primary Key:** `(playlist_id, dj_admission_id)` — one admission per playlist

---

#### `dj_export_state`
**Purpose:** Export manifests for deterministic XML emit/patch tracking.

| Column | Type | Purpose |
|--------|------|---------|
| `id` | INTEGER PRIMARY KEY | Unique export row |
| `kind` | TEXT | Export type (`xml-emit`, `xml-patch`, `m3u`, etc.) |
| `output_path` | TEXT | Output file path |
| `manifest_hash` | TEXT | SHA-256 of export scope JSON (determinism anchor) |
| `scope_json` | TEXT | JSON: playlist scope, track count, etc. |
| `emitted_at` | TEXT | Export timestamp |

**Index:** `kind`

---

#### `reconcile_log`
**Purpose:** Append-only audit log of reconciliation decisions.

| Column | Type | Purpose |
|--------|------|---------|
| `id` | INTEGER PRIMARY KEY | Unique log entry |
| `run_id` | TEXT | Reconciliation run identifier |
| `event_time` | TEXT | Event timestamp |
| `source` | TEXT | Source of decision (e.g., `isrc_match`, `title_match_fuzzy`, `manual_override`) |
| `action` | TEXT | Action taken (`admit`, `reject`, `flag_review`, etc.) |
| `confidence` | TEXT | Confidence score/level |
| `mp3_path` | TEXT | MP3 file path involved |
| `identity_id` | INTEGER | Linked identity |
| `lexicon_track_id` | INTEGER | Linked Lexicon track |
| `details_json` | TEXT | JSON dump of decision details |

**Indexes:** `run_id`, `identity_id`

---

### 5.2 Legacy DJ Columns on `files` Table

| Column | Purpose | Migrated To | Status |
|--------|---------|-------------|--------|
| `dj_pool_path` | DJ MP3 file location | `mp3_asset.path` | DEPRECATED |
| `rekordbox_id` | Rekordbox TrackID | `dj_track_id_map.rekordbox_track_id` | DEPRECATED |
| `dj_flag` | Manual DJ designation | `dj_admission.status` | DEPRECATED |
| `dj_set_role` | DJ set role assignment | `dj_admission` + gig context | DEPRECATED |

---

## 6. CLI ENTRY POINTS

### 6.1 Main Entry Point

**Entrypoint:** `poetry run tagslut` (defined in `pyproject.toml`)

```python
[project.scripts]
tagslut = "tagslut.cli.main:cli"
```

**Main CLI Group:** [tagslut/cli/main.py](tagslut/cli/main.py)

- **Version:** 3.0.0
- **Canonical command registration** from `tagslut/cli/commands/*`
- **DJ/MP3 group registration** via `cli.add_command()`

---

### 6.2 DJ Commands (Stage 3–4)

```bash
poetry run tagslut dj [subcommand]
```

**Subcommands:**

| Command | Stage | Purpose |
|---------|-------|---------|
| `tagslut dj admit --db <path> --identity-id <id> --mp3-asset-id <id>` | 3 | Admit a single track to DJ library |
| `tagslut dj backfill --db <path>` | 3 | Auto-admit all `mp3_asset` rows with `status='verified'` |
| `tagslut dj validate --db <path>` | 3 | Validate DJ library (missing files, empty metadata) |
| `tagslut dj xml emit --db <path> --out <file>` | 4a | Emit full Rekordbox XML from admitted tracks |
| `tagslut dj xml patch --db <path> --out <file>` | 4b | Patch prior XML preserving TrackIDs |
| `tagslut dj role` | 3 | DJ set role assignment subcommands |

---

### 6.3 MP3 Commands (Stage 2)

```bash
poetry run tagslut mp3 [subcommand]
```

| Command | Stage | Purpose |
|---------|-------|---------|
| `tagslut mp3 build --db <path> --dj-root <path> [--execute]` | 2a | Transcode FLAC to MP3 from canonical masters |
| `tagslut mp3 reconcile --db <path> --mp3-root <path> [--execute]` | 2b | Register existing MP3s without re-transcoding |

---

### 6.4 Gig Commands

```bash
poetry run tagslut gig [subcommand]
```

| Command | Purpose |
|---------|---------|
| `tagslut gig build --name <name> --filter <expr> --usb <path> --db <path>` | Build gig set with filter |
| `tagslut gig list --db <path>` | List saved gig sets |
| `tagslut gig apply-rekordbox-overlay --input-xml <file> --output-xml <file>` | Apply Rating/Colour overlay |

---

### 6.5 Intake Commands (Stage 1)

```bash
poetry run tagslut intake [provider-url]
```

Primary method for canonical master ingestion; all 4-stage DJ pipelines start here.

---

## 7. PIPELINE WORKFLOWS

### 7.1 Canonical 4-Stage DJ Pipeline

```bash
# Stage 1: Intake/refresh canonical masters
poetry run tagslut intake <provider-url>

# Stage 2a: Build MP3s from canonical identities
poetry run tagslut mp3 build \
  --db "$TAGSLUT_DB" \
  --dj-root "$DJ_LIBRARY" \
  --execute

# OR Stage 2b: Reconcile existing DJ MP3s
poetry run tagslut mp3 reconcile \
  --db "$TAGSLUT_DB" \
  --mp3-root "$DJ_LIBRARY" \
  --execute

# Stage 3a: Admit verified MP3s
poetry run tagslut dj backfill --db "$TAGSLUT_DB"

# Stage 3b: Validate DJ library state
poetry run tagslut dj validate --db "$TAGSLUT_DB"

# Stage 4a: Emit Rekordbox XML (initial)
poetry run tagslut dj xml emit \
  --db "$TAGSLUT_DB" \
  --out rekordbox.xml

# Stage 4b: Patch Rekordbox XML (after changes)
poetry run tagslut dj xml patch \
  --db "$TAGSLUT_DB" \
  --out rekordbox_v2.xml
```

### 7.2 Legacy Wrapper (Deprecated)

**Command:**
```bash
tools/get <provider-url> --dj
```

**Issues:**
- Emits deprecation warning
- Non-deterministic (depends on precheck inventory state)
- Two divergent code paths: `build_pool_v3.py` vs. `precheck_inventory_dj.py`
- **Do not use for new work**

---

## 8. ERROR HANDLING & VALIDATION

### 8.1 DJ Validation Points

| Stage | Validation | Command |
|-------|-----------|---------|
| 3 | Pre-admit checks | `tagslut dj validate` |
| 4 | Pre-emit validation | Built into `tagslut dj xml emit` |

### 8.2 Blocking Issues

| Issue | Resolution |
|-------|------------|
| Missing MP3 file | `tagslut dj validate --report` → locate missing file |
| Duplicate MP3 path | Consolidate to single `mp3_asset.path` |
| Missing metadata | Use enrichment to backfill BPM, key, etc. |
| Admission conflicts | Review `reconcile_log` for decision trace |

---

## 9. EXTENSION POINTS

### 9.1 Custom DJ Curation Policies

Create a YAML file matching `DjCurationConfig` structure:

```yaml
duration_min: 180
duration_max: 720
bpm_min: 100
bpm_max: 175
dj_genres:
  - house
  - tech house
  - techno
artist_blocklist:
  - artist_to_skip
```

Pass via:
```bash
export DJ_REVIEW_POLICY="path/to/policy.yaml"
```

### 9.2 Custom Rekordbox Overlay Config

`config/gig_overlay_rules.yaml` defines Rating/Colour heuristics for gig prep.

### 9.3 Track Overrides CSV

`config/dj/track_overrides.csv` — manual verdicts (safe/block/review) for specific tracks.

---

## 10. SUMMARY TABLE: FILES BY CATEGORY

### Code Files
- **Core DJ:** 11 modules in `tagslut/dj/`
- **MP3 Build:** `tagslut/exec/mp3_build.py`
- **Gig Builder:** `tagslut/exec/gig_builder.py`
- **Rekordbox:** 2 modules in `tagslut/adapters/rekordbox/`
- **Enrichment:** 5+ modules in `tagslut/metadata/`
- **CLI:** 5 command files in `tagslut/cli/commands/`

### Documentation Files
- **Canonical Reference:** 3 files (`DJ_PIPELINE.md`, `DJ_WORKFLOW.md`, `DJ_POOL.md`)
- **Audit & Analysis:** 4 files in `docs/audit/`
- **Agent Rules:** 3 files (`AGENT.md`, `CLAUDE.md`, `.claude/CLAUDE.md`)

### Test Files
- **End-to-end:** 2 files
- **CLI commands:** 3 files
- **Features:** 7 files
- **Rekordbox:** 4 files
- **MP3/Enrichment:** 8 files
- **Schema:** 5 files
- **Total:** 29+ test modules

### Database Schema
- **Core DJ tables:** 6 tables (`mp3_asset`, `dj_admission`, `dj_track_id_map`, `dj_playlist`, `dj_playlist_track`, `dj_export_state`, `reconcile_log`)
- **Migrations:** 2 primary DJ migrations (`0009`, `0010`)

### Scripts
- **Legacy wrappers:** 2 scripts (`tools/get`, `tools/get-intake`)
- **DJ tools:** 3 scripts (`build_special_pool_from_m3u.py`, `build_rekordbox_xml_from_pool.py`, `build_pool_v3.py`)
- **Metadata:** 5+ scripts

---

## 11. KEY DEPENDENCIES

### Internal
- **tagslut.storage.models** — DJ roles, constants
- **tagslut.storage.schema** — DB connection, transactions
- **tagslut.exec.transcoder** — MP3 encoding
- **tagslut.metadata.providers** — Beatport, TIDAL enrichment
- **tagslut.filters.gig_filter** — DJ filter expression parser

### External
- **mutagen** — MP3/FLAC tag reading/writing
- **openpyxl** — XLSX manifest parsing
- **click** — CLI framework
- **pyyaml** — YAML configuration loading
- **pyrekordbox** — Rekordbox USB database reading
- **essentia** — Audio analysis (BPM, key, energy)
- **keyfinder-cli** — Camelot key detection

---

## 12. KNOWN ISSUES & TODOS

| Issue | Status | Impact |
|-------|--------|--------|
| `tools/get --dj` non-determinism | DOCUMENTED | Use canonical 4-stage pipeline |
| `files.dj_pool_path` legacy column | DEPRECATED | Data migrated to `mp3_asset` table |
| Resume mode DJ path complexity | UNDER REVIEW | See `.github/prompts/resume-refresh-fix.prompt.md` |
| Missing Lexicon Dj backfill completeness | IN PROGRESS | Some fields remain unlinked |
| Rekordbox prep script location | KNOWN | Must be at repo root as `rekordbox_prep_dj.py` |

---

## 13. NEXT STEPS FOR CONTRIBUTOR

1. **Learn the pipeline:** Read [docs/DJ_PIPELINE.md](docs/DJ_PIPELINE.md) (5 min)
2. **Review schema:** Inspect `mp3_asset`, `dj_admission` tables in [tagslut/storage/migrations/0010_add_dj_pipeline_tables.sql](tagslut/storage/migrations/0010_add_dj_pipeline_tables.sql)
3. **Trace an admission:** Follow `tagslut dj backfill` through [tagslut/cli/commands/dj.py](tagslut/cli/commands/dj.py) → [tagslut/dj/admission.py](tagslut/dj/admission.py)
4. **Run tests:** `poetry run pytest tests/dj/test_dj_pipeline_e2e.py -v`
5. **Check audit:** [docs/audit/DJ_WORKFLOW_AUDIT.md](docs/audit/DJ_WORKFLOW_AUDIT.md) for known divergences and architectural decisions

---

**End of Architecture Map**
