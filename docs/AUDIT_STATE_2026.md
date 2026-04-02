# Tagslut Repo Audit — 2026-04-02

## 0. Audit Metadata
- Date: 2026-04-02
- Branch: `dev`
- Last commit (hash + message): `c91e175` `Refactor tools/get and tools/get-help for improved usage clarity and functionality; add audit_xml.py for Rekordbox XML processing; introduce executive summary documentation for API proposal and implementation roadmap.`
- Auditor: Codex GPT-5.4

## 1. Repo Surface Summary
- Repo root audited from: `/Users/georgeskhawam/Projects/tagslut`
- Environment bootstrap: `source env_exports.sh 2>/dev/null || true` succeeded. It set DB and library roots. Secret material printed by that loader was intentionally omitted from this report.
- Key audited surfaces present:
  - `tagslut/cli/commands/`
  - `tagslut/exec/intake_orchestrator.py`
  - `tagslut/metadata/providers/`
  - `tagslut/storage/v3/schema.py`
  - `tagslut/storage/v3/migrations/0006_track_identity_phase1.py` through `0015_dj_validation_state_audit.py`
  - `config/providers.toml`
  - `tools/get`
  - `tools/get-intake`
  - `tools/get-help`
  - `tools/enrich`
  - `docs/archive/reference/Technical Whitepaper Personal TIDAL Metadata Tagger.md`
  - `docs/archive/reference/Technical Whitepaper Building a Personal Beatport Metadata Tagger Using the Unofficial v4 API.md`
  - `docs/archive/reference/Technical Whitepaper Personal Qobuz Metadata Tagger.md`
- Key audited absences:
  - `tagslut/providers/` — ABSENT
  - `docs/archive/reference/tagslut_Provider_Architecture_Assessment_for_Qobuz__TIDAL__Beatport.md` — ABSENT
  - `tagslut/api/` — ABSENT
  - `alembic/versions/` — ABSENT
  - `dj-download.sh` — ABSENT
- Most common file types from the exact inventory walk, excluding `.git`, `node_modules`, `__pycache__`, and `.venv`:
  - `.json`: 3795
  - `.py`: 737
  - `.csv`: 558
  - `.md`: 372
  - no extension: 181
  - `.jsonl`: 146
  - `.txt`: 139
  - `.log`: 84
  - `.sh`: 26
  - `.sql`: 19
  - `.toml`: 7
- Structural health verdict: MIXED. Active code exists, but active operator surfaces, legacy wrappers, archived documents, and old DJ/XML assumptions are interleaved. The repo does not present a single authoritative current state.
- `AGENT.md` and `CLAUDE.md` both describe `ts-get` / `ts-enrich` / `ts-auth` as active wrappers and describe the 4-stage DJ/XML pipeline as retired. Active CLI code and active docs do not fully match that claim.
- `.github/prompts/` exists and includes current provider/auth prompts, including TIDAL logout, Qobuz routing, and ReccoBeats provider work items.

### Git Log (last 30)
```text
c91e175 Refactor tools/get and tools/get-help for improved usage clarity and functionality; add audit_xml.py for Rekordbox XML processing; introduce executive summary documentation for API proposal and implementation roadmap.
102cde5 chore(prompts): add mp3-consolidate prompt
f7c18b9 docs: update agent instructions to ts-get/ts-enrich/ts-auth
e700152 docs: archive root stray test shim
ee0b340 docs: archive remaining reference and report artifacts
6c6560c docs: collapse active surface to three docs and archive the rest
07da89f docs: consolidate operator docs and archive legacy guides
c47a135 docs: align ops and credentials with April 2026 workflow
800d64b docs: archive stale docs, refresh operator guides to April 2026
e539c98 chore(prompts): add docs-housekeeping-2026-04b prompt
483b9e8 fix(qobuz): pass --no-db to streamrip so previously-logged tracks aren't skipped
5d16a76 feat(intake): add playlist name option for DJ pool M3U generation
fd65df5 chore(prompts): add dj-pool-named-m3u prompt
4554fef fix(qobuz): use --config-path flag for streamrip (not --config)
5a0a257 fix(auth): qobuz sync is now one-way tagslut→streamrip; fix SSL issue in session check using requests
da6c848 fix(auth): qobuz refresh now validates session and surfaces expiry with re-login instruction
db9a7d4 fix(enrich): clarify mode label to 'Fill gaps' instead of 'Retry'
b65b949 fix(auth): beatport sync now attempts token refresh before copying stale credentials
b79855a fix(START_HERE): update quick commands to current workflow, fix DJ_LIBRARY default to MP3_LIBRARY
70e9da7 feat(mp3): add commands to register MP3 files and fix tags from filenames
dd54cf9 chore(prompts): add fix-mp3-tags-from-filenames and register-mp3-only prompts (C then B chain)
352bfc1 chore(prompts): add register-mp3-only prompt
6f47f77 feat(mp3): update MP3 asset management to use canonical root; add provenance tracking
26b4dca chore(auth): update script permissions to make it executable
364743d docs: add initial workplan for April 2026 with repo audit and enrichment phases
8410b83 docs: sync ROADMAP, COMMAND_GUIDE, DOWNLOAD_STRATEGY to April 2026 state; archive completed prompts; move whitepapers to docs/reference
3874845 chore(prompts): add docs-housekeeping-2026-04 prompt
39f0c50 fix(beatport): restore beatportdl download routing, replace hard error with actual download
b27b2a6 docs: add 2-day plan to session report
798cf76 docs: session report 2026-04-01
```

### Git Status
```text
## dev...origin/dev
```

## 2. Migration Chain
- `0001`–`0005` are embedded in `schema.py` initial DDL, not discrete migration files — by design.

