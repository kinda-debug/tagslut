# Phase 4 - CLI Convergence

Phase 4 introduces the canonical command groups:

- `tagslut intake`
- `tagslut index`
- `tagslut decide`
- `tagslut execute`
- `tagslut verify`
- `tagslut report`
- `tagslut auth`

Canonical bundle shorthand: `intake/index/decide/execute/verify/report/auth`.

## What Changed

1. Canonical groups added in `tagslut/cli/main.py`.
2. Existing workflows remain compatible via wrappers:
- `tagslut mgmt ...`
- `tagslut metadata ...`
- `tagslut recover ...`

3. Transitional wrappers now include explicit migration warnings with targets.
4. Converged wrappers map to existing operational paths so behavior remains stable.

## Group Mapping

1. Intake
- `tagslut intake run` -> `tools/get-intake`
- `tagslut intake prefilter` -> `tools/review/beatport_prefilter.py`

2. Index
- `tagslut index register` -> `tagslut mgmt register`
- `tagslut index check` -> `tagslut mgmt check`
- `tagslut index duration-check` -> `tagslut mgmt check-duration`
- `tagslut index duration-audit` -> `tagslut mgmt audit-duration`
- `tagslut index set-duration-ref` -> `tagslut mgmt set-duration-ref`
- `tagslut index enrich` -> `tagslut metadata enrich`

3. Decide
- `tagslut decide profiles` -> list policy profiles
- `tagslut decide plan` -> deterministic plan generation (`tagslut.decide`)

4. Execute
- `tagslut execute move-plan` -> `tools/review/move_from_plan.py`
- `tagslut execute quarantine-plan` -> `tools/review/quarantine_from_plan.py`
- `tagslut execute promote-tags` -> `tools/review/promote_by_tags.py`

5. Verify
- `tagslut verify duration` -> duration audit
- `tagslut verify recovery` -> recovery verify phase
- `tagslut verify parity` -> v3 parity validator
- `tagslut verify receipts` -> move receipt consistency summary

6. Report
- `tagslut report m3u` -> M3U generation
- `tagslut report duration` -> duration report
- `tagslut report recovery` -> recovery report phase
- `tagslut report plan-summary` -> plan summary helper

7. Auth
- `tagslut auth status|init|refresh|login` -> metadata auth flows

## Compatibility Contract

1. Old surfaces (`mgmt`, `metadata`, `recover`) are retained during migration.
2. They are explicitly marked transitional with deprecation guidance.
3. Wrapper invocations from canonical commands are tagged as internal so users do not see recursive warnings.

## Notes

- This phase does not remove `scan/recommend/apply/promote/quarantine` wrappers.
- Removal remains Phase 5 after burn-in and documentation handover.
