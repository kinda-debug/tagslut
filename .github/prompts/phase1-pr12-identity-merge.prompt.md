You are an expert Python/SQLite engineer working in the tagslut repository.

Goal:
Implement Phase 1 PR 12 (identity merge) as a focused, reversible patch on top of
PR 10 (`fix/identity-service`) behavior. Preserve v3 identity invariants and do
not expand scope beyond merge semantics and required tests/docs.

Read first (in order):
1. AGENT.md
2. CLAUDE.md
3. docs/PROJECT_DIRECTIVES.md
4. docs/PHASE1_STATUS.md
5. docs/architecture/V3_IDENTITY_HARDENING.md
6. tagslut/storage/v3/merge_identities.py
7. tagslut/storage/v3/identity_service.py
8. tests/storage/v3/test_identity_service.py
9. tests/storage/v3/test_transaction_boundaries.py

Verify before editing:
- Run:
  poetry run pytest tests/storage/v3/test_identity_service.py -v
  poetry run pytest tests/storage/v3/test_transaction_boundaries.py -v
- Capture current failures (if any) and use those as the implementation target.

Constraints:
- Smallest reversible patch set only.
- Do not modify DB files directly.
- Do not touch mounted volume/library paths.
- No new dependencies.
- Targeted pytest only (no full suite).
- Keep schema and migration compatibility intact.

Implementation scope:
1. Ensure merge behavior keeps exactly one active canonical winner (`merged_into_id IS NULL`) and preserves loser lineage via `merged_into_id` links.
2. Ensure provider-id uniqueness invariants remain valid for active rows after merge (no active-row duplicate IDs introduced).
3. Ensure asset links are repointed to the canonical winner deterministically.
4. Ensure legacy mirror writes remain consistent where merge touches identity-bearing fields.
5. Keep transaction boundaries explicit: no hidden commit/rollback management in service helpers.

Required verification after edits:
- poetry run pytest tests/storage/v3/test_identity_service.py -v
- poetry run pytest tests/storage/v3/test_transaction_boundaries.py -v
- If merge logic changed materially, also run:
  poetry run pytest tests/storage/v3/test_backfill_v3_identity_links.py -v

Done when:
- Tests above pass.
- Behavior matches Phase 1 status contract in docs/PHASE1_STATUS.md.
- Diff is limited to identity-merge surfaces and tightly-related tests.
- Conventional commit message is used, e.g.:
  fix(identity): harden canonical merge semantics and active-row invariants