| number | file | description | tables affected | confidence tier correct? |
|---|---|---|---|---|
| 0006 | `0006_track_identity_phase1.py` | Adds phase-1 canonical and provider ID columns to `track_identity`, including `merged_into_id`. | `track_identity` | N/A |
| 0007 | `0007_track_identity_phase1_rename.py` | Renames `label` -> `canonical_label`, `catalog_number` -> `canonical_catalog_number`, and `canonical_duration_s` -> `canonical_duration`. | `track_identity` | N/A |
| 0008 | `0008_asset_analysis.py` | Adds `asset_analysis` table and DJ export views. | `asset_analysis`, views | N/A |
| 0009 | `0009_chromaprint.py` | Adds Chromaprint fingerprint columns to `asset_file`. | `asset_file` | N/A |
| 0010 | `0010_track_identity_provider_uniqueness.py` | Adds active-provider uniqueness indexes for `beatport_id`, `tidal_id`, `qobuz_id`, `spotify_id`. | `track_identity` | N/A |
| 0011 | `0011_track_identity_provider_uniqueness_hardening.py` | Adds more provider uniqueness hardening for `apple_music_id`, `deezer_id`, `traxsource_id`. | `track_identity` | N/A |
| 0012 | `0012_ingestion_provenance.py` | Adds `ingested_at`, `ingestion_method`, `ingestion_source`, `ingestion_confidence`; backfills nulls; adds indexes and trigger. | `track_identity`; provenance columns | NO. It adds provenance but does not enforce the five-tier `CHECK`; `corroborated` is absent here. |
| 0013 | `0013_confidence_tier_update.py` | Rebuilds `track_identity`, preserves indexes, and enforces five-tier `ingestion_confidence` plus ingestion-method `CHECK`s. | `track_identity`; provenance columns | YES |
| 0014 | `0014_dj_validation_state.py` | Creates `dj_validation_state` with `state_hash`, `passed`, and `validated_at`. | `dj_validation_state` | N/A |
| 0015 | `0015_dj_validation_state_audit.py` | Adds audit fields `issue_count` and `summary` to `dj_validation_state`. | `dj_validation_state` | N/A |

## 3. Schema vs Migration Consistency
- `track_identity` current schema coverage by the audited v3 chain: YES. `0006`, `0007`, `0010`, `0011`, `0012`, and `0013` together cover the current post-0005 `track_identity` surface.
- `asset_file` current audited delta coverage: YES. `0009` adds the current Chromaprint columns.
- `asset_link` audited delta coverage in `0006`–`0015`: GAP. No audited v3 migration touches `asset_link`; its current shape depends on the pre-`0006` base.
- `files` audited delta coverage in `0006`–`0015`: GAP. No audited v3 migration touches `files`; its current shape depends on the pre-`0006` base.
- Columns in `schema.py` not covered by any audited `0006`–`0015` migration: NO. Current post-0005 additions visible in `schema.py`, including `spotify_id`, `canonical_mix_name`, provenance columns, `dj_validation_state`, `issue_count`, and `summary`, are all covered by at least one audited migration.
- Migrations that reference columns not present in current `schema.py`: YES, but they are transitional, not dangling. `0006` references pre-rename columns `label`, `catalog_number`, and `canonical_duration_s`; `0007` immediately renames them.
- Provenance columns on `track_identity`: YES. `0012` adds `ingested_at`, `ingestion_method`, `ingestion_source`, and `ingestion_confidence`; `0013` hardens them with `CHECK` constraints and a table rebuild.
- `0013` CHECK constraint for the five-tier confidence vocabulary: YES. `tagslut/storage/v3/migrations/0013_confidence_tier_update.py:59-60` uses `('verified','corroborated','high','uncertain','legacy')`.
- `0014` vs `0015` numbering discrepancy: RESOLVED. `0014` creates `dj_validation_state`; `0015` adds `issue_count` and `summary`. There is no numbering mismatch in code.
- `schema.py` state matches the final audited v3 chain endpoint: YES. `tagslut/storage/v3/schema.py:12` sets `V3_SCHEMA_VERSION = 15`, and the table/view/index definitions match the `0015` endpoint.

## 4. Provider Architecture
| provider | active | capabilities in code | e2e callable? | gaps vs whitepaper |
|---|---|---|---|---|
| `beatport` | YES. `config/providers.toml:6-9` has `metadata_enabled=true`, `download_enabled=false`, `trust="dj_primary"`. | `METADATA_FETCH_TRACK_BY_ID`, `METADATA_SEARCH_BY_ISRC`, `METADATA_SEARCH_BY_TEXT`, `METADATA_FETCH_ARTWORK`; provider maps BPM, key, genre, sub-genre, label, mix name, ISRC, artwork. | YES, metadata-only. | Camelot conversion is not explicit in code. Whitepaper says metadata authority only; config matches that because download is disabled. |
| `tidal` | YES. `config/providers.toml:11-14` has `metadata_enabled=true`, `download_enabled=true`, `trust="secondary"`. | `METADATA_FETCH_TRACK_BY_ID`, `METADATA_SEARCH_BY_ISRC`, `METADATA_SEARCH_BY_TEXT`, `METADATA_EXPORT_PLAYLIST_SEED`, `METADATA_FETCH_ARTWORK`; provider maps ISRC, release date, duration, explicit, audio quality, copyright, key, and a `bpm` field. | YES, metadata plus playlist-seed export. | No `albumartist` or `discnumber` mapping was found. Whitepaper says BPM is not available from TIDAL API, but code still maps `attributes.get("bpm")` at `tagslut/metadata/providers/tidal.py:321`. |
| `qobuz` | YES. `config/providers.toml:1-4` has `metadata_enabled=true`, `download_enabled=false`, `trust="secondary"`. | `METADATA_FETCH_TRACK_BY_ID`, `METADATA_SEARCH_BY_ISRC`, `METADATA_SEARCH_BY_TEXT`, `METADATA_FETCH_ARTWORK`; provider maps ISRC, label, release date, composer, genre, explicit, artwork, and track number. | YES, metadata-only. | No UPC, work, or replay-gain mapping was found. Whitepaper and older docs describe genre as not yet wired, but code implements it at `tagslut/metadata/providers/qobuz.py:179-185` and `:213`. |
| `reccobeats` | `config/providers.toml` section is ABSENT. Effective default is active through `DEFAULT_ACTIVE_PROVIDERS` in `tagslut/metadata/provider_registry.py:64`. | `METADATA_FETCH_TRACK_BY_ID`, `METADATA_SEARCH_BY_ISRC`; implements ISRC -> UUID -> `/audio-features` two-step. | YES, but only for ISRC-based audio-feature lookup. | No config section, no trust override, no text search, no artwork. It is not scaffold-only, but it is narrow. |

