# Agent Instructions (canonical)

This is a CLI-first Python repo. Use these rules for all agents.

## Execution
- Primary wrappers: `ts-get <url> [--dj]`, `ts-enrich [--provider ...]`, `ts-auth [tidal|beatport|qobuz|all]`.
- Legacy 4-stage DJ pipeline is archived; `tools/get --dj` and Rekordbox XML emit are legacy reference only.
- Do not rely on files under `docs/archive/` for current behavior. Start with `docs/README.md`, then read only the active docs relevant to your task.
- Tools PATH: `tools/_load_env.sh` exports `$repo_root/tools` onto PATH when `load_workspace_env` is called. No `START_HERE.sh` exists in this clone; `_load_env.sh` is the approved substitute.

## DJ pool (current model)
- DJ pool is M3U-based: `ts-get --dj` writes per-batch M3U + global `$MP3_LIBRARY/dj_pool.m3u`.
- No `DJ_LIBRARY` writes and no XML emit in the active workflow.

## Lexicon metadata
- Prefer Lexicon backup ZIP snapshots from `$HOME/Documents/Lexicon/Backups`; each snapshot contains `main.db`.
- `tagslut lexicon import --lexicon <main.db|backup.zip>` is the DB source-of-truth path.
- Match Lexicon paths by normalized `Track.locationUnique` before `Track.location`.
- Preserve Lexicon source payloads in `track_identity.canonical_payload_json`; do not flatten or discard them.

## Debugging workflow
1) Reproduce via CLI wrappers (ts-get/ts-enrich/ts-auth).
2) Inspect the smallest relevant module.
3) Apply the smallest reversible patch.

## Testing
- Prefer targeted pytest (`poetry run pytest tests/<module> -v`).
- Do not run the full suite unless necessary.

## Metadata test map

Use these focused pytest targets when making provider or metadata changes. Do not run
the full suite.

Token/auth changes:
  pytest -q tests/metadata/test_token_manager.py

Beatport provider/API changes:
  pytest -q tests/metadata/test_beatport_provider_api.py tests/metadata/test_beatport_normalize.py

Pipeline/resolution changes:
  pytest -q tests/metadata/test_pipeline_stages.py tests/metadata/test_pipeline_runner.py tests/metadata/test_enricher_policy.py tests/metadata/test_source_selection.py

Shared metadata/models/DB-sync changes:
  pytest -q tests/metadata/test_metadata_models.py tests/metadata/test_genre_normalization.py tests/metadata/test_track_db_sync.py

Note: test_provider_state.py and test_reccobeats_provider.py do not exist in this
clone. The map above reflects the actual current layout of tests/metadata/.

## Constraints
- Do not scan the entire repo; stay scoped.
- Do not modify artifacts, databases, or external volumes; use migrations for DB changes.
- Do not write to `$MASTER_LIBRARY`, `$DJ_LIBRARY`, or mounted volumes.
- Return minimal patches only.
