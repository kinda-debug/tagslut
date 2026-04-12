You are an expert Python/SQLite engineer working in the tagslut repository.

Goal:
Complete Phase 1 PR 10 by hardening the identity service (`tagslut/storage/v3/identity_service.py`)
against the new v3 schema introduced in migrations 0006 and 0007. Ensure exact-match resolution,
fuzzy fallback, and dual-write consistency for legacy mirroring without expanding scope beyond
identity service hardening and its required test coverage.

Read first (in order):
1. AGENT.md
2. CLAUDE.md
3. docs/PROJECT_DIRECTIVES.md
4. docs/PHASE1_STATUS.md
5. docs/architecture/V3_IDENTITY_HARDENING.md
6. tagslut/storage/v3/schema.py (v3 schema design)
7. tagslut/storage/v3/identity_service.py (current implementation)
8. tests/storage/v3/test_identity_service.py (test fixtures)
9. tests/storage/v3/test_transaction_boundaries.py (transaction invariants)

Verify before editing:
- On `fix/identity-service` branch, run:
  poetry run pytest tests/storage/v3/test_identity_service.py -v
  poetry run pytest tests/storage/v3/test_transaction_boundaries.py -v
- All tests should PASS on clean branch (baseline validation).

Constraints:
- Minimal, reversible patch set.
- No DB file edits; service functions only.
- No mounted volume/library writes.
- No new dependencies.
- Targeted pytest only.
- Keep branch/PR boundaries intact (do not fold PR 11/12 work into PR 10).
- Do not modify PR 9 work (merge_identities.py) unless fixing a direct regression.

Implementation scope:

1. **Exact-match resolution by ISRC**
   - `resolve_or_create_identity()` must first check for exact ISRC match in `track_identity`.
   - If ISRC is provided in metadata and exists in DB, reuse that identity (no create).
   - Test: `test_exact_reuse_by_isrc` ✓ (already passing).

2. **Exact-match resolution by provider ID (beatport_id, tidal_id, etc.)**
   - If no ISRC match but provider_id (e.g., beatport_id) is in metadata, check provider columns.
   - If provider_id exists and matches, reuse that identity.
   - Test: `test_exact_reuse_by_provider_id` ✓ (already passing).

3. **Fuzzy fallback matching**
   - If no exact ISRC or provider_id match, fuzzy-match by normalized artist/title/duration.
   - Use normalized text (case-insensitive, whitespace-normalized) and duration tolerance (±2s).
   - If fuzzy match found and score ≥ 92%, reuse that identity.
   - If no fuzzy match, create new identity.
   - Test: `test_fuzzy_reuse_then_create_when_no_match` ✓ (already passing).

4. **Single-merge-hop active identity resolution**
   - `resolve_active_identity()` must follow `merged_into_id` pointer to find canonical identity.
   - Only one hop allowed (no transitive chains).
   - Returns the active identity (merged_into_id IS NULL).
   - Test: `test_resolve_active_identity_follows_single_merge_hop` ✓ (already passing).

5. **Legacy mirror dual-write consistency**
   - When identity is resolved or created, legacy DB row must be synced via `mirror_identity_to_legacy()`.
   - Sync must update `library_tracks` view if canonical fields changed.
   - Test: `test_legacy_mirror_updates_files_and_library_tracks` ✓ (already passing).

6. **Transaction boundary isolation**
   - All identity service functions MUST NOT manage outer transactions.
   - If a function is called inside an outer transaction, it must yield control to the caller
     for commit/rollback decisions.
   - Test: 9 transaction boundary tests (all passing). Do not break them.

Required verification after edits:
- poetry run pytest tests/storage/v3/test_identity_service.py -v
- poetry run pytest tests/storage/v3/test_transaction_boundaries.py -v
- If identity_service.py changed significantly, also run:
  poetry run pytest tests/storage/v3/ -v (full v3 storage suite)

Done when:
- All 5 identity service tests PASS.
- All 9 transaction boundary tests PASS.
- No regressions in other storage v3 modules.
- No unrelated files from PR 11/12 are modified.
- Identity service hard requirements (exact-match, fuzzy, legacy sync, transaction isolation) are verified.
- Conventional commit message used, e.g.:
  feat(identity): harden identity service for v3 schema and legacy mirror sync