- Enrichment eligibility condition: `WHERE (flac_ok = 1 OR flac_ok IS NULL)` in `tagslut/metadata/store/db_reader.py:116`.
- `provider_registry.py` vs hard-coded `Enricher` mapping: RESOLVED. `tagslut/metadata/enricher.py:91` uses `resolve_active_metadata_providers(...)`, and `:107` resolves provider classes via `get_provider_class(...)`.
- `provider_state.py` eight-state implementation: PARTIAL. The enum defines all eight states at `tagslut/metadata/provider_state.py:28-31`, but the code does not actually model `enabled_subscription_inactive` anywhere.
- `do_not_use_for_canonical` support: PRESENT in registry typing and defaults. `tagslut/metadata/provider_registry.py:35` defines it as a trust literal, and the default Qobuz config uses it internally at `:55`. The active file config overrides Qobuz to `secondary`.
- Qobuz genre enrichment: IMPLEMENTED.
- ReccoBeats endpoint: correct plural. `tagslut/metadata/providers/reccobeats.py:93` uses `https://api.reccobeats.com/v1/audio-features`.

## 5. Auth and Token Management
| item | status | evidence |
|---|---|---|
| `tagslut auth` group with TIDAL `login` and `logout` | PARTIAL | `tagslut/cli/commands/auth.py:37-38` defines `auth`; `:198` defines `login`. No `logout` subcommand is registered. |
| TIDAL auth delegation via `tiddl` subprocess | IMPLEMENTED | `tagslut/cli/commands/auth.py:243-247` runs `tiddl auth login`; `:165-169` runs `tiddl auth refresh`; both then call `sync_from_tiddl()`. |
| Direct TIDAL token import from `~/.tiddl/auth.json` | IMPLEMENTED | `tagslut/metadata/auth.py:405` defines `sync_from_tiddl()`. The audit did not read the file itself. |
| TokenManager credential store path `~/.config/tagslut/tokens.json` | IMPLEMENTED | `tagslut/metadata/auth.py:26` defines `DEFAULT_TOKENS_PATH = Path.home() / ".config" / "tagslut" / "tokens.json"`. |
| Qobuz credential auto-refresh wired before every enrich run | PARTIAL | `tools/enrich:38` runs `tools/auth all` before `tagslut index enrich`. Direct enrich entrypoints do not do this. `tagslut/exec/intake_orchestrator.py:1503-1516` runs `tools/review/post_move_enrich_art.py` directly, with no Qobuz refresh call in that path. |
| Qobuz bundle.js scraping implementation | IMPLEMENTED | `tagslut/metadata/qobuz_credential_extractor.py` exists and scrapes bundle URLs, direct keys, and `initialSeed(...)` payloads. |
| Qobuz app credential refresh implementation | IMPLEMENTED | `tagslut/metadata/auth.py:305` defines `refresh_qobuz_app_credentials()`. |
| Qobuz session use before provider calls | IMPLEMENTED | `tagslut/metadata/providers/qobuz.py:36`, `:51`, and `:61` call `ensure_qobuz_token()`. |

