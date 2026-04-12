You are an expert Python/SQLite engineer working in the tagslut repository.

Goal:
Complete Phase 1 PR 9 by bringing `fix/migration-0006` to a merge-ready state
against current `dev` without expanding scope beyond migration 0006/0007 and their
required tests/docs wiring.

Read first (in order):
1. AGENT.md
2. CLAUDE.md
3. docs/PROJECT_DIRECTIVES.md
4. docs/PHASE1_STATUS.md
5. docs/architecture/V3_IDENTITY_HARDENING.md
6. tagslut/storage/v3/migrations/0006_track_identity_phase1.py
7. tagslut/storage/v3/migrations/0007_track_identity_phase1_rename.py
8. tests/storage/v3/test_migration_0006.py
9. tests/storage/v3/test_migration_runner_v3.py

Verify before editing:
- On target branch, run:
  poetry run pytest tests/storage/v3/test_migration_0006.py -v
  poetry run pytest tests/storage/v3/test_migration_runner_v3.py -v
- Record failures and only fix failures tied to migration 0006/0007 scope.

Constraints:
- Minimal, reversible patch set.
- No DB file edits; migrations only.
- No mounted volume/library writes.
- No new dependencies.
- Targeted pytest only.
- Keep branch/PR boundaries intact (do not fold PR 10/11 work into PR 9).

Implementation scope:
1. Ensure migration 0006 remains idempotent and safely upgrade-path oriented.
2. Ensure 0007 rename behavior is stable and no-op-safe when canonical columns already exist.
3. Ensure migration runner ordering/recording behavior remains correct for fresh vs upgrade paths.
4. Resolve only merge-readiness drift with current `dev` (conflicts, stale tests, stale docs references) that directly impacts PR 9.

Required verification after edits:
- poetry run pytest tests/storage/v3/test_migration_0006.py -v
- poetry run pytest tests/storage/v3/test_migration_runner_v3.py -v
- If migration wiring changed, also run:
  poetry run pytest tests/storage/v3/test_migration_0010.py -v
  poetry run pytest tests/storage/v3/test_migration_0011.py -v

Done when:
- PR 9 branch is conflict-free against current `dev` and migration-focused tests pass.
- No unrelated files from PR 10/11 are modified.
- Conventional commit message used, e.g.:
  fix(migrations): finalize phase1 migration 0006 merge readiness
