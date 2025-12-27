MERGE RECORD: merge/codex-into-main

This branch exists to provide a visible PR record for the local merge that
was already applied to `main`.

Summary:
- Source branch: `merge/codex-into-main` (codex changes and docs)
- Target branch: `main`
- Conflict resolution: kept `main` runtime code (notably `dedupe/cli.py` and
  `dedupe/scanner.py`) and accepted codex documentation updates.
- Local test results: 8 tests passed in the project virtualenv.

If you want the codex scanner/CLI refactor applied instead of the preserved
`main` implementations, ask and I will prepare a follow-up patch adapting
callers and re-run tests.

Signed-off-by: GitHub Copilot (automated PR record)