## 6. CLI and Pipeline
### Command Inventory
| command | group | purpose | tested? |
|---|---|---|---|
| `auth` | root | Auth/token command group. | YES |
| `token-get` | root | Print a stored provider token. | YES |
| `auth status` | `auth` | Show provider auth state. | YES |
| `auth init` | `auth` | Initialize auth/token state. | YES |
| `auth refresh` | `auth` | Refresh provider auth state. | YES |
| `auth token-get` | `auth` | Print a stored provider token from inside the group. | YES |
| `auth login` | `auth` | Login a provider; TIDAL delegates to `tiddl`, Qobuz uses scraped app creds. | YES |
| `decide` | root | Decision-engine command group. | YES |
| `decide profiles` | `decide` | Show decision profiles. | YES |
| `decide plan` | `decide` | Build a decision plan. | YES |
| `dj` | root | DJ workflow command group. | YES |
| `dj curate` | `dj` | Preview DJ curation from a manifest. | YES |
| `dj export` | `dj` | Curate and transcode DJ output from a manifest. | YES |
| `dj prep-rekordbox` | `dj` | Prepare a curated folder for Rekordbox. | YES |
| `dj lexicon` | `dj` | Lexicon helper subgroup. | YES |
| `dj lexicon status` | `dj lexicon` | Show Lexicon sync/status information. | YES |
| `dj lexicon estimate` | `dj lexicon` | Estimate Lexicon push/update work. | YES |
| `dj lexicon csv` | `dj lexicon` | Export Lexicon-oriented CSV output. | YES |
| `dj lexicon push` | `dj lexicon` | Push Lexicon data. | YES |
| `dj classify` | `dj` | Score tracks into safe/block/review buckets. | YES |
| `dj review-app` | `dj` | Launch the DJ review web app. | YES |
| `dj gig-prep` | `dj` | Build gig-focused DJ export material. | YES |
| `dj crates` | `dj` | Crate management subgroup. | YES |
| `dj crates list` | `dj crates` | List crates. | YES |
| `dj crates show` | `dj crates` | Show one crate. | YES |
| `dj crates move` | `dj crates` | Move tracks between crates. | YES |
| `dj crates retag` | `dj crates` | Retag crate contents. | YES |
| `dj crates export` | `dj crates` | Export crate output. | YES |
| `dj pool-wizard` | `dj` | Plan or build a DJ pool from curated-library state. | YES |
| `dj admit` | `dj` | Admit one verified MP3 into DJ state. | YES |
| `dj backfill` | `dj` | Auto-admit all verified MP3s into DJ state. | YES |
| `dj validate` | `dj` | Validate DJ library state and record hash/audit status. | YES |
| `dj xml` | `dj` | XML subgroup for Rekordbox emit/patch. | YES |
| `dj xml emit` | `dj xml` | Emit Rekordbox XML from admitted tracks. | YES |
| `dj xml patch` | `dj xml` | Patch a prior Rekordbox XML export. | YES |
| `execute` | root | Move-plan execution group. | YES |
| `execute move-plan` | `execute` | Execute a move plan. | YES |
| `execute quarantine-plan` | `execute` | Execute a quarantine plan. | YES |
| `execute promote-tags` | `execute` | Promote tags. | YES |
| `export` | root | Export command group. | YES |
| `export usb` | `export` | Perform USB export. | YES |
| `gig` | root | Gig workflow command group. | YES |
| `gig build` | `gig` | Build a gig selection. | YES |
| `gig list` | `gig` | List gigs. | YES |
| `gig status` | `gig` | Show gig status. | YES |
| `gig apply-rekordbox-overlay` | `gig` | Apply rating/colour overlay to Rekordbox XML. | YES |
| `index` | root | Inventory/index command group. | YES |
| `index register` | `index` | Register downloaded files. | YES |
| `index check` | `index` | Run index consistency checks. | YES |
| `index register-mp3` | `index` | Register MP3 files against the DB. | YES |
| `index duration-check` | `index` | Check duration mismatches. | YES |
| `index duration-audit` | `index` | Audit durations. | YES |
| `index set-duration-ref` | `index` | Set duration reference values. | YES |
| `index promote-classification` | `index` | Promote classification results. | YES |
| `index enrich` | `index` | Enrich indexed files from metadata providers. | YES |
| `index dj-flag` | `index` | Set a DJ flag. | YES |
| `index dj-autoflag` | `index` | Auto-flag DJ candidates. | YES |
| `index dj-status` | `index` | Show DJ flag status. | YES |
| `intake` | root | Canonical intake command group. | YES |
| `intake url` | `intake` | Intake one provider URL through precheck/download/promote/tag/mp3/dj logic. | YES |
| `intake resolve` | `intake` | Resolve URL or intake intent. | YES |
| `intake run` | `intake` | Run intake from a prepared request. | YES |
| `intake prefilter` | `intake` | Prefilter intake cohort. | YES |
| `intake process-root` | `intake` | Process an existing root. | YES |
| `lexicon` | root | Lexicon import/reconcile group. | YES |
| `lexicon import` | `lexicon` | Import Lexicon track metadata. | YES |
| `lexicon import-playlists` | `lexicon` | Import Lexicon playlists. | YES |
| `library` | root | Library utilities group. | YES |
| `library import-rekordbox` | `library` | Import Rekordbox XML into the DB. | YES |
| `master` | root | MASTER_LIBRARY operations group. | YES |
| `master scan` | `master` | Scan MASTER_LIBRARY and register `asset_file` rows. | YES |
| `tidal-seed` | root | Export TIDAL playlist seed rows. | YES |
| `beatport-enrich` | root | Enrich from Beatport outside the grouped CLI. | YES |
| `beatport-seed` | root | Export Beatport seed rows. | YES |
| `tidal-enrich` | root | Enrich from TIDAL outside the grouped CLI. | YES |
| `canonize` | root | Hidden canonicalization command. | YES |
| `show-zone` | root | Hidden zone display command. | YES |
| `explain-keeper` | root | Hidden keeper-explanation command. | YES |
| `enrich-file` | root | Hidden single-file enrich command. | YES |
| `init` | root | Initialize misc/root setup state. | YES |
| `mp3` | root | MP3 derivative command group. | YES |
| `mp3 build` | `mp3` | Build MP3 derivatives from canonical FLAC masters. | YES |
| `mp3 reconcile` | `mp3` | Reconcile an MP3 root against canonical identities. | YES |
| `mp3 scan` | `mp3` | Scan MP3 roots and write a manifest CSV. | YES |
| `mp3 reconcile-scan` | `mp3` | Reconcile a scan CSV against the DB. | YES |
| `mp3 missing-masters` | `mp3` | Report orphaned MP3s and FLACs without MP3s. | YES |
| `ops` | root | Operational maintenance group. | YES |
| `ops run-move-plan` | `ops` | Execute a move plan. | YES |
| `ops plan-dj-library-normalize` | `ops` | Plan DJ-library normalization work. | YES |
| `ops relink-dj-pool` | `ops` | Relink DJ pool entries. | YES |
| `ops writeback-canonical` | `ops` | Write canonical tags back to files. | YES |
| `postman` | root | Postman integration group. | NO |
| `postman ingest` | `postman` | Ingest Postman content. | NO |
| `provider` | root | Provider status group. | YES |
| `provider status` | `provider` | Show provider activation/auth status. | YES |
| `report` | root | Report command group. | YES |
| `report m3u` | `report` | Emit/report M3U data. | YES |
| `report duration` | `report` | Report duration mismatches or summaries. | YES |
| `report plan-summary` | `report` | Summarize a plan artifact. | YES |
| `report dj-review` | `report` | Launch or summarize DJ review output. | YES |
| `scan` | root | Hidden scan queue/orchestration group. | YES |
| `scan enqueue` | `scan` | Enqueue scan work. | YES |
| `scan run` | `scan` | Run scan work. | YES |
| `scan status` | `scan` | Show scan status. | YES |
| `scan issues` | `scan` | Show scan issues. | YES |
| `scan report` | `scan` | Report scan output. | YES |
| `tag` | root | Tag workflow group. | YES |
| `tag fetch` | `tag` | Fetch tag candidates. | YES |
| `tag batch-create` | `tag` | Create batch tag work. | YES |
| `tag review` | `tag` | Review tag proposals. | YES |
| `tag apply` | `tag` | Apply chosen tags. | YES |
| `tag export` | `tag` | Export tag data. | YES |
| `tag sync-to-files` | `tag` | Sync tag data back to files. | YES |
| `v3` | root | V3 data-model group. | YES |
| `v3 provenance` | `v3` | Provenance subgroup. | YES |
| `v3 provenance show` | `v3 provenance` | Show provenance for a record. | YES |
| `verify` | root | Verification group. | YES |
| `verify duration` | `verify` | Verify duration expectations. | YES |
| `verify parity` | `verify` | Verify parity conditions. | YES |
| `verify receipts` | `verify` | Verify execution receipts. | YES |

