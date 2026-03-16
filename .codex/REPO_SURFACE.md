# REPO_SURFACE.md

High-value directories

tagslut/cli/
CLI commands and argument handling.

tagslut/exec/
Execution layer (transcoder, DJ pipeline).

tagslut/storage/
Database layer.

tagslut/storage/v3/
Identity model and migrations.

tests/dj/
DJ workflow tests.

tests/storage/
Database and migration tests.

docs/audit/
Architecture and repo state audits.

Important facts

- `tagslut` is the only supported CLI command (the `dedupe` alias was removed).
- The repository uses the v3 identity model.
- Migration 0006 added columns and indexes to `track_identity`.
- DJ pipeline: FLAC → mp3 → dj → Rekordbox XML.

When debugging

1. Reproduce with CLI or failing test.
2. Inspect only the relevant module.
3. Apply minimal patch.
4. Verify with targeted pytest.
