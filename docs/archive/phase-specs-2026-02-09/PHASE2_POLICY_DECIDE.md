# Phase 2 - Policy + Decide Engine

Phase 2 introduces a policy-driven deterministic planning layer.

## What Was Added

1. `tagslut.policy` module
- Loader: `tagslut/policy/loader.py`
- Model types: `tagslut/policy/models.py`
- Lint rules: `tagslut/policy/lint.py`

2. Policy profiles
- `config/policies/dj_strict.yaml`
- `config/policies/library_balanced.yaml`
- `config/policies/bulk_recovery.yaml`

3. Deterministic planning API
- `tagslut/decide/planner.py`
- `tagslut/decide/__init__.py`

## Contract

Given:
- the same normalized input candidates
- the same policy profile/version

The planner returns:
- the same row ordering
- the same `plan_hash`
- the same deterministic `run_id` prefix (`<label>-<policy>-<hash12>`)

Plan artifacts are stamped with:
- `policy.name`
- `policy.version`
- `policy.hash`
- `run_id`

## Policy Profiles

1. `dj_strict`
- duplicate matches: `skip`
- unmatched: `keep`
- hard DJ gate: promotion requires `duration_status=ok`
- non-ok DJ duration action: `review`

2. `library_balanced`
- duplicate matches: `skip`
- unmatched: `keep`
- no strict duration hard gate

3. `bulk_recovery`
- duplicate matches: `review`
- unmatched: `promote`
- collision policy defaults to `abort`

## Usage (Python API)

```python
from tagslut.decide import PlanCandidate, build_deterministic_plan
from tagslut.policy import load_policy_profile

policy = load_policy_profile("library_balanced")
plan = build_deterministic_plan(
    [
        PlanCandidate(path="/music/intake/a.flac", match_reasons=("isrc",)),
        PlanCandidate(path="/music/intake/b.flac", proposed_action="promote"),
    ],
    policy,
    run_label="intake",
)

print(plan.run_id)
print(plan.plan_hash)
print(plan.to_json())
```

## Policy Lint

Lint all profiles:

```bash
poetry run python scripts/lint_policy_profiles.py
```

## Tests

Phase 2 coverage lives in:
- `tests/test_phase2_policy_decide.py`
- `tests/test_policy_lint_script.py`

These include deterministic hash checks and golden policy-plan snapshots.