### Active Pipeline Checklist
- `tools/enrich` exists and functions as a zero-config enrichment wrapper: YES. `tools/enrich:38` refreshes auth via `tools/auth all` and then runs `tagslut index enrich`.
- `tools/get-intake` exists: YES.
- `tools/get-intake` has `--no-download`: YES. `tools/get-intake:104` documents it.
- `tools/get-intake` documents the pre-scan tag-completion limitation: YES. `tools/get-intake:1059-1065` says pre-scan tag completion runs before planning in no-download mode only.
- `--dj` writes two M3U files: PARTIAL. `tagslut/exec/dj_pool_m3u.py:115-165` writes both batch and global M3Us, and `tagslut/cli/commands/intake.py:288-330` calls it. The CLI still passes `dj=False` into `run_intake()` at `tagslut/cli/commands/intake.py:272-280`, so the M3U behavior is implemented in CLI post-processing instead of the orchestrator DJ stage.
- `--tag` exists on `tagslut intake url`: YES. `tagslut/cli/commands/intake.py:154-158`.
- `--tag` is wired through `intake_orchestrator.py` without requiring `--mp3`: YES. `tests/exec/test_intake_orchestrator.py:675-726` covers `tag=True, mp3=False` and asserts enrich runs while MP3 is skipped.
- Unified `tagslut get <url>` command exists: NO. The unified wrapper is `tools/get`, not a `tagslut get` CLI command.
- `tagslut auth login/logout tidal` exists: NO. Login exists; logout does not.
- `--dj-cache-root` is not a current flag: NO. Active code still exposes it at `tagslut/cli/commands/dj.py:1080-1083`.

### `--tag` / `--dj` Gap
- Exact `--tag` help string: `Fully enrich and write back promoted FLACs in MASTER_LIBRARY before any optional MP3/DJ stages.` (`tagslut/cli/commands/intake.py:154-158`)
- Classification: CLEAR.
- Resulting behavior: `--tag` alone enriches promoted FLACs and leaves MP3 and M3U work undone. `tests/exec/test_intake_orchestrator.py:675-726` proves enrich runs and the MP3 stage is skipped with detail `--mp3 not passed`.
- `--tag` accepted without `--mp3-root`: YES. `tests/exec/test_intake_orchestrator.py:566-590` invokes `intake url ... --tag` and asserts `run_intake(... tag=True, mp3=False)` without requiring `--mp3-root`.

