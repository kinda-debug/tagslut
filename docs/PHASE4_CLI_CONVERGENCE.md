# Phase 4 - CLI Convergence

Phase 4 introduces the canonical command groups:

- `dedupe intake`
- `dedupe index`
- `dedupe decide`
- `dedupe execute`
- `dedupe verify`
- `dedupe report`
- `dedupe auth`

Canonical bundle shorthand: `intake/index/decide/execute/verify/report/auth`.

## What Changed

1. Canonical groups added in `dedupe/cli/main.py`.
2. Existing workflows remain compatible via wrappers:
- `dedupe mgmt ...`
- `dedupe metadata ...`
- `dedupe recover ...`

3. Transitional wrappers now include explicit migration warnings with targets.
4. Converged wrappers map to existing operational paths so behavior remains stable.

## Group Mapping

1. Intake
- `dedupe intake run` -> `tools/get-intake`
- `dedupe intake prefilter` -> `tools/review/beatport_prefilter.py`

2. Index
- `dedupe index register` -> `dedupe mgmt register`
- `dedupe index check` -> `dedupe mgmt check`
- `dedupe index duration-check` -> `dedupe mgmt check-duration`
- `dedupe index duration-audit` -> `dedupe mgmt audit-duration`
- `dedupe index set-duration-ref` -> `dedupe mgmt set-duration-ref`
- `dedupe index enrich` -> `dedupe metadata enrich`

3. Decide
- `dedupe decide profiles` -> list policy profiles
- `dedupe decide plan` -> deterministic plan generation (`dedupe.decide`)

4. Execute
- `dedupe execute move-plan` -> `tools/review/move_from_plan.py`
- `dedupe execute quarantine-plan` -> `tools/review/quarantine_from_plan.py`
- `dedupe execute promote-tags` -> `tools/review/promote_by_tags.py`

5. Verify
- `dedupe verify duration` -> duration audit
- `dedupe verify recovery` -> recovery verify phase
- `dedupe verify parity` -> v3 parity validator
- `dedupe verify receipts` -> move receipt consistency summary

6. Report
- `dedupe report m3u` -> M3U generation
- `dedupe report duration` -> duration report
- `dedupe report recovery` -> recovery report phase
- `dedupe report plan-summary` -> plan summary helper

7. Auth
- `dedupe auth status|init|refresh|login` -> metadata auth flows

## Compatibility Contract

1. Old surfaces (`mgmt`, `metadata`, `recover`) are retained during migration.
2. They are explicitly marked transitional with deprecation guidance.
3. Wrapper invocations from canonical commands are tagged as internal so users do not see recursive warnings.

## Notes

- This phase does not remove `scan/recommend/apply/promote/quarantine` wrappers.
- Removal remains Phase 5 after burn-in and documentation handover.
