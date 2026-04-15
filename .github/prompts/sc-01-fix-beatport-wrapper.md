# Codex Prompt: Fix tools/beatport broken wrapper

**Repo**: `kinda-debug/tagslut` | **Branch**: `dev`
**Save to**: `.github/prompts/sc-01-fix-beatport-wrapper.md`

---

## Context

`tools/beatport` currently contains:

```bash
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/get-sync" "$@"
```

`tools/get-sync` does not exist in the repo. The wrapper is broken.

`tools/get` already handles Beatport URLs natively (see the `*beatport.com*`
routing block in `tools/get`). `docs/SCRIPT_SURFACE.md` documents
`tools/get-sync` as a "deprecated compatibility alias for `tools/get`", which
means the original intent of `tools/beatport` was to forward to `tools/get`.

---

## Grounding pass (stop and report if any fail)

1. Read `tools/beatport` — confirm it still contains the broken `get-sync` exec.
2. Read `tools/get` lines 1–30 — confirm the shebang and that it handles
   beatport.com URLs.
3. Confirm `tools/get-sync` does NOT exist: `ls tools/get-sync 2>&1` should
   return "No such file".
4. Read `.git/logs/HEAD` last 20 lines — confirm branch is `dev`.

If any grounding step fails, stop and report.

---

## Task

Replace the contents of `tools/beatport` with a wrapper that forwards
directly to `tools/get`, matching the established pattern of other wrappers
in the `tools/` directory.

New content for `tools/beatport`:

```bash
#!/usr/bin/env bash
# beatport — compatibility wrapper for tools/get with Beatport URLs
#
# Forwards all arguments to tools/get. Beatport URL routing is handled
# natively by tools/get (see the *beatport.com* block in that file).
#
# Usage: tools/beatport <beatport-url> [flags]
# This wrapper exists for shell-history and shortcut compatibility only.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/get" "$@"
```

After writing the file, verify:
- `tools/beatport` is executable (`chmod +x tools/beatport` if needed — check
  with `ls -la tools/beatport`).
- The file content matches the above exactly.

---

## Constraints

- Do not recreate any existing file.
- Do not modify `tools/get` or any other file.
- Do not add `tools/get-sync`.
- Targeted pytest only: `poetry run pytest tests/tools/test_get_intake.py -v`
  to confirm nothing broke in the intake chain.

---

## Commit

```
fix(tools): replace broken beatport wrapper get-sync ref with tools/get forward
```
