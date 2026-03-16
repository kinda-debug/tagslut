# AGENTS.md

tagslut is a CLI-first Python project. Canonical command: `poetry run tagslut`.

For v3 identity hardening, use these docs as the source of record:

- `docs/architecture/V3_IDENTITY_HARDENING.md`
- `docs/operations/V3_IDENTITY_HARDENING_RUNBOOK.md`
- `docs/testing/V3_IDENTITY_HARDENING.md`

Implementation rule:

1. start from a failing command, traceback, or test
2. inspect the smallest relevant module
3. apply the smallest possible patch
4. verify with a targeted pytest run

Avoid large refactors, speculative redesigns, and unrelated file changes.
