# Quality Gates

## Decision
- `mypy` is gating in CI, but enforced via a baseline to allow incremental cleanup.
- `lint` (flake8) is advisory for now and runs locally only.

## Mypy Baseline Workflow
- CI runs: `poetry run python scripts/mypy_baseline_check.py`
- Update baseline when intentional changes shift the error surface:
  `python scripts/mypy_baseline_check.py --update`

## Burn-Down Plan
- Target: reduce baseline error count by 20% per month.
- Rule: any touched module should not increase its error count; fix or add targeted ignores.
- Check-in cadence: update the baseline only when the net error count decreases.