### Retired Pipeline Language
| file | line | text | classification |
|---|---:|---|---|
| `tagslut/cli/commands/intake.py` | 164 | `[LEGACY] Convenience shortcut. Prefer the explicit 4-stage DJ pipeline:` | LIVE CODE |
| `tagslut/cli/commands/intake.py` | 240 | `Canonical curated-library flow is the explicit 4-stage pipeline:` | LIVE CODE |
| `tagslut/cli/commands/intake.py` | 243 | `Stage 4 tagslut dj xml emit or tagslut dj xml patch.` | LIVE CODE |
| `tagslut/cli/commands/mp3.py` | 26 | `Part of the 4-stage DJ pipeline:` | LIVE CODE |
| `tagslut/cli/commands/mp3.py` | 159 | `"$DJ_LIBRARY, then $MP3_LIBRARY..."` | LIVE CODE |
| `tagslut/cli/commands/mp3.py` | 186 | `Uses one active MP3 asset root (DJ_LIBRARY aliasing MP3_LIBRARY).` | LIVE CODE |
| `tagslut/cli/commands/mp3.py` | 208 | `or os.environ.get("DJ_LIBRARY")` | LIVE CODE |
| `tagslut/cli/commands/mp3.py` | 214 | `Missing --mp3-root (or set DJ_LIBRARY / MP3_LIBRARY).` | LIVE CODE |
| `tagslut/cli/commands/index.py` | 645 | `default="/Volumes/MUSIC/DJ_LIBRARY"` | LIVE CODE |
| `tagslut/cli/commands/dj.py` | 247 | `DJ library operations (Stages 3 and 4 of the 4-stage pipeline).` | LIVE CODE |
| `tagslut/cli/commands/dj.py` | 1080 | `--dj-cache-root` | LIVE CODE |
| `tagslut/cli/commands/dj.py` | 1083 | `help="DJ_LIBRARY cache root path"` | LIVE CODE |
| `tagslut/metadata/track_db_sync.py` | 212 | `donor_location_like: str = "/Volumes/MUSIC/DJ_LIBRARY/%"` | LIVE CODE |
| `tagslut/exec/lexicon_import.py` | 99 | `For each active Lexicon track in DJ_LIBRARY or DJ_POOL_MANUAL_MP3:` | LIVE CODE |
| `tagslut/exec/lexicon_import.py` | 132 | `location LIKE '/Volumes/MUSIC/DJ_LIBRARY/%'` | LIVE CODE |
| `tagslut/exec/lexicon_import.py` | 133 | `OR location LIKE '/Volumes/MUSIC/DJ_POOL_MANUAL_MP3/%'` | LIVE CODE |
| `tools/get-intake` | 97 | `[LEGACY] --dj is deprecated. Use the 4-stage pipeline.` | LIVE CODE |
| `tools/get-intake` | 98 | `--dj-root PATH DJ MP3 root for legacy wrapper output (default: $DJ_MP3_ROOT or $DJ_LIBRARY)` | LIVE CODE |
| `tools/get-intake` | 788 | `DJ_ROOT="${DJ_MP3_ROOT:-${DJ_LIBRARY:-}}"` | LIVE CODE |
| `tools/get-intake` | 913 | `[LEGACY] --dj is deprecated. Use the 4-stage pipeline.` | LIVE CODE |
| `tools/get-intake` | 1101 | `Missing DJ root. Set --dj-root, DJ_MP3_ROOT, or DJ_LIBRARY.` | LIVE CODE |
| `tools/get-intake` | 1105 | `Missing DJ playlist dir. Set --dj-m3u-dir, DJ_PLAYLIST_ROOT, or DJ_LIBRARY.` | LIVE CODE |
| `tools/get-intake` | 1755 | `DJ mode requires --dj-root or DJ_MP3_ROOT / DJ_LIBRARY to be set` | LIVE CODE |
| `README.md` | 116 | `` `MP3_LIBRARY` is the single canonical active MP3 asset root. `DJ_LIBRARY` `` | DOCUMENTATION ONLY |
| `README.md` | 121 | `Building a curated DJ library follows a deterministic 4-stage pipeline.` | DOCUMENTATION ONLY |
| `README.md` | 152 | `poetry run tagslut dj xml emit --db "$TAGSLUT_DB" --out rekordbox.xml` | DOCUMENTATION ONLY |
| `docs/WORKFLOWS.md` | 25 | `export DJ_LIBRARY="${DJ_LIBRARY:-${DJ_MP3_ROOT:-}}"` | DOCUMENTATION ONLY |
| `docs/WORKFLOWS.md` | 447 | `Lexicon: import folder $DJ_LIBRARY` | DOCUMENTATION ONLY |
| `docs/ARCHITECTURE.md` | 95 | `The canonical downstream DJ path is the explicit 4-stage pipeline.` | DOCUMENTATION ONLY |
| `docs/ARCHITECTURE.md` | 99 | `### Explicit 4-stage pipeline (canonical)` | DOCUMENTATION ONLY |
| `docs/PROJECT_DIRECTIVES.md` | 68 | `/Volumes/MUSIC/DJ_LIBRARY DJ-admitted MP3s (admission-gated subset)` | DOCUMENTATION ONLY |
| `docs/PROJECT_DIRECTIVES.md` | 69 | `/Volumes/MUSIC/DJ_POOL_MANUAL_MP3 Manual DJ pool additions` | DOCUMENTATION ONLY |
| `docs/archive/OPERATIONS.md` | 30 | `` `DJ_LIBRARY` folder is legacy-only; not written by current workflows. `` | DOCUMENTATION ONLY |
| `docs/archive/OPERATIONS.md` | 37 | `4-stage DJ pipeline (backfill/validate/XML emit) and DJ_LIBRARY-based flows are retired.` | DOCUMENTATION ONLY |
| `docs/archive/ROADMAP.md` | 27 | `DJ pool M3U model — replace 4-stage pipeline ← COMPLETE (2026-04-01)` | DOCUMENTATION ONLY |

## 7. Test Coverage
- Exact test inventory commands found `1190` test functions.
- Audited-scope direct coverage:

| test file | module covered | test count | verdict |
|---|---|---:|---|
| `tests/metadata/test_provider_state.py` | `tagslut/metadata/provider_state.py` | 9 | DIRECT COVERAGE |
| `tests/metadata/test_provider_registry_activation.py` | `tagslut/metadata/provider_registry.py`, `tagslut/metadata/enricher.py` | 7 | DIRECT COVERAGE |
| `tests/metadata/test_reccobeats_provider.py` | `tagslut/metadata/providers/reccobeats.py` | 7 | DIRECT COVERAGE |
| `tests/metadata/test_qobuz_credential_extractor.py` | `tagslut/metadata/qobuz_credential_extractor.py` | 2 | DIRECT COVERAGE |
| `tests/metadata/store/test_db_reader.py` | `tagslut/metadata/store/db_reader.py` | 3 | DIRECT COVERAGE |
| `tests/metadata/test_token_manager.py` | `tagslut/metadata/auth.py` | 8 | DIRECT COVERAGE |
| `tests/cli/test_auth_token_get.py` | `tagslut/cli/commands/auth.py` | 5 | DIRECT COVERAGE |
| `tests/exec/test_intake_orchestrator.py` | `tagslut/exec/intake_orchestrator.py`, `tagslut/cli/commands/intake.py` | 25 | DIRECT COVERAGE |
| `tests/tools/test_get_intake.py` | `tools/get-intake` | 7 | DIRECT COVERAGE |
| `tests/exec/test_get_intake_m3u_contract.py` | `tools/get-intake` M3U behavior | 4 | DIRECT COVERAGE |
| `tests/exec/test_get_intake_console_render.py` | `tools/get-intake` console rendering | 6 | DIRECT COVERAGE |

