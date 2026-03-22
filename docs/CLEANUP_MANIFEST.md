## Deleted

- `Dual-SourceTIDALBeatportMetadataFlow.md` — obsolete root design note; active Beatport/TIDAL architecture lives in current docs.
- `build_playlist.py` — old one-off root helper with no active references.
- `inspect_music_db.py` — scratch diagnostic script with no active references.
- `post_task.sh` — session artifact, not part of the supported repo surface.
- `tidal_oauth.py` — scratch auth helper superseded by canonical `tagslut auth` flows.

## Archived

- `CLI_HELP_PARITY_WORK_ITEM.md` → `docs/archive/CLI_HELP_PARITY_WORK_ITEM.md` — stale work item; the mp3/dj stage-aware help text is already implemented.
- `docs/beatport_provider_report.md` → `docs/archive/beatport_provider_report.md` — one-off provider report, no longer part of the active docs set.
- `docs/tidal_beatport_enrichment.md` → `docs/archive/tidal_beatport_enrichment.md` — superseded by current architecture and workflow docs.
- `metadata.md` → `docs/archive/metadata.md` — root scratch notes, not part of the active operator surface.
- `scripts/apply_beatport_playlist_dump_refs.py` → `scripts/archive/apply_beatport_playlist_dump_refs.py` — one-off playlist dump helper.
- `scripts/bootstrap_duration_refs_local.py` → `scripts/archive/bootstrap_duration_refs_local.py` — one-off local bootstrap script.
- `scripts/bootstrap_relink_db.py` → `scripts/archive/bootstrap_relink_db.py` — one-off relink bootstrap helper.
- `scripts/classify_tracks_sqlite.py` → `scripts/archive/classify_tracks_sqlite.py` — pre-v3 classifier superseded by current flows.
- `scripts/extract_tracklists_from_links.py` → `scripts/archive/extract_tracklists_from_links.py` — one-off extraction script with no active references.
- `scripts/filter_songshift_existing.py` → `scripts/archive/filter_songshift_existing.py` — retired SongShift/Spotify utility.
- `scripts/make_phase_v3_playlists.py` → `scripts/archive/make_phase_v3_playlists.py` — phase-specific helper for completed work.
- `scripts/workflow_health_rescan.py` → `scripts/archive/workflow_health_rescan.py` — gitignored workflow-health utility, retained only as historical reference.
- `tools/add_codex_objectives.sh` → `tools/archive/add_codex_objectives.sh` — session artifact, not an active repo tool.
- `tools/beatport_import_my_tracks.py` → `tools/archive/beatport_import_my_tracks.py` — one-off import helper with no active references.
- `tools/dj_usb_analyzer.py` → `tools/archive/dj_usb_analyzer.py` — retired USB-analysis helper not used by current DJ flows.
- `tools/dj_usb_incremental.py` → `tools/archive/dj_usb_incremental.py` — retired incremental USB sync helper superseded by current DJ tooling.
- `tools/dj_usb_to_roon_m3u.py` → `tools/archive/dj_usb_to_roon_m3u.py` — retired conversion helper with no active references.
- `tools/inspect_api.py` → `tools/archive/inspect_api.py` — scratch API inspection script, not part of the active tool surface.

## Left in place (uncertain)

- `scripts/auto_env.py` — no active refs found, but it is still a plausible local env bootstrap helper.
- `scripts/reconcile_track_overrides.py` — no active refs found, but it still targets the live `config/dj/track_overrides.csv` workflow.
- `tools/fix_blocklist.py` — not broadly referenced, but still looks like a valid maintenance utility for DJ policy blocklists.
- `tools/get-all` — standalone end-to-end intake/DJ wrapper; not broadly linked, but not clearly dead.
- `REPORT.md` — current-state strategy summary at repo root; kept because it still reads like active project documentation.

## Not touched (active)

- Active docs stayed in place where references still exist: `docs/DJ_REVIEW_APP.md`, `docs/PROJECT.md`, `docs/REDESIGN_TRACKER.md`, `docs/SCRIPT_SURFACE.md`, `docs/SURFACE_POLICY.md`, and the `docs/PHASE5_LEGACY_DECOMMISSION.md` stub that preserves live links.
- Active scripts stayed in place where they are wired into the repo: `scripts/backfill_v3_provenance_from_logs.py` (Makefile/tests) and `scripts/capture_post_release_snapshot.py` (tests).
- Active tools stayed in place where code or docs still depend on them: `tools/dj_review_app.py`, `tools/dj_usb_sync.py`, `tools/get-auto`, `tools/get-sync`, and `tools/claude-clean`.
- No loose `*.log` files remained in repo root or under `artifacts/`, so no log relocation was needed in this pass.
