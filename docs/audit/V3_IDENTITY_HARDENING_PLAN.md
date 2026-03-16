1. Freeze the v3 identity model as the system of record.
   This is effectively complete. The stable core entities are `track_identity`, `asset_file`, `asset_link`, and `preferred_asset`. Canonical versus merged identity is represented by `merged_into_id`. Write paths use explicit transaction ownership and `BEGIN IMMEDIATE` when they own the transaction.

2. Keep schema-enforced invariants narrow and explicit.
   This is complete. Active-row uniqueness is enforced for seven provider IDs: `beatport_id`, `tidal_id`, `qobuz_id`, `spotify_id`, `apple_music_id`, `deezer_id`, and `traxsource_id`, via partial unique indexes. `isrc`, `itunes_id`, and `musicbrainz_id` remain helper-level or policy-level identifiers, not schema-level uniqueness keys.

3. Preserve reasoning in repo docs, not in chat.
   This is complete. Stable intent now lives in:
   - `docs/architecture`
   - `docs/operations`
   - `docs/testing`
   - `AGENTS.md` as a pointer only
   - `docs/audit` for dated proof reports
   - `docs/audit/README.md` as the audit index

4. Treat the hardening pass as complete and move into proof.
   This is complete. The forensic baseline is recorded in `docs/audit/2026-03-16_v3_identity_hardening_etat_des_lieux.md`.

5. Make the default migration runner policy explicit.
   This is complete. `_0009_chromaprint.py` is now excluded by policy from the default v3 migration runner because underscore-prefixed modules are treated as helpers, not numbered migrations. That behavior is implemented, tested, and documented.

6. Prove fresh bootstrap and upgrade-path equivalence.
   This is complete for the v11 surface. A strict schema-equivalence test was added, it exposed a real mismatch in `schema_migrations.note`, and that mismatch was fixed in `schema.py`. Fresh bootstrap and upgrade-path now match literally for the tested surface.

7. Keep proof strict where metadata is part of the contract.
   This is now the policy. `schema_migrations.note` is treated as normative repository metadata. Bootstrap and upgrade are not allowed to tell different historical stories. The equivalence test should remain strict.

8. Current verified state.
   The v3 identity hardening work is no longer just architectural intent. It is now implemented, documented, audited, and partially proven. The repo currently has:
   - a stable v3 identity model
   - provider uniqueness hardening for seven provider IDs
   - explicit transaction ownership in write paths
   - Beatport-specific merge automation
   - explicit default migration runner policy
   - a proof artifact under `docs/audit`
   - a strict v11 fresh-vs-upgrade schema equivalence test that passes

9. The main remaining technical gap is provider-repair asymmetry.
   Enforcement is broader than automated remediation. The schema blocks active duplicates for seven provider IDs, but duplicate discovery and merge automation are Beatport-centric in practice.

10. Decide whether that asymmetry is intentional.
   There are two valid branches:
   - If Beatport-only repair is intentional:
     Document it explicitly in architecture and operations docs. State that schema enforcement is broader than automated merge tooling, and that non-Beatport duplicate resolution is manual or operator-driven.
   - If provider-generic repair is desired:
     Add generic duplicate discovery helpers, generic merge-entry tooling, and tests for each enforced provider class. Do not redesign identity again; only make remediation match enforcement.

11. The next proof slice is transaction-boundary completeness.
   The repo already proves rollback behavior when functions own the transaction. The missing proof is outer-transaction behavior for:
   - `dual_write_registered_file()`
   - `resolve_or_create_identity()`
   - `merge_group_by_repointing_assets()`
   These should be tested directly.

12. The next doc/code alignment slice is migration-audit wording.
   The proof pass found wording drift: the `0010` and `0011` docs describe duplicate auditing more cleanly than the literal SQL does. That should be resolved either by tightening the docs to match the SQL or by changing the audit SQL to match the docs.

13. The next policy slice is `itunes_id` and `musicbrainz_id`.
   Their status should be made explicit:
   - either they remain policy-only identifiers and the docs say so clearly
   - or they later become schema-enforced, which would require a new migration, audit logic, and repair strategy

14. The next resilience slice is `merged_into_id` cycle posture.
   Today, cycle detection exists at runtime, not at schema level. This needs an explicit decision:
   - accept runtime detection as sufficient and document that storage does not prevent cycles directly
   - or add stronger prevention if the complexity is justified

15. The next operational slice is to make proof routine.
   The audit and proof work should stop being one-off exercises. Duplicate audits, schema-equivalence checks, and migration-runner expectations should become routine pre-release or pre-migration checks.

16. The next environment slice is test-runner hygiene.
   This is secondary to v3 itself, but still real. The unrelated pytest plugin autoload issue should eventually be cleaned up. For now, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` is a valid isolation mechanism for proof tests in this environment.

17. Closure criteria for this phase.
   This phase is fully closed when all of the following are true:
   - hardening invariants are stable
   - repo docs reflect literal behavior
   - default migration runner policy is explicit and tested
   - fresh bootstrap equals upgrade-path for the intended schema surface
   - transaction ownership is fully proven, including outer-transaction cases
   - provider-repair asymmetry is either documented as intentional or reduced by code
   - unresolved identifier policies like `itunes_id` and `musicbrainz_id` are explicit
   - routine proof checks exist so this does not need to be rediscovered later

18. Remaining execution order.
   1. Decide Beatport-only repair versus generic provider repair.
   2. Add outer-transaction proof tests for the main write paths.
   3. Align `0010` and `0011` migration-audit wording with literal SQL behavior.
   4. Decide and document long-term policy for `itunes_id` and `musicbrainz_id`.
   5. Decide and document whether runtime-only `merged_into_id` cycle detection is sufficient.
   6. Turn the audit and proof checks into routine repo checks.
   7. Clean the unrelated pytest plugin environment issue separately from v3.

That is the full plan in its current sane form.