- Audited implementation files with zero test coverage:
  - `tagslut/metadata/providers/tagslut_api_client.py`
  - `tagslut/metadata/providers/tagslut_validation.py`
  - `tagslut/cli/commands/postman.py`
  - `tagslut/cli/commands/track_hub_cli.py`
  - `tools/get-help`
- Test files importing paths that no longer exist:
  - `tests/archive/scan/test_orchestrator.py:12` imports `tagslut.scan.orchestrator`
  - `tests/archive/scan/test_validate.py:10` imports `tagslut.scan.validate`
  - `tests/archive/scan/test_integration.py:10` imports `tagslut.scan.dedupe`
  - `tests/archive/scan/test_integration.py:11` imports `tagslut.scan.orchestrator`
  - `tests/archive/scan/test_tags_and_archive.py:14` imports `tagslut.scan.archive`
  - `tests/archive/scan/test_tags_and_archive.py:15` imports `tagslut.scan.tags`
  - `tests/archive/scan/test_classify_and_dedupe.py:11` imports `tagslut.scan.classify`
  - `tests/archive/scan/test_classify_and_dedupe.py:12` imports `tagslut.scan.dedupe`
  - `tests/archive/scan/test_isrc.py:6` imports `tagslut.scan.isrc`
- `tests/exec/test_intake_orchestrator.py` coverage of required `--tag` cases:
  - `--tag` accepted without `--mp3-root`: YES
  - `--tag` runs enrich while MP3 remains skipped: YES

## 8. Rekordbox Integration
- `master.db` awareness: ABSENT. `~/Library/Pioneer/rekordbox/master.db` exists on this workstation, but no audited code reads or writes that path.
- M3U emission: IMPLEMENTED. `tagslut/exec/dj_pool_m3u.py:115-165` writes both a batch playlist and `MP3_LIBRARY/dj_pool.m3u`.
- 75-entry cleanup task: DOCUMENTED. `docs/SESSION_REPORT_2026-04-01.md:188` explicitly says `Rekordbox: delete the 75 missing entries from the collection`.
- Additional Rekordbox facts:
  - Active code reads and writes Rekordbox XML via `tagslut/dj/xml_emit.py`, `tagslut/exec/dj_xml_emit.py`, and `library import-rekordbox`.
  - This audit found no direct `master.db` integration in the active code surface.

## 9. Dependency Health
- Declared runtime dependencies that appear unused in the audited non-archive code paths:
  - `jsonschema`
  - `pandas`
  - `unidecode`
  - `roonapi`
  - `pydantic`
  - `matplotlib`
  - `psycopg`
- Third-party imports present in audited code but not declared in `project.dependencies`:
  - `requests` — used in `tools/get:443`, `:459`, `:551`, `:566`; `tagslut/metadata/qobuz_credential_extractor.py:9`; `tagslut/metadata/providers/tagslut_validation.py:8`
  - `psutil` — used in `tagslut/utils/io_monitor.py:7`
- Flask presence:
  - `pyproject.toml:37-39` defines Flask only as optional extra `web = ["flask>=3.1.2,<4.0.0"]`
  - `tagslut/_web/review_app.py:19-24` imports Flask
  - `tools/dj_review_app.py` calls the Flask-backed review app
  - `flask-smorest` is ABSENT from dependencies and ABSENT from code imports
- Migration stack inconsistency:
  - `alembic` is declared runtime dependency
  - `alembic/versions/` is ABSENT
  - Active v3 migration chain is custom Python migration code under `tagslut/storage/v3/migrations/`

## 10. Planning Document Cross-Reference
### 10.1 TIDAL Whitepaper
| Feature / Section | Implementation Status | Notes / Contradictions |
|---|---|---|
| OAuth login/refresh via delegated local client | IMPLEMENTED | `tagslut auth login tidal` and `tagslut auth refresh tidal` shell out to `tiddl` and then sync imported tokens. |
| ISRC search and direct track fetch | IMPLEMENTED | `tagslut/metadata/providers/tidal.py` supports both fetch-by-ID and ISRC search. |
| Metadata fields: ISRC, title, artist, release date, duration, explicit, audio quality, copyright | IMPLEMENTED | Code maps these at `tagslut/metadata/providers/tidal.py:318-328`. |
| Metadata fields: albumartist, discnumber | UNIMPLEMENTED | No mapping for `albumartist` or `discnumber` was found. |
| BPM is not available from TIDAL API | CONTRADICTS CODE | Provider still maps `bpm=attributes.get("bpm")` at `tagslut/metadata/providers/tidal.py:321`. |
| Playlist seed export | IMPLEMENTED | `METADATA_EXPORT_PLAYLIST_SEED` exists and the playlist export path is implemented. |

### 10.2 Beatport Whitepaper
| Feature / Section | Implementation Status | Notes / Contradictions |
|---|---|---|
| Unofficial v4 catalog/search API usage | IMPLEMENTED | Provider uses `/v4/catalog/...` and `/search/v1/tracks`. |
| BPM, key, genre, label, mix name, ISRC, artwork | IMPLEMENTED | Provider maps all of these in `ProviderTrack`. |
| Camelot key output | PARTIAL | Standard key data is present. Explicit Camelot translation was not found in the provider surface audited here. |
| Metadata authority only; not a download source | IMPLEMENTED | `config/providers.toml:6-9` sets `download_enabled = false`. |
| ISRC and text search | IMPLEMENTED | Both are explicitly supported. |

### 10.3 Qobuz Whitepaper
| Feature / Section | Implementation Status | Notes / Contradictions |
|---|---|---|
| Bundle.js credential extraction | IMPLEMENTED | `tagslut/metadata/qobuz_credential_extractor.py` performs bundle URL scraping and seed decoding. |
| API search/fetch with app ID and user auth token | IMPLEMENTED | `tagslut/metadata/providers/qobuz.py` uses `ensure_qobuz_token()` before provider requests. |
| Metadata fields: ISRC, label, release date, composer | IMPLEMENTED | These fields are mapped in `_normalize_track()`. |
| Metadata fields: UPC, work, replay_gain | UNIMPLEMENTED | No mapping for these fields was found. |
| Genre contribution documented as not yet wired | CONTRADICTS CODE | Genre is wired at `tagslut/metadata/providers/qobuz.py:179-185` and `:213`. |
| Auto-refresh before every enrich run | PARTIAL | `tools/enrich` refreshes auth first; direct enrich entrypoints do not. |

### 10.4 Provider Architecture Assessment
- Assessment document file: ABSENT. This section is checklist-only because there is no authoritative in-repo document to compare against.
- `config/providers.toml` key coverage:
  - `metadata_enabled`: YES
  - `download_enabled`: YES
  - `trust`: YES
  - `metadata_precedence_weight`: NO
  - `routing.metadata.precedence`: NO
  - `routing.download.precedence`: ABSENT from `config/providers.toml`
- `provider_registry.py` replaces hard-coded `Enricher` mapping: YES
- `provider_state.py` implements the eight activation states: PARTIAL
- `provider status` CLI command exists: YES (`tagslut/cli/commands/provider.py:21`)
- Stale surfaces listed in the prompt:
  - `tagslut/metadata/README.md`: STALE. It still says only Beatport and TIDAL are active and Qobuz is scaffold-only.
  - `tagslut/metadata/__init__.py` docstring: STALE. It still says Qobuz is scaffold-only and off by default.
  - `dj-download.sh`: ABSENT
  - `tools/get-intake` default `ENRICH_PROVIDERS`: STALE. `tools/get-intake:791` still defaults to `beatport,tidal`.
  - `tagslut/cli/commands/index.py` help text: STALE. `tagslut/cli/commands/index.py:66-68` still describes Qobuz as legacy/future.
- Current provider migration phase `0`–`6`: ABSENT AS DOCUMENTED. There is no authoritative phase marker in the repo because the assessment document itself is absent.

## 11. Immediate Action Items (≤1 week)
1. Fix `intake --dj` orchestration wiring — the CLI advertises DJ-stage behavior but passes `dj=False` into `run_intake()` — `tagslut/cli/commands/intake.py`
2. Remove live `DJ_LIBRARY` / `DJ_POOL_MANUAL_MP3` / `--dj-cache-root` language from active code paths — operator-visible surfaces still advertise retired roots and flags — `tagslut/cli/commands/dj.py`
3. Add or retire `auth logout tidal` explicitly — current auth CLI surface is incomplete relative to expected operator contract — `tagslut/cli/commands/auth.py`
4. Make Qobuz refresh behavior consistent across all enrich entrypoints — wrapper-only refresh creates non-deterministic auth behavior — `tools/enrich`
5. Align provider docs with actual activation state — active docs still describe Qobuz as scaffold-only and omit ReccoBeats — `tagslut/metadata/README.md`
6. Replace stale index/provider help text — active CLI help still describes Qobuz as legacy/future and uses `DJ_LIBRARY` defaults — `tagslut/cli/commands/index.py`

## 12. Short-Term Plan (1–4 weeks)
1. Collapse the active DJ contract onto the M3U model — depends on fixing `intake --dj` and removing live legacy flags — expected outcome: one operator-visible DJ path
2. Normalize provider activation/configuration — depends on deciding the authoritative provider architecture and phase target — expected outcome: config, registry, docs, and CLI all agree
3. Audit and either retire or test wrapper scripts — depends on deciding whether `tools/get-intake` remains supported — expected outcome: no ambiguous wrapper behavior
4. Reconcile active docs with code — depends on locking the real MP3/DJ/Rekordbox contract — expected outcome: `README.md`, `docs/WORKFLOWS.md`, and `docs/ARCHITECTURE.md` stop contradicting each other

## 13. Long-Term Plan (1–3 months)
1. Finalize a single provider architecture contract — prerequisite: replace missing provider-assessment document or formally retire it — risk: continued drift across config, registry, docs, and CLI
2. Keep `schema.py` baseline DDL and migrations `0006`–`0015` in lockstep — prerequisite: `schema.py` remains the authoritative creation source — risk: fresh-init safety regresses if bootstrap and incremental migrations diverge

## 14. Open Questions Requiring Operator Decision
1. Current provider migration phase and next concrete action — decide whether the repo is in a named provider-architecture phase or whether that phase model is retired.
2. `--tag` alone vs `--tag + --dj` — decide whether `--tag` is intentionally an enrich-only intermediate step or whether DJ admission/M3U output should be coupled to it.
3. Legacy DJ/XML surface — decide whether active code should still expose the 4-stage pipeline, `DJ_LIBRARY`, and `--dj-cache-root`, or whether those surfaces must be removed now.
